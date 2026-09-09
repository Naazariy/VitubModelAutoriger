import unittest
import sys
import os

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from tests.test_mesh_generator import test_mesh_generation_synthetic
from tests.test_geometry_engine import test_geometry_engine_normals_and_depth
from tests.test_deformation_solver import test_deformation_solver_identity_and_parallax
from tests.test_constraint_solver import test_mass_spring_constraint_solver_monotonic_energy_and_noninversion
from tests.test_renderer_occlusion import test_renderer_zbuffer_occlusion_correctness

class TestVTuberGeometryDeformation(unittest.TestCase):

    def test_01_mesh_generation(self):
        print("Running test_01_mesh_generation...")
        test_mesh_generation_synthetic()

    def test_02_geometry_engine(self):
        print("Running test_02_geometry_engine...")
        test_geometry_engine_normals_and_depth()

    def test_03_deformation_solver(self):
        print("Running test_03_deformation_solver...")
        test_deformation_solver_identity_and_parallax()

    def test_04_constraint_solver(self):
        print("Running test_04_constraint_solver...")
        test_mass_spring_constraint_solver_monotonic_energy_and_noninversion()

    def test_05_renderer_occlusion(self):
        print("Running test_05_renderer_occlusion...")
        test_renderer_zbuffer_occlusion_correctness()

if __name__ == "__main__":
    unittest.main()
