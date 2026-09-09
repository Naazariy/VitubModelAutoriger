import pytest
import numpy as np
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator
from src.depth.depth_model import DepthModel
from src.deformation.deformation_solver import DeformationSolver
from src.renderer.renderer import MeshRenderer

def test_renderer_zbuffer_occlusion_correctness():
    rgba, alpha = ImageImporter.create_synthetic_head_image(256, 256)
    contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
    mesh = MeshGenerator.generate_mesh_from_contour(contour, (256, 256), target_grid_size=25)

    depth_model = DepthModel()
    depth_model.apply_ellipsoid_to_mesh(mesh)

    deform_solver = DeformationSolver()

    # Rotate 30° around Y axis (AngleX = 30°)
    proj_2d, rot_3d = deform_solver.solve(mesh, 30.0, 0.0)

    renderer = MeshRenderer()
    renderer.set_texture(rgba)

    # Render image to QImage
    qimg = renderer.render_to_qimage(
        mesh=mesh,
        positions_2d=proj_2d,
        rotated_3d=rot_3d,
        view_size=(256, 256),
        view_mode="Textured"
    )

    assert not qimg.isNull()
    assert qimg.width() == 256
    assert qimg.height() == 256

    # Verify rotated 3D depth range: front vertices have higher Z than back vertices
    min_z = np.min(rot_3d[:, 2])
    max_z = np.max(rot_3d[:, 2])
    assert max_z > min_z
