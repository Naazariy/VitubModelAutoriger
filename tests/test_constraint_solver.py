import pytest
import numpy as np
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator
from src.depth.depth_model import DepthModel
from src.deformation.deformation_solver import DeformationSolver
from src.constraints.constraint_solver import MassSpringConstraintSolver

def test_mass_spring_constraint_solver_monotonic_energy_and_noninversion():
    rgba, alpha = ImageImporter.create_synthetic_head_image(256, 256)
    contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
    mesh = MeshGenerator.generate_mesh_from_contour(contour, (256, 256), target_grid_size=25)

    depth_model = DepthModel()
    depth_model.apply_ellipsoid_to_mesh(mesh)

    deform_solver = DeformationSolver()
    constraint_solver = MassSpringConstraintSolver(spring_weight=2.5)

    # Project for small AngleX rotation delta = 5°
    proj_target, _ = deform_solver.solve(mesh, 5.0, 0.0)

    # Solve iteratively and track energy per iteration
    energies = []
    curr_pos = proj_target.copy()

    for iter_step in range(1, 6):
        curr_pos, E = constraint_solver.solve(mesh, proj_target, num_iterations=iter_step)
        energies.append(E)

    # 1. Verify monotonic energy reduction / convergence for small rotation
    for i in range(len(energies) - 1):
        assert energies[i+1] <= energies[i] + 1e-4

    # 2. Verify triangle non-inversion (signed triangle areas > -1e-5)
    mesh_copy = mesh.copy()
    mesh_copy.set_positions(curr_pos)
    signed_areas = mesh_copy.compute_triangle_signed_areas()
    assert np.all(signed_areas > -1e-4)

def test_extreme_rotation_anglex_minus_30_arap_rigidity():
    rgba, alpha = ImageImporter.create_synthetic_head_image(256, 256)
    contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
    mesh = MeshGenerator.generate_mesh_from_contour(contour, (256, 256), target_grid_size=25)

    depth_model = DepthModel()
    depth_model.apply_ellipsoid_to_mesh(mesh)

    deform_solver = DeformationSolver()
    constraint_solver = MassSpringConstraintSolver(spring_weight=2.5)

    # Project for extreme rotation AngleX = -30°
    proj_target, _ = deform_solver.solve(mesh, -30.0, 0.0)
    solved_pos, E = constraint_solver.solve(mesh, proj_target, num_iterations=4)

    # Calculate total mesh area before and after deformation
    mesh_rest = mesh.copy()
    initial_areas = mesh_rest.compute_triangle_signed_areas()
    total_initial_area = np.sum(initial_areas)

    mesh_deformed = mesh.copy()
    mesh_deformed.set_positions(solved_pos)
    deformed_areas = mesh_deformed.compute_triangle_signed_areas()
    total_deformed_area = np.sum(deformed_areas)

    # 1. Verify no inverted triangles under extreme -30° rotation
    assert np.all(deformed_areas > -1e-4)

    # 2. Verify volume/area loss is bounded (mesh does not collapse to 0)
    area_ratio = total_deformed_area / total_initial_area
    assert area_ratio > 0.65  # Preserves at least 65% of 2D area under 30° turn
