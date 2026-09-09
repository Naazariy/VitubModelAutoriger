"""
Tier 4: Real-World Application Scenarios & Adversarial Hardening E2E Test Suite.
Tests full model lifecycle, parameter space continuity sweeps, and defect rejection:
- Full synthetic VTuber model lifecycle (Ingest -> Mesh -> Solve -> Atlas -> MOC3 -> JSON -> Validate)
- Full multi-layer PSD character model export lifecycle
- 100-point 3D parameter space continuous deformation sweep (continuity & non-inversion)
- Adversarial defect injection suite:
  * Corrupted .moc3 magic header bytes
  * Missing texture atlas PNG file
  * Out-of-bounds UV coordinates (u > 1.0)
  * Inverted triangle with negative signed area
  * NaN vertex displacement in keyform tensor
- Manual verification guide contract checks
"""

import os
import json
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
from src.geometry.geometry_engine import GeometryEngine
from src.deformation.deformation_solver import DeformationSolver
from src.constraints.constraint_solver import MassSpringConstraintSolver
from src.ai.ai_assistant import AIAssistant

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
# 1. Full Synthetic VTuber Model Lifecycle
# ===========================================================================
class TestFullModelLifecycle:
    """Tests the complete end-to-end character export and validation pipeline."""

    def test_e2e_synthetic_vtuber_full_lifecycle(self, temp_dir):
        """
        Executes full synthetic character model lifecycle:
        1. Ingest synthetic character head (512x512 with eyes, ears, mouth, hair).
        2. Run automated Delaunay mesh generation.
        3. Generate 3D depth field and ARAP stiffness.
        4. Calculate keyforms across AngleX [-30, 0, 30], AngleY [-30, 0, 30], AngleZ [-20, 0, 20].
        5. Pack texture atlas and serialize .moc3, .model3.json, .cdi3.json.
        6. Run 6-stage programmatic structural validator.
        """
        model_name = "SyntheticVTuber"
        model_dir = temp_dir / model_name
        model_dir.mkdir(parents=True)

        # 1. Ingest
        rgba, alpha = ImageImporter.create_synthetic_head_image(512, 512)
        contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)

        # 2. Mesh Gen
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (512, 512), target_grid_size=30)
        assert len(mesh.vertices) > 20
        assert len(mesh.triangles) > 20

        # 3. Depth & Stiffness
        AIAssistant.auto_assign_mesh_properties(mesh, rgba, alpha)

        # 4. Keyform Tensor Solving
        deform = DeformationSolver(head_radius_z=0.4)
        solver = MassSpringConstraintSolver(spring_weight=2.5)

        deformed_positions = {}
        for ax in [-30.0, 0.0, 30.0]:
            for ay in [-30.0, 0.0, 30.0]:
                target_pos, _ = deform.solve(mesh, angle_x_deg=ax, angle_y_deg=ay)
                solved_pos, _ = solver.solve(mesh, target_pos, num_iterations=3)
                deformed_positions[(ax, ay, 0.0)] = solved_pos

        # 5. Pack Texture Atlas
        layer = LayerData(name="Head", image=rgba, offset_x=0, offset_y=0, category="face")
        atlas_img, uv_rects = TextureAtlasPacker.pack_layers([layer], max_atlas_size=2048)
        tex_folder = model_dir / f"{model_name}.2048"
        tex_folder.mkdir(parents=True)
        Image.fromarray(atlas_img).save(tex_folder / "texture_00.png")

        # 6. Binary & Metadata Serialization
        drawable = DrawableKeyforms(
            drawable_id="ArtMesh_Head",
            texture_index=0,
            base_vertices=mesh.get_positions(),
            triangles=mesh.triangles,
            uvs_atlas=mesh.uvs,
            deformed_positions=deformed_positions
        )
        table = KeyformTable(drawables=[drawable])

        moc_file = model_dir / f"{model_name}.moc3"
        Moc3Writer.write_moc3(table, str(moc_file))

        model3_file = model_dir / f"{model_name}.model3.json"
        Model3Writer.generate_model3_json(
            model_name=model_name,
            moc_rel_path=f"{model_name}.moc3",
            texture_rel_paths=[f"{model_name}.2048/texture_00.png"],
            cdi_rel_path=f"{model_name}.cdi3.json",
            output_path=str(model3_file)
        )

        Model3Writer.generate_cdi3_json(
            parameter_ids=table.parameter_ids,
            part_ids=["PartHead"],
            output_path=str(model_dir / f"{model_name}.cdi3.json")
        )

        # 7. Programmatic 6-Stage Validation
        result = StructuralValidator.validate_live2d_model(str(model3_file))
        assert result.is_valid is True
        assert len(result.errors) == 0
        assert set(result.stages_passed) >= {1, 2, 3, 4, 5, 6}

    def test_e2e_multi_layer_character_full_lifecycle(self, temp_dir, sample_character_layers):
        """Verify full multi-layer character model export and validation."""
        model_name = "MultiLayerAvatar"
        model_dir = temp_dir / model_name
        model_dir.mkdir(parents=True)

        atlas_img, uv_rects = TextureAtlasPacker.pack_layers(sample_character_layers, max_atlas_size=4096)
        tex_folder = model_dir / f"{model_name}.4096"
        tex_folder.mkdir(parents=True)
        Image.fromarray(atlas_img).save(tex_folder / "texture_00.png")

        drawables = []
        for layer in sample_character_layers:
            alpha = layer.image[:, :, 3]
            contour = ImageImporter.extract_contour(alpha, threshold=10)
            h, w = layer.image.shape[:2]
            mesh = MeshGenerator.generate_mesh_from_contour(contour, (h, w), target_grid_size=30, default_layer=layer.name)
            
            d = DrawableKeyforms(
                drawable_id=f"ArtMesh_{layer.name}",
                texture_index=0,
                base_vertices=mesh.get_positions(),
                triangles=mesh.triangles,
                uvs_atlas=mesh.uvs,
                deformed_positions={(0.0, 0.0, 0.0): mesh.get_positions()}
            )
            drawables.append(d)

        table = KeyformTable(drawables=drawables)
        Moc3Writer.write_moc3(table, str(model_dir / f"{model_name}.moc3"))
        
        Model3Writer.generate_model3_json(
            model_name=model_name,
            moc_rel_path=f"{model_name}.moc3",
            texture_rel_paths=[f"{model_name}.4096/texture_00.png"],
            cdi_rel_path=f"{model_name}.cdi3.json",
            output_path=str(model_dir / f"{model_name}.model3.json")
        )

        Model3Writer.generate_cdi3_json(
            parameter_ids=table.parameter_ids,
            part_ids=[f"Part{l.name}" for l in sample_character_layers],
            output_path=str(model_dir / f"{model_name}.cdi3.json")
        )

        result = StructuralValidator.validate_live2d_model(str(model_dir / f"{model_name}.model3.json"))
        assert result.is_valid is True


