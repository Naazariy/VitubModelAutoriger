"""
tests/test_adversarial_m4_challenger.py
Empirical Adversarial Stress & Edge Case Test Suite for Milestone 4:
6-Stage Structural Validator, Standalone Validator CLI, and Headless Pipeline Runner.
Authored by Challenger 1 (Empirical Challenger).

Challenge Dimensions:
1. Binary boundary conditions (<64 bytes, 63 bytes, corrupt magic, invalid version/endianness)
2. Section table alignment, bounds, monotonicity, and CountInfoTable/CanvasInfo sanity
3. JSON manifest schema, backslash path normalization, and missing file references
4. Parameter bounds, missing required tracking IDs, inverted ranges, and non-monotonic keys
5. Texture atlas power-of-two dimensions, RGBA channels, out-of-bounds UVs, and NaN UVs
6. Topological non-inversion (signed area preservation > -1e-4), finite coordinates (NaN/Inf), and index bounds
7. CLI exit code specification adherence (0: success, 1: input/args, 2: mesh, 3: deformation, 4: export, 5: validation)
8. Standalone validator CLI (validate_live2d.py) options, strict mode, JSON reporting, and quiet/color toggles
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
from src.cli.main import (
    build_parser as build_cli_parser,
    parse_args as parse_cli_args,
    run_pipeline,
    main as cli_main,
    PipelineConfig,
    PipelineRunner,
    InputError,
    MeshGenerationError,
    DeformationError,
    ExportError,
    ValidationError,
    EXIT_SUCCESS,
    EXIT_ERR_INPUT,
    EXIT_ERR_MESH,
    EXIT_ERR_DEFORMATION,
    EXIT_ERR_EXPORT,
    EXIT_ERR_VALIDATION,
)
from validate_live2d import (
    build_parser as build_val_parser,
    main as val_main,
)


# ============================================================================
# FIXTURES & HELPERS
# ============================================================================

@pytest.fixture
def compliant_keyform_table() -> KeyformTable:
    """Constructs a fully compliant KeyformTable with positive signed area triangles."""
    base_verts = np.array([
        [-100.0, -100.0],
        [ 100.0, -100.0],
        [ 100.0,  100.0],
        [-100.0,  100.0]
    ], dtype=np.float32)
    # CCW triangles: [0, 1, 2] and [0, 2, 3] -> positive signed area
    triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    uvs = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32)

    deformed_positions = {
        (-30.0, -30.0): base_verts + np.array([-15.0, -15.0], dtype=np.float32),
        (-30.0,   0.0): base_verts + np.array([-15.0,   0.0], dtype=np.float32),
        (-30.0,  30.0): base_verts + np.array([-15.0,  15.0], dtype=np.float32),
        (  0.0, -30.0): base_verts + np.array([  0.0, -15.0], dtype=np.float32),
        (  0.0,   0.0): base_verts.copy(),
        (  0.0,  30.0): base_verts + np.array([  0.0,  15.0], dtype=np.float32),
        ( 30.0, -30.0): base_verts + np.array([ 15.0, -15.0], dtype=np.float32),
        ( 30.0,   0.0): base_verts + np.array([ 15.0,   0.0], dtype=np.float32),
        ( 30.0,  30.0): base_verts + np.array([ 15.0,  15.0], dtype=np.float32),
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
        drawables=[drawable],
        canvas_width=2048,
        canvas_height=2048,
        model_name="AdversarialCompliant"
    )


@pytest.fixture
def compliant_model_bundle(tmp_path, compliant_keyform_table) -> Path:
    """Creates a fully valid Live2D model directory with all 6 stages passing."""
    model_name = "AdversarialCompliant"
    model_dir = tmp_path / model_name
    model_dir.mkdir(parents=True, exist_ok=True)

    # 1. Texture Atlas (power-of-two 1024x1024 RGBA)
    tex_dir = model_dir / f"{model_name}.1024"
    tex_dir.mkdir(parents=True, exist_ok=True)
    tex_path = tex_dir / "texture_00.png"
    img = Image.new("RGBA", (1024, 1024), (255, 200, 180, 255))
    img.save(tex_path)

    # 2. Binary MOC3
    moc_path = model_dir / f"{model_name}.moc3"
    Moc3Writer.write_moc3(compliant_keyform_table, str(moc_path))

    # 3. CDI JSON
    cdi_path = model_dir / f"{model_name}.cdi3.json"
    Model3Writer.generate_cdi3_json(
        parameter_ids=compliant_keyform_table.parameter_ids,
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


@pytest.fixture
def synthetic_avatar_png(tmp_path) -> Path:
    """Creates a valid 512x512 RGBA PNG avatar with non-empty content."""
    png_path = tmp_path / "avatar_stress.png"
    arr = np.zeros((512, 512, 4), dtype=np.uint8)
    y, x = np.ogrid[:512, :512]
    mask = ((x - 256) ** 2 + (y - 256) ** 2) <= 150 ** 2
    arr[mask] = [255, 210, 185, 255]
    Image.fromarray(arr).save(png_path)
    return png_path


# ============================================================================
# CHALLENGE 1: STAGE 1 BINARY MOC3 HEADER EDGE CASES
# ============================================================================
class TestStage1Moc3HeaderAdversarial:
    """Stress-test binary header boundary conditions and malformed headers."""

    def test_0_byte_empty_file(self):
        """0-byte file must fail Stage 1 immediately without unhandled exception."""
        res = StructuralValidator.validate_stage1_moc3_header(b"")
        assert res.stage_number == 1
        assert res.passed is False
        assert any("File size too small" in e for e in res.errors)

    def test_63_byte_file_boundary(self):
        """63-byte file (1 byte below 64-byte header minimum) must fail."""
        data_63 = b"MOC3\x03\x00\x00\x00" + b"\x00" * 55  # 8 + 55 = 63 bytes
        assert len(data_63) == 63
        res = StructuralValidator.validate_stage1_moc3_header(data_63)
        assert res.passed is False
        assert any("File size too small" in e for e in res.errors)

    def test_64_byte_minimal_valid_header(self):
        """Exact 64-byte minimal header with valid magic/version/endian."""
        data_64 = b"MOC3\x03\x00\x00\x00" + b"\x00" * 56
        assert len(data_64) == 64
        res = StructuralValidator.validate_stage1_moc3_header(data_64)
        assert res.passed is True
        assert res.details["magic"] == "MOC3"
        assert res.details["version"] == 3
        assert res.details["endianness"] == "little-endian"

    @pytest.mark.parametrize("bad_magic", [b"MOC2", b"MOC4", b"LIVE", b"\x00\x00\x00\x00", b"\xff\xff\xff\xff"])
    def test_corrupt_magic_variations(self, bad_magic):
        """Invalid magic identifiers must fail Stage 1."""
        data = bad_magic + b"\x03\x00\x00\x00" + b"\x00" * 56
        res = StructuralValidator.validate_stage1_moc3_header(data)
        assert res.passed is False
        assert any("Magic bytes mismatch" in e for e in res.errors)

    @pytest.mark.parametrize("bad_version", [0, 6, 7, 99, 255])
    def test_unsupported_versions(self, bad_version):
        """Versions outside [1..5] must fail Stage 1."""
        data = b"MOC3" + bytes([bad_version]) + b"\x00\x00\x00" + b"\x00" * 56
        res = StructuralValidator.validate_stage1_moc3_header(data)
        assert res.passed is False
        assert any("Unsupported version" in e for e in res.errors)

    @pytest.mark.parametrize("bad_endian", [1, 2, 255])
    def test_invalid_endianness_flags(self, bad_endian):
        """Non-zero endianness flags (big-endian or invalid) must fail Stage 1."""
        data = b"MOC3\x03" + bytes([bad_endian]) + b"\x00\x00" + b"\x00" * 56
        res = StructuralValidator.validate_stage1_moc3_header(data)
        assert res.passed is False
        assert any("Invalid Endianness flag" in e for e in res.errors)


# ============================================================================
# CHALLENGE 2: STAGE 2 SECTION TABLE & COUNT SANITY ADVERSARIAL
# ============================================================================
class TestStage2SectionTablesAdversarial:
    """Stress-test 64-byte alignment, offset bounds, monotonicity, and count sanity."""

    def test_section_table_too_short_less_than_704_bytes(self):
        """MOC3 binary with 64-byte header but missing 640-byte section table must fail Stage 2."""
        data = b"MOC3\x03\x00\x00\x00" + b"\x00" * 200  # 208 bytes < 704 bytes
        res = StructuralValidator.validate_stage2_section_tables(data)
        assert res.stage_number == 2
        assert res.passed is False
        assert any("too short to contain 160-slot SectionOffsetTable" in e for e in res.errors)

    def test_unaligned_file_size_generates_warning(self, compliant_keyform_table):
        """MOC3 binary whose physical length is not a multiple of 64 triggers a warning."""
        moc_bytes = Moc3Writer.build_bytes(compliant_keyform_table)
        unaligned_bytes = moc_bytes + b"\x00\x00\x00"  # +3 bytes
        assert len(unaligned_bytes) % 64 != 0
        res = StructuralValidator.validate_stage2_section_tables(unaligned_bytes)
        # Should pass with warning
        assert any("not 64-byte aligned" in w for w in res.warnings)

    def test_section_offset_below_0x0740_header_area(self, compliant_keyform_table):
        """Non-zero section offset pointing into header/offset map area (< 0x0740) must fail."""
        moc_bytes = bytearray(Moc3Writer.build_bytes(compliant_keyform_table))
        # Slot 5 (offset at 64 + 5*4) corrupted to point to 0x0100 (< 0x0740)
        struct.pack_into("<I", moc_bytes, 64 + 5 * 4, 0x0100)
        res = StructuralValidator.validate_stage2_section_tables(bytes(moc_bytes))
        assert res.passed is False
        assert any("below header/map area" in e for e in res.errors)

    def test_non_monotonic_section_offsets(self, compliant_keyform_table):
        """Section offset decreasing relative to previous section offset must fail monotonicity."""
        moc_bytes = bytearray(Moc3Writer.build_bytes(compliant_keyform_table))
        # Slot 1 is 0x0840. Set slot 2 to 0x0780 (< 0x0840)
        struct.pack_into("<I", moc_bytes, 64 + 2 * 4, 0x0780)
        res = StructuralValidator.validate_stage2_section_tables(bytes(moc_bytes))
        assert res.passed is False
        assert any("violates monotonicity" in e for e in res.errors)

    def test_zero_art_meshes_count_table_failure(self, compliant_keyform_table):
        """CountInfoTable with 0 ArtMeshes must trigger Stage 2 error."""
        moc_bytes = bytearray(Moc3Writer.build_bytes(compliant_keyform_table))
        # CountInfoTable is at 0x0740 + 128 = 0x07C0. ArtMeshes is index 4
        struct.pack_into("<I", moc_bytes, 0x07C0 + 4 * 4, 0)
        res = StructuralValidator.validate_stage2_section_tables(bytes(moc_bytes))
        assert res.passed is False
        assert any("ArtMeshes count is 0" in e for e in res.errors)

    def test_zero_parameters_count_table_failure(self, compliant_keyform_table):
        """CountInfoTable with 0 Parameters must trigger Stage 2 error."""
        moc_bytes = bytearray(Moc3Writer.build_bytes(compliant_keyform_table))
        # Parameters is index 5
        struct.pack_into("<I", moc_bytes, 0x07C0 + 5 * 4, 0)
        res = StructuralValidator.validate_stage2_section_tables(bytes(moc_bytes))
        assert res.passed is False
        assert any("Parameters count is 0" in e for e in res.errors)

    def test_astronomical_count_table_failure(self, compliant_keyform_table):
        """CountInfoTable with astronomical count > 10M must trigger sanity error."""
        moc_bytes = bytearray(Moc3Writer.build_bytes(compliant_keyform_table))
        # Keys is index 14
        struct.pack_into("<I", moc_bytes, 0x07C0 + 14 * 4, 50_000_000)
        res = StructuralValidator.validate_stage2_section_tables(bytes(moc_bytes))
        assert res.passed is False
        assert any("astronomical" in e for e in res.errors)

    def test_non_positive_canvas_dimensions_failure(self, compliant_keyform_table):
        """CanvasInfo with width <= 0 or height <= 0 must fail Stage 2."""
        moc_bytes = bytearray(Moc3Writer.build_bytes(compliant_keyform_table))
        # CanvasInfo at 0x0840: 5 floats (ppu, ox, oy, width, height)
        # width is offset + 12, height is offset + 16
        struct.pack_into("<f", moc_bytes, 0x0840 + 12, 0.0)  # width = 0
        res = StructuralValidator.validate_stage2_section_tables(bytes(moc_bytes))
        assert res.passed is False
        assert any("Invalid Canvas dimensions" in e for e in res.errors)


# ============================================================================
# CHALLENGE 3: STAGE 3 JSON MANIFEST SCHEMA & PATH ADVERSARIAL
# ============================================================================
class TestStage3JsonManifestAdversarial:
    """Stress-test .model3.json and .cdi3.json parsing, missing fields, and paths."""

    def test_missing_model3_json_file(self, tmp_path):
        """Non-existent model3.json must fail Stage 3."""
        nonexistent = tmp_path / "NonExistent.model3.json"
        res, m3, cdi = StructuralValidator.validate_stage3_json_manifest(tmp_path, nonexistent)
        assert res.stage_number == 3
        assert res.passed is False
        assert any("model3.json not found" in e for e in res.errors)
        assert m3 is None

    def test_corrupted_json_syntax(self, compliant_model_bundle):
        """Syntax-corrupted JSON must fail Stage 3."""
        m3_path = compliant_model_bundle / "AdversarialCompliant.model3.json"
        with open(m3_path, "w") as f:
            f.write("{ Version: 3, FileReferences: { unquoted_key }")
        res, m3, cdi = StructuralValidator.validate_stage3_json_manifest(compliant_model_bundle, m3_path)
        assert res.passed is False
        assert any("Invalid JSON syntax" in e for e in res.errors)

    def test_unsupported_model3_version(self, compliant_model_bundle):
        """Version != 3 in model3.json must fail Stage 3."""
        m3_path = compliant_model_bundle / "AdversarialCompliant.model3.json"
        with open(m3_path, "r") as f:
            data = json.load(f)
        data["Version"] = 2
        with open(m3_path, "w") as f:
            json.dump(data, f)
        res, m3, _ = StructuralValidator.validate_stage3_json_manifest(compliant_model_bundle, m3_path)
        assert res.passed is False
        assert any("Expected Version == 3, got 2" in e for e in res.errors)

    def test_empty_file_references_in_model3_json(self, compliant_model_bundle):
        """model3.json missing FileReferences must fail Stage 3."""
        m3_path = compliant_model_bundle / "AdversarialCompliant.model3.json"
        with open(m3_path, "w") as f:
            json.dump({"Version": 3}, f)
        res, _, _ = StructuralValidator.validate_stage3_json_manifest(compliant_model_bundle, m3_path)
        assert res.passed is False
        assert any("Missing FileReferences" in e for e in res.errors)

    def test_empty_textures_list_in_model3_json(self, compliant_model_bundle):
        """Empty Textures list in FileReferences must fail Stage 3."""
        m3_path = compliant_model_bundle / "AdversarialCompliant.model3.json"
        with open(m3_path, "r") as f:
            data = json.load(f)
        data["FileReferences"]["Textures"] = []
        with open(m3_path, "w") as f:
            json.dump(data, f)
        res, _, _ = StructuralValidator.validate_stage3_json_manifest(compliant_model_bundle, m3_path)
        assert res.passed is False
        assert any("FileReferences.Textures is empty" in e for e in res.errors)

    def test_windows_backslash_rejection(self, compliant_model_bundle):
        """Windows backslash in relative paths must be flagged as an error for cross-platform portability."""
        m3_path = compliant_model_bundle / "AdversarialCompliant.model3.json"
        with open(m3_path, "r") as f:
            data = json.load(f)
        data["FileReferences"]["Moc"] = "subfolder\\model.moc3"
        with open(m3_path, "w") as f:
            json.dump(data, f)
        res, _, _ = StructuralValidator.validate_stage3_json_manifest(compliant_model_bundle, m3_path)
        assert res.passed is False
        assert any("Windows backslash" in e for e in res.errors)


# ============================================================================
# CHALLENGE 4: STAGE 4 PARAMETER & KEYFORM BOUNDS ADVERSARIAL
# ============================================================================
class TestStage4ParameterBoundsAdversarial:
    """Stress-test parameter definitions, range invariants, default bounds, and monotonicity."""

    def test_missing_param_angle_x(self):
        """CDI missing ParamAngleX must trigger Stage 4 error."""
        cdi = {"Version": 3, "Parameters": [{"Id": "ParamAngleY"}, {"Id": "ParamAngleZ"}]}
        res = StructuralValidator.validate_stage4_parameter_bounds(cdi)
        assert res.stage_number == 4
        assert res.passed is False
        assert any("Missing required parameter: ParamAngleX" in e for e in res.errors)

    def test_missing_param_angle_y(self):
        """CDI missing ParamAngleY must trigger Stage 4 error."""
        cdi = {"Version": 3, "Parameters": [{"Id": "ParamAngleX"}, {"Id": "ParamAngleZ"}]}
        res = StructuralValidator.validate_stage4_parameter_bounds(cdi)
        assert res.passed is False
        assert any("Missing required parameter: ParamAngleY" in e for e in res.errors)

    def test_missing_optional_param_angle_z_is_warning(self):
        """CDI with ParamAngleX/Y but missing ParamAngleZ should produce a warning, not an error."""
        cdi = {"Version": 3, "Parameters": [{"Id": "ParamAngleX"}, {"Id": "ParamAngleY"}]}
        res = StructuralValidator.validate_stage4_parameter_bounds(cdi)
        assert res.passed is True
        assert any("ParamAngleZ" in w for w in res.warnings)

    def test_inverted_parameter_bounds_min_greater_than_max(self):
        """KeyformTable with min_val >= max_val must fail Stage 4."""
        params = [
            ParameterBinding("ParamAngleX", min_val=30.0, default_val=0.0, max_val=-30.0),
            ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0),
        ]
        table = KeyformTable(parameters=params)
        cdi = {"Version": 3, "Parameters": [{"Id": "ParamAngleX"}, {"Id": "ParamAngleY"}]}
        res = StructuralValidator.validate_stage4_parameter_bounds(cdi, keyform_table=table)
        assert res.passed is False
        assert any("min (30.0) >= max (-30.0)" in e for e in res.errors)

    def test_default_value_out_of_bounds(self):
        """Parameter default value outside [min_val, max_val] must fail Stage 4."""
        params = [
            ParameterBinding("ParamAngleX", min_val=-30.0, default_val=45.0, max_val=30.0),
            ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0),
        ]
        table = KeyformTable(parameters=params)
        cdi = {"Version": 3, "Parameters": [{"Id": "ParamAngleX"}, {"Id": "ParamAngleY"}]}
        res = StructuralValidator.validate_stage4_parameter_bounds(cdi, keyform_table=table)
        assert res.passed is False
        assert any("default (45.0) not in [-30.0, 30.0]" in e for e in res.errors)

    def test_non_monotonic_key_values(self):
        """Non-monotonic key values array (e.g. [0.0, -30.0, 30.0]) must fail Stage 4."""
        params = [
            ParameterBinding("ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[0.0, -30.0, 30.0]),
            ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]),
        ]
        table = KeyformTable(parameters=params)
        cdi = {"Version": 3, "Parameters": [{"Id": "ParamAngleX"}, {"Id": "ParamAngleY"}]}
        res = StructuralValidator.validate_stage4_parameter_bounds(cdi, keyform_table=table)
        assert res.passed is False
        assert any("Non-monotonic key values" in e for e in res.errors)


# ============================================================================
# CHALLENGE 5: STAGE 5 TEXTURE ATLAS & UV COORDINATES ADVERSARIAL
# ============================================================================
class TestStage5TextureAtlasAndUVsAdversarial:
    """Stress-test texture POT dimensions, channel formats, and UV bounds."""

    @pytest.mark.parametrize("w,h", [(500, 500), (1023, 1024), (2048, 1536), (4097, 4096), (700, 800)])
    def test_non_power_of_two_dimensions(self, tmp_path, w, h):
        """Non-power-of-two texture dimensions must fail Stage 5."""
        tex_dir = tmp_path / "tex_test"
        tex_dir.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGBA", (w, h), (255, 0, 0, 255))
        tex_p = tex_dir / "bad_pot.png"
        img.save(tex_p)

        res = StructuralValidator.validate_stage5_textures_and_uvs(
            model_dir=tex_dir,
            texture_rel_paths=["bad_pot.png"]
        )
        assert res.stage_number == 5
        assert res.passed is False
        assert any("not power-of-two" in e for e in res.errors)

    def test_missing_texture_file_on_disk(self, tmp_path):
        """Missing texture file referenced in relative paths must fail Stage 5."""
        res = StructuralValidator.validate_stage5_textures_and_uvs(
            model_dir=tmp_path,
            texture_rel_paths=["ghost_texture_00.png"]
        )
        assert res.passed is False
        assert any("Texture file does not exist" in e for e in res.errors)

    def test_texture_dimension_outside_standard_range_warning(self, tmp_path):
        """POT Texture size 256x256 (<512) triggers a warning but not a hard error."""
        tex_dir = tmp_path / "small_tex"
        tex_dir.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGBA", (256, 256), (100, 100, 100, 255))
        img.save(tex_dir / "small_pot.png")

        res = StructuralValidator.validate_stage5_textures_and_uvs(
            model_dir=tex_dir,
            texture_rel_paths=["small_pot.png"]
        )
        assert res.passed is True
        assert any("outside standard range [512, 8192]" in w for w in res.warnings)

    def test_non_rgba_texture_format_warning(self, tmp_path):
        """RGB texture without alpha channel triggers a format warning."""
        tex_dir = tmp_path / "rgb_tex"
        tex_dir.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (1024, 1024), (200, 100, 50))
        img.save(tex_dir / "rgb.png")

        res = StructuralValidator.validate_stage5_textures_and_uvs(
            model_dir=tex_dir,
            texture_rel_paths=["rgb.png"]
        )
        assert res.passed is True
        assert any("Texture format is RGB" in w for w in res.warnings)

    def test_out_of_bounds_negative_uvs(self, compliant_model_bundle):
        """UV coordinates < 0.0 must trigger Stage 5 error."""
        bad_table = KeyformTable()
        bad_drawable = DrawableKeyforms(
            drawable_id="ArtMesh_BadUV",
            texture_index=0,
            base_vertices=np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float32),
            triangles=np.array([[0, 1, 2]], dtype=np.int32),
            uvs_atlas=np.array([[-0.1, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        )
        bad_table.drawables = [bad_drawable]

        res = StructuralValidator.validate_stage5_textures_and_uvs(
            model_dir=compliant_model_bundle,
            texture_rel_paths=["AdversarialCompliant.1024/texture_00.png"],
            keyform_table=bad_table
        )
        assert res.passed is False
        assert any("UV coordinates out of bounds" in e for e in res.errors)

    def test_out_of_bounds_excessive_uvs(self, compliant_model_bundle):
        """UV coordinates > 1.0 must trigger Stage 5 error."""
        bad_table = KeyformTable()
        bad_drawable = DrawableKeyforms(
            drawable_id="ArtMesh_BadUV",
            texture_index=0,
            base_vertices=np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float32),
            triangles=np.array([[0, 1, 2]], dtype=np.int32),
            uvs_atlas=np.array([[0.0, 0.0], [1.25, 0.0], [0.0, 1.0]], dtype=np.float32)
        )
        bad_table.drawables = [bad_drawable]

        res = StructuralValidator.validate_stage5_textures_and_uvs(
            model_dir=compliant_model_bundle,
            texture_rel_paths=["AdversarialCompliant.1024/texture_00.png"],
            keyform_table=bad_table
        )
        assert res.passed is False
        assert any("UV coordinates out of bounds" in e for e in res.errors)

    def test_nan_uv_coordinates_vulnerability(self, compliant_model_bundle):
        """
        Adversarial test: UV coordinates containing NaN.
        Documents whether Stage 5 detects NaN/Inf UV coordinates or if IEEE 754 NaN comparisons bypass bounds checks.
        """
        bad_table = KeyformTable()
        bad_drawable = DrawableKeyforms(
            drawable_id="ArtMesh_NaN_UV",
            texture_index=0,
            base_vertices=np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float32),
            triangles=np.array([[0, 1, 2]], dtype=np.int32),
            uvs_atlas=np.array([[np.nan, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        )
        bad_table.drawables = [bad_drawable]

        res = StructuralValidator.validate_stage5_textures_and_uvs(
            model_dir=compliant_model_bundle,
            texture_rel_paths=["AdversarialCompliant.1024/texture_00.png"],
            keyform_table=bad_table
        )
        assert res.passed is False
        assert any("NaN or Inf UV coordinates" in e for e in res.errors)



# ============================================================================
# CHALLENGE 6: STAGE 6 TOPOLOGY & NON-INVERSION ADVERSARIAL
# ============================================================================
class TestStage6TopologyAndDeformationAdversarial:
    """Stress-test non-inversion, NaN/Inf coordinates, and triangle index bounds."""

    def test_rest_pose_nan_vertex_coordinates(self):
        """Rest pose vertex array containing NaN must fail Stage 6."""
        base_v = np.array([[0.0, 0.0], [np.nan, 0.0], [0.0, 1.0]], dtype=np.float32)
        triangles = np.array([[0, 1, 2]], dtype=np.int32)
        d = DrawableKeyforms(
            drawable_id="ArtMesh_NaN",
            texture_index=0,
            base_vertices=base_v,
            triangles=triangles,
            uvs_atlas=np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float32)
        )
        table = KeyformTable(drawables=[d])
        res = StructuralValidator.validate_stage6_topology_and_deformation(keyform_table=table)
        assert res.stage_number == 6
        assert res.passed is False
        assert any("NaN or Inf vertex coordinates found in rest pose" in e for e in res.errors)

    def test_rest_pose_inf_vertex_coordinates(self):
        """Rest pose vertex array containing Infinity must fail Stage 6."""
        base_v = np.array([[0.0, 0.0], [np.inf, 0.0], [0.0, 1.0]], dtype=np.float32)
        triangles = np.array([[0, 1, 2]], dtype=np.int32)
        d = DrawableKeyforms(
            drawable_id="ArtMesh_Inf",
            texture_index=0,
            base_vertices=base_v,
            triangles=triangles,
            uvs_atlas=np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float32)
        )
        table = KeyformTable(drawables=[d])
        res = StructuralValidator.validate_stage6_topology_and_deformation(keyform_table=table)
        assert res.passed is False
        assert any("NaN or Inf vertex coordinates found in rest pose" in e for e in res.errors)

    def test_triangle_index_out_of_range(self):
        """Triangle referring to vertex index >= len(base_vertices) must fail Stage 6."""
        base_v = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32)  # 3 vertices [0, 1, 2]
        triangles = np.array([[0, 1, 99]], dtype=np.int32)  # Index 99 out of range
        d = DrawableKeyforms(
            drawable_id="ArtMesh_BadIndex",
            texture_index=0,
            base_vertices=base_v,
            triangles=triangles,
            uvs_atlas=np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float32)
        )
        table = KeyformTable(drawables=[d])
        res = StructuralValidator.validate_stage6_topology_and_deformation(keyform_table=table)
        assert res.passed is False
        assert any("Index out of range in triangles" in e for e in res.errors)

    def test_inverted_triangle_in_keyform_deformation(self):
        """Deformed keyform causing clockwise inverted triangle winding must fail Stage 6."""
        base_v = np.array([[0.0, 0.0], [10.0, 0.0], [0.0, 10.0]], dtype=np.float32)
        triangles = np.array([[0, 1, 2]], dtype=np.int32)
        # Flip vertex 1 from x=10 to x=-10 -> negative signed area
        inverted_kf = np.array([[0.0, 0.0], [-10.0, 0.0], [0.0, 10.0]], dtype=np.float32)

        d = DrawableKeyforms(
            drawable_id="ArtMesh_Inversion",
            texture_index=0,
            base_vertices=base_v,
            triangles=triangles,
            uvs_atlas=np.array([[0, 0], [1, 0], [0, 1]], dtype=np.float32),
            deformed_positions={(30.0, 30.0): inverted_kf}
        )
        table = KeyformTable(drawables=[d])
        res = StructuralValidator.validate_stage6_topology_and_deformation(keyform_table=table)
        assert res.passed is False
        assert any("Inverted triangle" in e for e in res.errors)


# ============================================================================
# CHALLENGE 7: MASTER VALIDATOR ENTRYPOINT & STRICT MODE ADVERSARIAL
# ============================================================================
class TestMasterValidatorAdversarial:
    """Stress-test validate_live2d_model entrypoint across multiple input representations."""

    def test_validate_directory_path(self, compliant_model_bundle):
        """Validator accepts root directory path."""
        report = validate_live2d_model(compliant_model_bundle)
        assert report.passed is True
        assert report.is_valid is True
        assert report.total_errors == 0
        assert len(report.stages_passed) == 6

    def test_validate_model3_json_path(self, compliant_model_bundle):
        """Validator accepts direct .model3.json path."""
        m3_path = compliant_model_bundle / "AdversarialCompliant.model3.json"
        report = validate_live2d_model(m3_path)
        assert report.passed is True
        assert report.total_errors == 0

    def test_validate_moc3_binary_path(self, compliant_model_bundle):
        """Validator accepts direct .moc3 binary path."""
        moc_path = compliant_model_bundle / "AdversarialCompliant.moc3"
        report = validate_live2d_model(moc_path)
        assert report.passed is True
        assert report.total_errors == 0

    def test_strict_mode_fails_on_warnings(self, compliant_model_bundle):
        """In strict=True mode, any warning causes report.passed to become False."""
        # Inject non-standard texture dimension (256x256) to trigger warning in Stage 5
        tex_path = compliant_model_bundle / "AdversarialCompliant.1024" / "texture_00.png"
        small_img = Image.new("RGBA", (256, 256), (255, 200, 180, 255))
        small_img.save(tex_path)

        # Normal mode: passes with warning
        report_normal = validate_live2d_model(compliant_model_bundle, strict=False)
        assert report_normal.passed is True
        assert report_normal.total_warnings > 0

        # Strict mode: fails because of warning
        report_strict = validate_live2d_model(compliant_model_bundle, strict=True)
        assert report_strict.passed is False
        assert report_strict.total_warnings > 0


# ============================================================================
# CHALLENGE 8: CLI INVOCATIONS & EXIT CODES ADVERSARIAL
# ============================================================================
class TestCLIInvocationsAndExitCodesAdversarial:
    """Stress-test CLI invocations, flag parsing, and exit codes 0..5."""

    def test_exit_code_1_on_missing_input_arguments(self):
        """Running pipeline without arguments returns EXIT_ERR_INPUT (1)."""
        exit_code = run_pipeline([])
        assert exit_code == EXIT_ERR_INPUT

    def test_exit_code_1_on_nonexistent_input_file(self, tmp_path):
        """Nonexistent input path returns EXIT_ERR_INPUT (1)."""
        bad_path = str(tmp_path / "phantom_asset.png")
        exit_code = run_pipeline([bad_path, "-o", str(tmp_path / "out")])
        assert exit_code == EXIT_ERR_INPUT

    def test_exit_code_1_on_unsupported_file_extension(self, tmp_path):
        """Unsupported file extension (.txt) returns EXIT_ERR_INPUT (1)."""
        txt_path = tmp_path / "invalid_asset.txt"
        txt_path.write_text("Hello Live2D", encoding="utf-8")
        exit_code = run_pipeline([str(txt_path), "-o", str(tmp_path / "out")])
        assert exit_code == EXIT_ERR_INPUT

    def test_exit_code_1_on_empty_layer_directory(self, tmp_path):
        """Empty folder with no valid image files returns EXIT_ERR_INPUT (1)."""
        empty_dir = tmp_path / "empty_layer_folder"
        empty_dir.mkdir(parents=True, exist_ok=True)
        exit_code = run_pipeline([str(empty_dir), "-o", str(tmp_path / "out")])
        assert exit_code == EXIT_ERR_INPUT

    def test_exit_code_0_on_successful_export_with_validation(self, synthetic_avatar_png, tmp_path):
        """Valid export with post-export validation returns EXIT_SUCCESS (0)."""
        out_dir = tmp_path / "cli_success_output"
        exit_code = run_pipeline([
            str(synthetic_avatar_png),
            "-o", str(out_dir),
            "-n", "AvatarSuccess",
            "--resolution", "1024",
            "--grid-size", "30",
            "--validate"
        ])
        assert exit_code == EXIT_SUCCESS
        model_dir = out_dir / "AvatarSuccess"
        assert (model_dir / "AvatarSuccess.model3.json").exists()
        assert (model_dir / "AvatarSuccess.moc3").exists()
        assert (model_dir / "AvatarSuccess.cdi3.json").exists()

    def test_standalone_validate_live2d_cli_exit_codes(self, compliant_model_bundle, tmp_path):
        """Standalone validate_live2d.py returns 0 on pass, 1 on missing/bad path, 5 on fail."""
        # 1. Missing arguments -> exit code 1
        assert val_main([]) == 1

        # 2. Non-existent path -> exit code 1
        assert val_main([str(tmp_path / "nonexistent_dir")]) == 1

        # 3. Valid model -> exit code 0
        assert val_main([str(compliant_model_bundle), "--quiet"]) == 0

        # 4. JSON report generation
        json_rep_path = tmp_path / "val_report.json"
        assert val_main([str(compliant_model_bundle), "-o", str(json_rep_path), "--quiet"]) == 0
        assert json_rep_path.exists()
        with open(json_rep_path, "r", encoding="utf-8") as f:
            rep_data = json.load(f)
        assert rep_data["is_valid"] is True

        # 5. Corrupt model (delete .moc3) -> exit code 5 (validation failure)
        moc_file = compliant_model_bundle / "AdversarialCompliant.moc3"
        moc_file.unlink()
        assert val_main([str(compliant_model_bundle), "--quiet"]) == 5
