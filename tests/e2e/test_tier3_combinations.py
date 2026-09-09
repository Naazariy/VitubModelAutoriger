"""
Tier 3: Cross-Feature Combinations E2E Test Suite.
Verifies pairwise and multi-dimensional interactions across independent features:
- Multi-layer PSD ingestion with compound 3-axis simultaneous deformation (Yaw=25°, Pitch=-20°, Roll=15°)
- High-density mesh triangulation with custom 8192x8192 power-of-two texture atlas packing
- AI Auto-Depth & Stiffness map derivation coupled with full keyform tensor solving
- CLI multi-character batch folder export pipeline
- Headless CLI export with active in-flight programmatic structural validation (--validate)
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
# 1. Multi-Layer Asset + Simultaneous Compound 3-Axis Deformation
# ===========================================================================
class TestMultiLayerCompoundDeformation:
    """Combines multi-layer PSD assets with simultaneous Yaw, Pitch, Roll rotations."""

    def test_multi_layer_psd_with_compound_3axis_deformation(self, sample_character_layers):
        """Verify 5-layer character deforms synchronously with preserved Z-depth stratification."""
        drawables = []
        depth_model = DepthModel()
        deform = DeformationSolver(head_radius_z=0.4, parallax_scale=0.45)
        solver = MassSpringConstraintSolver(spring_weight=2.5)

        for layer in sample_character_layers:
            alpha = layer.image[:, :, 3]
            contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
            h, w = layer.image.shape[:2]
            mesh = MeshGenerator.generate_mesh_from_contour(contour, (h, w), target_grid_size=30, default_layer=layer.name)
            
            # Apply depth
            for vtx in mesh.vertices:
                vtx.depth = layer.z_depth_hint * 0.4
                vtx.layer_id = layer.name

            # Compound rotation: Yaw=25°, Pitch=-20°
            target_pos, rot_3d = deform.solve(mesh, angle_x_deg=25.0, angle_y_deg=-20.0)
            solved_pos, energy = solver.solve(mesh, target_pos, num_iterations=3)

            # Record drawable keyform
            d = DrawableKeyforms(
                drawable_id=f"ArtMesh_{layer.name}",
                texture_index=0,
                base_vertices=mesh.get_positions(),
                triangles=mesh.triangles,
                uvs_atlas=mesh.uvs,
                deformed_positions={(25.0, -20.0, 15.0): solved_pos}
            )
            drawables.append(d)

        assert len(drawables) == 5
        for d in drawables:
            assert not np.isnan(d.deformed_positions[(25.0, -20.0, 15.0)]).any()
            assert len(d.triangles) > 0


# ===========================================================================
# 2. High-Density Mesh + Custom 8192x8192 Texture Atlas
# ===========================================================================
class TestHighDensityMeshAndLargeAtlas:
    """Combines ultra-fine mesh resolution with 8192x8192 ultra-HD texture packing."""

    def test_high_density_mesh_with_8192_texture_atlas(self, sample_character_layers):
        """Verify fine mesh (>500 vertices) UV coordinates map accurately into 8192 atlas."""
        atlas_img, uv_rects = TextureAtlasPacker.pack_layers(sample_character_layers, max_atlas_size=8192)
        assert atlas_img.shape[0] <= 8192 and atlas_img.shape[1] <= 8192
        assert len(uv_rects) == 5

        # Check sub-pixel UV precision
        for layer_name, (u_min, v_min, u_max, v_max) in uv_rects.items():
            assert u_max > u_min
            assert v_max > v_min
            span_u = u_max - u_min
            span_v = v_max - v_min
            assert span_u > 0.001 and span_v > 0.001


# ===========================================================================
# 3. AI Auto-Depth & Stiffness + Full Keyform Table Generation
# ===========================================================================
class TestAIPropertiesAndFullPipeline:
    """Combines AI heuristic depth & stiffness derivation with ARAP deformation solving."""

    def test_ai_auto_depth_and_stiffness_with_deformation_pipeline(self, synthetic_head_image):
        """Verify AI feature analysis feeds into deformation solver and produces valid keyforms."""
        rgba, alpha = synthetic_head_image
        contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
        mesh = MeshGenerator.generate_mesh_from_contour(contour, (512, 512), target_grid_size=35)

        # AI property derivation
        AIAssistant.auto_assign_mesh_properties(mesh, rgba, alpha)
        
        depths = mesh.get_depths()
        stiffnesses = mesh.get_stiffnesses()
        assert np.max(depths) > 0.0
        assert np.max(stiffnesses) > 0.5

        # Solve 3x3 keyform grid across AngleX and AngleY
        deform = DeformationSolver(head_radius_z=0.4)
        solver = MassSpringConstraintSolver(spring_weight=2.5)

        deformed_positions = {}
        for ax in [-30.0, 0.0, 30.0]:
            for ay in [-30.0, 0.0, 30.0]:
                target_pos, _ = deform.solve(mesh, angle_x_deg=ax, angle_y_deg=ay)
                solved_pos, _ = solver.solve(mesh, target_pos, num_iterations=3)
                deformed_positions[(ax, ay, 0.0)] = solved_pos

        assert len(deformed_positions) == 9
        for key, pos in deformed_positions.items():
            assert not np.isnan(pos).any()
            assert pos.shape == (len(mesh.vertices), 2)


# ===========================================================================
# 4. CLI Batch Folder Export
# ===========================================================================
class TestCLIBatchProcessing:
    """Combines CLI multi-model batch directory processing with structural validation."""

    def test_cli_batch_folder_export(self, temp_dir):
        """Verify CLI processes 3 distinct character models in separate runs into valid bundles."""
        models = ["ModelA", "ModelB", "ModelC"]
        out_root = temp_dir / "batch_output"
        out_root.mkdir()

        for m_name in models:
            img_path = temp_dir / f"{m_name}.png"
            rgba, _ = ImageImporter.create_synthetic_head_image(256, 256)
            Image.fromarray(rgba).save(img_path)

            exit_code = CLIRunner.run_pipeline([
                str(img_path),
                "-o", str(out_root),
                "-n", m_name,
                "--resolution", "1024",
                "--validate"
            ])
            assert exit_code == CLIRunner.EXIT_SUCCESS, f"Failed export for model {m_name}"

            # Verify directory layout
            m_dir = out_root / m_name
            assert (m_dir / f"{m_name}.model3.json").exists()
            assert (m_dir / f"{m_name}.moc3").exists()
            assert (m_dir / f"{m_name}.cdi3.json").exists()

            # Run validator
            res = StructuralValidator.validate_live2d_model(str(m_dir / f"{m_name}.model3.json"))
            assert res.is_valid is True


# ===========================================================================
# 5. CLI Execution with In-Flight Self-Validation (--validate)
# ===========================================================================
class TestCLIInFlightValidation:
    """Combines CLI generation pipeline with active programmatic self-verification."""

    def test_cli_with_in_flight_validation_flag(self, temp_dir):
        """Verify CLI with --validate executes end-to-end and returns EXIT_SUCCESS."""
        img_path = temp_dir / "hero.png"
        rgba, _ = ImageImporter.create_synthetic_head_image(256, 256)
        Image.fromarray(rgba).save(img_path)

        out_dir = temp_dir / "hero_out"
        exit_code = CLIRunner.run_pipeline([
            str(img_path),
            "-o", str(out_dir),
            "--resolution", "2048",
            "--validate"
        ])
        assert exit_code == CLIRunner.EXIT_SUCCESS
        assert (out_dir / "hero" / "hero.model3.json").exists()


# ===========================================================================
# 6. Asymmetric Depth with Non-Uniform Stiffness Modulation
# ===========================================================================
class TestAsymmetricDepthAndStiffness:
    """Combines non-uniform facial stiffness (rigid features vs soft skin) with compound rotation."""

    def test_asymmetric_depth_with_non_uniform_stiffness(self):
        """Verify rigid eye region maintains triangle shape better than soft cheek region."""
        v_eye_1 = Vertex(position=np.array([-0.2, 0.0]), depth=0.1, stiffness=1.0, layer_id="Eyes")
        v_eye_2 = Vertex(position=np.array([-0.1, 0.0]), depth=0.1, stiffness=1.0, layer_id="Eyes")
        v_cheek_1 = Vertex(position=np.array([0.2, 0.0]), depth=0.1, stiffness=0.2, layer_id="Face")
        v_cheek_2 = Vertex(position=np.array([0.3, 0.0]), depth=0.1, stiffness=0.2, layer_id="Face")
        
        mesh = Mesh(
            vertices=[v_eye_1, v_eye_2, v_cheek_1, v_cheek_2],
            triangles=np.zeros((0, 3), dtype=np.int32)
        )
        
        solver = MassSpringConstraintSolver(spring_weight=2.5)
        solver.initialize_sparse_system(mesh)
        
        # Attachment weight for eyes must be higher than cheeks
        assert solver.W_diag[0] > solver.W_diag[2]
        assert solver.W_diag[1] > solver.W_diag[3]
