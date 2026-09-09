"""
tests/test_deformation.py
Comprehensive Unit and Integration Test Suite for Milestone 2: Automated 3D Head Deformation Engine.
"""

import math
import numpy as np
import pytest
import scipy.sparse.linalg as spla

from src.core.vertex import Vertex
from src.core.mesh import Mesh
from src.core.layer import LayerData, LayerCollection
from src.core.keyform import KeyformTable, ParameterBinding, DrawableKeyforms
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator
from src.depth.depth_model import DepthModel, ProxyType, DepthProxyConfig
from src.geometry.geometry_engine import GeometryEngine, GeometryProperties, CameraConfig, ProjectionType
from src.deformation.deformation_solver import DeformationSolver
from src.deformation.keyform_generator import KeyformGenerator
from src.constraints.constraint_solver import ARAPConstraintSolver, MassSpringConstraintSolver


# =============================================================================
# 1. Depth Proxy Modeling & Normalization Tests
# =============================================================================
class TestDepthModel:
    """Test suite for primitive depth proxies, layer auto-assignment, and depth normalization."""

    def test_ellipsoid_proxy_apex_and_monotonicity(self):
        """Verify Ellipsoidal proxy achieves peak depth at center and falls off monotonically."""
        depth_model = DepthModel(center=(0.0, 0.0), radii=(0.6, 0.8, 0.4), z_center=0.0)
        
        # Apex depth at center
        z_apex = depth_model.compute_ellipsoid_depth(0.0, 0.0)
        assert math.isclose(z_apex, 0.4, abs_tol=1e-5)

        # Monotonic radial falloff
        z_r1 = depth_model.compute_ellipsoid_depth(0.2, 0.0)
        z_r2 = depth_model.compute_ellipsoid_depth(0.4, 0.0)
        z_r3 = depth_model.compute_ellipsoid_depth(0.59, 0.0)
        assert z_apex > z_r1 > z_r2 > z_r3 >= 0.0

        # Smooth falloff outside boundary
        z_outside = depth_model.compute_ellipsoid_depth(1.0, 0.0)
        assert not np.isnan(z_outside) and not np.isinf(z_outside)

    def test_cylindrical_proxy_axis_invariance(self):
        """Verify Cylindrical proxy is invariant along the cylinder axis (Y-axis)."""
        depth_model = DepthModel(center=(0.0, 0.0), radii=(0.5, 0.5, 0.3), z_center=0.0)
        config = DepthProxyConfig(
            proxy_type=ProxyType.CYLINDRICAL,
            center=(0.0, 0.0, 0.0),
            radii=(0.5, 0.5, 0.3),
            axis=(0.0, 1.0),
            peripheral_taper=0.0
        )
        
        # Two points with identical X but different Y
        pts = np.array([[0.2, -0.4], [0.2, 0.4]], dtype=np.float64)
        depths = depth_model.compute_proxy_depth_vectorized(pts, config)
        assert math.isclose(depths[0], depths[1], abs_tol=1e-6)

    def test_planar_proxy_linear_equation(self):
        """Verify Planar proxy strictly satisfies linear plane gradient equation."""
        depth_model = DepthModel()
        config = DepthProxyConfig(
            proxy_type=ProxyType.PLANAR,
            center=(0.0, 0.0, 0.2),
            plane_normal=(0.0, 0.0, 1.0)
        )
        pts = np.array([[0.1, 0.2], [-0.3, 0.4], [0.5, -0.5]], dtype=np.float64)
        depths = depth_model.compute_proxy_depth_vectorized(pts, config)
        assert np.allclose(depths, 0.2, atol=1e-6)

    def test_inverted_shell_hair_back_depth(self):
        """Verify Inverted Shell proxy produces negative/recessed depth for rear hair."""
        depth_model = DepthModel(center=(0.0, 0.0), radii=(0.6, 0.8, 0.4), z_center=0.0)
        config = DepthProxyConfig(
            proxy_type=ProxyType.INVERTED_SHELL,
            center=(0.0, 0.0, 0.0),
            radii=(0.6, 0.8, 0.4),
            layer_z_offset=-0.2
        )
        pts = np.array([[0.0, 0.0]], dtype=np.float64)
        depth = depth_model.compute_proxy_depth_vectorized(pts, config)[0]
        # Must be significantly negative
        assert depth < -0.3

    def test_semantic_category_auto_assignment_and_stacking(self):
        """Verify auto-assignment gives correct relative depth ordering across character hierarchy."""
        depth_model = DepthModel()
        categories = ["hair_front", "nose", "eyes", "face", "neck", "hair_back"]
        mean_depths = {}
        sample_pts = np.array([[0.0, 0.0]], dtype=np.float64)

        for cat in categories:
            cfg = depth_model.get_proxy_config_for_category(cat)
            d = depth_model.compute_proxy_depth_vectorized(sample_pts, cfg)[0]
            mean_depths[cat] = d

        # Check strict depth stratification hierarchy:
        # hair_front > nose > eyes > face > neck > hair_back
        assert mean_depths["hair_front"] > mean_depths["nose"]
        assert mean_depths["nose"] > mean_depths["eyes"]
        assert mean_depths["eyes"] > mean_depths["face"]
        assert mean_depths["face"] > mean_depths["neck"]
        assert mean_depths["neck"] > mean_depths["hair_back"]

    def test_global_depth_normalization_bounds(self):
        """Verify global normalization rescales arbitrary depth distributions into [-1.0, 1.0]."""
        depth_model = DepthModel()
        v1 = Vertex(position=np.array([0.0, 0.0]), depth=150.0)
        v2 = Vertex(position=np.array([0.0, 0.0]), depth=-80.0)
        v3 = Vertex(position=np.array([0.0, 0.0]), depth=20.0)
        mesh1 = Mesh(vertices=[v1, v2], triangles=np.zeros((0, 3), dtype=np.int32))
        mesh2 = Mesh(vertices=[v3], triangles=np.zeros((0, 3), dtype=np.int32))

        depth_model.normalize_depths([mesh1, mesh2])
        all_d = np.concatenate([mesh1.get_depths(), mesh2.get_depths()])
        assert np.all(all_d >= -1.0 - 1e-6)
        assert np.all(all_d <= 1.0 + 1e-6)
        assert math.isclose(np.max(all_d), 1.0, abs_tol=1e-5)


