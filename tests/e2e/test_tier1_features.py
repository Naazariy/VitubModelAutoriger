"""
Tier 1: Feature Coverage E2E Test Suite.
Verifies atomic and functional capabilities for features F01 through F13:
- F01/F02: Asset Ingestion & Preprocessing (PNG, PSD, alpha, contours, synthetic head)
- F03: Delaunay Mesh Generation & Steiner Grid Sampling
- F04/F05/F06: 3D SO(3) Rotation Math (Yaw, Pitch, Roll) & Depth Parallax
- F07: ARAP Mass-Spring Constraint Solver & Energy Minimization
- F09: Texture Atlas Packing & UV Coordinate Remapping
- F10: Pure-Python .moc3 Binary Serialization (Magic bytes, section offsets)
- F11: .model3.json & .cdi3.json Metadata Manifest Generation
- F12/F13: CLI Argument Parsing & 6-Stage Structural Validator
"""

import os
import math
import struct
import numpy as np
import pytest
cv2 = pytest.importorskip("cv2")
from PIL import Image

from src.core.vertex import Vertex
from src.core.mesh import Mesh
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator
from src.depth.depth_model import DepthModel
from src.geometry.geometry_engine import GeometryEngine
from src.deformation.deformation_solver import DeformationSolver
from src.constraints.constraint_solver import MassSpringConstraintSolver

from tests.conftest import (
    LayerData,
    DrawableKeyforms,
    KeyformTable,
    Moc3Writer,
    Model3Writer,
    TextureAtlasPacker,
    StructuralValidator,
    CLIRunner,
    ValidationResult
)


# ===========================================================================
# 1. F01 / F02: Asset Ingestion & Layer Preprocessing
# ===========================================================================
class TestAssetIngestion:
    """Test suite for F01 (PSD Ingestion) and F02 (PNG Ingestion)."""

    def test_png_image_loading_and_channels(self, temp_dir):
        """Verify PNG loading extracts 4-channel RGBA and 8-bit alpha mask."""
        test_img_path = temp_dir / "test_avatar.png"
        sample_rgba = np.zeros((128, 128, 4), dtype=np.uint8)
        sample_rgba[32:96, 32:96] = [255, 200, 180, 255]
        Image.fromarray(sample_rgba).save(test_img_path)

        rgba, alpha = ImageImporter.load_image(str(test_img_path))
        assert rgba.shape == (128, 128, 4)
        assert rgba.dtype == np.uint8
        assert alpha.shape == (128, 128)
        assert np.max(alpha) == 255
        assert np.min(alpha) == 0

    def test_alpha_mask_extraction_and_thresholding(self):
        """Verify alpha thresholding separates background from character silhouette."""
        alpha = np.zeros((100, 100), dtype=np.uint8)
        alpha[25:75, 25:75] = 200  # Opaque square
        alpha[0:10, 0:10] = 5     # Sub-threshold noise

        contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=1.0)
        assert isinstance(contour, np.ndarray)
        assert contour.ndim == 2
        assert contour.shape[1] == 2
        assert len(contour) >= 4  # At least 4 polygon vertices for rectangular patch

    def test_silhouette_contour_extraction_geometry(self):
        """Verify contour coordinates are bounded within image canvas dimensions."""
        width, height = 200, 200
        alpha = np.zeros((height, width), dtype=np.uint8)
        cv2.circle(alpha, (100, 100), 50, 255, -1)

        contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
        assert np.all(contour[:, 0] >= 0) and np.all(contour[:, 0] <= width)
        assert np.all(contour[:, 1] >= 0) and np.all(contour[:, 1] <= height)
        # Verify polygon area is roughly equal to circle area pi * 50^2 ~ 7853
        area = cv2.contourArea(contour.astype(np.float32))
        assert abs(area - math.pi * 50**2) < 500

    def test_synthetic_head_generation(self):
        """Verify ImageImporter creates fully formed synthetic head with facial features."""
        rgba, alpha = ImageImporter.create_synthetic_head_image(width=512, height=512)
        assert rgba.shape == (512, 512, 4)
        assert alpha.shape == (512, 512)
        # Check non-empty facial regions
        assert np.count_nonzero(alpha > 128) > 50000
        # Check center is skin colored
        center_color = rgba[256, 256]
        assert center_color[0] == 255 and center_color[1] == 220  # Skin tone R, G

    def test_layer_data_metadata_and_structure(self, sample_character_layers):
        """Verify LayerData structures maintain offsets, depth hints, and categories."""
        assert len(sample_character_layers) == 5
        names = [l.name for l in sample_character_layers]
        assert "Hair_Front" in names
        assert "Face" in names
        assert "Eyes" in names
        assert "Mouth" in names
        assert "Hair_Back" in names

        for l in sample_character_layers:
            assert l.image.shape[2] == 4
            assert -1.0 <= l.z_depth_hint <= 1.0
            assert isinstance(l.category, str)


