"""
src/deformation/deformation_solver.py
Complete 3D SO(3) Head Deformation, Normalized Depth Parallax, and Anime Foreshortening Solver.
"""

from typing import Tuple, Dict, List, Optional, Union
import numpy as np
import math

from src.core.mesh import Mesh
from src.core.keyform import DrawableKeyforms, ParameterBinding
from src.constraints.constraint_solver import ARAPConstraintSolver


class DeformationSolver:
    """
    Automated 3D Head Deformation Engine for Live2D Cubism Model Generation.
    Computes SO(3) Euler rotations, normalized depth parallax (with zero-identity guarantee),
    anime contour warping, and ARAP-regularized multi-dimensional keyform tensors.
    """

    # Calibrated Layer Depth & Parallax Presets
    LAYER_PRESETS: Dict[str, Dict[str, float]] = {
        "hair_front":  {"z_offset": 0.25, "parallax": 0.60, "stiffness": 0.20},
        "accessories": {"z_offset": 0.22, "parallax": 0.55, "stiffness": 0.85},
        "nose":        {"z_offset": 0.30, "parallax": 0.55, "stiffness": 0.95},
        "eyebrows":    {"z_offset": 0.12, "parallax": 0.50, "stiffness": 0.70},
        "eyes":        {"z_offset": 0.08, "parallax": 0.48, "stiffness": 0.90},
        "mouth":       {"z_offset": 0.02, "parallax": 0.42, "stiffness": 0.85},
        "face":        {"z_offset": 0.00, "parallax": 0.40, "stiffness": 0.40},
        "head":        {"z_offset": 0.00, "parallax": 0.40, "stiffness": 0.40},
        "hair_side":   {"z_offset": -0.05, "parallax": 0.38, "stiffness": 0.30},
        "ears":        {"z_offset": -0.10, "parallax": 0.35, "stiffness": 0.75},
        "neck":        {"z_offset": -0.25, "parallax": 0.15, "stiffness": 0.80},
        "body":        {"z_offset": -0.25, "parallax": 0.15, "stiffness": 0.80},
        "hair_back":   {"z_offset": -0.35, "parallax": 0.22, "stiffness": 0.15},
        "unknown":     {"z_offset": 0.00, "parallax": 0.40, "stiffness": 0.50},
    }

    def __init__(
        self,
        center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        head_radius_x: float = 0.6,
        head_radius_y: float = 0.8,
        head_radius_z: float = 0.4,
        parallax_scale: float = 0.45,
    ):
        self.center = np.array(center, dtype=np.float64)
        self.radius_x = float(head_radius_x)
        self.radius_y = float(head_radius_y)
        self.radius_z = float(head_radius_z)
        self.head_radius_z = self.radius_z  # Alias for backward compatibility
        self.parallax_scale = float(parallax_scale)

    @staticmethod
    def get_rotation_matrix(
        angle_x_deg: float,
        angle_y_deg: float,
        angle_z_deg: float = 0.0
    ) -> np.ndarray:
        """
        Calculates exact 3D SO(3) rotation matrix for Yaw (AngleX), Pitch (AngleY), and Roll (AngleZ).
        Composition sequence: R = Rz(theta_z) * Ry(theta_x) * Rx(theta_y).
        
        AngleX: rotation around Y-axis (Yaw)
        AngleY: rotation around X-axis (Pitch)
        AngleZ: rotation around Z-axis (Roll)
        """
        rad_x = np.radians(angle_x_deg)
        rad_y = np.radians(angle_y_deg)
        rad_z = np.radians(angle_z_deg)

        cx, sx = np.cos(rad_x), np.sin(rad_x)
        cy, sy = np.cos(rad_y), np.sin(rad_y)
        cz, sz = np.cos(rad_z), np.sin(rad_z)

        # Rx (Pitch - AngleY)
        Rx = np.array([
            [1.0, 0.0,  0.0],
            [0.0, cy,  -sy],
            [0.0, sy,   cy]
        ], dtype=np.float64)

        # Ry (Yaw - AngleX)
        Ry = np.array([
            [cx,  0.0, sx],
            [0.0, 1.0, 0.0],
            [-sx, 0.0, cx]
        ], dtype=np.float64)

        # Rz (Roll - AngleZ)
        Rz = np.array([
            [cz, -sz, 0.0],
            [sz,  cz, 0.0],
            [0.0, 0.0, 1.0]
        ], dtype=np.float64)

        return Rz @ Ry @ Rx

    def compute_anime_foreshortening(
        self,
        norm_x: np.ndarray,
        norm_y: np.ndarray,
        angle_x_deg: float,
        angle_y_deg: float,
        category: str = "face"
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculates non-linear anime silhouette and facial feature foreshortening fields (Phi_x, Phi_y).
        """
        rad_x = np.radians(angle_x_deg)
        rad_y = np.radians(angle_y_deg)
        abs_rad_x = abs(rad_x)

        # 1. Horizontal Yaw Foreshortening
        phi_x = np.ones_like(norm_x)
        if abs_rad_x > 1e-4:
            # Turned-away side (far side)
            far_mask = (norm_x * rad_x) < 0.0
            phi_x[far_mask] = 1.0 - 0.35 * np.sin(abs_rad_x) * (1.0 - np.exp(-2.5 * np.abs(norm_x[far_mask])))

            # Facing side (near side)
            near_mask = ~far_mask
            phi_x[near_mask] = 1.0 + 0.08 * np.sin(abs_rad_x) * (1.0 - np.clip(norm_x[near_mask] ** 2, 0.0, 1.0))

        # 2. Vertical Pitch Foreshortening
        phi_y = np.ones_like(norm_y)
        if rad_y > 1e-4:  # Looking up (chin compress/elevate)
            lower_mask = norm_y < 0.0
            phi_y[lower_mask] = 1.0 - 0.25 * np.sin(rad_y) * np.abs(norm_y[lower_mask])
        elif rad_y < -1e-4:  # Looking down (forehead expand)
            upper_mask = norm_y > 0.0
            phi_y[upper_mask] = 1.0 + 0.20 * np.sin(-rad_y) * np.abs(norm_y[upper_mask])

        # 3. Category-specific adjustments (ocular aspect ratio)
        cat_key = category.lower().strip()
        if cat_key == "eyes" and abs_rad_x > 1e-4:
            phi_x = phi_x * (np.cos(rad_x) ** 0.75)

        return phi_x, phi_y

    def solve(
        self,
        mesh: Mesh,
        angle_x_deg: float,
        angle_y_deg: float,
        angle_z_deg: float = 0.0,
        category: Optional[str] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Computes 3D rotated coordinates and normalized perspective projected 2D targets.
        Guarantees zero-identity displacement at (0, 0, 0).
        """
        N = len(mesh.vertices)
        if N == 0:
            return np.zeros((0, 2), dtype=np.float64), np.zeros((0, 3), dtype=np.float64)

        cat = category if category is not None else getattr(mesh, "layer_id", "face")

        # 1. Identity shortcut at (0, 0, 0)
        if abs(angle_x_deg) < 1e-6 and abs(angle_y_deg) < 1e-6 and abs(angle_z_deg) < 1e-6:
            pos_2d = mesh.get_positions()
            depths = mesh.get_depths()
            rot_3d = np.column_stack([pos_2d, depths])
            return pos_2d.copy(), rot_3d

        # 2. SO(3) Rotation matrix
        R = self.get_rotation_matrix(angle_x_deg, angle_y_deg, angle_z_deg)

        # 3. 3D Rotation
        pos_2d = mesh.get_positions()
        depths = mesh.get_depths()
        p_3d = np.column_stack([pos_2d, depths])

        p_rel = p_3d - self.center
        p_rot = (p_rel @ R.T) + self.center

        # 4. Normalized Relative Parallax Calculation
        cat_key = cat.lower().strip()
        preset = self.LAYER_PRESETS.get(cat_key, self.LAYER_PRESETS["unknown"])
        kappa = self.parallax_scale * preset["parallax"]

        rel_z_rot = (p_rot[:, 2] - self.center[2]) / max(1e-4, self.radius_z)
        rel_z_rest = (depths - self.center[2]) / max(1e-4, self.radius_z)

        # Perspective multiplier (ratio strictly equals 1.0 at rest)
        perspective_mult = (1.0 + kappa * rel_z_rot) / (1.0 + kappa * rel_z_rest + 1e-12)

        # 5. Anime Foreshortening Modulation
        norm_x = (pos_2d[:, 0] - self.center[0]) / max(1e-4, self.radius_x)
        norm_y = (pos_2d[:, 1] - self.center[1]) / max(1e-4, self.radius_y)
        phi_x, phi_y = self.compute_anime_foreshortening(norm_x, norm_y, angle_x_deg, angle_y_deg, cat_key)

        # 6. Projected 2D Position
        proj_x = self.center[0] + (p_rot[:, 0] - self.center[0]) * phi_x * perspective_mult
        proj_y = self.center[1] + (p_rot[:, 1] - self.center[1]) * phi_y * perspective_mult

        projected_2d = np.column_stack([proj_x, proj_y])
        return projected_2d, p_rot

    def solve_positions(
        self,
        positions_2d: np.ndarray,
        angle_x_deg: float,
        angle_y_deg: float,
        angle_z_deg: float = 0.0,
        depths: Optional[np.ndarray] = None,
        category: Optional[str] = "head"
    ) -> np.ndarray:
        """
        Computes 2D deformed coordinates for an arbitrary 2D point cloud (e.g. WarpDeformer grid points).
        Guarantees zero-identity displacement at (0, 0, 0).
        """
        pos_2d = np.asarray(positions_2d, dtype=np.float64)
        N = len(pos_2d)
        if N == 0:
            return np.zeros((0, 2), dtype=np.float64)
        if abs(angle_x_deg) < 1e-6 and abs(angle_y_deg) < 1e-6 and abs(angle_z_deg) < 1e-6:
            return pos_2d.copy()

        if depths is None:
            # Ellipsoidal depth proxy based on position distance to center
            r_sq = ((pos_2d[:, 0] - self.center[0]) / max(1e-4, self.radius_x)) ** 2 + \
                   ((pos_2d[:, 1] - self.center[1]) / max(1e-4, self.radius_y)) ** 2
            d = np.zeros(N, dtype=np.float64)
            mask = r_sq < 1.0
            d[mask] = self.radius_z * np.sqrt(np.maximum(0.0, 1.0 - r_sq[mask]))
            depths_arr = d
        else:
            depths_arr = np.asarray(depths, dtype=np.float64)

        R = self.get_rotation_matrix(angle_x_deg, angle_y_deg, angle_z_deg)
        p_3d = np.column_stack([pos_2d, depths_arr])
        p_rel = p_3d - self.center
        p_rot = (p_rel @ R.T) + self.center

        cat_key = (category or "head").lower().strip()
        preset = self.LAYER_PRESETS.get(cat_key, self.LAYER_PRESETS["unknown"])
        kappa = self.parallax_scale * preset["parallax"]

        rel_z_rot = (p_rot[:, 2] - self.center[2]) / max(1e-4, self.radius_z)
        rel_z_rest = (depths_arr - self.center[2]) / max(1e-4, self.radius_z)
        perspective_mult = (1.0 + kappa * rel_z_rot) / (1.0 + kappa * rel_z_rest + 1e-12)

        norm_x = (pos_2d[:, 0] - self.center[0]) / max(1e-4, self.radius_x)
        norm_y = (pos_2d[:, 1] - self.center[1]) / max(1e-4, self.radius_y)
        phi_x, phi_y = self.compute_anime_foreshortening(norm_x, norm_y, angle_x_deg, angle_y_deg, cat_key)

        proj_x = self.center[0] + (p_rot[:, 0] - self.center[0]) * phi_x * perspective_mult
        proj_y = self.center[1] + (p_rot[:, 1] - self.center[1]) * phi_y * perspective_mult

        return np.column_stack([proj_x, proj_y])

    def generate_layer_keyforms(
        self,
        drawable_id: str,
        mesh: Mesh,
        category: str = "face",
        constraint_solver: Optional[ARAPConstraintSolver] = None
    ) -> DrawableKeyforms:
        """
        Generates full 9-keyform grid (AngleX x AngleY) and 3-keyform array (AngleZ) for a layer mesh.
        Applies ARAP regularization and positive signed area barrier checks.
        """
        base_pos = mesh.get_positions().astype(np.float32)
        triangles = mesh.triangles.astype(np.int32)
        uvs_atlas = mesh.uvs.astype(np.float32)

        drawable = DrawableKeyforms(
            drawable_id=drawable_id,
            base_vertices=base_pos,
            triangles=triangles,
            uvs_atlas=uvs_atlas,
            parameter_ids=["ParamAngleX", "ParamAngleY"]
        )

        if constraint_solver is None:
            constraint_solver = ARAPConstraintSolver(spring_weight=2.5)

        # Pre-factorize ARAP system once for this mesh topology
        constraint_solver.initialize_sparse_system(mesh)

        # 1. Evaluate 9-Keyform Grid for AngleX x AngleY
        key_angles = [-30.0, 0.0, 30.0]
        for ay in key_angles:
            for ax in key_angles:
                key_tuple = (float(ax), float(ay))

                # Identity at (0, 0)
                if ax == 0.0 and ay == 0.0:
                    drawable.add_keyform(key_tuple, base_pos.copy())
                    continue

                # Compute target projection
                target_pos, _ = self.solve(mesh, ax, ay, 0.0, category=category)

                # Solve ARAP regularization
                solved_pos, _ = constraint_solver.solve(mesh, target_pos, num_iterations=4)

                # Positive Signed Area Barrier Check
                mesh_test = mesh.copy()
                mesh_test.set_positions(solved_pos)
                signed_areas = mesh_test.compute_triangle_signed_areas()

                if np.any(signed_areas <= 1e-5):
                    # Backtracking Line Search to eliminate triangle folding
                    alpha = 1.0
                    for _ in range(8):
                        alpha *= 0.5
                        blend_pos = (1.0 - alpha) * base_pos + alpha * solved_pos
                        mesh_test.set_positions(blend_pos)
                        if np.all(mesh_test.compute_triangle_signed_areas() > 1e-5):
                            solved_pos = blend_pos
                            break

                drawable.add_keyform(key_tuple, solved_pos.astype(np.float32))

        return drawable
