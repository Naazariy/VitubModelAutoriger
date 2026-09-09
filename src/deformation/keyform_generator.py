"""
src/deformation/keyform_generator.py
Live2D Multi-Dimensional Keyform Tensor & Deformer Hierarchy Generator.
Constructs standard Live2D Cubism deformer hierarchy:
RootPart -> RotationDeformer (Angle Z) -> WarpDeformer (Angle X/Y) -> ArtMeshes.
"""

from typing import Dict, List, Tuple, Optional, Any
import numpy as np

from src.core.mesh import Mesh
from src.core.layer import LayerData, LayerCollection
from src.core.keyform import (
    KeyformTable,
    ParameterBinding,
    DrawableKeyforms,
    WarpDeformer,
    RotationDeformer,
)
from src.deformation.deformation_solver import DeformationSolver
from src.constraints.constraint_solver import ARAPConstraintSolver


class KeyformGenerator:
    """
    Generates standard Live2D Cubism deformer hierarchies and keyform displacement tensors:
    - RootPart (Part 0)
    - RotationDeformer for Angle Z (-30, 0, 30 deg)
    - WarpDeformer for Angle X (-30, 0, 30) x Angle Y (-30, 0, 30) 3x3 Cartesian grid
    - ArtMeshes parented to WarpDeformer with clean rest geometry.
    """

    def __init__(
        self,
        deformation_solver: Optional[DeformationSolver] = None,
        constraint_solver: Optional[ARAPConstraintSolver] = None,
        key_angles_xy: Optional[List[float]] = None,
        key_angles_z: Optional[List[float]] = None,
        warp_grid_rows: int = 4,
        warp_grid_cols: int = 4,
    ):
        self.deform_solver = deformation_solver if deformation_solver is not None else DeformationSolver()
        self.constraint_solver = constraint_solver if constraint_solver is not None else ARAPConstraintSolver()
        self.key_angles_xy = list(key_angles_xy) if key_angles_xy is not None else [-30.0, 0.0, 30.0]
        self.key_angles_z = list(key_angles_z) if key_angles_z is not None else [-30.0, 0.0, 30.0]
        self.warp_grid_rows = int(warp_grid_rows)
        self.warp_grid_cols = int(warp_grid_cols)

    def generate_warp_deformer(
        self,
        deformer_id: str = "Warp_Head",
        parent_deformer_id: Optional[str] = "Rotation_Head",
        parent_part_id: str = "PartRoot",
        bounds: Optional[Tuple[float, float, float, float]] = None,
        meshes: Optional[List[Mesh]] = None
    ) -> WarpDeformer:
        """
        Generates a 2D Warp Deformer grid and evaluates 3x3 Cartesian keyforms for AngleX x AngleY.
        """
        # Determine spatial bounding box for the warp deformer grid
        if bounds is not None:
            min_x, min_y, max_x, max_y = bounds
        elif meshes and len(meshes) > 0:
            all_pos = []
            for m in meshes:
                if len(m.vertices) > 0:
                    all_pos.append(m.get_positions())
            if all_pos:
                cat_pos = np.vstack(all_pos)
                min_xy = np.min(cat_pos, axis=0)
                max_xy = np.max(cat_pos, axis=0)
                margin_x = max(0.1, (max_xy[0] - min_xy[0]) * 0.1)
                margin_y = max(0.1, (max_xy[1] - min_xy[1]) * 0.1)
                min_x = float(min_xy[0] - margin_x)
                min_y = float(min_xy[1] - margin_y)
                max_x = float(max_xy[0] + margin_x)
                max_y = float(max_xy[1] + margin_y)
            else:
                min_x, min_y, max_x, max_y = -1.0, -1.0, 1.0, 1.0
        else:
            min_x, min_y, max_x, max_y = -1.0, -1.0, 1.0, 1.0

        # Construct regular 2D grid in row-major order: ((rows+1)*(cols+1), 2)
        xs = np.linspace(min_x, max_x, self.warp_grid_cols + 1, dtype=np.float32)
        ys = np.linspace(min_y, max_y, self.warp_grid_rows + 1, dtype=np.float32)
        GX, GY = np.meshgrid(xs, ys)
        base_grid = np.column_stack([GX.ravel(), GY.ravel()]).astype(np.float32)

        warp = WarpDeformer(
            deformer_id=deformer_id,
            parent_part_id=parent_part_id,
            parent_deformer_id=parent_deformer_id,
            parameter_ids=["ParamAngleX", "ParamAngleY"],
            grid_rows=self.warp_grid_rows,
            grid_cols=self.warp_grid_cols,
            base_vertices=base_grid,
            opacity=1.0
        )

        # 3x3 Cartesian grid for Angle X x Angle Y
        for ay in self.key_angles_xy:
            for ax in self.key_angles_xy:
                key_tuple = (float(ax), float(ay))
                if abs(ax) < 1e-6 and abs(ay) < 1e-6:
                    warp.add_keyform(key_tuple, base_grid.copy())
                    continue

                deformed_grid = self.deform_solver.solve_positions(
                    base_grid, ax, ay, 0.0, category="head"
                )
                warp.add_keyform(key_tuple, deformed_grid.astype(np.float32))

        return warp

    def generate_rotation_deformer(
        self,
        deformer_id: str = "Rotation_Head",
        parent_deformer_id: Optional[str] = None,
        parent_part_id: str = "PartRoot",
        origin: Tuple[float, float] = (0.0, 0.0)
    ) -> RotationDeformer:
        """
        Generates a 2D Rotation Deformer for ParamAngleZ roll keyforms.
        """
        rot = RotationDeformer(
            deformer_id=deformer_id,
            parent_part_id=parent_part_id,
            parent_deformer_id=parent_deformer_id,
            parameter_ids=["ParamAngleZ"],
            base_angle=0.0,
            origin_x=float(origin[0]),
            origin_y=float(origin[1]),
            scale_x=1.0,
            scale_y=1.0
        )

        for az in self.key_angles_z:
            key_tuple = (float(az),)
            rot.add_keyform(
                key_tuple=key_tuple,
                angle=math.radians(az),
                origin=origin,
                scale=(1.0, 1.0),
                opacity=1.0
            )

        return rot

    def generate_drawable_keyforms(
        self,
        drawable_id: str,
        mesh: Mesh,
        category: str = "face",
        texture_index: int = 0,
        draw_order: int = 500,
        opacity: float = 1.0,
        parent_deformer_id: Optional[str] = "Warp_Head",
        include_angle_z: bool = False,
        direct_deform: bool = True
    ) -> DrawableKeyforms:
        """
        Generates an ArtMesh drawable keyform representation.
        Under the Live2D deformer hierarchy, rotation parameters are bound to parent deformers.
        If direct_deform=True, also evaluates discrete keyform deformations for standalone mesh diagnostics.
        """
        base_pos = mesh.get_positions().astype(np.float32)
        triangles = mesh.triangles.astype(np.int32)
        uvs_atlas = mesh.uvs.astype(np.float32)

        param_ids = [] if parent_deformer_id else ["ParamAngleX", "ParamAngleY"]
        if not parent_deformer_id and include_angle_z:
            param_ids.append("ParamAngleZ")

        drawable = DrawableKeyforms(
            drawable_id=drawable_id,
            texture_index=texture_index,
            base_vertices=base_pos,
            triangles=triangles,
            uvs_atlas=uvs_atlas,
            parameter_ids=param_ids,
            draw_order=draw_order,
            opacity=opacity,
            parent_deformer_id=parent_deformer_id
        )

        if not direct_deform:
            return drawable

        # Pre-factorize ARAP system once for this mesh topology
        self.constraint_solver.initialize_sparse_system(mesh)

        # 1. 3x3 Cartesian grid for Angle X x Angle Y
        for ay in self.key_angles_xy:
            for ax in self.key_angles_xy:
                key_tuple = (float(ax), float(ay)) if not include_angle_z else (float(ax), float(ay), 0.0)

                # Strict identity at (0, 0)
                if abs(ax) < 1e-6 and abs(ay) < 1e-6:
                    drawable.add_keyform(key_tuple, base_pos.copy())
                    continue

                # 3D SO(3) Euler projection + normalized depth parallax + anime foreshortening
                target_pos, _ = self.deform_solver.solve(mesh, ax, ay, 0.0, category=category)

                # ARAP Local-Global Energy Minimization
                solved_pos, _ = self.constraint_solver.solve(mesh, target_pos, num_iterations=4)

                # Backtracking line search positive area guarantee
                mesh_test = mesh.copy()
                mesh_test.set_positions(solved_pos)
                signed_areas = mesh_test.compute_triangle_signed_areas()

                if np.any(signed_areas <= 1e-5):
                    alpha = 1.0
                    for _ in range(8):
                        alpha *= 0.5
                        blend_pos = (1.0 - alpha) * base_pos + alpha * solved_pos
                        mesh_test.set_positions(blend_pos)
                        if np.all(mesh_test.compute_triangle_signed_areas() > 1e-5):
                            solved_pos = blend_pos
                            break

                drawable.add_keyform(key_tuple, solved_pos.astype(np.float32))

        # 2. Angle Z roll deformations if requested
        if include_angle_z:
            for az in self.key_angles_z:
                if abs(az) < 1e-6:
                    continue
                key_tuple = (0.0, 0.0, float(az))
                target_pos, _ = self.deform_solver.solve(mesh, 0.0, 0.0, az, category=category)
                solved_pos, _ = self.constraint_solver.solve(mesh, target_pos, num_iterations=3)
                drawable.add_keyform(key_tuple, solved_pos.astype(np.float32))

        return drawable

    def generate_keyform_table(
        self,
        layer_collection: LayerCollection,
        mesh_map: Dict[str, Mesh],
        model_name: str = "model",
        include_angle_z: bool = True,
        direct_deform: bool = False
    ) -> KeyformTable:
        """
        Constructs the master KeyformTable with standard Live2D Deformer Hierarchy:
        RootPart -> RotationDeformer (Angle Z) -> WarpDeformer (Angle X/Y) -> ArtMeshes.
        """
        table = KeyformTable(
            canvas_width=layer_collection.canvas_width,
            canvas_height=layer_collection.canvas_height,
            model_name=model_name,
            parts=["PartRoot"]
        )

        # 1. Register parameter bindings
        table.add_parameter(ParameterBinding(
            param_id="ParamAngleX",
            min_val=-30.0,
            default_val=0.0,
            max_val=30.0,
            key_values=list(self.key_angles_xy),
            name="Angle X"
        ))
        table.add_parameter(ParameterBinding(
            param_id="ParamAngleY",
            min_val=-30.0,
            default_val=0.0,
            max_val=30.0,
            key_values=list(self.key_angles_xy),
            name="Angle Y"
        ))
        if include_angle_z:
            table.add_parameter(ParameterBinding(
                param_id="ParamAngleZ",
                min_val=-30.0,
                default_val=0.0,
                max_val=30.0,
                key_values=list(self.key_angles_z),
                name="Angle Z"
            ))

        # 2. Collect all valid meshes to compute bounding box
        valid_meshes: List[Mesh] = []
        for layer in layer_collection.layers:
            mesh = mesh_map.get(layer.layer_id) or mesh_map.get(layer.name)
            if mesh is not None and len(mesh.vertices) > 0:
                valid_meshes.append(mesh)

        if not direct_deform:
            # 3. Create RotationDeformer (Angle Z) - Root deformer (parent deformer: None)
            rot_deformer = self.generate_rotation_deformer(
                deformer_id="Rotation_Head",
                parent_deformer_id=None,
                parent_part_id="PartRoot",
                origin=(0.0, 0.0)
            )
            if include_angle_z:
                table.add_rotation_deformer(rot_deformer)

            # 4. Create WarpDeformer (Angle X & Angle Y) - child of RotationDeformer
            parent_def_id = "Rotation_Head" if include_angle_z else None
            warp_deformer = self.generate_warp_deformer(
                deformer_id="Warp_Head",
                parent_deformer_id=parent_def_id,
                parent_part_id="PartRoot",
                meshes=valid_meshes
            )
            table.add_warp_deformer(warp_deformer)

        # 5. Generate ArtMeshes
        for idx, layer in enumerate(layer_collection.layers):
            mesh = mesh_map.get(layer.layer_id) or mesh_map.get(layer.name)
            if mesh is None or len(mesh.vertices) == 0:
                continue

            drawable_id = f"ArtMesh_{layer.name.replace(' ', '_')}"
            draw_order = 500 + idx * 10

            drawable = self.generate_drawable_keyforms(
                drawable_id=drawable_id,
                mesh=mesh,
                category=layer.category,
                texture_index=0,
                draw_order=draw_order,
                opacity=layer.opacity,
                parent_deformer_id="Warp_Head" if not direct_deform else None,
                direct_deform=direct_deform,
                include_angle_z=include_angle_z
            )
            table.add_drawable(drawable)

        return table

    @staticmethod
    def compute_displacement_buffer(
        base_positions: np.ndarray,
        deformed_positions: np.ndarray
    ) -> np.ndarray:
        """
        Calculates discrete vertex displacement delta buffer:
        Delta V = V_deformed - V_base
        """
        base = np.asarray(base_positions, dtype=np.float32)
        deformed = np.asarray(deformed_positions, dtype=np.float32)
        if base.shape != deformed.shape:
            raise ValueError(f"Shape mismatch: base {base.shape} vs deformed {deformed.shape}")
        return deformed - base

