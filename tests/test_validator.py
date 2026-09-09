"""
tests/test_validator.py
Comprehensive Unit & Integration Test Suite for the 6-Stage Live2D Structural Validator.
Tests all 6 stages with valid generated models and corrupted/adversarial fixtures.
"""

import json
import os
from pathlib import Path
import struct
import numpy as np
import pytest
from PIL import Image

from src.validator.structural_validator import (
    StructuralValidator,
    ValidationStageResult,
    ValidationReport,
    validate_live2d_model,
)
from src.core.keyform import KeyformTable, DrawableKeyforms, ParameterBinding
from src.exporter.moc3_writer import Moc3Writer
from src.exporter.model3_writer import Model3Writer


# ---------------------------------------------------------------------------
# Helper Fixtures & Factory
# ---------------------------------------------------------------------------
@pytest.fixture
def valid_keyform_table() -> KeyformTable:
    """Constructs a valid compliant KeyformTable."""
    base_verts = np.array([
        [-0.5, -0.5],
        [0.5, -0.5],
        [0.5, 0.5],
        [-0.5, 0.5]
    ], dtype=np.float32)
    # 2 CCW triangles with positive signed area
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    uvs = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32)

    deformed_positions = {
        (-30.0, -30.0): base_verts + np.array([-0.1, -0.1], dtype=np.float32),
        (-30.0, 0.0): base_verts + np.array([-0.1, 0.0], dtype=np.float32),
        (-30.0, 30.0): base_verts + np.array([-0.1, 0.1], dtype=np.float32),
        (0.0, -30.0): base_verts + np.array([0.0, -0.1], dtype=np.float32),
        (0.0, 0.0): base_verts.copy(),
        (0.0, 30.0): base_verts + np.array([0.0, 0.1], dtype=np.float32),
        (30.0, -30.0): base_verts + np.array([0.1, -0.1], dtype=np.float32),
        (30.0, 0.0): base_verts + np.array([0.1, 0.0], dtype=np.float32),
        (30.0, 30.0): base_verts + np.array([0.1, 0.1], dtype=np.float32),
    }

    drawable = DrawableKeyforms(
        drawable_id="ArtMesh_Face",
        texture_index=0,
        base_vertices=base_verts,
        triangles=triangles,
        uvs_atlas=uvs,
        deformed_positions=deformed_positions
    )

    params = [
        ParameterBinding("ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]),
        ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]),
        ParameterBinding("ParamAngleZ", min_val=-20.0, default_val=0.0, max_val=20.0, key_values=[-20.0, 0.0, 20.0]),
    ]

    return KeyformTable(
        parameters=params,
        drawables=[drawable]
    )


@pytest.fixture
def valid_model_bundle(tmp_path, valid_keyform_table) -> Path:
    """Creates a fully valid Live2D model directory with all 6 stages passing."""
    model_name = "TestAvatar"
    model_dir = tmp_path / model_name
    model_dir.mkdir(parents=True, exist_ok=True)

    # 1. Texture Atlas
    tex_dir = model_dir / f"{model_name}.1024"
    tex_dir.mkdir(parents=True, exist_ok=True)
    tex_path = tex_dir / "texture_00.png"
    img = Image.new("RGBA", (1024, 1024), (255, 200, 180, 255))
    img.save(tex_path)

    # 2. Binary MOC3
    moc_path = model_dir / f"{model_name}.moc3"
    Moc3Writer.write_moc3(valid_keyform_table, str(moc_path))

    # 3. CDI JSON
    cdi_path = model_dir / f"{model_name}.cdi3.json"
    Model3Writer.generate_cdi3_json(
        parameter_ids=valid_keyform_table.parameter_ids,
        part_ids=["PartHead"],
        output_path=str(cdi_path)
    )

    # 4. Model3 JSON
    model3_path = model_dir / f"{model_name}.model3.json"
    Model3Writer.generate_model3_json(
        model_name=model_name,
        moc_rel_path=f"{model_name}.moc3",
        texture_rel_paths=[f"{model_name}.1024/texture_00.png"],
        cdi_rel_path=f"{model_name}.cdi3.json",
        output_path=str(model3_path)
    )

    return model_dir