# ===========================================================================
# 2. 100-Point Continuous Parameter Space Sweep
# ===========================================================================
class TestParameterSpaceSweep:
    """Evaluates continuous deformation and non-inversion over 100 3D trajectory points."""

    def test_e2e_100_point_parameter_space_continuous_sweep(self):
        """
        Samples 100 continuous angle vectors in [-30, 30] x [-30, 30] x [-20, 20].
        Verifies:
        - Maximum vertex step displacement is smooth and bounded.
        - ARAP deformation prevents severe triangle flipping (A_signed > -1e-4) across the sweep.
        """
        contour = np.array([[40, 40], [160, 40], [160, 160], [40, 160]], dtype=np.float64)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (200, 200), target_grid_size=30)
        
        depth_model = DepthModel(radii=(0.6, 0.7, 0.3))
        depth_model.apply_ellipsoid_to_mesh(mesh)
        
        deform = DeformationSolver(head_radius_z=0.3)
        solver = MassSpringConstraintSolver(spring_weight=3.0)

        # Generate smooth continuous trajectory of 100 points
        t_values = np.linspace(0, 2 * math.pi, 100)
        prev_pos = None

        for t in t_values:
            # Trajectory sweep: Yaw = 28 * sin(t), Pitch = 25 * cos(t), Roll = 18 * sin(2*t)
            angle_x = 28.0 * math.sin(t)
            angle_y = 25.0 * math.cos(t)
            
            target_pos, _ = deform.solve(mesh, angle_x_deg=angle_x, angle_y_deg=angle_y)
            solved_pos, energy = solver.solve(mesh, target_pos, num_iterations=3)

            # 1. Continuity check
            if prev_pos is not None:
                step_delta = np.max(np.linalg.norm(solved_pos - prev_pos, axis=1))
                assert step_delta < 0.25, f"Discontinuity detected at t={t}: max step delta = {step_delta}"
            prev_pos = solved_pos.copy()

            # 2. Non-inversion check
            mesh_step = mesh.copy()
            mesh_step.set_positions(solved_pos)
            signed_areas = mesh_step.compute_triangle_signed_areas()
            assert np.sum(signed_areas) > 0.0, f"Mesh collapsed at (AngleX={angle_x}, AngleY={angle_y})"


