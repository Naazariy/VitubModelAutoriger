"""
src/cli/main.py
Headless Zero-Intervention CLI Pipeline Runner for Automated VTuber Key Deformation & Live2D Export.
Connects Asset Ingestion -> Mesh Generation -> 3D Deformation -> MaxRects Packing -> MOC3 Serialization -> 6-Stage Validation.
"""

import argparse
from dataclasses import dataclass, field
import json
import logging
import math
import os
from pathlib import Path
import sys
import time
from typing import Dict, List, Tuple, Optional, Any, Union
import numpy as np
from PIL import Image

from src.core.layer import LayerData, LayerCollection
from src.core.mesh import Mesh
from src.core.keyform import KeyformTable, DrawableKeyforms, ParameterBinding, WarpDeformer, RotationDeformer
from src.importer.image_importer import ImageImporter
from src.importer.psd_importer import PSDImporter
from src.importer.semantic_classifier import SemanticClassifier
from src.generator.mesh_generator import MeshGenerator
from src.depth.depth_model import DepthModel
from src.deformation.deformation_solver import DeformationSolver
from src.deformation.keyform_generator import KeyformGenerator
from src.constraints.constraint_solver import ARAPConstraintSolver
from src.exporter.texture_packer import TextureAtlasPacker, PackingConfig
from src.exporter.moc3_writer import Moc3Writer
from src.exporter.model3_writer import Model3Writer
from src.validator.structural_validator import validate_live2d_model, ValidationReport


# Standardized Exit Codes
EXIT_SUCCESS = 0               # Pipeline succeeded
EXIT_ERR_INPUT = 1             # Input asset missing, corrupted, or invalid CLI arguments
EXIT_ERR_INVALID_ARGS = 1      # Alias
EXIT_ERR_INPUT_NOT_FOUND = 1   # Alias
EXIT_ERR_MESH = 2              # Mesh triangulation or contour generation error
EXIT_ERR_DEFORMATION = 3       # 3D deformation solve or ARAP regularization failure
EXIT_ERR_PROCESSING_FAILED = 3 # Alias
EXIT_ERR_EXPORT = 4            # Texture packing, .moc3 writer, or IO write failure
EXIT_ERR_EXPORT_FAILED = 4     # Alias
EXIT_ERR_VALIDATION = 5        # 6-stage structural validation failed
EXIT_ERR_VALIDATION_FAILED = 5 # Alias


