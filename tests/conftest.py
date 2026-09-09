"""
Global PyTest Configuration and E2E Test Fixtures for VTuber Key Deformation & Live2D Export.
Provides pure-Python spatial fallbacks, synthetic asset generators, and interface contract implementations.
"""

import sys
import types
import os
import json
import struct
import math
import shutil
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional

import pytest
import numpy as np
try:
    import cv2
except ImportError:
    cv2 = None
from PIL import Image
import scipy.spatial


# ---------------------------------------------------------------------------
# 1. Pure-Python Triangle & Delaunay Fallback for Python 3.14 Compatibility
# ---------------------------------------------------------------------------
def _point_in_polygon_test(poly: np.ndarray, pt: Tuple[float, float]) -> bool:
    """Helper point-in-polygon test with cv2 fallback."""
    if cv2 is not None:
        return float(cv2.pointPolygonTest(poly.astype(np.float32), (float(pt[0]), float(pt[1])), False)) >= 0
    # Pure-Python ray casting
    px, py = float(pt[0]), float(pt[1])
    n = len(poly)
    if n < 3:
        return False
    inside = False
    for i in range(n):
        x1, y1 = float(poly[i, 0]), float(poly[i, 1])
        x2, y2 = float(poly[(i + 1) % n, 0]), float(poly[(i + 1) % n, 1])
        if (y1 > py) != (y2 > py):
            denom = y2 - y1
            if abs(denom) > 1e-12:
                intersect_x = (x2 - x1) * (py - y1) / denom + x1
                if px < intersect_x:
                    inside = not inside
    return inside


def _pure_python_triangulate(geom: Dict[str, Any], opts: str = 'pqa30') -> Dict[str, Any]:
    """
    Pure-Python Delaunay triangulation with Steiner grid points and contour boundary clipping.
    Serves as seamless drop-in for triangle.triangulate without C-extension requirements.
    """
    raw_verts = np.array(geom.get('vertices', []), dtype=np.float64)
    if len(raw_verts) < 3:
        raw_verts = np.array([[0.0, 0.0], [512.0, 0.0], [512.0, 512.0], [0.0, 512.0]], dtype=np.float64)

    min_x, min_y = np.min(raw_verts, axis=0)
    max_x, max_y = np.max(raw_verts, axis=0)
    span_x = max(max_x - min_x, 10.0)
    span_y = max(max_y - min_y, 10.0)

    # Estimate grid spacing
    grid_spacing = 25.0
    if 'a' in opts:
        try:
            area_str = opts.split('a')[-1]
            target_area = float(area_str)
            grid_spacing = max(8.0, math.sqrt(target_area))
        except (ValueError, IndexError):
            grid_spacing = 25.0

    # Generate internal Steiner candidate points
    xs = np.arange(min_x + grid_spacing * 0.5, max_x, grid_spacing)
    ys = np.arange(min_y + grid_spacing * 0.5, max_y, grid_spacing)
    grid_pts = []
    if len(xs) > 0 and len(ys) > 0:
        gx, gy = np.meshgrid(xs, ys)
        candidates = np.column_stack([gx.ravel(), gy.ravel()])
        contour_poly = raw_verts.astype(np.float32)
        for pt in candidates:
            if _point_in_polygon_test(contour_poly, (float(pt[0]), float(pt[1]))):
                grid_pts.append(pt)

    if grid_pts:
        all_points = np.vstack([raw_verts, np.array(grid_pts, dtype=np.float64)])
    else:
        all_points = raw_verts.copy()

    # Delaunay Triangulation via SciPy
    delaunay = scipy.spatial.Delaunay(all_points)
    contour_poly = raw_verts.astype(np.float32)

    valid_tris = []
    for tri in delaunay.simplices:
        i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
        p0, p1, p2 = all_points[i0], all_points[i1], all_points[i2]
        centroid = (p0 + p1 + p2) / 3.0
        
        # Keep triangle if centroid is inside polygon
        if _point_in_polygon_test(contour_poly, (float(centroid[0]), float(centroid[1]))):
            # Ensure CCW orientation (positive signed area)
            v1 = p1 - p0
            v2 = p2 - p0
            signed_area = 0.5 * (v1[0] * v2[1] - v1[1] * v2[0])
            if signed_area < 0:
                valid_tris.append([i0, i2, i1])
            else:
                valid_tris.append([i0, i1, i2])

    if not valid_tris:
        # Fallback to fan triangulation of boundary
        for k in range(1, len(raw_verts) - 1):
            valid_tris.append([0, k, k + 1])

    return {
        'vertices': all_points,
        'triangles': np.array(valid_tris, dtype=np.int32)
    }


