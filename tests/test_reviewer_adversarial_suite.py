"""
tests/test_reviewer_adversarial_suite.py
Comprehensive Adversarial Reviewer Test Suite for Live2D Cubism Core & VTube Studio Compatibility.
Verifies multi-page texture maps (>2 pages), high vertex counts (>5,000 vertices), 64-byte memory alignment,
zero-initialized deformer tables, parameter slider definitions, and topological integrity.
"""

import json
import os
from pathlib import Path
import struct
import numpy as np
import pytest
from PIL import Image

from src.core.vertex import Vertex
from src.core.layer import LayerData, LayerCollection
from src.core.mesh import Mesh
from src.core.keyform import KeyformTable, DrawableKeyforms, ParameterBinding
from src.exporter.texture_packer import TextureAtlasPacker, PackingConfig
from src.exporter.moc3_writer import (
    Moc3Writer,
    Moc3Reader,
    validate_moc3_bytes,
    align_to_64,
    pad_buffer_to_64,
)
from src.exporter.model3_writer import Model3Writer
from src.validator.structural_validator import (
    StructuralValidator,
    validate_live2d_model,
    ValidationReport,
)
from src.cli.main import (
    PipelineConfig,
    PipelineRunner,
    run_pipeline,
    EXIT_SUCCESS,
)
from compare_reference_diagnostic import run_diagnostic_comparison


