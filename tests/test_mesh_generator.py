import pytest
import numpy as np
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator
from src.core.mesh import Mesh
from src.core.layer import LayerData


class TestMeshGenerator:
    """Comprehensive unit test suite for Pure-Python SciPy Delaunay Mesh Generator."""

    def test_mesh_generation_synthetic_head(self):
        rgba, alpha = ImageImporter.create_synthetic_head_image(256, 256)
        contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
        assert len(contour) >= 3
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (256, 256), target_grid_size=25)

        assert len(mesh.vertices) > 10
        assert len(mesh.triangles) > 10
        assert len(mesh.edges) > 0
        assert len(mesh.uvs) == len(mesh.vertices)
        
        # Check topological integrity
        is_valid, errors = mesh.validate_topology()
        assert is_valid, f"Topology validation errors: {errors}"

    def test_positive_signed_areas(self):
        rgba, alpha = ImageImporter.create_synthetic_head_image(128, 128)
        contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (128, 128), target_grid_size=20)

        areas = mesh.compute_triangle_signed_areas()
        assert len(areas) > 0
        # All triangles must have strictly positive signed area (CCW winding order)
        assert np.all(areas > 1e-6), f"Found non-positive triangle areas: {areas[areas <= 1e-6]}"

    def test_rectangular_mesh_generation(self):
        rect_contour = np.array([[20.0, 20.0], [100.0, 20.0], [100.0, 80.0], [20.0, 80.0]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(rect_contour, (100, 120), target_grid_size=15)

        assert len(mesh.vertices) >= 4
        assert len(mesh.triangles) >= 2

        # Verify all UVs within [0.0, 1.0]
        assert np.all(mesh.uvs >= 0.0) and np.all(mesh.uvs <= 1.0)

        # Verify normalized vertex positions within [-1.0, 1.0]
        positions = mesh.get_positions()
        assert np.all(positions >= -1.0) and np.all(positions <= 1.0)

    def test_concave_horseshoe_filtering(self):
        # U-shape / horseshoe polygon with deep cavity
        u_contour = np.array([
            [10.0, 10.0], [90.0, 10.0], [90.0, 90.0], [60.0, 90.0],
            [60.0, 40.0], [40.0, 40.0], [40.0, 90.0], [10.0, 90.0]
        ], dtype=np.float64)

        mesh = MeshGenerator.generate_mesh_from_contour(u_contour, (100, 100), target_grid_size=10)
        assert len(mesh.triangles) > 0

        # Verify that no triangle centroid falls inside the exterior cavity ((42, 58) x (42, 90))
        positions = mesh.get_positions()
        pixel_x = (positions[:, 0] + 1.0) * 50.0
        pixel_y = (positions[:, 1] + 1.0) * 50.0

        for tri in mesh.triangles:
            cx = float(np.mean(pixel_x[tri]))
            cy = float(np.mean(pixel_y[tri]))
            in_cavity = (42.0 < cx < 58.0) and (42.0 < cy < 90.0)
            assert not in_cavity, f"Exterior triangle centroid leaked into concave cavity at ({cx:.1f}, {cy:.1f})"

    def test_boundary_vertex_pinning(self):
        angles = np.linspace(0, 2 * np.pi, 16, endpoint=False)
        circle_contour = np.column_stack([
            50.0 + 30.0 * np.cos(angles),
            50.0 + 30.0 * np.sin(angles)
        ])

        mesh_unsmoothed = MeshGenerator.generate_mesh_from_contour(
            circle_contour, (100, 100), target_grid_size=15, smoothing_iterations=0
        )
        mesh_smoothed = MeshGenerator.generate_mesh_from_contour(
            circle_contour, (100, 100), target_grid_size=15, smoothing_iterations=5
        )

        pos_unsmoothed = mesh_unsmoothed.get_positions()
        pos_smoothed = mesh_smoothed.get_positions()

        # The first 16 boundary vertices must match exactly
        np.testing.assert_allclose(pos_smoothed[:16], pos_unsmoothed[:16], atol=1e-5)

    def test_duplicate_vertex_pruning(self):
        redundant_contour = np.array([
            [10.0, 10.0], [10.0, 10.0], [80.0, 10.0], [80.0, 80.0], [80.0, 80.0], [10.0, 80.0]
        ], dtype=np.float64)

        mesh = MeshGenerator.generate_mesh_from_contour(redundant_contour, (100, 100), target_grid_size=20)
        assert len(mesh.vertices) >= 4
        assert len(mesh.triangles) >= 2

        # Verify no unreferenced vertices
        used_indices = set(mesh.triangles.flatten())
        assert len(used_indices) == len(mesh.vertices)

    def test_generate_from_alpha_mask(self):
        alpha = np.zeros((120, 120), dtype=np.uint8)
        y, x = np.ogrid[:120, :120]
        mask = (x - 60)**2 + (y - 60)**2 <= 40**2
        alpha[mask] = 255

        mesh = MeshGenerator.generate_mesh_from_alpha_mask(alpha, target_grid_size=15)
        assert len(mesh.vertices) > 0
        assert len(mesh.triangles) > 0
        assert np.all(mesh.compute_triangle_signed_areas() > 1e-6)

    def test_generate_from_layer(self):
        img = np.zeros((100, 100, 4), dtype=np.uint8)
        img[20:80, 20:80, :3] = 255
        img[20:80, 20:80, 3] = 255
        layer = LayerData(name="Hair_Front", image=img, z_depth_hint=0.5)

        mesh = MeshGenerator.generate_mesh_from_layer(layer, target_grid_size=20)
        assert mesh.layer_id == "Hair_Front"
        assert len(mesh.vertices) > 0
        assert len(mesh.triangles) > 0
        assert np.all(mesh.compute_triangle_signed_areas() > 1e-6)

    def test_degenerate_contour_fallback(self):
        empty_contour = np.zeros((0, 2), dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(empty_contour, (100, 100), target_grid_size=25)

        assert len(mesh.vertices) >= 4
        assert len(mesh.triangles) >= 2

    def test_edge_rebuild_and_rest_lengths(self):
        rect_contour = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(rect_contour, (10, 10), target_grid_size=10)

        assert len(mesh.edges) > 0
        assert len(mesh.rest_edge_lengths) == len(mesh.edges)
        assert np.all(mesh.rest_edge_lengths > 0.0)

    def test_pure_python_distance_fallback(self):
        poly = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]], dtype=np.float64)

        inside_pt = (5.0, 5.0)
        outside_pt = (15.0, 5.0)

        d_in = MeshGenerator._point_polygon_test_pure_python(poly, inside_pt)
        d_out = MeshGenerator._point_polygon_test_pure_python(poly, outside_pt)

        assert d_in > 0.0
        assert d_out < 0.0
        assert abs(d_in - 5.0) < 1e-3
        assert abs(d_out - (-5.0)) < 1e-3

    def test_synthetic_layered_head_all_layers_topology_all_grids(self):
        """
        Iterates over all 14 layers of create_synthetic_layered_head(512, 512)
        across grid sizes [10, 15, 20, 25, 30], asserting mesh.validate_topology()
        returns (True, []) and np.all(mesh.compute_triangle_signed_areas() > 1e-6).
        """
        layers = ImageImporter.create_synthetic_layered_head(512, 512)
        assert len(layers) == 14
        grid_sizes = [10, 15, 20, 25, 30]

        for grid_size in grid_sizes:
            for layer in layers:
                mesh = MeshGenerator.generate_mesh_from_layer(layer, target_grid_size=grid_size)
                is_valid, errors = mesh.validate_topology()
                assert is_valid, f"Topology invalid for layer '{layer.name}' at grid_size={grid_size}: {errors}"
                areas = mesh.compute_triangle_signed_areas()
                assert len(areas) > 0, f"No triangles generated for layer '{layer.name}' at grid_size={grid_size}"
                assert np.all(areas > 1e-6), (
                    f"Non-positive or degenerate triangle in layer '{layer.name}' at grid_size={grid_size}: "
                    f"min area = {np.min(areas):.2e}"
                )

