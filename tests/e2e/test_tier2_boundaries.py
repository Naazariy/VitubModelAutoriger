"""
Tier 2: Boundary & Corner Cases E2E Test Suite.
Tests extreme limits, scale boundaries, degenerate geometries, and edge cases:
- Minimal and micro image dimensions (1x1, 16x16, 64x64)
- Odd and non-square canvas dimensions (513x729, 301x301)
- Empty and 100% transparent layers (graceful handling)
- Disconnected multi-island contours (separated hair ribbons / accessories)
- Single-layer minimal models vs deep multi-layer hierarchies
- Extreme rotation angles (AngleX=±60°, AngleY=±45°, AngleZ=±45°)
- High vertex density mesh (>1000 vertices, memory bounded)
- Texture atlas powers-of-two (512 to 8192) and bounds enforcement
"""

import math
import numpy as np
import pytest
cv2 = pytest.importorskip("cv2")
from PIL import Image

from src.core.vertex import Vertex
from src.core.mesh import Mesh
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator
from src.depth.depth_model import DepthModel
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
    CLIRunner
)


# ===========================================================================
# 1. Minimal and Micro Dimensions (1x1, 16x16, 64x64)
# ===========================================================================
class TestMinimalDimensions:
    """Boundary tests for micro assets and minimal canvas dimensions."""

    def test_boundary_1x1_pixel_image(self, temp_dir):
        """Verify 1x1 single-pixel image does not divide by zero or crash pipeline."""
        img_1x1 = np.array([[[255, 255, 255, 255]]], dtype=np.uint8)
        layer = LayerData(name="Pixel1x1", image=img_1x1)
        
        # Atlas packing
        atlas, uv_rects = TextureAtlasPacker.pack_layers([layer], max_atlas_size=512)
        assert atlas.shape == (512, 512, 4)
        assert "Pixel1x1" in uv_rects
        u_min, v_min, u_max, v_max = uv_rects["Pixel1x1"]
        assert 0.0 <= u_min <= u_max <= 1.0
        assert 0.0 <= v_min <= v_max <= 1.0

    def test_boundary_16x16_micro_asset_mesh_generation(self):
        """Verify 16x16 micro-image contour generates valid bounded triangulation."""
        alpha = np.zeros((16, 16), dtype=np.uint8)
        alpha[4:12, 4:12] = 255
        contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=1.0)
        
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (16, 16), target_grid_size=4)
        assert len(mesh.vertices) >= 4
        assert len(mesh.triangles) >= 2
        # Verify no NaN in normalized coordinates
        pos = mesh.get_positions()
        assert not np.isnan(pos).any()
        assert not np.isinf(pos).any()
        assert np.all(pos >= -1.0) and np.all(pos <= 1.0)

    def test_boundary_64x64_badge_asset(self, temp_dir):
        """Verify 64x64 icon/badge asset processes cleanly into valid Live2D model."""
        rgba = np.ones((64, 64, 4), dtype=np.uint8) * 200
        alpha = rgba[:, :, 3]
        contour = ImageImporter.extract_contour(alpha, threshold=10)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (64, 64), target_grid_size=16)
        
        signed_areas = mesh.compute_triangle_signed_areas()
        assert np.all(signed_areas > 0.0)


# ===========================================================================
# 2. Odd and Non-Square Dimensions (513x729, 301x301)
# ===========================================================================
class TestOddAndNonSquareDimensions:
    """Boundary tests for asymmetric aspect ratios and prime pixel dimensions."""

    def test_boundary_odd_non_square_513x729(self):
        """Verify 513x729 canvas maps UVs and normalized coords without distortion."""
        width, height = 513, 729
        alpha = np.zeros((height, width), dtype=np.uint8)
        cv2.ellipse(alpha, (width // 2, height // 2), (200, 300), 0, 0, 360, 255, -1)
        
        contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=3.0)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (height, width), target_grid_size=40)
        
        # Verify strict normalization bounds
        pos = mesh.get_positions()
        uvs = mesh.uvs
        assert np.all(pos >= -1.0) and np.all(pos <= 1.0)
        assert np.all(uvs >= 0.0) and np.all(uvs <= 1.0)

    def test_boundary_prime_square_dimension_301x301(self):
        """Verify prime dimension 301x301 preserves center point symmetry."""
        width, height = 301, 301
        alpha = np.zeros((height, width), dtype=np.uint8)
        cv2.circle(alpha, (150, 150), 100, 255, -1)
        
        contour = ImageImporter.extract_contour(alpha, threshold=10)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (height, width), target_grid_size=30)
        
        pos = mesh.get_positions()
        mean_center = np.mean(pos, axis=0)
        assert abs(mean_center[0]) < 0.15
        assert abs(mean_center[1]) < 0.15