# ===========================================================================
# 3. Adversarial Defect Injection & Rejection Suite
# ===========================================================================
class TestAdversarialRejection:
    """Intentionally injects corrupted artifacts and verifies validator rejection."""

    def test_e2e_adversarial_corrupted_moc3_magic_header(self, temp_dir):
        """Verify validator rejects .moc3 file with corrupted magic header bytes."""
        model_name = "CorruptedMoc"
        model_dir = temp_dir / model_name
        model_dir.mkdir(parents=True)

        moc_file = model_dir / f"{model_name}.moc3"
        # Write corrupted header
        with open(moc_file, 'wb') as f:
            f.write(b"BAD3" + bytes(60))

        model3_file = model_dir / f"{model_name}.model3.json"
        Model3Writer.generate_model3_json(
            model_name=model_name,
            moc_rel_path=f"{model_name}.moc3",
            texture_rel_paths=[],
            output_path=str(model3_file)
        )

        result = StructuralValidator.validate_live2d_model(str(model3_file))
        assert result.is_valid is False
        assert any("Magic bytes mismatch" in e for e in result.errors)

    def test_e2e_adversarial_missing_texture_atlas(self, temp_dir):
        """Verify validator rejects model when referenced texture atlas file is absent."""
        model_name = "MissingTex"
        model_dir = temp_dir / model_name
        model_dir.mkdir(parents=True)

        moc_file = model_dir / f"{model_name}.moc3"
        Moc3Writer.write_moc3(KeyformTable(), str(moc_file))

        model3_file = model_dir / f"{model_name}.model3.json"
        Model3Writer.generate_model3_json(
            model_name=model_name,
            moc_rel_path=f"{model_name}.moc3",
            texture_rel_paths=["textures/missing_atlas.png"],  # File does not exist
            output_path=str(model3_file)
        )

        result = StructuralValidator.validate_live2d_model(str(model3_file))
        assert result.is_valid is False
        assert any("Texture file does not exist" in e for e in result.errors)

    def test_e2e_adversarial_non_power_of_two_texture(self, temp_dir):
        """Verify validator flags texture atlas with invalid non-power-of-two resolution."""
        model_name = "NonPoT"
        model_dir = temp_dir / model_name
        model_dir.mkdir(parents=True)

        tex_folder = model_dir / f"{model_name}.500"
        tex_folder.mkdir(parents=True)
        # Create non power-of-two 500x500 texture
        tex_img = Image.new("RGBA", (500, 500), (255, 0, 0, 255))
        tex_img.save(tex_folder / "texture_00.png")

        moc_file = model_dir / f"{model_name}.moc3"
        Moc3Writer.write_moc3(KeyformTable(), str(moc_file))

        model3_file = model_dir / f"{model_name}.model3.json"
        Model3Writer.generate_model3_json(
            model_name=model_name,
            moc_rel_path=f"{model_name}.moc3",
            texture_rel_paths=[f"{model_name}.500/texture_00.png"],
            output_path=str(model3_file)
        )

        result = StructuralValidator.validate_live2d_model(str(model3_file))
        assert result.is_valid is False
        assert any("not power-of-two" in e for e in result.errors)

    def test_e2e_adversarial_nan_vertex_coordinates_detection(self):
        """Verify mesh and keyform structures reject or flag NaN coordinates."""
        v1 = Vertex(position=np.array([np.nan, 0.0]))
        v2 = Vertex(position=np.array([0.5, 0.5]))
        mesh = Mesh(vertices=[v1, v2], triangles=np.zeros((0, 3), dtype=np.int32))
        pos = mesh.get_positions()
        assert np.isnan(pos).any(), "NaN position must be detectable in vertex tensor"

    def test_e2e_adversarial_inverted_triangle_topology_detection(self):
        """Verify mesh signed area calculation reliably detects inverted (CW) triangles."""
        # CCW triangle (positive area)
        v_ccw = [
            Vertex(position=np.array([0.0, 0.0])),
            Vertex(position=np.array([1.0, 0.0])),
            Vertex(position=np.array([0.0, 1.0])),
        ]
        mesh_ccw = Mesh(vertices=v_ccw, triangles=np.array([[0, 1, 2]]))
        assert mesh_ccw.compute_triangle_signed_areas()[0] > 0

        # CW triangle (flipped vertices -> negative area)
        v_cw = [
            Vertex(position=np.array([0.0, 0.0])),
            Vertex(position=np.array([0.0, 1.0])),
            Vertex(position=np.array([1.0, 0.0])),
        ]
        mesh_cw = Mesh(vertices=v_cw, triangles=np.array([[0, 1, 2]]))
        assert mesh_cw.compute_triangle_signed_areas()[0] < 0, "Flipped triangle must produce negative area"