# ---------------------------------------------------------------------------
# Test Suite: Stage 1 - Binary MOC3 Header Integrity
# ---------------------------------------------------------------------------
class TestStage1Moc3Header:
    """Tests for Stage 1: Header verification."""

    def test_stage1_valid_header(self, valid_keyform_table):
        moc3_bytes = Moc3Writer.build_bytes(valid_keyform_table)
        res = StructuralValidator.validate_stage1_moc3_header(moc3_bytes)
        assert res.stage_number == 1
        assert res.passed is True
        assert len(res.errors) == 0
        assert res.details["magic"] == "MOC3"
        assert res.details["version"] == 3
        assert res.details["endianness"] == "little-endian"

    def test_stage1_corrupt_magic_bytes(self, valid_keyform_table):
        moc3_bytes = bytearray(Moc3Writer.build_bytes(valid_keyform_table))
        moc3_bytes[0:4] = b"MOC2"
        res = StructuralValidator.validate_stage1_moc3_header(bytes(moc3_bytes))
        assert res.passed is False
        assert any("Magic bytes mismatch" in e for e in res.errors)

    def test_stage1_unsupported_version(self, valid_keyform_table):
        moc3_bytes = bytearray(Moc3Writer.build_bytes(valid_keyform_table))
        moc3_bytes[4] = 99
        res = StructuralValidator.validate_stage1_moc3_header(bytes(moc3_bytes))
        assert res.passed is False
        assert any("Unsupported version" in e for e in res.errors)

    def test_stage1_invalid_endianness(self, valid_keyform_table):
        moc3_bytes = bytearray(Moc3Writer.build_bytes(valid_keyform_table))
        moc3_bytes[5] = 1  # Big-Endian
        res = StructuralValidator.validate_stage1_moc3_header(bytes(moc3_bytes))
        assert res.passed is False
        assert any("Endianness" in e for e in res.errors)

    def test_stage1_truncated_file(self):
        truncated = b"MOC3\x03\x00\x00\x00"  # Only 8 bytes
        res = StructuralValidator.validate_stage1_moc3_header(truncated)
        assert res.passed is False
        assert any("File size too small" in e for e in res.errors)


# ---------------------------------------------------------------------------
# Test Suite: Stage 2 - Section Table Offsets & Count Table Sanity
# ---------------------------------------------------------------------------
class TestStage2SectionTables:
    """Tests for Stage 2: Section tables, 64-byte alignment, counts and canvas."""

    def test_stage2_valid_section_table(self, valid_keyform_table):
        moc3_bytes = Moc3Writer.build_bytes(valid_keyform_table)
        res = StructuralValidator.validate_stage2_section_tables(moc3_bytes)
        assert res.stage_number == 2
        assert res.passed is True
        assert len(res.errors) == 0
        assert res.details["art_meshes"] >= 1
        assert res.details["parameters"] >= 1

    def test_stage2_misaligned_offset(self, valid_keyform_table):
        moc3_bytes = bytearray(Moc3Writer.build_bytes(valid_keyform_table))
        # Corrupt section offset at slot 7 (0x40 + 7*4 = 0x5C) to be non-multiple of 64
        struct.pack_into("<I", moc3_bytes, 64 + 7 * 4, 0x0741)
        res = StructuralValidator.validate_stage2_section_tables(bytes(moc3_bytes))
        assert res.passed is False
        assert any("64-byte alignment" in e for e in res.errors)

    def test_stage2_offset_exceeds_filesize(self, valid_keyform_table):
        moc3_bytes = bytearray(Moc3Writer.build_bytes(valid_keyform_table))
        # Corrupt section offset to point past end of file
        struct.pack_into("<I", moc3_bytes, 64 + 2 * 4, len(moc3_bytes) + 1024)
        res = StructuralValidator.validate_stage2_section_tables(bytes(moc3_bytes))
        assert res.passed is False
        assert any("exceeds binary size" in e for e in res.errors)

    def test_stage2_astronomical_count_table(self, valid_keyform_table):
        moc3_bytes = bytearray(Moc3Writer.build_bytes(valid_keyform_table))
        # CountInfoTable is at 0x0740 + 128 = 0x07C0
        struct.pack_into("<I", moc3_bytes, 0x07C0 + 4 * 4, 999_999_999)  # 1B art meshes
        res = StructuralValidator.validate_stage2_section_tables(bytes(moc3_bytes))
        assert res.passed is False
        assert any("astronomical" in e or "sanity check failed" in e for e in res.errors)