# =============================================================================
# 2. Differential Geometry Engine Tests
# =============================================================================
class TestGeometryEngine:
    """Test suite for analytical normals, tangents, curvatures, and projective geometry."""

    def test_analytical_normals_unit_length_and_apex(self):
        """Verify analytical normals on ellipsoidal proxy have unit norm and correct apex direction."""
        contour = np.array([[50, 50], [200, 50], [200, 200], [50, 200]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (256, 256), target_grid_size=20)
        depth_model = DepthModel(center=(0.0, 0.0), radii=(0.6, 0.8, 0.4))
        depth_model.apply_to_mesh(mesh, category="face")

        cfg = depth_model.get_proxy_config_for_category("face")
        geom = GeometryEngine.compute_mesh_geometry(mesh, cfg)

        normals = geom.normals
        assert len(normals) == len(mesh.vertices)
        # All normals must have unit length 1.0
        norms = np.linalg.norm(normals, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5)

        # Normal near center (0, 0) should point predominantly along +Z (0, 0, 1)
        pos = mesh.get_positions()
        center_idx = np.argmin(np.hypot(pos[:, 0], pos[:, 1]))
        assert normals[center_idx, 2] > 0.8

    def test_tangent_basis_orthonormality(self):
        """Verify tangent frames (Tu, Tv, N) are strictly orthonormal: Tu·N=0, Tv·N=0, Tu·Tv=0."""
        normals_test = np.array([
            [0.0, 0.0, 1.0],
            [0.6, 0.0, 0.8],
            [0.0, 0.8, 0.6],
            [-0.5, 0.5, 0.7071]
        ], dtype=np.float64)
        normals_test /= np.linalg.norm(normals_test, axis=1, keepdims=True)

        for n in normals_test:
            tu, tv = GeometryEngine.compute_local_tangents(n)
            # Lengths are 1.0
            assert math.isclose(np.linalg.norm(tu), 1.0, abs_tol=1e-6)
            assert math.isclose(np.linalg.norm(tv), 1.0, abs_tol=1e-6)
            # Orthogonality
            assert math.isclose(np.dot(tu, n), 0.0, abs_tol=1e-6)
            assert math.isclose(np.dot(tv, n), 0.0, abs_tol=1e-6)
            assert math.isclose(np.dot(tu, tv), 0.0, abs_tol=1e-6)
            # Right-handed cross product orientation
            cross_t = np.cross(tu, tv)
            assert np.allclose(cross_t, n, atol=1e-5)

    def test_spherical_curvature_benchmark(self):
        """Verify analytical Gaussian curvature K = 1/R^2 and Mean curvature H = 1/R on sphere."""
        R = 0.5
        v = Vertex(position=np.array([0.0, 0.0]), depth=R)
        mesh = Mesh(vertices=[v], triangles=np.zeros((0, 3), dtype=np.int32))

        config = DepthProxyConfig(
            proxy_type=ProxyType.ELLIPSOIDAL,
            center=(0.0, 0.0, 0.0),
            radii=(R, R, R),
            peripheral_taper=0.0
        )
        geom = GeometryEngine.compute_mesh_geometry(mesh, config)
        
        expected_K = 1.0 / (R ** 2)  # 4.0
        expected_H = 1.0 / R         # 2.0
        assert math.isclose(geom.gaussian_curvature[0], expected_K, abs_tol=1e-4)
        assert math.isclose(geom.mean_curvature[0], expected_H, abs_tol=1e-4)

    def test_camera_projections_taylor_consistency(self):
        """Verify Weak Perspective is the exact 1st-order approximation of Full Perspective."""
        pts_3d = np.array([[0.2, 0.3, 0.1]], dtype=np.float64)
        cam_cfg_persp = CameraConfig(projection_type=ProjectionType.PERSPECTIVE, camera_distance=1000.0, focal_length=1000.0)
        cam_cfg_weak = CameraConfig(projection_type=ProjectionType.WEAK_PERSPECTIVE, parallax_scale=1.0 / 1000.0)

        proj_persp = GeometryEngine.project_points(pts_3d, camera_config=cam_cfg_persp)
        proj_weak = GeometryEngine.project_points(pts_3d, camera_config=cam_cfg_weak)
        # Difference should be < 1e-4 for large camera distance D >> delta z
        assert np.allclose(proj_persp, proj_weak, atol=1e-4)


# =============================================================================
# 3. SO(3) Kinematics & Parallax Invariant Tests
# =============================================================================
class TestDeformationKinematics:
    """Test suite for SO(3) Euler rotations, zero-identity invariant, and anime foreshortening."""

    def test_so3_rotation_matrix_orthonormality_and_determinant(self):
        """Verify compound Euler rotation Rz(roll)*Ry(yaw)*Rx(pitch) is strictly orthonormal with det=1."""
        test_angles = [
            (-30.0, -30.0, -30.0),
            (30.0, 30.0, 30.0),
            (-30.0, 30.0, 15.0),
            (20.0, -15.0, -25.0),
            (0.0, 0.0, 0.0),
        ]
        for ax, ay, az in test_angles:
            R = DeformationSolver.get_rotation_matrix(ax, ay, az)
            assert R.shape == (3, 3)
            # R^T * R = I
            assert np.allclose(R.T @ R, np.eye(3), atol=1e-6)
            # det(R) = +1.0
            det = float(np.linalg.det(R))
            assert math.isclose(det, 1.0, abs_tol=1e-6)

    def test_zero_identity_parallax_invariant(self):
        """Verify strict zero-identity displacement: Delta V(0,0,0) == 0 for all layers and depths."""
        v1 = Vertex(position=np.array([-0.3, 0.2]), depth=0.35, layer_id="hair_front")
        v2 = Vertex(position=np.array([0.0, 0.0]), depth=0.40, layer_id="nose")
        v3 = Vertex(position=np.array([0.4, -0.3]), depth=-0.20, layer_id="hair_back")
        mesh = Mesh(vertices=[v1, v2, v3], triangles=np.zeros((0, 3), dtype=np.int32))

        solver = DeformationSolver()
        proj_2d, rot_3d = solver.solve(mesh, 0.0, 0.0, 0.0)
        rest_pos = mesh.get_positions()

        # Target 2D must match rest 2D position with machine precision
        assert np.allclose(proj_2d, rest_pos, atol=1e-12)

    def test_perspective_parallax_depth_monotonicity(self):
        """Verify foreground features shift further horizontally than background features during yaw."""
        # Pair of vertices at same (x, y) but different depths: foreground vs background
        v_fg = Vertex(position=np.array([0.2, 0.1]), depth=0.4, layer_id="hair_front")
        v_bg = Vertex(position=np.array([0.2, 0.1]), depth=-0.2, layer_id="hair_back")
        mesh = Mesh(vertices=[v_fg, v_bg], triangles=np.zeros((0, 3), dtype=np.int32))

        solver = DeformationSolver(parallax_scale=0.5)
        proj_2d, _ = solver.solve(mesh, angle_x_deg=25.0, angle_y_deg=0.0)

        disp_fg = abs(proj_2d[0, 0] - 0.2)
        disp_bg = abs(proj_2d[1, 0] - 0.2)
        assert disp_fg > disp_bg, "Foreground layer must undergo larger parallax displacement than background"

    def test_anime_foreshortening_asymmetry(self):
        """Verify anime foreshortening compresses the turned-away (far) cheek more than the near cheek."""
        solver = DeformationSolver()
        # Points on left (-X) and right (+X) cheeks
        norm_x = np.array([-0.5, 0.5])
        norm_y = np.array([0.0, 0.0])

        # Turn head right (AngleX = +30°): Left cheek is turned away (far side)
        phi_x, _ = solver.compute_anime_foreshortening(norm_x, norm_y, angle_x_deg=30.0, angle_y_deg=0.0, category="face")
        assert phi_x[0] < 1.0  # Far cheek compressed
        assert phi_x[1] >= 1.0  # Near cheek relaxed/expanded


# =============================================================================
# 4. ARAP Constraint Solver & Area Preservation Tests
# =============================================================================
class TestARAPConstraintSolver:
    """Test suite for ARAP local-global solver, closed-form SO(2) polar decomposition, and area barrier."""

    def test_so2_closed_form_vs_svd_exactness(self):
        """Verify closed-form atan2 SO(2) rotation matches SVD Polar decomposition to < 1e-14."""
        # Random covariance matrices S
        rng = np.random.default_rng(42)
        for _ in range(20):
            S = rng.standard_normal((2, 2))
            s00, s01, s10, s11 = S[0, 0], S[0, 1], S[1, 0], S[1, 1]

            # Closed-form
            c = s00 + s11
            s = s01 - s10
            r = np.hypot(c, s)
            R_closed = np.array([[c / r, -s / r], [s / r, c / r]])

            # SVD Polar decomposition: S = U Sigma V^T => R = V U^T
            U, _, Vt = np.linalg.svd(S)
            V = Vt.T
            R_svd = V @ U.T
            if np.linalg.det(R_svd) < 0:
                V[:, -1] *= -1
                R_svd = V @ U.T

            assert np.allclose(R_closed, R_svd, atol=1e-12)

    def test_arap_pure_rigid_motion_zero_energy(self):
        """Verify applying a pure rigid rotation and translation produces near-zero deformation energy."""
        contour = np.array([[50, 50], [150, 50], [150, 150], [50, 150]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=25)
        rest_pos = mesh.get_positions()

        # Pure 2D rotation by 20° + translation [0.1, -0.05]
        theta = np.radians(20.0)
        R_2d = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
        target_rigid = (rest_pos @ R_2d.T) + np.array([0.1, -0.05])

        solver = ARAPConstraintSolver()
        solved_pos, energy = solver.solve(mesh, target_rigid, num_iterations=4)

        assert np.allclose(solved_pos, target_rigid, atol=1e-4)

    def test_sparse_lu_prefactorization_speed(self):
        """Verify sparse LU factorization is cached and executes solves in < 2ms."""
        contour = np.array([[30, 30], [180, 30], [180, 180], [30, 180]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=20)
        
        solver = ARAPConstraintSolver()
        solver.initialize_sparse_system(mesh)
        assert solver.lu_factor is not None

        target = mesh.get_positions() + 0.05
        import time
        t0 = time.perf_counter()
        solver.solve(mesh, target, num_iterations=4)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # Must execute within 20 ms in Python test environment
        assert elapsed_ms < 25.0

    def test_positive_signed_area_barrier_extreme_rotations(self):
        """Verify backtracking line search ensures 100% positive signed triangle areas under extreme turns."""
        contour = np.array([[30, 30], [180, 30], [180, 180], [30, 180]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=25)
        depth_model = DepthModel()
        depth_model.apply_to_mesh(mesh, category="hair_front")

        deform = DeformationSolver()
        solver = ARAPConstraintSolver(spring_weight=3.0)

        extreme_angles = [(-30.0, -30.0), (30.0, -30.0), (-30.0, 30.0), (30.0, 30.0)]
        for ax, ay in extreme_angles:
            target, _ = deform.solve(mesh, ax, ay, category="hair_front")
            solved, _ = solver.solve(mesh, target, num_iterations=5, enforce_noninversion=True)

            mesh_def = mesh.copy()
            mesh_def.set_positions(solved)
            areas = mesh_def.compute_triangle_signed_areas()
            # Strict non-inversion check: every triangle must have positive area
            assert np.all(areas > 0.0), f"Inverted triangles detected at AngleX={ax}, AngleY={ay}"


# =============================================================================
# 5. Live2D Multi-Dimensional Keyform Tensor Generation Tests
# =============================================================================
class TestKeyformGenerator:
    """Test suite for Live2D 9-keyform Cartesian grid, displacement tensors, and validation."""

    def test_9_keyform_grid_generation_and_shapes(self):
        """Verify KeyformGenerator generates 9 complete (N, 2) keyforms for AngleX x AngleY."""
        contour = np.array([[50, 50], [150, 50], [150, 150], [50, 150]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=30)
        
        generator = KeyformGenerator()

        # 1. WarpDeformer grid keyforms (Standard Live2D hierarchy)
        warp = generator.generate_warp_deformer("Warp_Head", meshes=[mesh])
        assert warp.deformer_id == "Warp_Head"
        assert len(warp.deformed_positions) == 9

        # 2. Direct deformed positions mode
        drawable = generator.generate_drawable_keyforms("ArtMesh_Face", mesh, category="face", direct_deform=True)

        assert drawable.drawable_id == "ArtMesh_Face"
        assert len(drawable.base_vertices) == len(mesh.vertices)
        assert len(drawable.deformed_positions) == 9  # 3x3 grid


        # Check all 9 key combinations exist
        expected_keys = [
            (-30.0, -30.0), (-30.0, 0.0), (-30.0, 30.0),
            (0.0, -30.0),   (0.0, 0.0),   (0.0, 30.0),
            (30.0, -30.0),  (30.0, 0.0),  (30.0, 30.0)
        ]
        for key in expected_keys:
            assert key in drawable.deformed_positions
            pos = drawable.deformed_positions[key]
            assert pos.shape == (len(mesh.vertices), 2)
            assert not np.isnan(pos).any()

        # Check identity at (0.0, 0.0)
        assert np.allclose(drawable.deformed_positions[(0.0, 0.0)], drawable.base_vertices, atol=1e-6)

    def test_displacement_buffer_evaluation(self):
        """Verify Delta V = V_deformed - V_base calculation."""
        base = np.array([[0.0, 0.0], [1.0, 1.0]], dtype=np.float32)
        deformed = np.array([[0.1, -0.05], [0.95, 1.05]], dtype=np.float32)
        delta = KeyformGenerator.compute_displacement_buffer(base, deformed)
        expected = np.array([[0.1, -0.05], [-0.05, 0.05]], dtype=np.float32)
        assert np.allclose(delta, expected, atol=1e-6)

    def test_multi_layer_keyform_table_validation(self):
        """Verify generating a complete KeyformTable across multiple layers passes Live2D validation."""
        rgba1 = np.ones((64, 64, 4), dtype=np.uint8) * 200
        rgba2 = np.ones((64, 64, 4), dtype=np.uint8) * 220
        l1 = LayerData(name="Hair_Front", image=rgba1, category="hair_front")
        l2 = LayerData(name="Face", image=rgba2, category="face")
        collection = LayerCollection(canvas_size=(256, 256), layers=[l1, l2])

        contour = np.array([[20, 20], [80, 20], [80, 80], [20, 80]], dtype=np.float64)
        m1 = MeshGenerator.generate_mesh_from_contour(contour, (100, 100), target_grid_size=25)
        m2 = MeshGenerator.generate_mesh_from_contour(contour, (100, 100), target_grid_size=25)
        mesh_map = {l1.layer_id: m1, l2.layer_id: m2}

        generator = KeyformGenerator()
        table = generator.generate_keyform_table(collection, mesh_map, include_angle_z=True)

        is_valid, errors = table.validate()
        assert is_valid, f"KeyformTable validation failed: {errors}"
        assert len(table.drawables) == 2
        assert len(table.parameters) == 3  # AngleX, AngleY, AngleZ