class PipelineException(Exception):
    """Base exception for all Live2D export pipeline failures."""
    exit_code: int = EXIT_ERR_INPUT

    def __init__(self, message: str, stage: str = "Pipeline", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.details = details or {}


class InputError(PipelineException):
    """Raised when input asset is missing, corrupted, or unsupported."""
    exit_code = EXIT_ERR_INPUT


class MeshGenerationError(PipelineException):
    """Raised when contour extraction or Delaunay triangulation fails."""
    exit_code = EXIT_ERR_MESH


class DeformationError(PipelineException):
    """Raised when 3D math, depth modeling, or ARAP regularization fails."""
    exit_code = EXIT_ERR_DEFORMATION


class ExportError(PipelineException):
    """Raised when texture packing, binary moc3 serialization, or file I/O fails."""
    exit_code = EXIT_ERR_EXPORT


class ValidationError(PipelineException):
    """Raised when exported model bundle fails 6-stage structural validation."""
    exit_code = EXIT_ERR_VALIDATION


def parse_float_range(range_str: str, default: Tuple[float, float]) -> Tuple[float, float]:
    """Parses a comma-separated float range string (e.g. '-30.0,30.0')."""
    try:
        parts = [float(p.strip()) for p in range_str.split(",")]
        if len(parts) == 2:
            return (parts[0], parts[1])
    except Exception:
        pass
    return default


def parse_float_triplet(triplet_str: str, default: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Parses a comma-separated float triplet string (e.g. '0.6,0.8,0.4')."""
    try:
        parts = [float(p.strip()) for p in triplet_str.split(",")]
        if len(parts) == 3:
            return (parts[0], parts[1], parts[2])
    except Exception:
        pass
    return default


@dataclass
class PipelineConfig:
    """Strongly-typed pipeline configuration container."""
    input_path: str
    output_dir: str = "./output"
    model_name: Optional[str] = None
    atlas_size: int = 4096
    grid_size: int = 25
    contour_threshold: int = 10
    simplify_eps: float = 2.0
    smoothing_iterations: int = 3
    angle_x_range: Tuple[float, float] = (-30.0, 30.0)
    angle_y_range: Tuple[float, float] = (-30.0, 30.0)
    angle_z_range: Tuple[float, float] = (-20.0, 20.0)
    keyforms_x: int = 3
    keyforms_y: int = 3
    keyforms_z: int = 3
    include_angle_z: bool = True
    head_radii: Tuple[float, float, float] = (0.6, 0.8, 0.4)
    parallax_scale: float = 0.45
    arap_weight: float = 2.5
    arap_iterations: int = 4
    padding: int = 4
    bleed_radius: int = 2
    crop_transparent: bool = True
    include_hidden: bool = False
    auto_depth: bool = True
    auto_stiffness: bool = True
    validate: bool = False
    strict: bool = False
    gui: bool = False
    overwrite: bool = False
    quiet: bool = False
    verbose: bool = False
    json_output: bool = False

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> 'PipelineConfig':
        input_target = args.input_path or args.input_flag or ""
        angle_x = parse_float_range(getattr(args, "angle_x_range", "-30.0,30.0"), (-30.0, 30.0))
        angle_y = parse_float_range(getattr(args, "angle_y_range", "-30.0,30.0"), (-30.0, 30.0))
        angle_z = parse_float_range(getattr(args, "angle_z_range", "-20.0,20.0"), (-20.0, 20.0))
        head_r = parse_float_triplet(getattr(args, "head_radii", "0.6,0.8,0.4"), (0.6, 0.8, 0.4))

        return cls(
            input_path=input_target,
            output_dir=getattr(args, "output_dir", "./output"),
            model_name=getattr(args, "model_name", None),
            atlas_size=getattr(args, "atlas_size", 4096),
            grid_size=getattr(args, "grid_size", 25),
            contour_threshold=getattr(args, "contour_threshold", 10),
            simplify_eps=getattr(args, "simplify_eps", 2.0),
            smoothing_iterations=getattr(args, "smoothing_iterations", 3),
            angle_x_range=angle_x,
            angle_y_range=angle_y,
            angle_z_range=angle_z,
            keyforms_x=getattr(args, "keyforms_x", 3),
            keyforms_y=getattr(args, "keyforms_y", 3),
            keyforms_z=getattr(args, "keyforms_z", 3),
            include_angle_z=getattr(args, "include_angle_z", True),
            head_radii=head_r,
            parallax_scale=getattr(args, "parallax_scale", 0.45),
            arap_weight=getattr(args, "arap_weight", 2.5),
            arap_iterations=getattr(args, "arap_iterations", 4),
            padding=getattr(args, "padding", 4),
            bleed_radius=getattr(args, "bleed_radius", 2),
            crop_transparent=getattr(args, "crop_transparent", True),
            include_hidden=getattr(args, "include_hidden", False),
            auto_depth=getattr(args, "auto_depth", True),
            auto_stiffness=getattr(args, "auto_stiffness", True),
            validate=getattr(args, "validate", False),
            strict=getattr(args, "strict", False),
            gui=getattr(args, "gui", False),
            overwrite=getattr(args, "overwrite", False),
            quiet=getattr(args, "quiet", False),
            verbose=getattr(args, "verbose", False),
            json_output=getattr(args, "json_output", False),
        )


class PipelineRunner:
    """Executes the complete end-to-end Live2D export pipeline."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.metrics: Dict[str, Any] = {}

    def log(self, msg: str, level: str = "INFO") -> None:
        if not self.config.quiet:
            print(f"[{level}] {msg}")

    def stage_ingest(self) -> LayerCollection:
        """Stage 1: Ingests PSD, layer folder, or single image into LayerCollection."""
        in_path = Path(self.config.input_path).resolve()
        if not in_path.exists():
            raise InputError(f"Input path does not exist: {in_path}")

        layers: List[LayerData] = []
        collection = LayerCollection()

        if in_path.is_dir():
            self.log(f"Ingesting directory of layer images from: {in_path.name}")
            layers = ImageImporter.load_directory(str(in_path))
            if not layers:
                raise InputError(f"No valid image files found in directory: {in_path}")
            for l in layers:
                collection.add_layer(l)
        elif in_path.suffix.lower() in (".psd", ".psb"):
            self.log(f"Ingesting Adobe Photoshop PSD file: {in_path.name}")
            try:
                layers = PSDImporter.load_psd(str(in_path), include_hidden=self.config.include_hidden)
            except Exception as e:
                raise InputError(f"Failed to parse PSD file: {e}")
            if not layers:
                raise InputError(f"No drawable layers extracted from PSD: {in_path}")
            for l in layers:
                collection.add_layer(l)
        elif in_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp"):
            self.log(f"Ingesting single image asset: {in_path.name}")
            try:
                rgba, alpha = ImageImporter.load_image(str(in_path))
            except Exception as e:
                raise InputError(f"Failed to read image file: {e}")
            layer = LayerData(
                name=in_path.stem or "Head",
                image=rgba,
                offset_x=0,
                offset_y=0,
                z_depth_hint=0.0,
                category="face",
                layer_id=f"{in_path.stem}_0"
            )
            collection.add_layer(layer)
        else:
            raise InputError(f"Unsupported file format: {in_path.suffix} (supported: .psd, .png, .jpg, folder)")

        self.metrics["layer_count"] = len(collection.layers)
        self.log(f"  [OK] Ingested {len(collection.layers)} layers")
        return collection

    def stage_mesh_generation(self, collection: LayerCollection) -> Dict[str, Mesh]:
        """Stage 2: Generates Delaunay meshes for each layer."""
        self.log(f"Generating Delaunay meshes (grid resolution: {self.config.grid_size}px)...")
        mesh_map: Dict[str, Mesh] = {}
        total_verts = 0
        total_tris = 0

        for layer in collection.layers:
            try:
                mesh = MeshGenerator.generate_mesh_from_layer(
                    layer=layer,
                    target_grid_size=self.config.grid_size,
                    threshold=self.config.contour_threshold,
                    simplify_eps=self.config.simplify_eps
                )
                if len(mesh.vertices) == 0 or len(mesh.triangles) == 0:
                    raise MeshGenerationError(f"Generated mesh for layer '{layer.name}' is empty")
                mesh_map[layer.name] = mesh
                mesh_map[layer.layer_id] = mesh
                total_verts += len(mesh.vertices)
                total_tris += len(mesh.triangles)
            except Exception as e:
                if isinstance(e, MeshGenerationError):
                    raise e
                raise MeshGenerationError(f"Mesh generation failed for layer '{layer.name}': {e}")

        self.metrics["total_vertices"] = total_verts
        self.metrics["total_triangles"] = total_tris
        self.log(f"  [OK] Triangulated {len(collection.layers)} layers (Vertices: {total_verts}, Triangles: {total_tris})")
        return mesh_map

    def stage_deformation_keyforms(
        self, collection: LayerCollection, mesh_map: Dict[str, Mesh]
    ) -> KeyformTable:
        """
        Stage 3: Generates official Live2D Deformer Hierarchy & Parameter Bindings:
        RootPart -> RotationDeformer (AngleZ) -> WarpDeformer (AngleX/AngleY) -> ArtMeshes.
        ArtMeshes are parented to the WarpDeformer with clean rest geometry and no direct rotation parameter bindings.
        """
        from src.core.vertex import Vertex
        from src.core.keyform import WarpDeformer, RotationDeformer

        self.log("Solving Live2D Deformer Hierarchy (RotationDeformer + WarpDeformer)...")
        try:
            # 1. Depth stratification
            if self.config.auto_depth:
                depth_engine = DepthModel(radii=self.config.head_radii)
                depth_engine.apply_to_layer_collection(collection, mesh_map)

            # 2. Setup deformation solver
            solver = DeformationSolver(
                head_radius_x=self.config.head_radii[0],
                head_radius_y=self.config.head_radii[1],
                head_radius_z=self.config.head_radii[2],
                parallax_scale=self.config.parallax_scale
            )

            # 3. Angle grid values
            kx = self.config.keyforms_x
            ky = self.config.keyforms_y
            kz = self.config.keyforms_z

            x_min, x_max = self.config.angle_x_range
            y_min, y_max = self.config.angle_y_range
            z_min, z_max = self.config.angle_z_range

            angles_x = np.linspace(x_min, x_max, kx).tolist()
            angles_y = np.linspace(y_min, y_max, ky).tolist()
            angles_z = np.linspace(z_min, z_max, kz).tolist() if self.config.include_angle_z else [0.0]

            # 4. Compute overall bounds across all layer meshes
            all_x: List[float] = []
            all_y: List[float] = []
            for layer in collection.layers:
                m = mesh_map.get(layer.name) or mesh_map.get(layer.layer_id)
                if m and len(m.vertices) > 0:
                    pos = m.get_positions()
                    all_x.extend(pos[:, 0].tolist())
                    all_y.extend(pos[:, 1].tolist())

            if all_x and all_y:
                min_x, max_x = float(min(all_x)), float(max(all_x))
                min_y, max_y = float(min(all_y)), float(max(all_y))
            else:
                min_x, max_x = -500.0, 500.0
                min_y, max_y = -500.0, 500.0

            span_x = max(100.0, max_x - min_x)
            span_y = max(100.0, max_y - min_y)
            pad_x = span_x * 0.15
            pad_y = span_y * 0.15
            grid_min_x = min_x - pad_x
            grid_max_x = max_x + pad_x
            grid_min_y = min_y - pad_y
            grid_max_y = max_y + pad_y

            # 5. Build WarpDeformer grid (5x5 grid -> 6x6 = 36 control points)
            warp_cols = 5
            warp_rows = 5
            xs = np.linspace(grid_min_x, grid_max_x, warp_cols + 1)
            ys = np.linspace(grid_min_y, grid_max_y, warp_rows + 1)
            grid_pts = []
            for y in ys:
                for x in xs:
                    grid_pts.append([x, y])
            base_warp_pts = np.array(grid_pts, dtype=np.float32)

            # Build synthetic grid mesh for 3D deformation solving
            grid_verts = [Vertex(position=pt) for pt in base_warp_pts]
            grid_tris = []
            for r in range(warp_rows):
                for c in range(warp_cols):
                    i0 = r * (warp_cols + 1) + c
                    i1 = i0 + 1
                    i2 = (r + 1) * (warp_cols + 1) + c
                    i3 = i2 + 1
                    grid_tris.append([i0, i1, i2])
                    grid_tris.append([i1, i3, i2])
            grid_mesh = Mesh(
                vertices=grid_verts,
                triangles=np.array(grid_tris, dtype=np.int32),
                layer_id="head"
            )
            grid_mesh.set_depths(np.zeros(len(base_warp_pts), dtype=np.float64))

            warp_deformer = WarpDeformer(
                deformer_id="Warp_Head",
                parent_part_id="PartRoot",
                parent_deformer_id="Rotation_Head" if self.config.include_angle_z else None,
                parameter_ids=["ParamAngleX", "ParamAngleY"],
                grid_rows=warp_rows,
                grid_cols=warp_cols,
                base_vertices=base_warp_pts
            )

            arap_warp = ARAPConstraintSolver(spring_weight=self.config.arap_weight)
            arap_warp.initialize_sparse_system(grid_mesh)

            for ay in angles_y:
                for ax in angles_x:
                    key_tuple = (float(ax), float(ay))
                    if abs(ax) < 1e-4 and abs(ay) < 1e-4:
                        warp_deformer.add_keyform(key_tuple, base_warp_pts.copy())
                        continue

                    target_pos, _ = solver.solve(grid_mesh, ax, ay, 0.0, category="head")
                    solved_pos, _ = arap_warp.solve(grid_mesh, target_pos, num_iterations=self.config.arap_iterations)

                    # Area barrier check
                    mesh_test = grid_mesh.copy()
                    mesh_test.set_positions(solved_pos)
                    signed_areas = mesh_test.compute_triangle_signed_areas()
                    if np.any(signed_areas <= 1e-5):
                        alpha = 1.0
                        for _ in range(8):
                            alpha *= 0.5
                            blend_pos = (1.0 - alpha) * base_warp_pts + alpha * solved_pos
                            mesh_test.set_positions(blend_pos)
                            if np.all(mesh_test.compute_triangle_signed_areas() > 1e-5):
                                solved_pos = blend_pos
                                break

                    warp_deformer.add_keyform(key_tuple, solved_pos.astype(np.float32))

            # 6. Build RotationDeformer (for ParamAngleZ)
            pivot_x = float((min_x + max_x) * 0.5)
            pivot_y = float((min_y + max_y) * 0.5)

            rot_deformer = RotationDeformer(
                deformer_id="Rotation_Head",
                parent_part_id="PartRoot",
                parent_deformer_id=None,
                parameter_ids=["ParamAngleZ"] if self.config.include_angle_z else [],
                origin_x=pivot_x,
                origin_y=pivot_y,
                base_angle=0.0
            )

            if self.config.include_angle_z:
                for az in angles_z:
                    rot_deformer.add_keyform(
                        key_tuple=(float(az),),
                        angle=math.radians(az),
                        origin=(pivot_x, pivot_y),
                        scale=(1.0, 1.0),
                        opacity=1.0
                    )
            else:
                rot_deformer.add_keyform(
                    key_tuple=(0.0,),
                    angle=0.0,
                    origin=(pivot_x, pivot_y),
                    scale=(1.0, 1.0),
                    opacity=1.0
                )

            # 7. Build ArtMeshes (parented to Warp_Head, NO direct parameter bindings!)
            drawables: List[DrawableKeyforms] = []
            for layer in collection.layers:
                mesh = mesh_map.get(layer.name) or mesh_map.get(layer.layer_id)
                if not mesh:
                    continue

                base_v = mesh.get_positions().astype(np.float32)
                tris = mesh.triangles.astype(np.int32)
                uvs = mesh.uvs.astype(np.float32)

                drawable = DrawableKeyforms(
                    drawable_id=f"ArtMesh_{layer.name}",
                    texture_index=0,
                    base_vertices=base_v,
                    triangles=tris,
                    uvs_atlas=uvs,
                    parameter_ids=[],  # ArtMeshes no longer have rotation parameters bound directly to vertices!
                    parent_deformer_id="Warp_Head",
                    parent_part_id="PartRoot",
                    opacity=1.0,
                    draw_order=500,
                    blend_mode=0
                )
                drawables.append(drawable)

            params = [
                ParameterBinding("ParamAngleX", min_val=x_min, default_val=0.0, max_val=x_max, key_values=angles_x),
                ParameterBinding("ParamAngleY", min_val=y_min, default_val=0.0, max_val=y_max, key_values=angles_y),
            ]
            if self.config.include_angle_z:
                params.append(
                    ParameterBinding("ParamAngleZ", min_val=z_min, default_val=0.0, max_val=z_max, key_values=angles_z)
                )

            canvas_w = int(collection.canvas_width) if collection.canvas_width > 0 else int(self.config.atlas_size)
            canvas_h = int(collection.canvas_height) if collection.canvas_height > 0 else int(self.config.atlas_size)

            keyform_table = KeyformTable(
                parameters=params,
                drawables=drawables,
                parts=["PartRoot"],
                warp_deformers=[warp_deformer],
                rotation_deformers=[rot_deformer] if self.config.include_angle_z else [],
                canvas_width=canvas_w,
                canvas_height=canvas_h,
                model_name=self.config.model_name or "model"
            )

            self.metrics["deformer_count"] = len(keyform_table.warp_deformers) + len(keyform_table.rotation_deformers)
            self.metrics["keyform_count"] = len(angles_x) * len(angles_y) + (len(angles_z) if self.config.include_angle_z else 0)
            self.log(f"  [OK] Generated deformer hierarchy (1 Rotation + 1 Warp) controlling {len(drawables)} ArtMeshes")
            return keyform_table

        except Exception as e:
            if isinstance(e, DeformationError):
                raise e
            raise DeformationError(f"3D Deformation solving failed: {e}")

    def stage_texture_packing(
        self,
        collection: LayerCollection,
        mesh_map: Dict[str, Mesh],
        keyform_table: KeyformTable
    ) -> Any:
        """Stage 4: Power-of-two MaxRects texture packing & UV remapping."""
        self.log(f"Packing Texture Atlas (max size: {self.config.atlas_size}, padding: {self.config.padding}px)...")
        try:
            cfg = PackingConfig(
                max_atlas_size=self.config.atlas_size,
                padding=self.config.padding,
                bleed_radius=self.config.bleed_radius,
                crop_transparent=self.config.crop_transparent
            )

            result = TextureAtlasPacker.pack(
                layers=collection,
                meshes=mesh_map,
                config=cfg
            )

            # Update UVs and texture page index in keyform_table drawables
            for d in keyform_table.drawables:
                # Find matching remapped mesh
                match_id = d.drawable_id.replace("ArtMesh_", "")
                match_keys = [d.drawable_id, match_id, f"{match_id}_0"]
                for mk in match_keys:
                    if mk in result.remapped_meshes:
                        rm = result.remapped_meshes[mk]
                        d.uvs_atlas = rm.uvs.astype(np.float32)
                        break
                for mk in match_keys:
                    if mk in result.placements:
                        d.texture_index = result.placements[mk].page_index
                        break

            self.metrics["atlas_pages"] = len(result.pages)
            self.metrics["atlas_dimensions"] = [list(p.shape[:2][::-1]) for p in result.pages]
            if result.stats:
                self.metrics["packing_efficiency"] = float(result.stats.efficiency)

            self.log(f"  [OK] Packed {len(collection.layers)} layers into {len(result.pages)} atlas page(s)")
            return result

        except Exception as e:
            if isinstance(e, ExportError):
                raise e
            raise ExportError(f"Texture atlas packing failed: {e}")

    def stage_export_bundle(
        self,
        keyform_table: KeyformTable,
        packing_result: Any,
        model_name: str,
        output_dir: str
    ) -> Dict[str, str]:
        """Stage 5: Live2D Binary (.moc3) and Metadata (.model3.json, .cdi3.json, textures) serialization."""
        self.log(f"Serializing Live2D Model Bundle: {model_name}...")
        try:
            bundle = Model3Writer.export_model_bundle(
                output_dir=output_dir,
                model_name=model_name,
                keyform_table=keyform_table,
                texture_pages=packing_result.pages
            )
            self.metrics["bundle"] = bundle
            self.log(f"  [OK] Live2D model bundle created at: {bundle['model_dir']}")
            return bundle
        except Exception as e:
            if isinstance(e, ExportError):
                raise e
            raise ExportError(f"Live2D bundle serialization failed: {e}")

    def stage_validate(self, model3_path: str) -> bool:
        """Stage 6: 6-stage structural validator execution."""
        self.log("Executing 6-Stage Programmatic Structural Validation...")
        report = validate_live2d_model(model3_path, strict=self.config.strict)

        self.metrics["validation"] = {
            "is_valid": report.is_valid,
            "passed": report.passed,
            "total_errors": report.total_errors,
            "total_warnings": report.total_warnings,
            "stages_passed": report.stages_passed,
            "errors": report.errors,
            "warnings": report.warnings,
        }

        if not self.config.quiet:
            use_color = sys.stdout.isatty() if hasattr(sys.stdout, 'isatty') else True
            print(report.format_console(use_color=use_color))

        return report.is_valid and report.passed

    def run(self) -> int:
        """Executes the complete pipeline end-to-end and returns standard numeric exit code."""
        start_time = time.time()

        if not self.config.input_path:
            print("[ERROR] Missing input asset path. Usage: python export_live2d.py <input.png_or_psd>", file=sys.stderr)
            return EXIT_ERR_INPUT

        in_p = Path(self.config.input_path).resolve()
        if not in_p.exists():
            print(f"[ERROR] Input asset not found: {in_p}", file=sys.stderr)
            return EXIT_ERR_INPUT

        model_name = self.config.model_name or in_p.stem
        self.metrics["model_name"] = model_name

        if not self.config.quiet:
            print("======================================================================")
            print("    Live2D Automated 3D Key Deformation Pipeline (v1.0.0)")
            print("======================================================================")

        try:
            # Stage 1: Asset Ingestion
            layers = self.stage_ingest()

            # Stage 2: Mesh Generation
            mesh_map = self.stage_mesh_generation(layers)

            # Stage 3: 3D Deformation & Keyforms
            keyform_table = self.stage_deformation_keyforms(layers, mesh_map)

            # Stage 4: Texture Packing
            packing_result = self.stage_texture_packing(layers, mesh_map, keyform_table)

            # Stage 5: Live2D Export
            bundle = self.stage_export_bundle(
                keyform_table=keyform_table,
                packing_result=packing_result,
                model_name=model_name,
                output_dir=self.config.output_dir
            )

            # Stage 6: Validation
            if self.config.validate:
                valid = self.stage_validate(bundle["model3_json"])
                if not valid:
                    return EXIT_ERR_VALIDATION

            elapsed = time.time() - start_time
            self.metrics["status"] = "success"
            self.metrics["exit_code"] = EXIT_SUCCESS
            self.metrics["elapsed_seconds"] = round(elapsed, 3)

            if not self.config.quiet:
                print("======================================================================")
                print(f"[SUCCESS] Export completed in {elapsed:.2f}s! Exit Code: 0")
                print(f"  Model directory: {bundle['model_dir']}")
                print("======================================================================")

            if self.config.json_output:
                print(json.dumps(self.metrics, indent=2))

            return EXIT_SUCCESS

        except InputError as e:
            print(f"[INPUT ERROR] {e}", file=sys.stderr)
            return EXIT_ERR_INPUT
        except MeshGenerationError as e:
            print(f"[MESH ERROR] {e}", file=sys.stderr)
            return EXIT_ERR_MESH
        except DeformationError as e:
            print(f"[DEFORMATION ERROR] {e}", file=sys.stderr)
            return EXIT_ERR_DEFORMATION
        except ExportError as e:
            print(f"[EXPORT ERROR] {e}", file=sys.stderr)
            return EXIT_ERR_EXPORT
        except ValidationError as e:
            print(f"[VALIDATION ERROR] {e}", file=sys.stderr)
            return EXIT_ERR_VALIDATION
        except Exception as e:
            print(f"[UNEXPECTED ERROR] {e}", file=sys.stderr)
            return EXIT_ERR_EXPORT


def build_parser() -> argparse.ArgumentParser:
    """Constructs the full CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="export_live2d",
        description="Automated Zero-Intervention 3D Key Deformation & Live2D Model Exporter",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Positional & Input/Output
    parser.add_argument("input_path", nargs="?", default=None, help="Path to input PSD, PNG, or layer folder")
    parser.add_argument("-i", "--input", dest="input_flag", type=str, default=None, help="Input asset path (alias)")
    parser.add_argument("-o", "--output", "--output-dir", dest="output_dir", type=str, default="./output", help="Root output directory")
    parser.add_argument("-n", "--name", "--model-name", dest="model_name", type=str, default=None, help="Model name identifier")
    parser.add_argument("-f", "--force", "--overwrite", dest="overwrite", action="store_true", default=False, help="Overwrite existing output")

    # Mesh Generation Options
    parser.add_argument("--grid-size", "--mesh-density", dest="grid_size", type=int, default=25, help="Delaunay Steiner grid spacing (px)")
    parser.add_argument("--threshold", "--contour-threshold", dest="contour_threshold", type=int, default=10, help="Alpha silhouette threshold [0-255]")
    parser.add_argument("--simplify-eps", "--contour-epsilon", dest="simplify_eps", type=float, default=2.0, help="Douglas-Peucker contour epsilon")
    parser.add_argument("--smoothing-iterations", "--smoothing", dest="smoothing_iterations", type=int, default=3, help="Laplacian smoothing iterations")

    # 3D Deformation & Angles
    parser.add_argument("--angle-x-range", type=str, default="-30.0,30.0", help="Angle X (Yaw) range min,max in degrees")
    parser.add_argument("--angle-y-range", type=str, default="-30.0,30.0", help="Angle Y (Pitch) range min,max in degrees")
    parser.add_argument("--angle-z-range", type=str, default="-20.0,20.0", help="Angle Z (Roll) range min,max in degrees")
    parser.add_argument("--keyforms-x", type=int, default=3, help="Keyform count for Angle X")
    parser.add_argument("--keyforms-y", type=int, default=3, help="Keyform count for Angle Y")
    parser.add_argument("--keyforms-z", type=int, default=3, help="Keyform count for Angle Z")
    parser.add_argument("--include-angle-z", "--enable-roll", dest="include_angle_z", action="store_true", default=True, help="Include Angle Z roll")
    parser.add_argument("--no-angle-z", dest="include_angle_z", action="store_false", help="Disable Angle Z roll")
    parser.add_argument("--head-radii", type=str, default="0.6,0.8,0.4", help="Head ellipsoid radii Rx,Ry,Rz")
    parser.add_argument("--parallax-scale", type=float, default=0.45, help="Perspective depth parallax factor")
    parser.add_argument("--arap-weight", type=float, default=2.5, help="ARAP regularization stiffness weight")
    parser.add_argument("--arap-iterations", type=int, default=4, help="ARAP solver iterations per keyform")
    parser.add_argument("--auto-depth", action="store_true", default=True, help="Auto-estimate 3D depth field")
    parser.add_argument("--auto-stiffness", action="store_true", default=True, help="Auto-estimate feature stiffness")

    # Texture Atlas Packing
    parser.add_argument("--resolution", "--atlas-size", "--texture-size", dest="atlas_size", type=int, default=4096, help="Max texture atlas dimension (POT)")
    parser.add_argument("--padding", "--atlas-padding", dest="padding", type=int, default=4, help="Sprite padding in pixels")
    parser.add_argument("--bleed-radius", "--edge-bleed", dest="bleed_radius", type=int, default=2, help="Voronoi color bleed dilation radius")
    parser.add_argument("--crop-transparent", dest="crop_transparent", action="store_true", default=True, help="Crop transparent margins")
    parser.add_argument("--include-hidden", dest="include_hidden", action="store_true", default=False, help="Include hidden PSD layers")

    # Validation & Diagnostics
    parser.add_argument("--validate", action="store_true", default=False, help="Run 6-stage structural validator post-export")
    parser.add_argument("--strict", action="store_true", default=False, help="Treat validation warnings as errors")
    parser.add_argument("--gui", "--launch-gui", dest="gui", action="store_true", default=False, help="Launch interactive visualizer after export")
    parser.add_argument("-q", "--quiet", action="store_true", default=False, help="Suppress console logging")
    parser.add_argument("-v", "--verbose", action="store_true", default=False, help="Enable verbose debug logging")
    parser.add_argument("--json-output", action="store_true", default=False, help="Emit JSON summary metrics to stdout")

    return parser


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses command-line arguments into an argparse.Namespace."""
    parser = build_parser()
    return parser.parse_args(args)


def run_pipeline(args_or_namespace: Union[List[str], argparse.Namespace]) -> int:
    """Executes the pipeline with either CLI argument list or parsed Namespace."""
    if isinstance(args_or_namespace, list):
        try:
            parsed = parse_args(args_or_namespace)
        except SystemExit:
            return EXIT_ERR_INPUT
    elif isinstance(args_or_namespace, argparse.Namespace):
        parsed = args_or_namespace
    else:
        return EXIT_ERR_INPUT

    config = PipelineConfig.from_args(parsed)
    runner = PipelineRunner(config)
    return runner.run()


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for export_live2d."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())
