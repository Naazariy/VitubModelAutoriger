"""
src/geometry/geometry_engine.py
Differential Geometry Engine: Surface Normals, Tangents, Curvatures, and Projective Geometry.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Tuple, Optional, List, Union
import numpy as np

from src.core.mesh import Mesh
from src.depth.depth_model import DepthProxyConfig, ProxyType


class ProjectionType(Enum):
    """Camera and perspective projection models."""
    WEAK_PERSPECTIVE = "weak_perspective"
    PERSPECTIVE = "perspective"
    ORTHOGRAPHIC = "orthographic"
    ANIME_HYBRID = "anime_hybrid"


@dataclass
class GeometryProperties:
    """Differential geometric surface properties for a 2.5D/3D mesh."""
    normals: np.ndarray                            # (N, 3) float64 unit normal vectors
    tangents_u: np.ndarray                         # (N, 3) float64 orthonormal tangents (X/U)
    tangents_v: np.ndarray                         # (N, 3) float64 orthonormal bitangents (Y/V)
    mean_curvature: np.ndarray                     # (N,) float64 mean surface curvature H
    gaussian_curvature: np.ndarray                 # (N,) float64 Gaussian curvature K
    tbn_matrices: Optional[np.ndarray] = None      # (N, 3, 3) float64 TBN transformation matrices


@dataclass
class CameraConfig:
    """Camera and perspective projection parameters."""
    projection_type: ProjectionType = ProjectionType.ANIME_HYBRID
    camera_distance: float = 1000.0                # Virtual pinhole camera distance D
    focal_length: float = 1000.0                   # Virtual focal length f
    parallax_scale: float = 0.45                   # Parallax scale coefficient kappa
    fov_degrees: float = 45.0                      # Camera field of view


class GeometryEngine:
    """
    Computes local differential geometric surface metrics and projective transformations:
    - 3D analytical and discrete unit normal vectors N(x, y, z)
    - Orthonormal tangent bases (Tu, Tv) and UV-aligned TBN matrices
    - First and Second Fundamental Forms, Mean Curvature (H), Gaussian Curvature (K)
    - Weak Perspective, Full Pinhole Perspective, and Anime Foreshortening projections
    """

    @staticmethod
    def compute_mesh_geometry(
        mesh: Mesh,
        proxy_config: Optional[DepthProxyConfig] = None
    ) -> GeometryProperties:
        """
        Computes analytical surface normals, orthonormal tangent frames,
        and curvature fields for a given mesh and optional depth proxy configuration.
        """
        positions_2d = mesh.get_positions()
        depths = mesh.get_depths()
        N = len(positions_2d)

        if N == 0:
            return GeometryProperties(
                normals=np.zeros((0, 3), dtype=np.float64),
                tangents_u=np.zeros((0, 3), dtype=np.float64),
                tangents_v=np.zeros((0, 3), dtype=np.float64),
                mean_curvature=np.zeros(0, dtype=np.float64),
                gaussian_curvature=np.zeros(0, dtype=np.float64)
            )

        pos_3d = np.column_stack([positions_2d, depths])

        # 1. Compute 3D unit normal vectors
        normals = np.zeros((N, 3), dtype=np.float64)
        mean_h = np.zeros(N, dtype=np.float64)
        gauss_k = np.zeros(N, dtype=np.float64)

        if proxy_config is not None:
            ptype = proxy_config.proxy_type
            if isinstance(ptype, str):
                ptype = ProxyType(ptype)

            xc, yc, zc = proxy_config.center
            rx = max(1e-5, proxy_config.radii[0])
            ry = max(1e-5, proxy_config.radii[1])
            rz = max(1e-5, proxy_config.radii[2])

            dx = pos_3d[:, 0] - xc
            dy = pos_3d[:, 1] - yc
            dz = pos_3d[:, 2] - zc

            if ptype in (ProxyType.ELLIPSOIDAL, ProxyType.ELLIPSOID, ProxyType.CONICAL_BUMP, ProxyType.CONE_BUMP, ProxyType.CONFORMING):
                # Implicit gradient: grad F = [2*dx/rx^2, 2*dy/ry^2, 2*dz/rz^2]
                nx = dx / (rx * rx)
                ny = dy / (ry * ry)
                nz = np.maximum(dz / (rz * rz), 1e-4)

                norms = np.sqrt(nx * nx + ny * ny + nz * nz)
                norms_safe = np.where(norms > 1e-12, norms, 1.0)
                normals = np.column_stack([nx / norms_safe, ny / norms_safe, nz / norms_safe])

                # Analytical Ellipsoid Curvatures
                nu = np.sqrt((dx ** 2) / (rx ** 4) + (dy ** 2) / (ry ** 4) + (dz ** 2) / (rz ** 4))
                nu_safe = np.where(nu > 1e-12, nu, 1.0)
                gauss_k = 1.0 / ((rx * ry * rz * (nu_safe ** 2)) ** 2)
                mean_h = (nu_safe ** 2 * (1.0 / rx ** 2 + 1.0 / ry ** 2 + 1.0 / rz ** 2) - (
                    dx ** 2 / rx ** 6 + dy ** 2 / ry ** 6 + dz ** 2 / rz ** 6
                )) / (2.0 * (nu_safe ** 3))

            elif ptype in (ProxyType.CYLINDRICAL, ProxyType.CYLINDER):
                axis_len = np.hypot(proxy_config.axis[0], proxy_config.axis[1])
                adx = proxy_config.axis[0] / axis_len if axis_len > 1e-6 else 0.0
                ady = proxy_config.axis[1] / axis_len if axis_len > 1e-6 else 1.0

                p_perp = -(pos_3d[:, 0] - xc) * ady + (pos_3d[:, 1] - yc) * adx
                nx = -ady * (p_perp / (rx * rx))
                ny = adx * (p_perp / (rx * rx))
                nz = np.maximum(dz / (rz * rz), 1e-4)

                norms = np.sqrt(nx * nx + ny * ny + nz * nz)
                norms_safe = np.where(norms > 1e-12, norms, 1.0)
                normals = np.column_stack([nx / norms_safe, ny / norms_safe, nz / norms_safe])
                gauss_k = np.zeros(N, dtype=np.float64)  # Cylinders are developable (K = 0)
                mean_h = 0.5 / rx

            elif ptype in (ProxyType.PLANAR, ProxyType.PLANE):
                pn = np.array(proxy_config.plane_normal, dtype=np.float64)
                pn_norm = np.linalg.norm(pn)
                unit_pn = pn / pn_norm if pn_norm > 1e-12 else np.array([0.0, 0.0, 1.0])
                normals = np.tile(unit_pn, (N, 1))
                gauss_k = np.zeros(N, dtype=np.float64)
                mean_h = np.zeros(N, dtype=np.float64)

            elif ptype == ProxyType.INVERTED_SHELL:
                nx = -(dx / (rx * rx))
                ny = -(dy / (ry * ry))
                nz = np.maximum(-dz / (rz * rz), 1e-4)
                norms = np.sqrt(nx * nx + ny * ny + nz * nz)
                norms_safe = np.where(norms > 1e-12, norms, 1.0)
                normals = np.column_stack([nx / norms_safe, ny / norms_safe, nz / norms_safe])
                mean_h = 0.5 * (1.0 / rx + 1.0 / ry)
                gauss_k = 1.0 / (rx * ry)

            else:
                normals[:, 2] = 1.0

        else:
            # Discrete Mesh Normal Accumulation (Angle-weighted / Area-weighted)
            if len(mesh.triangles) > 0:
                p0 = pos_3d[mesh.triangles[:, 0]]
                p1 = pos_3d[mesh.triangles[:, 1]]
                p2 = pos_3d[mesh.triangles[:, 2]]

                e1 = p1 - p0
                e2 = p2 - p0
                tri_normals = np.cross(e1, e2)
                tri_norms = np.linalg.norm(tri_normals, axis=1, keepdims=True)
                tri_norms_safe = np.where(tri_norms > 1e-12, tri_norms, 1.0)
                unit_tri_normals = tri_normals / tri_norms_safe

                for t_idx, (i, j, k) in enumerate(mesh.triangles):
                    normals[i] += unit_tri_normals[t_idx]
                    normals[j] += unit_tri_normals[t_idx]
                    normals[k] += unit_tri_normals[t_idx]

                v_norms = np.linalg.norm(normals, axis=1, keepdims=True)
                v_norms_safe = np.where(v_norms > 1e-12, v_norms, 1.0)
                normals = normals / v_norms_safe
            else:
                normals[:, 2] = 1.0

            # Discrete normal gradient across edges for curvature estimation
            if len(mesh.edges) > 0:
                edge_counts = np.zeros(N, dtype=np.float64)
                for i, j in mesh.edges:
                    dp = np.linalg.norm(pos_3d[i] - pos_3d[j])
                    if dp > 1e-6:
                        dn = np.linalg.norm(normals[i] - normals[j])
                        kappa = dn / dp
                        mean_h[i] += kappa
                        mean_h[j] += kappa
                        edge_counts[i] += 1
                        edge_counts[j] += 1
                nonzero = edge_counts > 0
                mean_h[nonzero] /= edge_counts[nonzero]

        # 2. Orthonormal Tangent Bases (Tu, Tv)
        # Select initial reference vector not parallel to normal
        ref_x = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        ref_y = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        
        is_parallel_x = np.abs(normals[:, 0]) > 0.9
        init_tangents = np.where(is_parallel_x[:, np.newaxis], ref_y, ref_x)

        # Gram-Schmidt: Tu = init_tangent - (init_tangent . N) * N
        dot_init_n = np.sum(init_tangents * normals, axis=1, keepdims=True)
        tangents_u = init_tangents - dot_init_n * normals
        tu_norms = np.linalg.norm(tangents_u, axis=1, keepdims=True)
        tu_norms_safe = np.where(tu_norms > 1e-12, tu_norms, 1.0)
        tangents_u = tangents_u / tu_norms_safe

        # Tv = N x Tu
        tangents_v = np.cross(normals, tangents_u)
        tv_norms = np.linalg.norm(tangents_v, axis=1, keepdims=True)
        tv_norms_safe = np.where(tv_norms > 1e-12, tv_norms, 1.0)
        tangents_v = tangents_v / tv_norms_safe

        # 3. Assemble (N, 3, 3) TBN matrices
        tbn_matrices = np.stack([tangents_u, tangents_v, normals], axis=-1)

        # Update mesh normals in-place
        mesh.set_normals(normals)

        return GeometryProperties(
            normals=normals,
            tangents_u=tangents_u,
            tangents_v=tangents_v,
            mean_curvature=mean_h,
            gaussian_curvature=gauss_k,
            tbn_matrices=tbn_matrices
        )

    @staticmethod
    def update_mesh_normals_and_geometry(
        mesh: Mesh,
        depth_model_params: Tuple[Tuple[float, float], Tuple[float, float, float]]
    ):
        """
        Calculates 3D surface unit normals and geometry for each vertex in mesh.
        Maintains backward compatibility with M1/M2 tests.
        """
        (cx, cy), (rx, ry, rz) = depth_model_params
        config = DepthProxyConfig(
            proxy_type=ProxyType.ELLIPSOIDAL,
            center=(cx, cy, 0.0),
            radii=(rx, ry, rz),
            peripheral_taper=0.0
        )
        geom = GeometryEngine.compute_mesh_geometry(mesh, config)
        mesh.set_normals(geom.normals)

    @staticmethod
    def compute_local_tangents(normal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Computes orthonormal tangent basis (Tx, Ty) for a given unit normal.
        """
        norm = np.asarray(normal, dtype=np.float64)
        norm_len = np.linalg.norm(norm)
        n = norm / norm_len if norm_len > 1e-12 else np.array([0.0, 0.0, 1.0])

        nx, ny, nz = n[0], n[1], n[2]
        if abs(nz) < 0.999:
            tx = np.array([nz, 0.0, -nx], dtype=np.float64)
        else:
            tx = np.array([1.0, 0.0, 0.0], dtype=np.float64)

        tx /= np.linalg.norm(tx)
        ty = np.cross(n, tx)
        ty /= np.linalg.norm(ty)
        return tx, ty

    @staticmethod
    def compute_surface_curvatures(mesh: Mesh) -> np.ndarray:
        """
        Estimates local mean curvature H at vertices based on normal gradients.
        Returns array of shape (N,) with curvature magnitudes.
        """
        geom = GeometryEngine.compute_mesh_geometry(mesh)
        return geom.mean_curvature

    @staticmethod
    def compute_fundamental_forms(
        f_x: np.ndarray,
        f_y: np.ndarray,
        f_xx: np.ndarray,
        f_xy: np.ndarray,
        f_yy: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Computes First Fundamental Form (E, F, G) and Second Fundamental Form (e, f, g)
        for surface z = f(x, y).
        """
        E = 1.0 + f_x ** 2
        F = f_x * f_y
        G = 1.0 + f_y ** 2
        W = np.sqrt(1.0 + f_x ** 2 + f_y ** 2)
        W_safe = np.where(W > 1e-12, W, 1.0)

        e = f_xx / W_safe
        f_val = f_xy / W_safe
        g = f_yy / W_safe
        return E, F, G, e, f_val, g

    @staticmethod
    def project_points(
        points_3d: np.ndarray,
        center: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        camera_config: Optional[CameraConfig] = None
    ) -> np.ndarray:
        """
        Projects 3D points (N, 3) to 2D canvas coordinates (N, 2) using specified camera config.
        """
        if len(points_3d) == 0:
            return np.zeros((0, 2), dtype=np.float64)

        cfg = camera_config if camera_config is not None else CameraConfig()
        xc, yc, zc = center
        px = points_3d[:, 0]
        py = points_3d[:, 1]
        pz = points_3d[:, 2]

        ptype = cfg.projection_type

        if ptype == ProjectionType.ORTHOGRAPHIC:
            return np.column_stack([px, py])

        elif ptype == ProjectionType.WEAK_PERSPECTIVE:
            # Scaled orthographic linear parallax
            rel_z = pz - zc
            scale = 1.0 + cfg.parallax_scale * rel_z
            proj_x = xc + (px - xc) * scale
            proj_y = yc + (py - yc) * scale
            return np.column_stack([proj_x, proj_y])

        elif ptype == ProjectionType.PERSPECTIVE:
            # Full pinhole camera projection: f / (D - Delta z)
            D = cfg.camera_distance
            f = cfg.focal_length
            rel_z = pz - zc
            denom = np.maximum(1e-3, D - rel_z)
            scale = f / denom
            proj_x = xc + (px - xc) * scale
            proj_y = yc + (py - yc) * scale
            return np.column_stack([proj_x, proj_y])

        else:  # ANIME_HYBRID
            rel_z = pz - zc
            scale = 1.0 + cfg.parallax_scale * rel_z
            proj_x = xc + (px - xc) * scale
            proj_y = yc + (py - yc) * scale
            return np.column_stack([proj_x, proj_y])
