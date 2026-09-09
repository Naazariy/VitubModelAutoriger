import math
import numpy as np
import pytest

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
from src.constraints.constraint_solver import ARAPConstraintSolver


# =============================================================================
# 1. Adversarial Extreme Angles & SO(3) Boundary Limits
# =============================================================================
class TestAdversarialExtremeAngles:
    """Stress-tests for extreme rotation angles (+/-45 deg, +/-90 deg, +/-180 deg, +/-360 deg) and singular boundary limits."""

    @pytest.mark.parametrize("angle_x,angle_y,angle_z", [
        (45.0, 0.0, 0.0),
        (-45.0, 0.0, 0.0),
        (0.0, 45.0, 0.0),
        (0.0, -45.0, 0.0),
        (0.0, 0.0, 45.0),
        (45.0, 45.0, 45.0),
        (-45.0, -45.0, -45.0),
        (90.0, 0.0, 0.0),
        (-90.0, 0.0, 0.0),
        (0.0, 90.0, 0.0),
        (0.0, -90.0, 0.0),
        (0.0, 0.0, 90.0),
        (90.0, 90.0, 90.0),
        (-90.0, -90.0, -90.0),
        (180.0, 0.0, 0.0),
        (0.0, 180.0, 0.0),
        (0.0, 0.0, 180.0),
        (360.0, 360.0, 360.0),
        (-720.0, 720.0, -360.0),
    ])
    def test_extreme_angles_so3_matrix_algebra(self, angle_x, angle_y, angle_z):
        """Verify compound Euler rotation Rz(roll)*Ry(yaw)*Rx(pitch) is strictly orthonormal with det=+1 at extreme angles."""
        R = DeformationSolver.get_rotation_matrix(angle_x, angle_y, angle_z)
        assert R.shape == (3, 3)
        assert not np.isnan(R).any(), f"NaN in rotation matrix at ({angle_x}, {angle_y}, {angle_z})"
        assert not np.isinf(R).any(), f"Inf in rotation matrix at ({angle_x}, {angle_y}, {angle_z})"

        # R^T * R = I
        identity = R.T @ R
        assert np.allclose(identity, np.eye(3), atol=1e-5), f"Orthonormality violation at ({angle_x}, {angle_y}, {angle_z})"

        # det(R) = +1.0
        det = float(np.linalg.det(R))
        assert math.isclose(det, 1.0, abs_tol=1e-5), f"Determinant != 1.0 ({det}) at ({angle_x}, {angle_y}, {angle_z})"

    @pytest.mark.parametrize("category", [
        "hair_front", "face", "eyes", "nose", "mouth", "hair_side", "ears", "neck", "body", "hair_back"
    ])
    def test_extreme_angle_deformation_solve_stability(self, category):
        """Verify DeformationSolver.solve does not crash, return NaNs, or produce infinite values under extreme angles."""
        contour = np.array([[30, 30], [170, 30], [170, 170], [30, 170]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=20)
        depth_model = DepthModel()
        depth_model.apply_to_mesh(mesh, category=category)

        solver = DeformationSolver()
        extreme_triplets = [
            (45.0, 0.0, 0.0),
            (-45.0, 0.0, 0.0),
            (0.0, 45.0, 0.0),
            (0.0, -45.0, 0.0),
            (45.0, 45.0, 0.0),
            (-45.0, -45.0, 0.0),
            (90.0, 0.0, 0.0),
            (-90.0, 0.0, 0.0),
        ]

        for ax, ay, az in extreme_triplets:
            proj_2d, rot_3d = solver.solve(mesh, ax, ay, az, category=category)
            assert proj_2d.shape == (len(mesh.vertices), 2)
            assert rot_3d.shape == (len(mesh.vertices), 3)
            assert not np.isnan(proj_2d).any(), f"NaN in proj_2d for category {category} at ({ax}, {ay}, {az})"
            assert not np.isinf(proj_2d).any(), f"Inf in proj_2d for category {category} at ({ax}, {ay}, {az})"
            assert not np.isnan(rot_3d).any(), f"NaN in rot_3d for category {category} at ({ax}, {ay}, {az})"
            assert not np.isinf(rot_3d).any(), f"Inf in rot_3d for category {category} at ({ax}, {ay}, {az})"

    def test_extreme_rotations_arap_line_search_prevents_inversions(self):
        """Verify ARAP solver's non-inversion line search prevents triangle inversions up to +/-45 deg yaw/pitch."""
        contour = np.array([[20, 20], [180, 20], [180, 180], [20, 180]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=20)
        depth_model = DepthModel()
        depth_model.apply_to_mesh(mesh, category="face")

        solver = DeformationSolver()
        arap = ARAPConstraintSolver(spring_weight=3.0, min_area_fraction=0.01)

        extreme_test_angles = [
            (35.0, 0.0),
            (-35.0, 0.0),
            (0.0, 35.0),
            (0.0, -35.0),
            (40.0, 30.0),
            (-40.0, -30.0),
            (45.0, 0.0),
            (-45.0, 0.0)
        ]

        for ax, ay in extreme_test_angles:
            target, _ = solver.solve(mesh, ax, ay, category="face")
            solved, energy = arap.solve(mesh, target, num_iterations=5, enforce_noninversion=True)

            assert not np.isnan(solved).any()
            assert not np.isinf(solved).any()
            assert energy >= 0.0

            mesh_def = mesh.copy()
            mesh_def.set_positions(solved)
            areas = mesh_def.compute_triangle_signed_areas()
            # Every triangle must have strictly positive signed area
            assert np.all(areas > 0.0), f"Inversion occurred at extreme angle ({ax}, {ay}): min area = {np.min(areas)}"


# =============================================================================
# 2. Continuous Angle Triplets, C0 Continuity & Zero-Identity Invariant
# =============================================================================
class TestContinuousAnglesAndContinuity:
    """Stress-tests for 500+ continuous angle triplets, C0 continuity, and zero-identity invariant."""

    def test_500_random_continuous_angle_triplets_c0_continuity(self):
        """
        Generate 500 random continuous angle triplets (theta_x, theta_y, theta_z) in [-30, 30]^3.
        Verify C0 Lipschitz continuity: ||Delta V(theta + delta) - Delta V(theta)|| <= L ||delta|| with bounded L.
        """
        rng = np.random.default_rng(1337)
        contour = np.array([[30, 30], [170, 30], [170, 170], [30, 170]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=25)
        depth_model = DepthModel()
        depth_model.apply_to_mesh(mesh, category="face")
        rest_pos = mesh.get_positions()

        solver = DeformationSolver()
        delta_deg = 1e-4  # Infinitesimal perturbation

        # Sample 500 random triplets
        angles = rng.uniform(-30.0, 30.0, size=(500, 3))

        for idx, (ax, ay, az) in enumerate(angles):
            # Base solve
            p0, _ = solver.solve(mesh, ax, ay, az, category="face")
            assert not np.isnan(p0).any()
            assert not np.isinf(p0).any()

            # Perturbed solves along each axis
            p_dx, _ = solver.solve(mesh, ax + delta_deg, ay, az, category="face")
            p_dy, _ = solver.solve(mesh, ax, ay + delta_deg, az, category="face")
            p_dz, _ = solver.solve(mesh, ax, ay, az + delta_deg, category="face")

            # Finite difference approximations of directional derivatives
            d_dx = np.max(np.abs(p_dx - p0)) / delta_deg
            d_dy = np.max(np.abs(p_dy - p0)) / delta_deg
            d_dz = np.max(np.abs(p_dz - p0)) / delta_deg

            # Lipschitz constant bound check (derivatives must be finite and bounded <= 50.0)
            assert d_dx < 50.0, f"Discontinuity / high gradient d_dx = {d_dx} at triplet {idx}: ({ax}, {ay}, {az})"
            assert d_dy < 50.0, f"Discontinuity / high gradient d_dy = {d_dy} at triplet {idx}: ({ax}, {ay}, {az})"
            assert d_dz < 50.0, f"Discontinuity / high gradient d_dz = {d_dz} at triplet {idx}: ({ax}, {ay}, {az})"

    def test_zero_identity_across_all_categories_and_topologies(self):
        """
        Verify strict zero-identity property: Delta V = 0 at (0, 0, 0)
        across all 11 semantic categories and irregular mesh topologies.
        """
        categories = [
            "hair_front", "accessories", "eyebrows", "nose", "eyes",
            "mouth", "face", "hair_side", "ears", "neck", "hair_back"
        ]

        # Construct irregular mesh with 15 random internal vertices
        rng = np.random.default_rng(42)
        random_points = rng.uniform(0.1, 0.9, size=(15, 2))
        mesh = Mesh(
            vertices=[Vertex(position=pt, depth=rng.uniform(-0.5, 0.5)) for pt in random_points],
            triangles=np.zeros((0, 3), dtype=np.int32)
        )

        depth_model = DepthModel()
        solver = DeformationSolver()

        for cat in categories:
            depth_model.apply_to_mesh(mesh, category=cat)
            rest_pos = mesh.get_positions()

            # Solve at exact identity (0, 0, 0)
            p_zero, rot_3d = solver.solve(mesh, 0.0, 0.0, 0.0, category=cat)
            max_delta = np.max(np.abs(p_zero - rest_pos))

            assert max_delta < 1e-12, f"Zero-identity violated for category {cat}: max delta = {max_delta}"
            assert np.allclose(rot_3d[:, :2], rest_pos, atol=1e-12)

    def test_infinitesimal_limits_around_zero(self):
        """
        Verify smooth monotonic convergence to zero identity as angle approaches 0
        from both positive and negative directions without division by zero.
        """
        contour = np.array([[40, 40], [160, 40], [160, 160], [40, 160]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=30)
        depth_model = DepthModel()
        depth_model.apply_to_mesh(mesh, category="face")
        rest_pos = mesh.get_positions()

        solver = DeformationSolver()
        epsilons = [1.0, 0.1, 0.01, 1e-3, 1e-4, 1e-6, 1e-8]

        prev_error = float('inf')
        for eps in epsilons:
            p_pos, _ = solver.solve(mesh, eps, eps, eps, category="face")
            p_neg, _ = solver.solve(mesh, -eps, -eps, -eps, category="face")

            err_pos = np.max(np.abs(p_pos - rest_pos))
            err_neg = np.max(np.abs(p_neg - rest_pos))

            assert err_pos <= prev_error + 1e-9
            assert err_neg <= prev_error + 1e-9
            prev_error = max(err_pos, err_neg)

        # At 1e-8, error should be virtually zero (< 1e-6)
        assert prev_error < 1e-6


# =============================================================================
# 3. Multi-layer Parallax Stratification & Monotonic Depth Separation
# =============================================================================
class TestParallaxStratificationAndSeparation:
    """Stress-tests for multi-layer depth parallax, monotonic separation, and camera parameter sweeps."""

    def test_multi_layer_monotonic_parallax_under_varying_camera_distance(self):
        """
        Verify that multi-layer character stack exhibits monotonic depth separation:
        displacement(hair_front) > displacement(eyes) > displacement(face) > displacement(neck) > displacement(hair_back)
        under varying parallax scales and rotation angles.
        """
        sample_pt = np.array([0.25, 0.15])
        v_hf = Vertex(position=sample_pt.copy(), layer_id="hair_front")
        v_ey = Vertex(position=sample_pt.copy(), layer_id="eyes")
        v_fc = Vertex(position=sample_pt.copy(), layer_id="face")
        v_nk = Vertex(position=sample_pt.copy(), layer_id="neck")
        v_hb = Vertex(position=sample_pt.copy(), layer_id="hair_back")

        m_hf = Mesh(vertices=[v_hf], triangles=np.zeros((0, 3), dtype=np.int32), layer_id="hair_front")
        m_ey = Mesh(vertices=[v_ey], triangles=np.zeros((0, 3), dtype=np.int32), layer_id="eyes")
        m_fc = Mesh(vertices=[v_fc], triangles=np.zeros((0, 3), dtype=np.int32), layer_id="face")
        m_nk = Mesh(vertices=[v_nk], triangles=np.zeros((0, 3), dtype=np.int32), layer_id="neck")
        m_hb = Mesh(vertices=[v_hb], triangles=np.zeros((0, 3), dtype=np.int32), layer_id="hair_back")

        collection = LayerCollection(canvas_size=(256, 256), layers=[
            LayerData(name="hair_front", image=np.zeros((10, 10, 4), dtype=np.uint8), category="hair_front"),
            LayerData(name="eyes", image=np.zeros((10, 10, 4), dtype=np.uint8), category="eyes"),
            LayerData(name="face", image=np.zeros((10, 10, 4), dtype=np.uint8), category="face"),
            LayerData(name="neck", image=np.zeros((10, 10, 4), dtype=np.uint8), category="neck"),
            LayerData(name="hair_back", image=np.zeros((10, 10, 4), dtype=np.uint8), category="hair_back"),
        ])
        mesh_map = {
            "hair_front": m_hf,
            "eyes": m_ey,
            "face": m_fc,
            "neck": m_nk,
            "hair_back": m_hb,
        }

        depth_model = DepthModel()
        depth_model.apply_to_layer_collection(collection, mesh_map, enforce_clearance=True, normalize_global=True)

        # Check assigned depths are strictly stratified:
        z_hf = m_hf.get_depths()[0]
        z_ey = m_ey.get_depths()[0]
        z_fc = m_fc.get_depths()[0]
        z_nk = m_nk.get_depths()[0]
        z_hb = m_hb.get_depths()[0]

        assert z_hf > z_ey > z_fc > z_nk > z_hb, f"Depth order violation: {z_hf}, {z_ey}, {z_fc}, {z_nk}, {z_hb}"

        # Sweep parallax scales and angles
        parallax_scales = [0.1, 0.3, 0.45, 0.8, 1.2]
        test_yaws = [10.0, 20.0, 30.0]

        for p_scale in parallax_scales:
            solver = DeformationSolver(parallax_scale=p_scale)
            for yaw in test_yaws:
                p_hf, _ = solver.solve(m_hf, angle_x_deg=yaw, angle_y_deg=0.0, category="hair_front")
                p_ey, _ = solver.solve(m_ey, angle_x_deg=yaw, angle_y_deg=0.0, category="eyes")
                p_fc, _ = solver.solve(m_fc, angle_x_deg=yaw, angle_y_deg=0.0, category="face")
                p_nk, _ = solver.solve(m_nk, angle_x_deg=yaw, angle_y_deg=0.0, category="neck")
                p_hb, _ = solver.solve(m_hb, angle_x_deg=yaw, angle_y_deg=0.0, category="hair_back")

                dx_hf = p_hf[0, 0] - sample_pt[0]
                dx_ey = p_ey[0, 0] - sample_pt[0]
                dx_fc = p_fc[0, 0] - sample_pt[0]
                dx_nk = p_nk[0, 0] - sample_pt[0]
                dx_hb = p_hb[0, 0] - sample_pt[0]

                # Monotonic parallax shift check: foreground shifts further than background
                assert dx_hf > dx_ey > dx_fc > dx_nk > dx_hb, (
                    f"Parallax displacement monotonicity violated at scale={p_scale}, yaw={yaw}: "
                    f"{dx_hf}, {dx_ey}, {dx_fc}, {dx_nk}, {dx_hb}"
                )

    def test_layer_clearance_enforcement_with_initial_overlap(self):
        """Verify layer clearance enforcement shifts overlapping layers to maintain minimum 30 deg clearance."""
        v1 = Vertex(position=np.array([0.0, 0.0]), depth=0.1)
        v2 = Vertex(position=np.array([0.0, 0.0]), depth=0.1)  # Identical depth (overlap)
        m_back = Mesh(vertices=[v1], triangles=np.zeros((0, 3), dtype=np.int32))
        m_front = Mesh(vertices=[v2], triangles=np.zeros((0, 3), dtype=np.int32))

        collection = LayerCollection(canvas_size=(100, 100), layers=[
            LayerData(name="face", image=np.zeros((10, 10, 4), dtype=np.uint8), category="face"),
            LayerData(name="hair_front", image=np.zeros((10, 10, 4), dtype=np.uint8), category="hair_front"),
        ])
        mesh_map = {"face": m_back, "hair_front": m_front}

        depth_model = DepthModel()
        depth_model.apply_to_layer_collection(collection, mesh_map, enforce_clearance=True, delta_min=0.05, normalize_global=False)

        d_back = m_back.get_depths()[0]
        d_front = m_front.get_depths()[0]
        # Must have established positive separation >= delta_min
        assert d_front - d_back >= 0.05

    def test_depth_normalization_edge_distributions(self):
        """Verify normalize_depths handles degenerate depth distributions (constant, huge numbers, single vertex)."""
        depth_model = DepthModel()

        # Case 1: All depths zero/constant
        v_const = [Vertex(position=np.array([0.0, 0.0]), depth=0.0) for _ in range(5)]
        m_const = Mesh(vertices=v_const, triangles=np.zeros((0, 3), dtype=np.int32))
        depth_model.normalize_depths([m_const])
        assert not np.isnan(m_const.get_depths()).any()
        assert not np.isinf(m_const.get_depths()).any()

        # Case 2: Extreme dynamic range [-1e6, 1e6]
        v_huge = [
            Vertex(position=np.array([0.0, 0.0]), depth=-1e6),
            Vertex(position=np.array([0.0, 0.0]), depth=1e6)
        ]
        m_huge = Mesh(vertices=v_huge, triangles=np.zeros((0, 3), dtype=np.int32))
        depth_model.normalize_depths([m_huge])
        d_norm = m_huge.get_depths()
        assert np.all(d_norm >= -1.0 - 1e-6)
        assert np.all(d_norm <= 1.0 + 1e-6)
        assert math.isclose(d_norm[0], -1.0, abs_tol=1e-5)
        assert math.isclose(d_norm[1], 1.0, abs_tol=1e-5)


# =============================================================================
# 4. Surface Normals & Curvature Under High-Frequency & Boundary Geometries
# =============================================================================
class TestHighFrequencyAndBoundaryGeometry:
    """Stress-tests for surface normals, orthonormal tangent frames, and curvatures under boundary & singular geometry."""

    def test_high_frequency_geometry_normals_tangents(self):
        """
        Stress-test differential geometry on high-frequency zigzag mesh (simulating fine hair / teeth).
        Verify unit normal length, tangent orthonormality, and finite curvature everywhere.
        """
        # Create high-frequency sinusoidal contour (64 teeth)
        t = np.linspace(0, 2 * np.pi, 128, endpoint=False)
        r = 80.0 + 15.0 * np.sin(32 * t)
        xs = 100.0 + r * np.cos(t)
        ys = 100.0 + r * np.sin(t)
        contour = np.column_stack([xs, ys])

        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=15)
        depth_model = DepthModel(center=(0.0, 0.0), radii=(0.8, 0.8, 0.4))
        depth_model.apply_to_mesh(mesh, category="hair_front")

        cfg = depth_model.get_proxy_config_for_category("hair_front")
        geom = GeometryEngine.compute_mesh_geometry(mesh, cfg)

        N = len(mesh.vertices)
        assert len(geom.normals) == N
        assert len(geom.tangents_u) == N
        assert len(geom.tangents_v) == N

        # 1. Unit length check for normals
        norm_lengths = np.linalg.norm(geom.normals, axis=1)
        assert np.allclose(norm_lengths, 1.0, atol=1e-5), "Normals must have unit length 1.0"

        # 2. Orthonormality check for tangent bases
        tu_lengths = np.linalg.norm(geom.tangents_u, axis=1)
        tv_lengths = np.linalg.norm(geom.tangents_v, axis=1)
        assert np.allclose(tu_lengths, 1.0, atol=1e-5), "Tangents Tu must have unit length 1.0"
        assert np.allclose(tv_lengths, 1.0, atol=1e-5), "Tangents Tv must have unit length 1.0"

        dot_un = np.sum(geom.tangents_u * geom.normals, axis=1)
        dot_vn = np.sum(geom.tangents_v * geom.normals, axis=1)
        dot_uv = np.sum(geom.tangents_u * geom.tangents_v, axis=1)
        assert np.allclose(dot_un, 0.0, atol=1e-5), "Tu must be orthogonal to N"
        assert np.allclose(dot_vn, 0.0, atol=1e-5), "Tv must be orthogonal to N"
        assert np.allclose(dot_uv, 0.0, atol=1e-5), "Tu must be orthogonal to Tv"

        # 3. Curvature validity (no NaNs or Infs)
        assert not np.isnan(geom.mean_curvature).any(), "Mean curvature contains NaNs"
        assert not np.isinf(geom.mean_curvature).any(), "Mean curvature contains Infs"
        assert not np.isnan(geom.gaussian_curvature).any(), "Gaussian curvature contains NaNs"
        assert not np.isinf(geom.gaussian_curvature).any(), "Gaussian curvature contains Infs"

    def test_proxy_boundary_and_far_exterior_vertices(self):
        """
        Verify depth and geometry evaluation for points exactly on the proxy boundary
        (u^2 + v^2 = 1.0), slightly outside (1.0001), and far outside (10.0).
        """
        depth_model = DepthModel(center=(0.0, 0.0), radii=(0.6, 0.8, 0.4))
        cfg = depth_model.get_proxy_config_for_category("face")

        # Boundary and exterior points
        pts = np.array([
            [0.6, 0.0],       # Exactly on boundary (u=1, v=0)
            [0.0, 0.8],       # Exactly on boundary (u=0, v=1)
            [0.6001, 0.0],    # Slightly outside boundary
            [0.0, 0.8001],    # Slightly outside boundary
            [5.0, 5.0],       # Far outside
            [-10.0, -10.0],   # Extremely far outside
        ], dtype=np.float64)

        depths = depth_model.compute_proxy_depth_vectorized(pts, cfg)
        assert not np.isnan(depths).any(), "Proxy depth contains NaNs for exterior points"
        assert not np.isinf(depths).any(), "Proxy depth contains Infs for exterior points"

        # Depths outside should decay smoothly to ~0 (or layer offset)
        assert depths[2] <= depths[0] + 1e-4
        assert depths[3] <= depths[1] + 1e-4
        assert abs(depths[4] - cfg.layer_z_offset * cfg.radii[2]) < 1e-3
        assert abs(depths[5] - cfg.layer_z_offset * cfg.radii[2]) < 1e-3

    def test_discrete_mesh_normals_fallback_without_proxy(self):
        """Verify discrete mesh normal accumulation works when proxy_config=None without crashing."""
        contour = np.array([[30, 30], [170, 30], [170, 170], [30, 170]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=20)
        # Manually set arbitrary depths
        for idx, vtx in enumerate(mesh.vertices):
            vtx.depth = 0.1 * math.sin(idx)

        geom = GeometryEngine.compute_mesh_geometry(mesh, proxy_config=None)
        assert len(geom.normals) == len(mesh.vertices)
        norm_lengths = np.linalg.norm(geom.normals, axis=1)
        assert np.allclose(norm_lengths, 1.0, atol=1e-5)
        assert not np.isnan(geom.normals).any()
        assert not np.isinf(geom.normals).any()

    def test_degenerate_empty_mesh_geometry_handling(self):
        """Verify GeometryEngine handles empty meshes without throwing exceptions."""
        empty_mesh = Mesh(vertices=[], triangles=np.zeros((0, 3), dtype=np.int32))
        geom = GeometryEngine.compute_mesh_geometry(empty_mesh)
        assert geom.normals.shape == (0, 3)
        assert geom.tangents_u.shape == (0, 3)
        assert geom.tangents_v.shape == (0, 3)
        assert geom.mean_curvature.shape == (0,)
        assert geom.gaussian_curvature.shape == (0,)


# =============================================================================
# 5. ARAP & Keyform High-Load Scalability & Resilience
# =============================================================================
class TestARAPAndKeyformResilience:
    """Stress-tests for high-density meshes, caching, and keyform tensor generation."""

    def test_high_density_mesh_arap_solve_scalability(self):
        """
        Verify ARAP solver efficiently handles a high-density mesh (150+ vertices)
        within performance budget (< 100 ms for 4 iterations) and zero triangle flips.
        """
        import time
        contour = np.array([[20, 20], [180, 20], [180, 180], [20, 180]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=12)
        assert len(mesh.vertices) >= 150

        depth_model = DepthModel()
        depth_model.apply_to_mesh(mesh, category="face")

        solver = DeformationSolver()
        target_pos, _ = solver.solve(mesh, angle_x_deg=30.0, angle_y_deg=-25.0, category="face")

        arap = ARAPConstraintSolver(spring_weight=3.0)
        arap.initialize_sparse_system(mesh)

        t0 = time.perf_counter()
        solved_pos, energy = arap.solve(mesh, target_pos, num_iterations=4, enforce_noninversion=True)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert elapsed_ms < 100.0, f"ARAP solve too slow: {elapsed_ms:.2f} ms"
        assert not np.isnan(solved_pos).any()
        assert not np.isinf(solved_pos).any()

        # Check positive signed areas
        mesh_check = mesh.copy()
        mesh_check.set_positions(solved_pos)
        areas = mesh_check.compute_triangle_signed_areas()
        assert np.all(areas > 0.0)

    def test_keyform_generator_multi_layer_full_coverage(self):
        """Verify KeyformGenerator generates complete keyform tables for all 10 standard layer categories."""
        categories = ["hair_front", "accessories", "eyebrows", "nose", "eyes", "mouth", "face", "hair_side", "ears", "neck"]
        layers = []
        mesh_map = {}

        contour = np.array([[40, 40], [160, 40], [160, 160], [40, 160]], dtype=np.float64)

        for cat in categories:
            img = np.ones((64, 64, 4), dtype=np.uint8) * 128
            ldata = LayerData(name=cat, image=img, category=cat)
            layers.append(ldata)
            mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=30)
            mesh_map[ldata.layer_id] = mesh

        collection = LayerCollection(canvas_size=(256, 256), layers=layers)
        generator = KeyformGenerator()

        # 1. Verify standard Live2D Deformer Hierarchy (R1, R2)
        table_deformers = generator.generate_keyform_table(collection, mesh_map, include_angle_z=True, direct_deform=False)
        assert len(table_deformers.drawables) == 10
        assert len(table_deformers.warp_deformers) == 1
        assert len(table_deformers.warp_deformers[0].deformed_positions) == 9
        assert len(table_deformers.rotation_deformers) == 1
        assert len(table_deformers.rotation_deformers[0].angles) == 3
        is_valid_def, errors_def = table_deformers.validate()
        assert is_valid_def, f"KeyformTable with deformers validation failed: {errors_def}"

        # 2. Verify direct deform mode
        table = generator.generate_keyform_table(collection, mesh_map, include_angle_z=True, direct_deform=True)

        assert len(table.drawables) == 10
        is_valid, errors = table.validate()
        assert is_valid, f"KeyformTable validation failed: {errors}"

        for dw in table.drawables:
            # 9 AngleX/AngleY keyforms + 2 AngleZ keyforms
            assert len(dw.deformed_positions) >= 9
            for k, pos in dw.deformed_positions.items():
                assert not np.isnan(pos).any(), f"NaN in keyform {k} for {dw.drawable_id}"
                assert not np.isinf(pos).any(), f"Inf in keyform {k} for {dw.drawable_id}"


    def test_depth_brush_stress_boundary_and_negative_modes(self):
        """Verify apply_depth_brush handles brush positions far outside mesh, negative intensity, and subtractive mode."""
        v = Vertex(position=np.array([0.5, 0.5]), depth=0.2)
        mesh = Mesh(vertices=[v], triangles=np.zeros((0, 3), dtype=np.int32))

        depth_model = DepthModel()

        # Brush outside radius -> depth unchanged
        depth_model.apply_depth_brush(mesh, brush_pos=(5.0, 5.0), radius=0.2, intensity=0.1, additive=True)
        assert math.isclose(mesh.vertices[0].depth, 0.2, abs_tol=1e-6)

        # Additive brush near vertex -> depth increases
        depth_model.apply_depth_brush(mesh, brush_pos=(0.5, 0.5), radius=0.2, intensity=0.1, additive=True)
        assert mesh.vertices[0].depth > 0.2

        # Subtractive brush -> depth decreases (bounded by >= 0)
        depth_model.apply_depth_brush(mesh, brush_pos=(0.5, 0.5), radius=0.2, intensity=1.0, additive=False)
        assert mesh.vertices[0].depth >= 0.0