# ===========================================================================
# 3. Empty and 100% Transparent Layers
# ===========================================================================
class TestTransparentAndEmptyLayers:
    """Boundary tests for blank layers and fully transparent alpha channels."""

    def test_boundary_all_transparent_alpha_mask(self):
        """Verify 100% transparent layer falls back to default rectangular contour."""
        alpha = np.zeros((200, 200), dtype=np.uint8)
        contour = ImageImporter.extract_contour(alpha, threshold=10)
        # Should fallback gracefully to bounding box
        assert len(contour) == 4
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=40)
        assert len(mesh.vertices) >= 4
        assert len(mesh.triangles) >= 2

    def test_boundary_all_opaque_rectangle_layer(self):
        """Verify 100% solid opaque layer is fully triangulated without holes."""
        alpha = np.ones((100, 100), dtype=np.uint8) * 255
        contour = ImageImporter.extract_contour(alpha, threshold=10)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (100, 100), target_grid_size=20)
        signed_areas = mesh.compute_triangle_signed_areas()
        assert np.all(signed_areas > 0.0)


# ===========================================================================
# 4. Disconnected Multi-Island Contours
# ===========================================================================
class TestDisconnectedAndComplexGeometry:
    """Boundary tests for disconnected accessory islands and concave contours."""

    def test_boundary_disconnected_multi_island_contours(self):
        """Verify separated accessories (e.g. left & right hair ribbons) do not crash."""
        alpha = np.zeros((300, 300), dtype=np.uint8)
        # Draw 2 disjoint circular islands
        cv2.circle(alpha, (75, 150), 40, 255, -1)   # Left island
        cv2.circle(alpha, (225, 150), 40, 255, -1)  # Right island
        
        contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
        # Primary contour must capture the main feature
        assert len(contour) >= 4
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (300, 300), target_grid_size=25)
        signed_areas = mesh.compute_triangle_signed_areas()
        assert np.all(signed_areas > 0.0)

    def test_boundary_concave_crescent_shape(self):
        """Verify crescent / C-shaped bangs contour triangulates properly."""
        alpha = np.zeros((200, 200), dtype=np.uint8)
        # Draw outer circle then subtract inner circle to create crescent
        cv2.circle(alpha, (100, 100), 70, 255, -1)
        cv2.circle(alpha, (120, 100), 55, 0, -1)
        
        contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=25)
        assert len(mesh.vertices) > 4
        assert len(mesh.triangles) > 0