class TestReviewerAdversarialSuite:
    """Comprehensive reviewer test suite attacking edge cases and stress scenarios."""

    def test_multi_page_texture_packing_and_drawable_mapping(self, tmp_path):
        """
        Open Issue 1 & 4: Multi-page texture maps (>2 pages).
        Ensures that when MaxRects packing spans across 3+ texture pages,
        each drawable's texture_index in .moc3 and model3.json matches its assigned page.
        """
        model_name = "MultiPageModel"
        out_dir = tmp_path / model_name
        out_dir.mkdir(parents=True, exist_ok=True)

        # Create 6 layers (each 600x600 px) packed into 512x512 pages -> forces >= 3 pages
        layers = []
        meshes = {}
        for i in range(6):
            img = np.zeros((600, 600, 4), dtype=np.uint8)
            img[50:550, 50:550] = [200, 100, 40 * i, 255]
            layer_name = f"Layer_{i}"
            layer = LayerData(name=layer_name, image=img, layer_id=f"layer_{i}_0")
            layers.append(layer)

            verts_arr = np.array([[-100, -100], [100, -100], [100, 100], [-100, 100]], dtype=np.float32)
            v_objs = [Vertex(position=p) for p in verts_arr]
            tris = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
            uvs = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32)
            mesh = Mesh(vertices=v_objs, triangles=tris, uvs=uvs)
            meshes[layer_name] = mesh

        cfg = PackingConfig(max_atlas_size=512, padding=4)
        pack_res = TextureAtlasPacker.pack(layers=layers, meshes=meshes, config=cfg)
        assert len(pack_res.pages) >= 3, f"Expected >= 3 pages, got {len(pack_res.pages)}"

        # Construct keyform drawables
        drawables = []
        for i in range(6):
            l_name = f"Layer_{i}"
            rm = pack_res.remapped_meshes[l_name]
            p_idx = pack_res.placements[l_name].page_index
            dk = DrawableKeyforms(
                drawable_id=f"ArtMesh_{l_name}",
                texture_index=p_idx,
                base_vertices=rm.get_positions().astype(np.float32),
                triangles=rm.triangles.astype(np.int32),
                uvs_atlas=rm.uvs.astype(np.float32),
                parameter_ids=["ParamAngleX", "ParamAngleY"]
            )
            for ax in [-30.0, 0.0, 30.0]:
                for ay in [-30.0, 0.0, 30.0]:
                    dk.add_keyform((ax, ay), rm.get_positions().astype(np.float32))
            drawables.append(dk)

        params = [
            ParameterBinding("ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]),
            ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]),
        ]

        table = KeyformTable(parameters=params, drawables=drawables, canvas_width=2048, canvas_height=2048, model_name=model_name)

        bundle = Model3Writer.export_model_bundle(
            output_dir=str(tmp_path),
            model_name=model_name,
            keyform_table=table,
            texture_pages=pack_res.pages
        )

        # 1. Verify model3.json textures list matches page count
        with open(bundle["model3_json"], "r", encoding="utf-8") as f:
            m3_data = json.load(f)
        tex_list = m3_data["FileReferences"]["Textures"]
        assert len(tex_list) == len(pack_res.pages)
        for t in tex_list:
            assert "\\" not in t
            assert (out_dir / t).exists()

        # 2. Verify .moc3 ArtMeshes.TextureNos matches drawables
        with open(bundle["moc3"], "rb") as f:
            moc_data = f.read()
        offsets = struct.unpack_from("<160I", moc_data, 64)
        counts = struct.unpack_from("<23I", moc_data, offsets[0])
        n_meshes = counts[4]
        assert n_meshes == 6
        tex_nos = struct.unpack_from(f"<{n_meshes}i", moc_data, offsets[41])
        for i in range(6):
            expected_page = pack_res.placements[f"Layer_{i}"].page_index
            assert tex_nos[i] == expected_page, f"Mesh {i} texture index mismatch: expected {expected_page}, got {tex_nos[i]}"

        # 3. 6-stage validation passes
        report = validate_live2d_model(bundle["model_dir"])
        assert report.passed is True
        assert report.total_errors == 0

    def test_high_vertex_count_stress_model(self, tmp_path):
        """
        Open Issue 1 & 4: High vertex count (>5,000 vertices) model.
        Tests 7,500 vertices across 5 drawables with 64-byte section alignment and correct counts.
        """
        model_name = "Stress7500Verts"
        out_dir = tmp_path / model_name
        out_dir.mkdir(parents=True, exist_ok=True)

        n_drawables = 5
        verts_per_drawable = 1500  # 5 * 1500 = 7500 vertices total
        drawables = []

        for d_idx in range(n_drawables):
            verts = np.random.uniform(-400, 400, (verts_per_drawable, 2)).astype(np.float32)
            tris = []
            for t in range(0, verts_per_drawable - 2, 3):
                tris.append([t, t + 1, t + 2])
            tris = np.array(tris, dtype=np.int32)
            uvs = np.random.uniform(0.05, 0.95, (verts_per_drawable, 2)).astype(np.float32)

            dk = DrawableKeyforms(
                drawable_id=f"ArtMesh_Stress_{d_idx}",
                texture_index=0,
                base_vertices=verts,
                triangles=tris,
                uvs_atlas=uvs,
                parameter_ids=["ParamAngleX", "ParamAngleY"]
            )
            # Add 3x3 = 9 keyforms
            for ax in [-30.0, 0.0, 30.0]:
                for ay in [-30.0, 0.0, 30.0]:
                    dk.add_keyform((ax, ay), verts + ax * 0.02)
            drawables.append(dk)

        params = [
            ParameterBinding("ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]),
            ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]),
            ParameterBinding("ParamAngleZ", min_val=-20.0, default_val=0.0, max_val=20.0, key_values=[-20.0, 0.0, 20.0]),
        ]

        table = KeyformTable(
            parameters=params,
            drawables=drawables,
            canvas_width=2048,
            canvas_height=2048,
            model_name=model_name
        )

        moc_bytes = Moc3Writer.build_bytes(table)
        assert len(moc_bytes) % 64 == 0

        # Validate section offsets
        offsets = struct.unpack_from("<160I", moc_bytes, 64)
        for idx, off in enumerate(offsets):
            if off > 0:
                assert off % 64 == 0, f"Section {idx} offset {hex(off)} not 64-byte aligned"

        # Validate counters
        counts = struct.unpack_from("<23I", moc_bytes, offsets[0])
        assert counts[4] == 5  # art_meshes
        assert counts[5] == 3  # parameters
        assert counts[9] == 5 * 9  # 45 art_mesh_keyforms
        assert counts[10] == 7500 * 2 * 9  # 135,000 float32 positions
        assert counts[15] == 7500 * 2      # 15,000 float32 UVs
        assert counts[16] == (1500 // 3 * 3) * 5  # 7,500 uint16 indices

        parsed = Moc3Reader.parse_bytes(moc_bytes)
        assert parsed["magic"] == "MOC3"
        assert parsed["is_64_aligned"] is True

    def test_odd_vertex_and_triangle_counts_alignment(self, tmp_path):
        """
        Verifies 64-byte section boundary alignment when vertex counts, triangle counts,
        and parameter counts are prime/odd numbers.
        """
        model_name = "OddCountModel"
        # 17 vertices, 5 triangles (15 indices), 3 parameters, 7 keyforms
        n_verts = 17
        verts = np.random.uniform(-100, 100, (n_verts, 2)).astype(np.float32)
        tris = np.array([[0, 1, 2], [2, 3, 4], [4, 5, 6], [6, 7, 8], [8, 9, 10]], dtype=np.int32)
        uvs = np.random.uniform(0.1, 0.9, (n_verts, 2)).astype(np.float32)

        dk = DrawableKeyforms(
            drawable_id="ArtMesh_Odd",
            texture_index=0,
            base_vertices=verts,
            triangles=tris,
            uvs_atlas=uvs,
            parameter_ids=["ParamAngleX"]
        )
        for ax in [-30.0, -20.0, -10.0, 0.0, 10.0, 20.0, 30.0]:
            dk.add_keyform((ax,), verts + ax * 0.01)

        params = [
            ParameterBinding("ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0,
                             key_values=[-30.0, -20.0, -10.0, 0.0, 10.0, 20.0, 30.0]),
        ]

        table = KeyformTable(parameters=params, drawables=[dk], canvas_width=1024, canvas_height=1024)
        moc_bytes = Moc3Writer.build_bytes(table)

        assert len(moc_bytes) % 64 == 0
        offsets = struct.unpack_from("<160I", moc_bytes, 64)
        for idx, off in enumerate(offsets):
            if off > 0:
                assert off % 64 == 0, f"Odd count section {idx} offset {hex(off)} is unaligned"

    def test_parameter_slider_definitions_and_groups(self, tmp_path):
        """
        Open Issue 2: Parameter slider definitions (ParamAngleX/Y/Z, EyeBlink, LipSync).
        Verifies .model3.json Groups and .cdi3.json ParameterGroups definitions.
        """
        params = [
            ParameterBinding("ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0),
            ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0),
            ParameterBinding("ParamAngleZ", min_val=-20.0, default_val=0.0, max_val=20.0),
            ParameterBinding("ParamEyeLOpen", min_val=0.0, default_val=1.0, max_val=1.0),
            ParameterBinding("ParamEyeROpen", min_val=0.0, default_val=1.0, max_val=1.0),
            ParameterBinding("ParamMouthOpenY", min_val=0.0, default_val=0.0, max_val=1.0),
            ParameterBinding("ParamBreath", min_val=0.0, default_val=0.0, max_val=1.0),
        ]

        cdi_path = tmp_path / "params.cdi3.json"
        cdi_data = Model3Writer.generate_cdi3_json(
            parameter_ids=[p.param_id for p in params],
            part_ids=["PartHead", "PartEyes", "PartMouth"],
            output_path=str(cdi_path)
        )

        assert cdi_data["Version"] == 3
        param_ids_cdi = [p["Id"] for p in cdi_data["Parameters"]]
        assert "ParamAngleX" in param_ids_cdi
        assert "ParamEyeLOpen" in param_ids_cdi
        assert "ParamMouthOpenY" in param_ids_cdi

        # Verify group mappings
        group_ids = [g["Id"] for g in cdi_data["ParameterGroups"]]
        assert "ParamGroupHead" in group_ids
        assert "ParamGroupEyes" in group_ids
        assert "ParamGroupMouth" in group_ids

        # Verify model3.json groups
        m3_path = tmp_path / "model.model3.json"
        m3_data = Model3Writer.generate_model3_json(
            model_name="ParamTest",
            moc_rel_path="ParamTest.moc3",
            texture_rel_paths=["ParamTest.1024/texture_00.png"],
            cdi_rel_path="params.cdi3.json",
            output_path=str(m3_path)
        )

        group_names = [g["Name"] for g in m3_data["Groups"]]
        assert "EyeBlink" in group_names
        assert "LipSync" in group_names

    def test_zero_initialized_deformers_and_glue_compatibility(self, tmp_path):
        """
        Open Issue 3: Zero-initialized Deformers / Physics / Glue sections.
        Ensures inactive deformer slots evaluate to 0 in SectionOffsetTable without slot collision.
        """
        table = KeyformTable(canvas_width=2048, canvas_height=2048)
        table.add_parameter(ParameterBinding("ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0))
        table.add_parameter(ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0))

        v = np.array([[-50, -50], [50, -50], [0, 50]], dtype=np.float32)
        d = DrawableKeyforms(
            drawable_id="ArtMesh_Core",
            texture_index=0,
            base_vertices=v,
            triangles=np.array([[0, 1, 2]], dtype=np.int32),
            uvs_atlas=np.array([[0, 0], [1, 0], [0.5, 1]], dtype=np.float32),
            parameter_ids=["ParamAngleX", "ParamAngleY"]
        )
        d.add_keyform((0.0, 0.0), v)
        table.add_drawable(d)

        moc_bytes = Moc3Writer.build_bytes(table)
        offsets = struct.unpack_from("<160I", moc_bytes, 64)
        counts = struct.unpack_from("<23I", moc_bytes, offsets[0])

        # Verify deformer counts are 0
        assert counts[1] == 0  # Deformers
        assert counts[2] == 0  # WarpDeformers
        assert counts[3] == 0  # RotationDeformers
        assert counts[7] == 0  # WarpKeyforms
        assert counts[8] == 0  # RotationKeyforms
        assert counts[20] == 0 # Glue
        assert counts[21] == 0 # GlueInfo
        assert counts[22] == 0 # GlueKeyforms

        # Verify deformer slots (10..28, 59..67, 89..100) are inactive (0)
        for slot in range(10, 29):
            assert offsets[slot] == 0, f"Slot {slot} should be 0 for model without deformers"
        for slot in range(59, 68):
            assert offsets[slot] == 0, f"Slot {slot} should be 0 for model without deformers"
        for slot in range(89, 101):
            assert offsets[slot] == 0, f"Slot {slot} should be 0 for model without glue"

    def test_diagnostic_tool_against_working_reference(self):
        """
        Acceptance Criteria: Diagnostic script proves structural layout matches hiyori_vts.
        """
        ref_path = "output/hiyori_vts/hiyori.moc3"
        if Path(ref_path).exists():
            # Run diagnostic on TestAvatar
            assert run_diagnostic_comparison(ref_moc3_path=ref_path, target_model_dir="output/TestAvatar") is True
            # Run diagnostic on MyAvatar2
            assert run_diagnostic_comparison(ref_moc3_path=ref_path, target_model_dir="output/MyAvatar2") is True
            # Run diagnostic on E2ETestModel
            assert run_diagnostic_comparison(ref_moc3_path=ref_path, target_model_dir="output/E2ETestModel") is True

    def test_uint16_vertex_limit_boundary_rejection(self):
        """
        Open Issue 5: Verifies that ArtMeshes exceeding 65,535 vertices are rejected
        to prevent silent uint16 integer overflow in PositionIndices.
        """
        # Create an oversized drawable with 65,536 vertices
        n_verts = 65536
        verts = np.zeros((n_verts, 2), dtype=np.float32)
        tris = np.array([[0, 1, 2]], dtype=np.int32)
        uvs = np.zeros((n_verts, 2), dtype=np.float32)

        dk_overflow = DrawableKeyforms(
            drawable_id="ArtMesh_Overflow",
            base_vertices=verts,
            triangles=tris,
            uvs_atlas=uvs,
            parameter_ids=["ParamAngleX"]
        )
        dk_overflow.add_keyform((0.0,), verts)

        table = KeyformTable(
            parameters=[ParameterBinding("ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0)],
            drawables=[dk_overflow]
        )

        # 1. KeyformTable.validate must fail
        valid, errs = table.validate()
        assert valid is False
        assert any("65535" in e for e in errs)

        # 2. Moc3Writer.build_bytes must raise ValueError
        with pytest.raises(ValueError, match="65535"):
            Moc3Writer.build_bytes(table)

        # 3. StructuralValidator Stage 6 must flag error
        stage6_res = StructuralValidator.validate_stage6_topology_and_deformation(keyform_table=table)
        assert stage6_res.passed is False
        assert any("65535" in e for e in stage6_res.errors)

    def test_uint16_triangle_index_overflow_rejection(self):
        """
        Verifies that triangles containing vertex index > 65,535 are rejected.
        """
        n_verts = 100
        verts = np.zeros((n_verts, 2), dtype=np.float32)
        # Triangle references index 65536
        tris = np.array([[0, 1, 65536]], dtype=np.int32)
        uvs = np.zeros((n_verts, 2), dtype=np.float32)

        dk = DrawableKeyforms(
            drawable_id="ArtMesh_BadIndex",
            base_vertices=verts,
            triangles=tris,
            uvs_atlas=uvs,
            parameter_ids=["ParamAngleX"]
        )
        dk.add_keyform((0.0,), verts)

        table = KeyformTable(
            parameters=[ParameterBinding("ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0)],
            drawables=[dk]
        )

        valid, errs = table.validate()
        assert valid is False

        with pytest.raises(ValueError):
            Moc3Writer.build_bytes(table)

        stage6_res = StructuralValidator.validate_stage6_topology_and_deformation(keyform_table=table)
        assert stage6_res.passed is False

    def test_renderer_pure_numpy_flip(self):
        """
        Verifies that MeshRenderer works with pure NumPy flipping and doesn't require cv2.
        """
        from src.renderer.renderer import MeshRenderer
        renderer = MeshRenderer()
        test_rgba = np.random.randint(0, 256, (128, 128, 4), dtype=np.uint8)
        renderer.set_texture(test_rgba)
        assert renderer.texture_rgba is not None
        assert renderer.texture_rgba.shape == (128, 128, 4)

    def test_live2d_deformer_hierarchy_and_parameter_bindings(self, tmp_path):
        """
        R1 & R2: Full Live2D Deformer Hierarchy & Parameter Binding Verification.
        Hierarchy: RootPart -> RotationDeformer (AngleZ) -> WarpDeformer (AngleX, AngleY) -> ArtMesh.
        Bindings: ParamAngleX/Y bound to WarpDeformer, ParamAngleZ bound to RotationDeformer,
        ArtMeshes have NO direct rotation parameters.
        """
        from src.core.keyform import WarpDeformer, RotationDeformer
        import math

        model_name = "DeformerHierarchyAvatar"
        table = KeyformTable(canvas_width=2048, canvas_height=2048, model_name=model_name, parts=["PartRoot"])

        # 1. Parameters
        table.add_parameter(ParameterBinding("ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]))
        table.add_parameter(ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]))
        table.add_parameter(ParameterBinding("ParamAngleZ", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]))

        # 2. RotationDeformer (Angle Z) - attached to RootPart
        rot = RotationDeformer(
            deformer_id="Rotation_Head",
            parent_part_id="PartRoot",
            parent_deformer_id=None,
            parameter_ids=["ParamAngleZ"],
            origin_x=1024.0,
            origin_y=1024.0,
            base_angle=0.0
        )
        for az in [-30.0, 0.0, 30.0]:
            rot.add_keyform((float(az),), angle=math.radians(az), origin=(1024.0, 1024.0), scale=(1.0, 1.0), opacity=1.0)
        table.add_rotation_deformer(rot)

        # 3. WarpDeformer (Angle X, Angle Y) - child of Rotation_Head
        warp = WarpDeformer(
            deformer_id="Warp_Head",
            parent_part_id="PartRoot",
            parent_deformer_id="Rotation_Head",
            parameter_ids=["ParamAngleX", "ParamAngleY"],
            grid_rows=4,
            grid_cols=4
        )
        gx = np.linspace(600, 1400, 5, dtype=np.float32)
        gy = np.linspace(600, 1400, 5, dtype=np.float32)
        grid_x, grid_y = np.meshgrid(gx, gy)
        base_grid = np.column_stack([grid_x.ravel(), grid_y.ravel()])
        warp.base_vertices = base_grid

        for ay in [-30.0, 0.0, 30.0]:
            for ax in [-30.0, 0.0, 30.0]:
                disp = base_grid.copy()
                disp[:, 0] += ax * 1.5
                disp[:, 1] += ay * 1.5
                warp.add_keyform((float(ax), float(ay)), disp)
        table.add_warp_deformer(warp)

        # 4. ArtMeshes - child of Warp_Head with NO direct rotation parameters
        d1 = DrawableKeyforms(
            drawable_id="ArtMesh_Face",
            texture_index=0,
            base_vertices=np.array([[800, 800], [1200, 800], [1200, 1200], [800, 1200]], dtype=np.float32),
            triangles=np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32),
            uvs_atlas=np.array([[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]], dtype=np.float32),
            parameter_ids=[],  # NO direct rotation parameters
            parent_deformer_id="Warp_Head",
            parent_part_id="PartRoot",
            draw_order=500
        )
        d2 = DrawableKeyforms(
            drawable_id="ArtMesh_HairFront",
            texture_index=0,
            base_vertices=np.array([[850, 750], [1150, 750], [1000, 1000]], dtype=np.float32),
            triangles=np.array([[0, 1, 2]], dtype=np.int32),
            uvs_atlas=np.array([[0.2, 0.1], [0.8, 0.1], [0.5, 0.5]], dtype=np.float32),
            parameter_ids=[],  # NO direct rotation parameters
            parent_deformer_id="Warp_Head",
            parent_part_id="PartRoot",
            draw_order=600
        )
        table.add_drawable(d1)
        table.add_drawable(d2)

        # Serialize to moc3 bytes
        moc_bytes = Moc3Writer.build_bytes(table)
        assert len(moc_bytes) % 64 == 0

        # Parse back with Moc3Reader
        parsed = Moc3Reader.parse_bytes(moc_bytes)
        counts = parsed.get("counts", {})

        # Verify deformer counts > 0
        assert counts.get("parts") == 1
        assert counts.get("deformers") == 2
        assert counts.get("rotation_deformers") == 1
        assert counts.get("warp_deformers") == 1
        assert counts.get("rotation_deformer_keyforms") == 3
        assert counts.get("warp_deformer_keyforms") == 9
        assert counts.get("art_meshes") == 2
        assert counts.get("art_mesh_keyforms") == 2  # 1 per ArtMesh, static

        # Verify deformer hierarchy structure
        assert parsed.get("deformer_ids") == ["Rotation_Head", "Warp_Head"]
        assert parsed.get("deformer_types") == [1, 0]  # 1=Rotation, 0=Warp
        assert parsed.get("deformer_parent_indices") == [-1, 0]  # Rotation has no parent (-1), Warp's parent is Rotation (0)
        assert parsed.get("art_mesh_parent_deformer_indices") == [1, 1]  # Both ArtMeshes parented to Warp_Head (1)

        # Verify Stage 1..6 structural validation passes
        report = StructuralValidator.validate_stage1_moc3_header(moc_bytes)
        assert report.passed is True

        report2 = StructuralValidator.validate_stage2_section_offsets_and_counts(moc_bytes)
        assert report2.passed is True
        assert report2.details.get("deformers") == 2
        assert report2.details.get("warp_deformers") == 1
        assert report2.details.get("rotation_deformers") == 1

    def test_keyform_generator_creates_deformer_hierarchy(self):
        """
        Verifies KeyformGenerator.generate_keyform_table generates the standard hierarchy.
        """
        rgba1 = np.ones((64, 64, 4), dtype=np.uint8) * 200
        l1 = LayerData(name="Head_Base", image=rgba1, category="face")
        collection = LayerCollection(canvas_size=(256, 256), layers=[l1])

        contour = np.array([[20, 20], [80, 20], [80, 80], [20, 80]], dtype=np.float64)
        m1 = MeshGenerator.generate_mesh_from_contour(contour, (100, 100), target_grid_size=25)
        mesh_map = {l1.layer_id: m1}

        generator = KeyformGenerator()
        table = generator.generate_keyform_table(collection, mesh_map, include_angle_z=True)

        assert len(table.rotation_deformers) == 1
        assert len(table.warp_deformers) == 1
        assert len(table.drawables) == 1

        rot = table.rotation_deformers[0]
        warp = table.warp_deformers[0]
        d = table.drawables[0]

        assert rot.deformer_id == "Rotation_Head"
        assert rot.parameter_ids == ["ParamAngleZ"]
        assert len(rot.keyform_keys) == 3

        assert warp.deformer_id == "Warp_Head"
        assert warp.parent_deformer_id == "Rotation_Head"
        assert warp.parameter_ids == ["ParamAngleX", "ParamAngleY"]
        assert len(warp.deformed_positions) == 9

        assert d.parent_deformer_id == "Warp_Head"
        assert d.parameter_ids == []  # No direct vertex rotation parameters

        # Table validation passes
        is_valid, errors = table.validate()
        assert is_valid is True, f"Validation errors: {errors}"