# ---------------------------------------------------------------------------
# Test Suite: Stage 3 - JSON Manifest Schema & Path Conformance
# ---------------------------------------------------------------------------
class TestStage3JsonManifest:
    """Tests for Stage 3: .model3.json and .cdi3.json schema & path existence."""

    def test_stage3_valid_manifest(self, valid_model_bundle):
        model3_path = valid_model_bundle / "TestAvatar.model3.json"
        res, model3_data, cdi3_data = StructuralValidator.validate_stage3_json_manifest(
            model_dir=valid_model_bundle,
            model3_path=model3_path
        )
        assert res.stage_number == 3
        assert res.passed is True
        assert len(res.errors) == 0
        assert model3_data is not None
        assert model3_data["Version"] == 3

    def test_stage3_invalid_json_syntax(self, valid_model_bundle):
        model3_path = valid_model_bundle / "TestAvatar.model3.json"
        with open(model3_path, "w") as f:
            f.write("{ invalid json syntax ...")
        res, _, _ = StructuralValidator.validate_stage3_json_manifest(
            model_dir=valid_model_bundle,
            model3_path=model3_path
        )
        assert res.passed is False
        assert any("Invalid JSON syntax" in e for e in res.errors)

    def test_stage3_missing_moc_file(self, valid_model_bundle):
        model3_path = valid_model_bundle / "TestAvatar.model3.json"
        with open(model3_path, "r") as f:
            data = json.load(f)
        data["FileReferences"]["Moc"] = "nonexistent_model.moc3"
        with open(model3_path, "w") as f:
            json.dump(data, f)

        res, _, _ = StructuralValidator.validate_stage3_json_manifest(
            model_dir=valid_model_bundle,
            model3_path=model3_path
        )
        assert res.passed is False
        assert any("Moc file does not exist" in e for e in res.errors)

    def test_stage3_backslash_in_relative_path(self, valid_model_bundle):
        model3_path = valid_model_bundle / "TestAvatar.model3.json"
        with open(model3_path, "r") as f:
            data = json.load(f)
        data["FileReferences"]["Textures"] = ["TestAvatar.1024\\texture_00.png"]
        with open(model3_path, "w") as f:
            json.dump(data, f)

        res, _, _ = StructuralValidator.validate_stage3_json_manifest(
            model_dir=valid_model_bundle,
            model3_path=model3_path
        )
        assert res.passed is False
        assert any("Windows backslash" in e for e in res.errors)


# ---------------------------------------------------------------------------
# Test Suite: Stage 4 - Parameter & Keyform Bounds
# ---------------------------------------------------------------------------
class TestStage4ParameterBounds:
    """Tests for Stage 4: Parameter IDs, keyforms, ranges and monotonicity."""

    def test_stage4_valid_parameters(self, valid_keyform_table):
        cdi3 = {
            "Version": 3,
            "Parameters": [
                {"Id": "ParamAngleX", "Name": "Angle X"},
                {"Id": "ParamAngleY", "Name": "Angle Y"},
                {"Id": "ParamAngleZ", "Name": "Angle Z"},
            ]
        }
        res = StructuralValidator.validate_stage4_parameter_bounds(cdi3, keyform_table=valid_keyform_table)
        assert res.stage_number == 4
        assert res.passed is True
        assert len(res.errors) == 0

    def test_stage4_missing_required_param(self):
        cdi3 = {
            "Version": 3,
            "Parameters": [
                {"Id": "ParamEyeLOpen", "Name": "Eye Open"},
            ]
        }
        res = StructuralValidator.validate_stage4_parameter_bounds(cdi3)
        assert res.passed is False
        assert any("Missing required parameter: ParamAngleX" in e for e in res.errors)

    def test_stage4_inverted_parameter_range(self):
        cdi3 = {"Version": 3, "Parameters": [{"Id": "ParamAngleX"}, {"Id": "ParamAngleY"}]}
        bad_params = [
            ParameterBinding("ParamAngleX", min_val=30.0, default_val=0.0, max_val=-30.0),
            ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0),
        ]
        bad_table = KeyformTable(parameters=bad_params)
        res = StructuralValidator.validate_stage4_parameter_bounds(cdi3, keyform_table=bad_table)
        assert res.passed is False
        assert any("Invalid parameter range for ParamAngleX" in e for e in res.errors)

    def test_stage4_out_of_bounds_default_value(self):
        cdi3 = {"Version": 3, "Parameters": [{"Id": "ParamAngleX"}, {"Id": "ParamAngleY"}]}
        bad_params = [
            ParameterBinding("ParamAngleX", min_val=-30.0, default_val=50.0, max_val=30.0),
            ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0),
        ]
        bad_table = KeyformTable(parameters=bad_params)
        res = StructuralValidator.validate_stage4_parameter_bounds(cdi3, keyform_table=bad_table)
        assert res.passed is False
        assert any("Default value out of bounds for ParamAngleX" in e for e in res.errors)