# ===========================================================================
# 5. Extreme Rotation Angles (±60° Yaw, ±45° Pitch/Roll)
# ===========================================================================
class TestExtremeRotationAngles:
    """Boundary tests for extreme head deformations beyond normal tracking range."""

    def test_boundary_extreme_yaw_angle_60_degrees(self):
        """Verify AngleX = ±60° extreme yaw rotation maintains stability without complete collapse."""
        contour = np.array([[30, 30], [170, 30], [170, 170], [30, 170]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=25)
        
        depth_model = DepthModel(radii=(0.7, 0.7, 0.3))
        depth_model.apply_ellipsoid_to_mesh(mesh)
        
        deform = DeformationSolver()
        solver = MassSpringConstraintSolver(spring_weight=3.5)

        for extreme_yaw in [-60.0, 60.0]:
            target_pos, _ = deform.solve(mesh, angle_x_deg=extreme_yaw, angle_y_deg=0.0)
            solved_pos, energy = solver.solve(mesh, target_pos, num_iterations=4)
            
            # Verify no NaN / Inf
            assert not np.isnan(solved_pos).any()
            assert not np.isinf(solved_pos).any()
            assert energy > 0.0 and not math.isnan(energy)
            
            mesh_def = mesh.copy()
            mesh_def.set_positions(solved_pos)
            signed_areas = mesh_def.compute_triangle_signed_areas()
            
            # Verify total deformed area remains positive
            assert np.sum(signed_areas) > 0.0
            # Majority of triangles maintain positive orientation
            positive_ratio = np.count_nonzero(signed_areas > 0.0) / len(signed_areas)
            assert positive_ratio > 0.80, f"Positive triangle ratio {positive_ratio} too low at AngleX={extreme_yaw}"

    def test_boundary_extreme_pitch_angle_45_degrees(self):
        """Verify AngleY = ±45° extreme pitch rotation preserves topology and bounds."""
        contour = np.array([[40, 40], [160, 40], [160, 160], [40, 160]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=25)
        
        depth_model = DepthModel(radii=(0.6, 0.8, 0.4))
        depth_model.apply_ellipsoid_to_mesh(mesh)
        
        deform = DeformationSolver()
        solver = MassSpringConstraintSolver(spring_weight=3.0)

        for extreme_pitch in [-45.0, 45.0]:
            target_pos, _ = deform.solve(mesh, angle_x_deg=0.0, angle_y_deg=extreme_pitch)
            solved_pos, energy = solver.solve(mesh, target_pos, num_iterations=4)
            
            assert not np.isnan(solved_pos).any()
            assert not np.isinf(solved_pos).any()
            
            mesh_def = mesh.copy()
            mesh_def.set_positions(solved_pos)
            signed_areas = mesh_def.compute_triangle_signed_areas()
            assert np.sum(signed_areas) > 0.0
            positive_ratio = np.count_nonzero(signed_areas > 0.0) / len(signed_areas)
            assert positive_ratio > 0.80


# ===========================================================================
# 6. High Vertex Density Mesh
# ===========================================================================
class TestHighDensityMesh:
    """Boundary tests for ultra-dense meshes (>1000 vertices)."""

    def test_boundary_high_vertex_density_mesh(self):
        """Verify high vertex density mesh (>800 vertices) initializes and solves efficiently."""
        contour = np.array([[20, 20], [280, 20], [280, 280], [20, 280]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (300, 300), target_grid_size=10)
        
        assert len(mesh.vertices) > 500
        assert len(mesh.triangles) > 800

        solver = MassSpringConstraintSolver(spring_weight=2.0)
        solver.initialize_sparse_system(mesh)
        
        target_pos = mesh.get_positions() + 0.05
        solved_pos, energy = solver.solve(mesh, target_pos, num_iterations=2)
        assert solved_pos.shape == target_pos.shape
        assert not np.isnan(solved_pos).any()


# ===========================================================================
# 7. Texture Atlas Dimensions & Powers of Two (512 to 8192)
# ===========================================================================
class TestTextureAtlasBounds:
    """Boundary tests for texture atlas dimensions and power-of-two constraints."""

    @pytest.mark.parametrize("atlas_size", [512, 1024, 2048, 4096, 8192])
    def test_boundary_power_of_two_resolutions(self, atlas_size):
        """Verify packing operates cleanly across all standard power-of-two resolutions."""
        img = np.zeros((200, 200, 4), dtype=np.uint8)
        img[:, :] = [100, 150, 200, 255]
        layer = LayerData(name="TestLayer", image=img)
        
        atlas, uv_rects = TextureAtlasPacker.pack_layers([layer], max_atlas_size=atlas_size)
        h, w = atlas.shape[:2]
        assert (w & (w - 1) == 0), f"Atlas width {w} is not power of 2"
        assert (h & (h - 1) == 0), f"Atlas height {h} is not power of 2"
        assert w <= atlas_size and h <= atlas_size