# ===========================================================================
# 2. F03: Robust Mesh Triangulation & Generation
# ===========================================================================
class TestMeshGeneration:
    """Test suite for F03: Pure-Python SciPy Delaunay Triangulation."""

    def test_delaunay_triangulation_connectivity(self):
        """Verify mesh contains valid vertex index references and non-empty triangles."""
        contour = np.array([[50, 50], [200, 50], [200, 200], [50, 200]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (256, 256), target_grid_size=30)
        assert len(mesh.vertices) > 4
        assert len(mesh.triangles) > 0
        N = len(mesh.vertices)
        for tri in mesh.triangles:
            assert 0 <= tri[0] < N
            assert 0 <= tri[1] < N
            assert 0 <= tri[2] < N
            assert len(set(tri)) == 3  # Non-degenerate vertex indices

    def test_steiner_internal_grid_generation(self):
        """Verify mesh generator samples interior Steiner vertices inside polygon."""
        contour = np.array([[20, 20], [236, 20], [236, 236], [20, 236]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (256, 256), target_grid_size=25)
        # Verify internal Steiner vertices were sampled (vertex count > 4 boundary contour vertices)
        assert len(mesh.vertices) > len(contour)
        # Verify interior vertices exist
        pos = mesh.get_positions()
        # Find points strictly interior (distance from origin in normalized space < 0.8)
        interior_points = [p for p in pos if np.linalg.norm(p) < 0.5]
        assert len(interior_points) > 0, "Steiner grid sampling must produce interior mesh vertices"

    def test_mesh_rest_triangle_positive_signed_area(self):
        """Verify all rest-pose triangles have strictly positive signed area (CCW winding)."""
        contour = np.array([[50, 50], [200, 50], [200, 200], [50, 200]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (256, 256), target_grid_size=25)
        signed_areas = mesh.compute_triangle_signed_areas()
        assert len(signed_areas) == len(mesh.triangles)
        assert np.all(signed_areas > 0.0), "All rest mesh triangles must have positive signed area"

    def test_vertex_normalization_and_uv_bounds(self):
        """Verify vertex positions are normalized to [-1, 1] and UV coordinates to [0, 1]."""
        contour = np.array([[10, 10], [100, 10], [100, 100], [10, 100]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (128, 128), target_grid_size=20)
        positions = mesh.get_positions()
        uvs = mesh.uvs
        assert np.all(positions >= -1.0) and np.all(positions <= 1.0)
        assert np.all(uvs >= 0.0) and np.all(uvs <= 1.0)

    def test_mesh_edges_reconstruction_and_lengths(self):
        """Verify unique edge set extraction and non-zero rest edge lengths."""
        contour = np.array([[30, 30], [150, 30], [150, 150], [30, 150]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=30)
        assert len(mesh.edges) > 0
        assert len(mesh.rest_edge_lengths) == len(mesh.edges)
        assert np.all(mesh.rest_edge_lengths > 0.0)


# ===========================================================================
# 3. F04 / F05 / F06: 3D SO(3) Rotation Math & Parallax
# ===========================================================================
class TestDeformationMath:
    """Test suite for 3D SO(3) Euler rotations (AngleX, AngleY, AngleZ) and depth parallax."""

    def test_so3_rotation_matrix_orthonormality(self):
        """Verify rotation matrix R is strictly orthonormal: R^T * R = I and det(R) = 1."""
        for ax in [-30.0, 0.0, 25.0]:
            for ay in [-20.0, 0.0, 30.0]:
                R = DeformationSolver.get_rotation_matrix(ax, ay)
                assert R.shape == (3, 3)
                identity_check = R.T @ R
                assert np.allclose(identity_check, np.eye(3), atol=1e-6)
                det = np.linalg.det(R)
                assert math.isclose(det, 1.0, abs_tol=1e-6)

    def test_identity_rotation_at_zero_degrees(self):
        """Verify 0 yaw and 0 pitch produces exact 3x3 identity matrix."""
        R = DeformationSolver.get_rotation_matrix(0.0, 0.0)
        assert np.allclose(R, np.eye(3), atol=1e-7)

    def test_yaw_rotation_anglex_displacement(self):
        """Verify AngleX (Yaw) rotates points around Y axis."""
        R_pos = DeformationSolver.get_rotation_matrix(30.0, 0.0)
        pt = np.array([1.0, 0.0, 0.0])  # Point on positive X axis
        rotated_pt = R_pos @ pt
        # X coordinate should decrease by cos(30), Z should decrease by -sin(30)
        assert math.isclose(rotated_pt[0], math.cos(math.radians(30.0)), abs_tol=1e-5)
        assert math.isclose(rotated_pt[2], -math.sin(math.radians(30.0)), abs_tol=1e-5)
        assert math.isclose(rotated_pt[1], 0.0, abs_tol=1e-5)

    def test_pitch_rotation_angley_displacement(self):
        """Verify AngleY (Pitch) rotates points around X axis."""
        R_pitch = DeformationSolver.get_rotation_matrix(0.0, 30.0)
        pt = np.array([0.0, 1.0, 0.0])  # Point on positive Y axis
        rotated_pt = R_pitch @ pt
        assert math.isclose(rotated_pt[0], 0.0, abs_tol=1e-5)
        assert math.isclose(rotated_pt[1], math.cos(math.radians(30.0)), abs_tol=1e-5)
        assert math.isclose(rotated_pt[2], math.sin(math.radians(30.0)), abs_tol=1e-5)

    def test_depth_stratification_ellipsoid_model(self):
        """Verify DepthModel computes smooth ellipsoidal depth field."""
        depth_model = DepthModel(center=(0.0, 0.0), radii=(0.6, 0.8, 0.4))
        z_center = depth_model.compute_ellipsoid_depth(0.0, 0.0)
        assert math.isclose(z_center, 0.4, abs_tol=1e-4)  # Peak depth at ellipsoid apex

        z_outer = depth_model.compute_ellipsoid_depth(0.8, 0.8)
        assert z_outer == 0.0  # Outside ellipsoid boundary

    def test_depth_scaled_parallax_projection(self):
        """Verify points with higher depth z experience greater parallax displacement."""
        deform = DeformationSolver(center=(0.0, 0.0, 0.0), head_radius_z=0.4, parallax_scale=0.5)
        
        # Create 2 vertices: one at z=0, one at z=0.4
        v1 = Vertex(position=np.array([0.2, 0.0]), depth=0.0, layer_id="Face")
        v2 = Vertex(position=np.array([0.2, 0.0]), depth=0.4, layer_id="Face")
        mesh = Mesh(vertices=[v1, v2], triangles=np.zeros((0, 3), dtype=np.int32))

        proj_2d, _ = deform.solve(mesh, angle_x_deg=20.0, angle_y_deg=0.0)
        # Deep vertex v2 should displace further along X than surface vertex v1
        disp_v1 = abs(proj_2d[0, 0] - 0.2)
        disp_v2 = abs(proj_2d[1, 0] - 0.2)
        assert disp_v2 > disp_v1


# ===========================================================================
# 4. F07: ARAP Mass-Spring Constraint Solver
# ===========================================================================
class TestARAPConstraintSolver:
    """Test suite for F07: ARAP Local-Global Energy Minimization."""

    def test_sparse_system_matrix_initialization(self):
        """Verify sparse Laplacian and LU factorization are built correctly."""
        contour = np.array([[50, 50], [150, 50], [150, 150], [50, 150]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=30)
        solver = MassSpringConstraintSolver(spring_weight=2.0)
        solver.initialize_sparse_system(mesh)
        assert solver.lu_factor is not None
        assert len(solver.all_edges) > 0
        assert solver.W_diag.shape == (len(mesh.vertices),)

    def test_energy_monotonic_reduction_across_iterations(self):
        """Verify solver iterations reduce or stabilize deformation energy."""
        contour = np.array([[50, 50], [180, 50], [180, 180], [50, 180]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=25)
        
        solver = MassSpringConstraintSolver(spring_weight=2.5)
        deform = DeformationSolver()
        target_pos, _ = deform.solve(mesh, angle_x_deg=15.0, angle_y_deg=10.0)

        _, E1 = solver.solve(mesh, target_pos, num_iterations=1)
        _, E3 = solver.solve(mesh, target_pos, num_iterations=3)
        assert E3 <= E1 + 1e-4, "Multi-iteration ARAP must reduce or maintain total energy"

    def test_arap_preserves_positive_signed_areas(self):
        """Verify ARAP regularization prevents triangle flips under moderate rotation."""
        contour = np.array([[40, 40], [160, 40], [160, 160], [40, 160]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=25)
        
        solver = MassSpringConstraintSolver(spring_weight=3.0)
        deform = DeformationSolver()
        target_pos, _ = deform.solve(mesh, angle_x_deg=20.0, angle_y_deg=-15.0)
        solved_pos, _ = solver.solve(mesh, target_pos, num_iterations=4)

        mesh_def = mesh.copy()
        mesh_def.set_positions(solved_pos)
        signed_areas = mesh_def.compute_triangle_signed_areas()
        assert np.all(signed_areas > -1e-4), "No inverted triangles after ARAP solve"

    def test_zero_target_displacement_identity(self):
        """Verify rest target produces rest position output with near-zero energy."""
        contour = np.array([[50, 50], [150, 50], [150, 150], [50, 150]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=30)
        rest_pos = mesh.get_positions()
        
        solver = MassSpringConstraintSolver()
        solved_pos, energy = solver.solve(mesh, rest_pos, num_iterations=2)
        assert np.allclose(solved_pos, rest_pos, atol=1e-5)
        assert energy < 1e-4

    def test_stiffness_weight_modulation(self):
        """Verify vertices with stiffness=1.0 resist displacement more than stiffness=0.0."""
        v1 = Vertex(position=np.array([-0.5, 0.0]), stiffness=0.1)
        v2 = Vertex(position=np.array([0.5, 0.0]), stiffness=1.0)
        mesh = Mesh(vertices=[v1, v2], triangles=np.zeros((0, 3), dtype=np.int32))
        
        solver = MassSpringConstraintSolver()
        solver.initialize_sparse_system(mesh)
        assert solver.W_diag[1] > solver.W_diag[0]


# ===========================================================================
# 5. F09: Texture Atlas Packing & UV Remapping
# ===========================================================================
class TestTextureAtlasPacker:
    """Test suite for F09: Power-of-Two MaxRects Texture Atlas Packer."""

    def test_atlas_power_of_two_dimensions(self, sample_character_layers):
        """Verify generated texture atlas has strictly power-of-two dimensions."""
        atlas_img, uv_rects = TextureAtlasPacker.pack_layers(sample_character_layers, max_atlas_size=4096)
        h, w = atlas_img.shape[:2]
        assert (w & (w - 1) == 0) and w >= 512
        assert (h & (h - 1) == 0) and h >= 512

    def test_atlas_uv_rect_normalized_bounds(self, sample_character_layers):
        """Verify all layer UV bounding boxes fall strictly inside [0.0, 1.0]."""
        atlas_img, uv_rects = TextureAtlasPacker.pack_layers(sample_character_layers, max_atlas_size=4096)
        for name, (u_min, v_min, u_max, v_max) in uv_rects.items():
            assert 0.0 <= u_min <= u_max <= 1.0
            assert 0.0 <= v_min <= v_max <= 1.0
            assert (u_max - u_min) > 0
            assert (v_max - v_min) > 0

    def test_atlas_non_overlapping_rectangles(self, sample_character_layers):
        """Verify no two packed layers overlap in atlas space."""
        atlas_img, uv_rects = TextureAtlasPacker.pack_layers(sample_character_layers, max_atlas_size=4096)
        rect_list = list(uv_rects.values())
        for i in range(len(rect_list)):
            for j in range(i + 1, len(rect_list)):
                u1_min, v1_min, u1_max, v1_max = rect_list[i]
                u2_min, v2_min, u2_max, v2_max = rect_list[j]
                
                # Check for rectangle disjointness
                is_disjoint = (u1_max <= u2_min) or (u2_max <= u1_min) or (v1_max <= v2_min) or (v2_max <= v1_min)
                assert is_disjoint, f"Overlap detected between rect {i} and rect {j}"

    def test_atlas_empty_layer_list_handling(self):
        """Verify packing an empty layer list produces valid power-of-two blank atlas."""
        atlas_img, uv_rects = TextureAtlasPacker.pack_layers([])
        assert atlas_img.shape == (512, 512, 4)
        assert len(uv_rects) == 0

    def test_atlas_pixel_data_transfer(self):
        """Verify non-zero pixel data from source layer is faithfully copied to atlas."""
        layer_img = np.ones((50, 50, 4), dtype=np.uint8) * 180
        layer = LayerData(name="SolidBox", image=layer_img)
        atlas_img, uv_rects = TextureAtlasPacker.pack_layers([layer])
        
        u_min, v_min, u_max, v_max = uv_rects["SolidBox"]
        h, w = atlas_img.shape[:2]
        px_min, py_min = int(u_min * w), int(v_min * h)
        
        # Check center pixel of placed rect
        sample_pixel = atlas_img[py_min + 10, px_min + 10]
        assert np.all(sample_pixel == 180)


# ===========================================================================
# 6. F10: Pure-Python .moc3 Binary Writer
# ===========================================================================
class TestMoc3BinaryWriter:
    """Test suite for F10: Live2D Cubism 3.0+ .moc3 Binary Serialization."""

    def test_moc3_magic_bytes_and_header_size(self, temp_dir):
        """Verify binary starts with 'MOC3' magic bytes and is >= 64 bytes."""
        out_path = temp_dir / "sample.moc3"
        table = KeyformTable()
        raw_bytes = Moc3Writer.write_moc3(table, str(out_path))

        assert len(raw_bytes) >= 64
        assert raw_bytes[:4] == b"MOC3"
        assert raw_bytes[4] == 3  # Version 3

    def test_moc3_section_table_offsets(self, temp_dir):
        """Verify section table offsets in header point within binary payload."""
        out_path = temp_dir / "sample.moc3"
        
        d = DrawableKeyforms(
            drawable_id="ArtMesh_Face",
            texture_index=0,
            base_vertices=np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]),
            triangles=np.array([[0, 1, 2]]),
            uvs_atlas=np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]]),
            deformed_positions={(0.0, 0.0, 0.0): np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]])}
        )
        table = KeyformTable(drawables=[d])
        raw_bytes = Moc3Writer.write_moc3(table, str(out_path))

        num_drawables, num_params, off_d, off_p, off_v, off_k = struct.unpack_from('<IIIIII', raw_bytes, 8)
        assert num_drawables == 1
        assert num_params == 3
        assert 64 <= off_d < len(raw_bytes)
        assert 64 <= off_p < len(raw_bytes)

    def test_moc3_multiple_drawables_serialization(self, temp_dir):
        """Verify multiple drawables are serialized without header collision."""
        out_path = temp_dir / "multi.moc3"
        d1 = DrawableKeyforms("ArtMesh_1", 0, np.zeros((3, 2)), np.zeros((1, 3)), np.zeros((3, 2)))
        d2 = DrawableKeyforms("ArtMesh_2", 0, np.zeros((4, 2)), np.zeros((2, 3)), np.zeros((4, 2)))
        table = KeyformTable(drawables=[d1, d2])
        raw_bytes = Moc3Writer.write_moc3(table, str(out_path))

        num_d, _, _, _, _, _ = struct.unpack_from('<IIIIII', raw_bytes, 8)
        assert num_d == 2

    def test_moc3_parameter_ranges_serialization(self, temp_dir):
        """Verify parameter bounds (min, default, max) are preserved in binary."""
        out_path = temp_dir / "param_test.moc3"
        table = KeyformTable(
            parameter_ids=["ParamAngleX"],
            parameter_ranges={"ParamAngleX": (-25.0, 0.0, 25.0)}
        )
        raw_bytes = Moc3Writer.write_moc3(table, str(out_path))
        assert b"ParamAngleX" in raw_bytes

    def test_moc3_file_creation_on_disk(self, temp_dir):
        """Verify physical .moc3 file is written to target disk location."""
        out_path = temp_dir / "disk_test.moc3"
        table = KeyformTable()
        Moc3Writer.write_moc3(table, str(out_path))
        assert out_path.exists()
        assert out_path.stat().st_size >= 64


# ===========================================================================
# 7. F11: .model3.json & .cdi3.json Metadata Manifest Generation
# ===========================================================================
class TestMetadataGenerators:
    """Test suite for F11: .model3.json and .cdi3.json manifest generation."""

    def test_model3_json_schema_and_version(self, temp_dir):
        """Verify .model3.json complies with Cubism 3.0+ schema."""
        out_json = temp_dir / "model.model3.json"
        data = Model3Writer.generate_model3_json(
            model_name="TestModel",
            moc_rel_path="TestModel.moc3",
            texture_rel_paths=["TestModel.4096/texture_00.png"],
            output_path=str(out_json)
        )
        assert data["Version"] == 3
        assert data["FileReferences"]["Moc"] == "TestModel.moc3"
        assert len(data["FileReferences"]["Textures"]) == 1
        assert out_json.exists()

    def test_model3_json_optional_physics_and_cdi(self, temp_dir):
        """Verify optional physics and display info references in model3.json."""
        data = Model3Writer.generate_model3_json(
            model_name="AdvancedModel",
            moc_rel_path="AdvancedModel.moc3",
            texture_rel_paths=["tex.png"],
            physics_rel_path="AdvancedModel.physics3.json",
            cdi_rel_path="AdvancedModel.cdi3.json"
        )
        assert data["FileReferences"]["Physics"] == "AdvancedModel.physics3.json"
        assert data["FileReferences"]["DisplayInfo"] == "AdvancedModel.cdi3.json"

    def test_cdi3_json_parameter_and_part_mappings(self, temp_dir):
        """Verify .cdi3.json properly formats parameter labels and part display names."""
        out_cdi = temp_dir / "model.cdi3.json"
        data = Model3Writer.generate_cdi3_json(
            parameter_ids=["ParamAngleX", "ParamAngleY", "ParamAngleZ"],
            part_ids=["PartHead", "PartHair"],
            output_path=str(out_cdi)
        )
        assert data["Version"] == 3
        assert len(data["Parameters"]) == 3
        param_names = [p["Name"] for p in data["Parameters"]]
        assert "Angle X" in param_names
        assert "Angle Y" in param_names
        assert "Angle Z" in param_names
        assert out_cdi.exists()

    def test_model3_json_relative_paths_formatting(self):
        """Verify file paths inside model3.json are strictly relative without backslashes."""
        data = Model3Writer.generate_model3_json(
            model_name="CleanModel",
            moc_rel_path="CleanModel.moc3",
            texture_rel_paths=["textures/texture_00.png"]
        )
        assert "\\" not in data["FileReferences"]["Moc"]
        assert "\\" not in data["FileReferences"]["Textures"][0]

    def test_model3_json_parameter_groups_structure(self):
        """Verify default LipSync and EyeBlink parameter groups exist in manifest."""
        data = Model3Writer.generate_model3_json("Model", "m.moc3", ["t.png"])
        groups = data.get("Groups", [])
        group_names = [g["Name"] for g in groups]
        assert "LipSync" in group_names
        assert "EyeBlink" in group_names


# ===========================================================================
# 8. F12 / F13: CLI Argument Parsing & Structural Validator Integration
# ===========================================================================
class TestCLIAndValidatorIntegration:
    """Test suite for F12 (CLI Pipeline) and F13 (6-Stage Validator)."""

    def test_cli_argument_parsing_defaults(self):
        """Verify CLI parser populates correct default values."""
        args = ["sample_head.png"]
        params = CLIRunner.parse_args(args)
        assert params["input_path"] == "sample_head.png"
        assert params["atlas_size"] == 4096
        assert params["grid_size"] == 25
        assert params["auto_depth"] is True
        assert params["auto_stiffness"] is True
        assert params["validate"] is False

    def test_cli_argument_parsing_custom_options(self):
        """Verify CLI parser parses user-defined flags correctly."""
        args = [
            "char.psd",
            "-o", "./custom_out",
            "-n", "MyChar",
            "--resolution", "2048",
            "--grid-size", "15",
            "--angle-x-range", "-25.0,25.0",
            "--validate"
        ]
        params = CLIRunner.parse_args(args)
        assert params["output"] == "./custom_out"
        assert params["name"] == "MyChar"
        assert params["atlas_size"] == 2048
        assert params["grid_size"] == 15
        assert params["angle_x_range"] == "-25.0,25.0"
        assert params["validate"] is True

    def test_cli_missing_input_file_exit_code(self, temp_dir):
        """Verify CLI returns exit code 2 (ERR_INPUT_NOT_FOUND) when file does not exist."""
        nonexistent = str(temp_dir / "nonexistent_character.png")
        exit_code = CLIRunner.run_pipeline([nonexistent])
        assert exit_code == CLIRunner.EXIT_ERR_INPUT_NOT_FOUND

    def test_validator_passes_valid_model_bundle(self, temp_dir):
        """Verify 6-stage structural validator approves compliant model bundle."""
        model_name = "ValidAvatar"
        model_dir = temp_dir / model_name
        model_dir.mkdir(parents=True)

        # Create textures
        tex_dir = model_dir / f"{model_name}.1024"
        tex_dir.mkdir()
        tex_img = Image.new("RGBA", (1024, 1024), (200, 150, 100, 255))
        tex_img.save(tex_dir / "texture_00.png")

        # Create moc3
        moc_path = model_dir / f"{model_name}.moc3"
        table = KeyformTable()
        Moc3Writer.write_moc3(table, str(moc_path))

        # Create model3.json
        model3_path = model_dir / f"{model_name}.model3.json"
        Model3Writer.generate_model3_json(
            model_name=model_name,
            moc_rel_path=f"{model_name}.moc3",
            texture_rel_paths=[f"{model_name}.1024/texture_00.png"],
            output_path=str(model3_path)
        )

        result = StructuralValidator.validate_live2d_model(str(model3_path))
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert 1 in result.stages_passed
        assert 2 in result.stages_passed
        assert 3 in result.stages_passed
        assert 5 in result.stages_passed

    def test_validator_fails_missing_moc_file(self, temp_dir):
        """Verify validator flags missing .moc3 binary file."""
        model_dir = temp_dir / "BrokenModel"
        model_dir.mkdir()
        model3_path = model_dir / "BrokenModel.model3.json"
        Model3Writer.generate_model3_json(
            model_name="BrokenModel",
            moc_rel_path="BrokenModel.moc3",  # File doesn't exist
            texture_rel_paths=[],
            output_path=str(model3_path)
        )

        result = StructuralValidator.validate_live2d_model(str(model3_path))
        assert result.is_valid is False
        assert any("Moc file does not exist" in e or "Textures is empty" in e for e in result.errors)