# ---------------------------------------------------------------------------
# Test Suite: Stage 5 - Texture Atlas & UV Coordinates
# ---------------------------------------------------------------------------
class TestStage5TexturesAndUVs:
    """Tests for Stage 5: Texture POT dimensions, RGBA mode, and UV coordinates."""

    def test_stage5_valid_texture(self, valid_model_bundle, valid_keyform_table):
        res = StructuralValidator.validate_stage5_textures_and_uvs(
            model_dir=valid_model_bundle,
            texture_rel_paths=["TestAvatar.1024/texture_00.png"],
            keyform_table=valid_keyform_table
        )
        assert res.stage_number == 5
        assert res.passed is True
        assert len(res.errors) == 0

    def test_stage5_non_power_of_two_texture(self, tmp_path):
        bad_dir = tmp_path / "BadTextureModel"
        bad_dir.mkdir()
        bad_img = Image.new("RGBA", (500, 500), (200, 200, 200, 255))
        bad_img.save(bad_dir / "texture_00.png")

        res = StructuralValidator.validate_stage5_textures_and_uvs(
            model_dir=bad_dir,
            texture_rel_paths=["texture_00.png"]
        )
        assert res.passed is False
        assert any("not power-of-two" in e for e in res.errors)

    def test_stage5_out_of_bounds_uvs(self, valid_model_bundle):
        bad_table = KeyformTable()
        bad_drawable = DrawableKeyforms(
            drawable_id="ArtMesh_Face",
            texture_index=0,
            base_vertices=np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float32),
            triangles=np.array([[0, 1, 2]], dtype=np.int32),
            uvs_atlas=np.array([[0.0, 0.0], [1.5, 0.0], [0.0, 1.0]], dtype=np.float32)  # u=1.5 > 1.0
        )
        bad_table.drawables = [bad_drawable]

        res = StructuralValidator.validate_stage5_textures_and_uvs(
            model_dir=valid_model_bundle,
            texture_rel_paths=["TestAvatar.1024/texture_00.png"],
            keyform_table=bad_table
        )
        assert res.passed is False
        assert any("UV coordinates out of bounds" in e for e in res.errors)


# ---------------------------------------------------------------------------
# Test Suite: Stage 6 - Topological Non-Inversion & Deformation Continuity
# ---------------------------------------------------------------------------
class TestStage6TopologyAndDeformation:
    """Tests for Stage 6: Positive signed area preservation, finite coordinates, and index bounds."""

    def test_stage6_valid_topology(self, valid_keyform_table):
        res = StructuralValidator.validate_stage6_topology_and_deformation(keyform_table=valid_keyform_table)
        assert res.stage_number == 6
        assert res.passed is True
        assert len(res.errors) == 0

    def test_stage6_inverted_triangle_keyform(self):
        base_v = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        triangles = np.array([[0, 1, 2]], dtype=np.int32)
        # Flip vertex 1 to x = -1, creating clockwise inverted winding
        inverted_kf_pos = np.array([[0.0, 0.0], [-1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

        drawable = DrawableKeyforms(
            drawable_id="ArtMesh_Inverted",
            texture_index=0,
            base_vertices=base_v,
            triangles=triangles,
            uvs_atlas=np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float32),
            deformed_positions={
                (30.0, 0.0): inverted_kf_pos
            }
        )
        table = KeyformTable(drawables=[drawable])
        res = StructuralValidator.validate_stage6_topology_and_deformation(keyform_table=table)
        assert res.passed is False
        assert any("Inverted triangle" in e for e in res.errors)

    def test_stage6_nan_coordinates(self):
        base_v = np.array([[0.0, 0.0], [np.nan, 0.0], [0.0, 1.0]], dtype=np.float32)
        triangles = np.array([[0, 1, 2]], dtype=np.int32)
        drawable = DrawableKeyforms(
            drawable_id="ArtMesh_NaN",
            texture_index=0,
            base_vertices=base_v,
            triangles=triangles,
            uvs_atlas=np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float32)
        )
        table = KeyformTable(drawables=[drawable])
        res = StructuralValidator.validate_stage6_topology_and_deformation(keyform_table=table)
        assert res.passed is False
        assert any("NaN or Inf" in e for e in res.errors)


# ---------------------------------------------------------------------------
# Test Suite: End-to-End Validation Report & Function
# ---------------------------------------------------------------------------
class TestValidationReportAndEntrypoint:
    """Tests for master validate_live2d_model entrypoint and report formatting."""

    def test_validate_live2d_model_on_valid_bundle(self, valid_model_bundle):
        report = validate_live2d_model(valid_model_bundle)
        assert isinstance(report, ValidationReport)
        assert report.is_valid is True
        assert report.passed is True
        assert report.total_errors == 0
        assert len(report.stages) == 6
        assert all(s.passed for s in report.stages)
        assert 1 in report.stages_passed
        assert 2 in report.stages_passed
        assert 3 in report.stages_passed
        assert 4 in report.stages_passed
        assert 5 in report.stages_passed
        assert 6 in report.stages_passed

    def test_validation_report_to_dict_and_console(self, valid_model_bundle):
        report = validate_live2d_model(valid_model_bundle)
        d = report.to_dict()
        assert d["is_valid"] is True
        assert len(d["stages"]) == 6

        console_text = report.format_console(use_color=False)
        assert "LIVE2D 6-STAGE STRUCTURAL VALIDATION REPORT" in console_text
        assert "[PASSED]" in console_text
        assert "Stage 1" in console_text
        assert "Stage 6" in console_text
