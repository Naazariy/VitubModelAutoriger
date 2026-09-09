import pytest
import numpy as np
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator
from src.depth.depth_model import DepthModel
from src.geometry.geometry_engine import GeometryEngine

def test_geometry_engine_normals_and_depth():
    rgba, alpha = ImageImporter.create_synthetic_head_image(256, 256)
    contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
    mesh = MeshGenerator.generate_mesh_from_contour(contour, (256, 256), target_grid_size=25)

    depth_model = DepthModel(center=(0.0, 0.0), radii=(0.6, 0.8, 0.4))
    depth_model.apply_ellipsoid_to_mesh(mesh)

    GeometryEngine.update_mesh_normals_and_geometry(
        mesh,
        ((depth_model.center_x, depth_model.center_y),
         (depth_model.radius_x, depth_model.radius_y, depth_model.radius_z))
    )

    # Check normal vectors are unit length
    normals = mesh.get_normals()
    norms = np.linalg.norm(normals, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)

    # Check center vertex depth is non-zero
    depths = mesh.get_depths()
    assert np.max(depths) > 0.1