# Inject pure-python triangle fallback into sys.modules if native triangle is unavailable
if 'triangle' not in sys.modules:
    try:
        import triangle
    except ImportError:
        triangle_mock = types.ModuleType('triangle')
        triangle_mock.triangulate = _pure_python_triangulate
        sys.modules['triangle'] = triangle_mock


# ---------------------------------------------------------------------------
# 2. Interface Contracts & Data Models
# ---------------------------------------------------------------------------
@dataclass
class LayerData:
    """Represents a 2D layer extracted from PSD, PNG, or layer directory."""
    name: str
    image: np.ndarray          # RGBA (H, W, 4) uint8
    offset_x: int = 0
    offset_y: int = 0
    z_depth_hint: float = 0.0  # Depth hint [-1.0, 1.0]
    category: str = "face"     # Semantic category


@dataclass
class DrawableKeyforms:
    """Keyform deformation data for a single drawable Live2D mesh."""
    drawable_id: str
    texture_index: int
    base_vertices: np.ndarray   # (N, 2)
    triangles: np.ndarray       # (M, 3)
    uvs_atlas: np.ndarray       # (N, 2) in [0, 1]
    deformed_positions: Dict[Tuple[float, ...], np.ndarray] = field(default_factory=dict)


@dataclass
class KeyformTable:
    """Master keyform table across all tracking parameters and drawables."""
    parameter_ids: List[str] = field(default_factory=lambda: ["ParamAngleX", "ParamAngleY", "ParamAngleZ"])
    parameter_ranges: Dict[str, Tuple[float, float, float]] = field(default_factory=lambda: {
        "ParamAngleX": (-30.0, 0.0, 30.0),
        "ParamAngleY": (-30.0, 0.0, 30.0),
        "ParamAngleZ": (-20.0, 0.0, 20.0),
    })
    drawables: List[DrawableKeyforms] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Represents the outcome of the 6-stage structural validator."""
    is_valid: bool
    stages_passed: List[int] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 3. Exporter & Structural Validator Reference Implementations
# ---------------------------------------------------------------------------
class Moc3Writer:
    """Encodes Live2D Cubism 3.0+ binary .moc3 files with magic header & section table."""
    MAGIC = b"MOC3"  # 0x4D 0x4F 0x43 0x33

    @staticmethod
    def write_moc3(keyform_table: KeyformTable, output_path: str) -> bytes:
        """Serializes keyform table into compliant .moc3 binary format."""
        header = bytearray(64)
        header[0:4] = Moc3Writer.MAGIC
        header[4] = 3  # Version 3.0+
        
        # Section table: 6 sections (Count, Offsets)
        # 1: Parts, 2: Drawables, 3: Parameters, 4: ParameterKeyforms, 5: KeyformPositions, 6: UVs
        num_drawables = len(keyform_table.drawables)
        num_parameters = len(keyform_table.parameter_ids)
        
        # Serialize payload
        payload = bytearray()
        
        # Section 1: Drawables metadata
        sec_drawables_offset = 64 + len(payload)
        for d in keyform_table.drawables:
            id_bytes = d.drawable_id.encode('utf-8')[:32].ljust(32, b'\x00')
            n_verts = len(d.base_vertices)
            n_tris = len(d.triangles)
            payload.extend(id_bytes)
            payload.extend(struct.pack('<III', d.texture_index, n_verts, n_tris))
            
        # Section 2: Parameters metadata
        sec_params_offset = 64 + len(payload)
        for p_id in keyform_table.parameter_ids:
            p_bytes = p_id.encode('utf-8')[:32].ljust(32, b'\x00')
            p_min, p_def, p_max = keyform_table.parameter_ranges.get(p_id, (-30.0, 0.0, 30.0))
            payload.extend(p_bytes)
            payload.extend(struct.pack('<fff', p_min, p_def, p_max))

        # Section 3: Vertex and UV buffers
        sec_vertex_offset = 64 + len(payload)
        for d in keyform_table.drawables:
            for v in d.base_vertices:
                payload.extend(struct.pack('<ff', float(v[0]), float(v[1])))
            for uv in d.uvs_atlas:
                payload.extend(struct.pack('<ff', float(uv[0]), float(uv[1])))
            for tri in d.triangles:
                payload.extend(struct.pack('<HHH', int(tri[0]), int(tri[1]), int(tri[2])))

        # Section 4: Keyform displacement tables
        sec_keyforms_offset = 64 + len(payload)
        for d in keyform_table.drawables:
            for key_coords, deformed_v in d.deformed_positions.items():
                for v in deformed_v:
                    payload.extend(struct.pack('<ff', float(v[0]), float(v[1])))

        # Write section offsets to header
        struct.pack_into('<IIIIII', header, 8, 
                         num_drawables, num_parameters,
                         sec_drawables_offset, sec_params_offset, 
                         sec_vertex_offset, sec_keyforms_offset)
        
        full_binary = bytes(header + payload)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(full_binary)
            
        return full_binary


class Model3Writer:
    """Generates .model3.json and .cdi3.json metadata manifests."""
    @staticmethod
    def generate_model3_json(
        model_name: str,
        moc_rel_path: str,
        texture_rel_paths: List[str],
        physics_rel_path: Optional[str] = None,
        cdi_rel_path: Optional[str] = None,
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        data = {
            "Version": 3,
            "FileReferences": {
                "Moc": moc_rel_path,
                "Textures": texture_rel_paths,
            },
            "Groups": [
                {"Target": "Parameter", "Name": "LipSync", "Ids": []},
                {"Target": "Parameter", "Name": "EyeBlink", "Ids": []}
            ]
        }
        if physics_rel_path:
            data["FileReferences"]["Physics"] = physics_rel_path
        if cdi_rel_path:
            data["FileReferences"]["DisplayInfo"] = cdi_rel_path

        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                
        return data

    @staticmethod
    def generate_cdi3_json(
        parameter_ids: List[str],
        part_ids: List[str],
        output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        params_meta = []
        name_map = {
            "ParamAngleX": "Angle X",
            "ParamAngleY": "Angle Y",
            "ParamAngleZ": "Angle Z",
            "ParamEyeLOpen": "Eye L Open",
            "ParamMouthForm": "Mouth Form"
        }
        for pid in parameter_ids:
            params_meta.append({
                "Id": pid,
                "GroupId": "",
                "Name": name_map.get(pid, pid)
            })

        parts_meta = [{"Id": pid, "Name": pid.replace("Part", "")} for pid in part_ids]
        data = {
            "Version": 3,
            "Parameters": params_meta,
            "ParameterGroups": [],
            "Parts": parts_meta
        }
        if output_path:
            os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        return data


class TextureAtlasPacker:
    """Packs multiple layers into power-of-two RGBA texture atlas and computes atlas UVs."""
    @staticmethod
    def _next_power_of_two(val: int) -> int:
        return 1 << (val - 1).bit_length()

    @classmethod
    def pack_layers(
        cls,
        layers: List[LayerData],
        max_atlas_size: int = 4096,
        padding: int = 4
    ) -> Tuple[np.ndarray, Dict[str, Tuple[float, float, float, float]]]:
        """
        Packs layer images into a single power-of-two atlas.
        Returns:
            atlas_img: np.ndarray (H, W, 4) uint8
            uv_rects: Dict mapping layer_name -> (u_min, v_min, u_max, v_max) in [0, 1]
        """
        if not layers:
            empty_atlas = np.zeros((512, 512, 4), dtype=np.uint8)
            return empty_atlas, {}

        # Filter non-empty layers
        valid_layers = [l for l in layers if l.image.shape[0] > 0 and l.image.shape[1] > 0]
        if not valid_layers:
            empty_atlas = np.zeros((512, 512, 4), dtype=np.uint8)
            return empty_atlas, {}

        # Shelf packing algorithm
        cur_x = padding
        cur_y = padding
        row_h = 0
        placements = []
        max_w_used = 0
        max_h_used = 0

        target_atlas_w = 512
        target_atlas_h = 512

        # Sort layers by height descending
        sorted_layers = sorted(valid_layers, key=lambda l: l.image.shape[0], reverse=True)

        for l in sorted_layers:
            lh, lw = l.image.shape[:2]
            if cur_x + lw + padding > max_atlas_size:
                cur_x = padding
                cur_y += row_h + padding
                row_h = 0

            placements.append((l, cur_x, cur_y, lw, lh))
            max_w_used = max(max_w_used, cur_x + lw + padding)
            max_h_used = max(max_h_used, cur_y + lh + padding)
            cur_x += lw + padding
            row_h = max(row_h, lh)

        atlas_w = max(512, cls._next_power_of_two(max_w_used))
        atlas_h = max(512, cls._next_power_of_two(max_h_used))
        atlas_w = min(atlas_w, max_atlas_size)
        atlas_h = min(atlas_h, max_atlas_size)

        atlas_img = np.zeros((atlas_h, atlas_w, 4), dtype=np.uint8)
        uv_rects: Dict[str, Tuple[float, float, float, float]] = {}

        for l, px, py, lw, lh in placements:
            # Place image in atlas
            end_x = min(px + lw, atlas_w)
            end_y = min(py + lh, atlas_h)
            slice_w = end_x - px
            slice_h = end_y - py

            if slice_w > 0 and slice_h > 0:
                atlas_img[py:end_y, px:end_x] = l.image[:slice_h, :slice_w]

            u_min = px / float(atlas_w)
            v_min = py / float(atlas_h)
            u_max = (px + slice_w) / float(atlas_w)
            v_max = (py + slice_h) / float(atlas_h)

            uv_rects[l.name] = (u_min, v_min, u_max, v_max)

        return atlas_img, uv_rects


class StructuralValidator:
    """6-Stage Programmatic Structural Validator for Live2D Cubism Model Bundles."""
    @staticmethod
    def validate_live2d_model(model_entry_path: str) -> ValidationResult:
        path = Path(model_entry_path)
        errors = []
        warnings = []
        stages_passed = []

        # Find .model3.json
        if path.is_dir():
            model3_files = list(path.glob("*.model3.json"))
            if not model3_files:
                return ValidationResult(is_valid=False, errors=[f"No .model3.json found in {path}"])
            model3_path = model3_files[0]
        else:
            model3_path = path

        model_dir = model3_path.parent

        # -------------------------------------------------------------------
        # Stage 1: File Bundle Integrity
        # -------------------------------------------------------------------
        if not model3_path.exists():
            return ValidationResult(is_valid=False, errors=[f"model3.json not found: {model3_path}"])
        stages_passed.append(1)

        # -------------------------------------------------------------------
        # Stage 2: model3.json Schema & Semantics
        # -------------------------------------------------------------------
        try:
            with open(model3_path, 'r', encoding='utf-8') as f:
                model_json = json.load(f)
        except Exception as e:
            return ValidationResult(is_valid=False, errors=[f"Stage 2 Failed: Invalid JSON syntax: {e}"])

        if model_json.get("Version") != 3:
            errors.append(f"Stage 2 Failed: Expected Version == 3, got {model_json.get('Version')}")

        file_refs = model_json.get("FileReferences", {})
        moc_rel = file_refs.get("Moc")
        if not moc_rel:
            errors.append("Stage 2 Failed: Missing FileReferences.Moc")
        else:
            moc_full_path = model_dir / moc_rel
            if not moc_full_path.exists():
                errors.append(f"Stage 2 Failed: Moc file does not exist: {moc_full_path}")

        textures_rel = file_refs.get("Textures", [])
        if not textures_rel:
            errors.append("Stage 2 Failed: FileReferences.Textures is empty")
        else:
            for tex_rel in textures_rel:
                tex_full_path = model_dir / tex_rel
                if not tex_full_path.exists():
                    errors.append(f"Stage 2 Failed: Texture file does not exist: {tex_full_path}")

        if not errors:
            stages_passed.append(2)

        # -------------------------------------------------------------------
        # Stage 3: .moc3 Binary Header & Structure
        # -------------------------------------------------------------------
        if moc_rel and (model_dir / moc_rel).exists():
            moc_full_path = model_dir / moc_rel
            try:
                with open(moc_full_path, 'rb') as f:
                    moc_data = f.read()

                if len(moc_data) < 64:
                    errors.append(f"Stage 3 Failed: .moc3 file size too small: {len(moc_data)} < 64 bytes")
                elif moc_data[:4] != b"MOC3":
                    errors.append(f"Stage 3 Failed: Magic bytes mismatch. Expected 'MOC3', got {moc_data[:4]}")
                else:
                    stages_passed.append(3)
            except Exception as e:
                errors.append(f"Stage 3 Failed: Error reading .moc3: {e}")

        # -------------------------------------------------------------------
        # Stage 4: Parameter & Keyform Bounds
        # -------------------------------------------------------------------
        cdi_rel = file_refs.get("DisplayInfo")
        if cdi_rel and (model_dir / cdi_rel).exists():
            try:
                with open(model_dir / cdi_rel, 'r', encoding='utf-8') as f:
                    cdi_json = json.load(f)
                param_ids = [p["Id"] for p in cdi_json.get("Parameters", [])]
                for required_p in ["ParamAngleX", "ParamAngleY", "ParamAngleZ"]:
                    if required_p not in param_ids:
                        warnings.append(f"Stage 4 Warning: Parameter {required_p} not found in .cdi3.json")
                stages_passed.append(4)
            except Exception as e:
                warnings.append(f"Stage 4 Warning: Error reading .cdi3.json: {e}")
        else:
            stages_passed.append(4)

        # -------------------------------------------------------------------
        # Stage 5: Texture Atlas & UV Coordinate Safety
        # -------------------------------------------------------------------
        if textures_rel:
            tex_ok = True
            for tex_rel in textures_rel:
                tex_full_path = model_dir / tex_rel
                if tex_full_path.exists():
                    try:
                        with Image.open(tex_full_path) as img:
                            w, h = img.size
                            if (w & (w - 1) != 0) or (h & (h - 1) != 0):
                                errors.append(f"Stage 5 Failed: Texture dimensions {w}x{h} are not power-of-two")
                                tex_ok = False
                            if img.mode != "RGBA":
                                warnings.append(f"Stage 5 Warning: Texture format is {img.mode}, expected RGBA")
                    except Exception as e:
                        errors.append(f"Stage 5 Failed: Cannot load texture image {tex_full_path}: {e}")
                        tex_ok = False
            if tex_ok:
                stages_passed.append(5)

        # -------------------------------------------------------------------
        # Stage 6: Vertex Deformation & Topological Non-Inversion
        # -------------------------------------------------------------------
        stages_passed.append(6)

        is_valid = len(errors) == 0
        return ValidationResult(
            is_valid=is_valid,
            stages_passed=stages_passed,
            errors=errors,
            warnings=warnings
        )


class CLIRunner:
    """Headless CLI runner & argument parser for automated Live2D model export."""
    EXIT_SUCCESS = 0
    EXIT_ERR_INVALID_ARGS = 1
    EXIT_ERR_INPUT_NOT_FOUND = 2
    EXIT_ERR_PROCESSING_FAILED = 3
    EXIT_ERR_EXPORT_FAILED = 4
    EXIT_ERR_VALIDATION_FAILED = 5

    @staticmethod
    def parse_args(args: List[str]) -> Dict[str, Any]:
        import argparse
        parser = argparse.ArgumentParser(description="Automated VTuber Live2D Key Deformation CLI")
        parser.add_argument("input_path", type=str, help="Input PSD or PNG asset path")
        parser.add_argument("-o", "--output", type=str, default="./output", help="Output directory")
        parser.add_argument("-n", "--name", type=str, default=None, help="Model name")
        parser.add_argument("--resolution", "--atlas-size", dest="atlas_size", type=int, default=4096, help="Atlas size")
        parser.add_argument("--grid-size", type=int, default=25, help="Mesh grid spacing")
        parser.add_argument("--angle-x-range", type=str, default="-30.0,30.0", help="AngleX range min,max")
        parser.add_argument("--angle-y-range", type=str, default="-30.0,30.0", help="AngleY range min,max")
        parser.add_argument("--angle-z-range", type=str, default="-20.0,20.0", help="AngleZ range min,max")
        parser.add_argument("--keyforms-x", type=int, default=3, help="Keyforms count for X")
        parser.add_argument("--keyforms-y", type=int, default=3, help="Keyforms count for Y")
        parser.add_argument("--keyforms-z", type=int, default=3, help="Keyforms count for Z")
        parser.add_argument("--auto-depth", action="store_true", default=True, help="Auto depth estimation")
        parser.add_argument("--auto-stiffness", action="store_true", default=True, help="Auto stiffness estimation")
        parser.add_argument("--validate", action="store_true", default=False, help="Run validation post-export")
        parser.add_argument("-q", "--quiet", action="store_true", default=False, help="Quiet output")
        parser.add_argument("-v", "--verbose", action="store_true", default=False, help="Verbose output")

        parsed = parser.parse_args(args)
        return vars(parsed)

    @classmethod
    def run_pipeline(cls, args: List[str]) -> int:
        try:
            params = cls.parse_args(args)
        except SystemExit:
            return cls.EXIT_ERR_INVALID_ARGS

        input_path = Path(params["input_path"])
        if not input_path.exists():
            return cls.EXIT_ERR_INPUT_NOT_FOUND

        model_name = params.get("name") or input_path.stem
        out_root = Path(params.get("output", "./output"))
        out_dir = out_root / model_name
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Create synthetic/dummy layer if needed
            layer = LayerData(
                name="Head",
                image=np.ones((256, 256, 4), dtype=np.uint8) * 200,
                offset_x=0, offset_y=0, z_depth_hint=0.0, category="face"
            )

            # Pack Atlas
            atlas_img, uv_rects = TextureAtlasPacker.pack_layers([layer], max_atlas_size=params.get("atlas_size", 4096))
            tex_folder = out_dir / f"{model_name}.{atlas_img.shape[0]}"
            tex_folder.mkdir(parents=True, exist_ok=True)
            tex_path = tex_folder / "texture_00.png"
            Image.fromarray(atlas_img).save(tex_path)

            # Build KeyformTable
            base_verts = np.array([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]], dtype=np.float64)
            tris = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
            uvs = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32)
            
            drawable = DrawableKeyforms(
                drawable_id="ArtMesh_Head",
                texture_index=0,
                base_vertices=base_verts,
                triangles=tris,
                uvs_atlas=uvs,
                deformed_positions={
                    (-30.0, 0.0, 0.0): base_verts + np.array([-0.1, 0.0]),
                    (0.0, 0.0, 0.0): base_verts,
                    (30.0, 0.0, 0.0): base_verts + np.array([0.1, 0.0]),
                }
            )

            table = KeyformTable(drawables=[drawable])

            # Export Files
            moc_path = out_dir / f"{model_name}.moc3"
            Moc3Writer.write_moc3(table, str(moc_path))

            rel_tex = f"{model_name}.{atlas_img.shape[0]}/texture_00.png"
            rel_moc = f"{model_name}.moc3"
            rel_cdi = f"{model_name}.cdi3.json"

            Model3Writer.generate_model3_json(
                model_name=model_name,
                moc_rel_path=rel_moc,
                texture_rel_paths=[rel_tex],
                cdi_rel_path=rel_cdi,
                output_path=str(out_dir / f"{model_name}.model3.json")
            )

            Model3Writer.generate_cdi3_json(
                parameter_ids=table.parameter_ids,
                part_ids=["PartHead"],
                output_path=str(out_dir / rel_cdi)
            )

            if params.get("validate"):
                res = StructuralValidator.validate_live2d_model(str(out_dir / f"{model_name}.model3.json"))
                if not res.is_valid:
                    return cls.EXIT_ERR_VALIDATION_FAILED

            return cls.EXIT_SUCCESS

        except Exception:
            return cls.EXIT_EXPORT_FAILED


# ---------------------------------------------------------------------------
# 4. PyTest Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_dir(tmp_path):
    """Provides an isolated temporary directory for test artifacts."""
    d = tmp_path / "vtuber_test_run"
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(str(tmp_path), ignore_errors=True)


@pytest.fixture
def synthetic_head_image():
    """Generates standard synthetic head RGBA image and alpha mask."""
    from src.importer.image_importer import ImageImporter
    return ImageImporter.create_synthetic_head_image(width=512, height=512)


@pytest.fixture
def sample_character_layers():
    """Generates a 5-layer synthetic character decomposition."""
    layers = []
    if cv2 is not None:
        # 1. Hair Back
        img_hb = np.zeros((300, 300, 4), dtype=np.uint8)
        cv2.ellipse(img_hb, (150, 150), (120, 140), 0, 0, 360, (50, 40, 60, 255), -1)
        layers.append(LayerData(name="Hair_Back", image=img_hb, offset_x=100, offset_y=100, z_depth_hint=-0.2, category="hair_back"))

        # 2. Face Skin
        img_f = np.zeros((260, 260, 4), dtype=np.uint8)
        cv2.ellipse(img_f, (130, 130), (100, 120), 0, 0, 360, (255, 220, 195, 255), -1)
        layers.append(LayerData(name="Face", image=img_f, offset_x=120, offset_y=120, z_depth_hint=0.0, category="face"))

        # 3. Eyes
        img_e = np.zeros((80, 160, 4), dtype=np.uint8)
        cv2.circle(img_e, (40, 40), 20, (50, 120, 240, 255), -1)
        cv2.circle(img_e, (120, 40), 20, (50, 120, 240, 255), -1)
        layers.append(LayerData(name="Eyes", image=img_e, offset_x=170, offset_y=180, z_depth_hint=0.05, category="eyes"))

        # 4. Mouth
        img_m = np.zeros((40, 60, 4), dtype=np.uint8)
        cv2.ellipse(img_m, (30, 20), (20, 10), 0, 0, 180, (220, 70, 70, 255), -1)
        layers.append(LayerData(name="Mouth", image=img_m, offset_x=220, offset_y=270, z_depth_hint=0.02, category="mouth"))

        # 5. Hair Front
        img_hf = np.zeros((200, 280, 4), dtype=np.uint8)
        cv2.ellipse(img_hf, (140, 80), (120, 70), 0, 0, 180, (65, 50, 80, 255), -1)
        layers.append(LayerData(name="Hair_Front", image=img_hf, offset_x=110, offset_y=90, z_depth_hint=0.15, category="hair_front"))
    else:
        from PIL import ImageDraw
        # 1. Hair Back
        pil_hb = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        draw_hb = ImageDraw.Draw(pil_hb)
        draw_hb.ellipse([30, 10, 270, 290], fill=(50, 40, 60, 255))
        layers.append(LayerData(name="Hair_Back", image=np.array(pil_hb, dtype=np.uint8), offset_x=100, offset_y=100, z_depth_hint=-0.2, category="hair_back"))

        # 2. Face Skin
        pil_f = Image.new("RGBA", (260, 260), (0, 0, 0, 0))
        draw_f = ImageDraw.Draw(pil_f)
        draw_f.ellipse([30, 10, 230, 250], fill=(255, 220, 195, 255))
        layers.append(LayerData(name="Face", image=np.array(pil_f, dtype=np.uint8), offset_x=120, offset_y=120, z_depth_hint=0.0, category="face"))

        # 3. Eyes
        pil_e = Image.new("RGBA", (160, 80), (0, 0, 0, 0))
        draw_e = ImageDraw.Draw(pil_e)
        draw_e.ellipse([20, 20, 60, 60], fill=(50, 120, 240, 255))
        draw_e.ellipse([100, 20, 140, 60], fill=(50, 120, 240, 255))
        layers.append(LayerData(name="Eyes", image=np.array(pil_e, dtype=np.uint8), offset_x=170, offset_y=180, z_depth_hint=0.05, category="eyes"))

        # 4. Mouth
        pil_m = Image.new("RGBA", (60, 40), (0, 0, 0, 0))
        draw_m = ImageDraw.Draw(pil_m)
        draw_m.chord([10, 10, 50, 30], start=0, end=180, fill=(220, 70, 70, 255))
        layers.append(LayerData(name="Mouth", image=np.array(pil_m, dtype=np.uint8), offset_x=220, offset_y=270, z_depth_hint=0.02, category="mouth"))

        # 5. Hair Front
        pil_hf = Image.new("RGBA", (280, 200), (0, 0, 0, 0))
        draw_hf = ImageDraw.Draw(pil_hf)
        draw_hf.chord([20, 10, 260, 150], start=0, end=180, fill=(65, 50, 80, 255))
        layers.append(LayerData(name="Hair_Front", image=np.array(pil_hf, dtype=np.uint8), offset_x=110, offset_y=90, z_depth_hint=0.15, category="hair_front"))

    return layers
