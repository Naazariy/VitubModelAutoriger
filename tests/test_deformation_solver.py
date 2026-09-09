import pytest
import numpy as np
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator
from src.depth.depth_model import DepthModel
from src.deformation.deformation_solver import DeformationSolver

def test_deformation_solver_identity_and_parallax():
    rgba, alpha = ImageImporter.create_synthetic_head_image(256, 256)
    contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
    mesh = MeshGenerator.generate_mesh_from_contour(contour, (256, 256), target_grid_size=25)

    depth_model = DepthModel()
    depth_model.apply_ellipsoid_to_mesh(mesh)

    deform_solver = DeformationSolver()

    # 1. Identity deformation test at AngleX = 0, AngleY = 0
    proj_0, rot_3d_0 = deform_solver.solve(mesh, 0.0, 0.0)
    pos_orig = mesh.get_positions()
    
    # Vertices near center should be identical
    assert np.allclose(proj_0, pos_orig, atol=0.1)

    # 2. AngleX = 30° parallax shift test
    proj_30, rot_3d_30 = deform_solver.solve(mesh, 30.0, 0.0)
    
    # Vertices with positive depth should shift in +X direction during 30° rotation
    center_idx = np.argmax(mesh.get_depths())
    assert proj_30[center_idx, 0] != pos_orig[center_idx, 0]
