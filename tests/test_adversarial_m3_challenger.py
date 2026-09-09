"""
tests/test_adversarial_m3_challenger.py
Empirical Adversarial Stress Test Suite for Live2D Exporter Pipeline (Milestone 3).
Authored by Challenger 2 (Empirical Challenger).

Stress-tests:
1. Strict binary byte-level layout (magic, version, endianness, SectionOffsetTable, null map, CountInfoTable, CanvasInfo)
2. Strict 64-byte alignment invariants across diverse mesh topologies and counts
3. 9-keyform Cartesian grid ($3 \times 3$ Angle X/Y) displacement tensors and vertex integrity
4. Fuzzing, byte-flipping, offset corruptions, and error handling resilience
5. Live2D Cubism Version 3 manifest JSON schema validation and forward-slash path safety
"""

import copy
import json
import os
from pathlib import Path
import random
import struct
import numpy as np
import pytest

from src.core.keyform import KeyformTable, ParameterBinding, DrawableKeyforms
from src.exporter.moc3_writer import (
    Moc3Writer,
    Moc3Reader,
    validate_moc3_bytes,
    align_to_64,
    pad_buffer_to_64,
    encode_id_64,
    decode_id_64,
)
from src.exporter.model3_writer import Model3Writer
from src.exporter.texture_packer import TextureAtlasPacker, MaxRectsBin


# ============================================================================
# FIXTURES & HELPERS
# ============================================================================

@pytest.fixture
def complex_9keyform_model():
    """
    Creates a multi-drawable model with realistic 9-keyform Cartesian grid
    (3x3 for Angle X in [-30, 0, 30] and Angle Y in [-30, 0, 30]) plus Angle Z.
    """
    table = KeyformTable(
        canvas_width=2048,
        canvas_height=2048,
        model_name="AdversarialAvatar"
    )

    table.add_parameter(ParameterBinding(
        param_id="ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0,
        key_values=[-30.0, 0.0, 30.0], name="Angle X"
    ))
    table.add_parameter(ParameterBinding(
        param_id="ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0,
        key_values=[-30.0, 0.0, 30.0], name="Angle Y"
    ))
    table.add_parameter(ParameterBinding(
        param_id="ParamAngleZ", min_val=-30.0, default_val=0.0, max_val=30.0,
        key_values=[-30.0, 0.0, 30.0], name="Angle Z"
    ))

    # Drawable 1: Quad mesh (4 vertices, 2 triangles)
    base_v1 = np.array([
        [-100.0, -100.0],
        [ 100.0, -100.0],
        [ 100.0,  100.0],
        [-100.0,  100.0]
    ], dtype=np.float32)
    tris1 = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    uvs1 = np.array([[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]], dtype=np.float32)

    d1 = DrawableKeyforms(
        drawable_id="ArtMesh_Face",
        texture_index=0,
        base_vertices=base_v1,
        triangles=tris1,
        uvs_atlas=uvs1,
        draw_order=500,
        opacity=1.0,
        blend_mode=0
    )

    # Populate 9 keyforms for 3x3 AngleX / AngleY
    for ay in [-30.0, 0.0, 30.0]:
        for ax in [-30.0, 0.0, 30.0]:
            if ax == 0.0 and ay == 0.0:
                d1.add_keyform((ax, ay), base_v1.copy())  # Identity keyform
            else:
                shift = np.array([ax * 0.5, ay * 0.5], dtype=np.float32)
                d1.add_keyform((ax, ay), base_v1 + shift)

    table.add_drawable(d1)

    # Drawable 2: Triangle mesh (3 vertices, 1 triangle) with distinct texture and displacements
    base_v2 = np.array([
        [-50.0, -150.0],
        [ 50.0, -150.0],
        [  0.0,  -80.0]
    ], dtype=np.float32)
    tris2 = np.array([[0, 1, 2]], dtype=np.int32)
    uvs2 = np.array([[0.5, 0.1], [0.8, 0.1], [0.65, 0.3]], dtype=np.float32)

    d2 = DrawableKeyforms(
        drawable_id="ArtMesh_HairFront",
        texture_index=0,
        base_vertices=base_v2,
        triangles=tris2,
        uvs_atlas=uvs2,
        draw_order=600,
        opacity=1.0,
        blend_mode=1
    )

    for ay in [-30.0, 0.0, 30.0]:
        for ax in [-30.0, 0.0, 30.0]:
            if ax == 0.0 and ay == 0.0:
                d2.add_keyform((ax, ay), base_v2.copy())  # Identity keyform
            else:
                shift = np.array([ax * 1.2, ay * 1.2], dtype=np.float32)
                d2.add_keyform((ax, ay), base_v2 + shift)

    table.add_drawable(d2)
    return table


# ============================================================================
# 1. BINARY BYTE-LEVEL INSPECTION TESTS
# ============================================================================

class TestBinaryByteLevelInspection:
    """Byte-accurate dissection of .moc3 binary layout according to Live2D specification."""

    def test_fixed_header_byte_layout(self, complex_9keyform_model):
        """Dissect and verify the exact 64-byte file header at offset 0x0000."""
        raw = Moc3Writer.build_bytes(complex_9keyform_model)
        assert len(raw) >= 64

        # Magic: offset 0x0000, 4 bytes == b"MOC3"
        magic = raw[0:4]
        assert magic == b"MOC3", f"Expected b'MOC3', got {magic}"

        # Version: offset 0x0004, 1 byte uint8 == 3
        version = raw[4]
        assert version == 3, f"Expected Version 3, got {version}"

        # Endianness: offset 0x0005, 1 byte uint8 == 0 (Little Endian)
        endianness = raw[5]
        assert endianness == 0, f"Expected Little-Endian (0), got {endianness}"

        # Diagnostic summary integers packed in header[8..32]
        num_drawables, num_params = struct.unpack_from("<II", raw, 8)
        assert num_drawables == 2
        assert num_params == 3

    def test_section_offset_table_160_entries_at_0x0040(self, complex_9keyform_model):
        """Verify the 640-byte SectionOffsetTable (160 uint32 entries) at offset 0x0040."""
        raw = Moc3Writer.build_bytes(complex_9keyform_model)
        assert len(raw) >= 0x02C0  # 704 bytes

        # Read 160 uint32 entries starting at offset 64 (0x0040)
        offsets = struct.unpack_from("<160I", raw, 0x0040)
        assert len(offsets) == 160

        # Section 0 (CountInfoTable) must be at 0x07C0 (after 64B header + 640B offset table + 1280B runtime map)
        assert offsets[0] == 0x07C0, f"CountInfoTable expected at 0x07C0, got {hex(offsets[0])}"
        # Section 1 (CanvasInfo) must be at 0x0840
        assert offsets[1] == 0x0840, f"CanvasInfo expected at 0x0840, got {hex(offsets[1])}"

        # Check all non-zero offsets are strictly >= 0x07C0
        for i, off in enumerate(offsets):
            if off != 0:
                assert off >= 0x07C0, f"Section [{i}] offset {hex(off)} placed before payload base (0x07C0)"

    def test_null_runtime_address_map_at_0x02C0(self, complex_9keyform_model):
        """Verify the 1280-byte null map at 0x02C0 reserved for csmReviveMocInPlace."""
        raw = Moc3Writer.build_bytes(complex_9keyform_model)
        assert len(raw) >= 0x07C0  # 1984 bytes

        null_map = raw[0x02C0:0x07C0]
        assert len(null_map) == 1280, f"Expected 1280 bytes null map, got {len(null_map)}"
        assert null_map == b"\x00" * 1280, "RuntimeAddressMap at 0x02C0 is not pure null bytes"

    def test_count_info_table_structure_at_0x07c0(self, complex_9keyform_model):
        """Verify CountInfoTable structure (128 bytes = 32 uint32s) at offset 0x07C0."""
        raw = Moc3Writer.build_bytes(complex_9keyform_model)
        assert len(raw) >= 0x0840

        count_table_data = raw[0x07C0:0x0840]
        assert len(count_table_data) == 128

        # Unpack the 23 uint32 counters
        counters = struct.unpack_from("<23I", count_table_data, 0)
        parts = counters[0]
        art_meshes = counters[4]
        parameters = counters[5]
        art_mesh_keyforms = counters[9]
        keyform_positions = counters[10]
        keys = counters[14]
        uvs = counters[15]
        position_indices = counters[16]

        assert parts == 1  # PartRoot
        assert art_meshes == 2
        assert parameters == 3
        assert art_mesh_keyforms == 18  # 2 drawables * 9 keyforms
        assert keyform_positions == 126  # ((4 verts * 9) + (3 verts * 9)) * 2 floats = (36 + 27) * 2 = 126
        assert keys == 9  # 3 params * 3 keys each
        assert uvs == 14  # (4 verts + 3 verts) * 2 floats = 14
        assert position_indices == 9  # (2 tris * 3) + (1 tri * 3) = 6 + 3 = 9

    def test_canvas_info_structure_at_0x0840(self, complex_9keyform_model):
        """Verify CanvasInfo section (64 bytes) at offset 0x0840."""
        raw = Moc3Writer.build_bytes(complex_9keyform_model)
        assert len(raw) >= 0x0880

        canvas_data = raw[0x0840:0x0880]
        assert len(canvas_data) == 64

        ppu, ox, oy, cw, ch, flags = struct.unpack_from("<5fB", canvas_data, 0)
        assert cw == 2048.0
        assert ch == 2048.0
        assert ox == 1024.0
        assert oy == 1024.0
        assert ppu == 2048.0
        assert flags == 0

        # Trailing 43 bytes padding
        canvas_pad = canvas_data[21:]
        assert len(canvas_pad) == 43
        assert canvas_pad == b"\x00" * 43, "CanvasInfo trailing 43-byte pad is not null"


# ============================================================================
# 2. STRICT 64-BYTE ALIGNMENT STRESS TESTS
# ============================================================================

class TestStrict64ByteAlignment:
    """Stress-tests memory alignment across extreme vertex counts and topologies."""

    @pytest.mark.parametrize("n_drawables", [1, 2, 5, 13])
    @pytest.mark.parametrize("verts_per_mesh", [3, 4, 7, 11, 23])
    def test_64_byte_alignment_invariant(self, n_drawables, verts_per_mesh):
        """Verify that every section offset and total file length is strictly a multiple of 64."""
        table = KeyformTable(canvas_width=1024, canvas_height=1024)
        table.add_parameter(ParameterBinding("ParamAngleX", -30.0, 0.0, 30.0, [-30.0, 0.0, 30.0]))

        for d_idx in range(n_drawables):
            # Generate arbitrary mesh with verts_per_mesh
            verts = np.random.uniform(-100, 100, (verts_per_mesh, 2)).astype(np.float32)
            # Create at least 1 triangle
            tris = np.array([[0, 1, 2]], dtype=np.int32) if verts_per_mesh >= 3 else np.array([[0, 0, 0]], dtype=np.int32)
            uvs = np.random.uniform(0.0, 1.0, (verts_per_mesh, 2)).astype(np.float32)

            d = DrawableKeyforms(
                drawable_id=f"Mesh_{d_idx:03d}",
                texture_index=0,
                base_vertices=verts,
                triangles=tris,
                uvs_atlas=uvs
            )
            # 3 keyforms
            for k in [-30.0, 0.0, 30.0]:
                d.add_keyform((k,), verts + float(k) * 0.1)
            table.add_drawable(d)

        raw = Moc3Writer.build_bytes(table)

        # 1. Total size must be divisible by 64
        assert len(raw) % 64 == 0, f"Binary size {len(raw)} is not 64-byte aligned"

        # 2. Every non-zero section offset must be divisible by 64 and within binary bounds
        section_offsets = struct.unpack_from("<160I", raw, 0x0040)
        for slot_idx, off in enumerate(section_offsets):
            if off > 0:
                assert off % 64 == 0, f"Slot {slot_idx} offset {hex(off)} not aligned to 64 bytes"
                assert off < len(raw), f"Slot {slot_idx} offset {hex(off)} >= binary size {len(raw)}"

        # 3. Structural validator must confirm validity
        val_res = validate_moc3_bytes(raw)
        assert val_res["is_valid"] is True
        assert len(val_res["errors"]) == 0


# ============================================================================
# 3. 9-KEYFORM DISPLACEMENT ARRAY VERIFICATION
# ============================================================================

class TestKeyformDisplacementTensorVerification:
    """Verifies that 9-keyform Cartesian grid deformations are accurately serialized."""

    def test_9keyform_displacement_extraction_and_identity_check(self, complex_9keyform_model):
        """
        Extracts raw float32 arrays from KeyformPositions.XYs (section 32)
        and verifies identity keyform (0, 0) and non-zero displacements.
        """
        raw = Moc3Writer.build_bytes(complex_9keyform_model)
        offsets = struct.unpack_from("<160I", raw, 0x0040)

        pos_offset = offsets[71]  # Section 71: KeyformPositions.XYs
        assert pos_offset > 0

        # Drawable 1 has 4 vertices * 9 keyforms = 36 points (72 floats)
        # Drawable 2 has 3 vertices * 9 keyforms = 27 points (54 floats)
        # Total = 63 points (126 floats = 504 bytes)
        total_floats = 63 * 2
        raw_floats = struct.unpack_from(f"<{total_floats}f", raw, pos_offset)
        coords = np.array(raw_floats, dtype=np.float32).reshape(-1, 2)

        # Inspect Drawable 1: first 36 points (9 keyforms of 4 vertices each)
        d1_coords = coords[:36].reshape(9, 4, 2)
        d1_base = complex_9keyform_model.drawables[0].base_vertices

        # Keyform index 4 corresponds to (ay=0, ax=0) because grid is:
        # (-30,-30), (-30,0), (-30,30), (0,-30), (0,0), (0,30), (30,-30), (30,0), (30,30)
        kf_tuples = [
            (-30.0, -30.0), (-30.0, 0.0), (-30.0, 30.0),
            (0.0, -30.0),   (0.0, 0.0),   (0.0, 30.0),
            (30.0, -30.0),  (30.0, 0.0),  (30.0, 30.0)
        ]

        for kf_idx, (ay, ax) in enumerate(kf_tuples):
            kf_verts = d1_coords[kf_idx]
            if ax == 0.0 and ay == 0.0:
                # Identity check: EXACT match with base vertices
                np.testing.assert_allclose(kf_verts, d1_base, atol=1e-5,
                                           err_msg=f"Identity keyform (0,0) does not match base vertices")
            else:
                expected_shift = np.array([ax * 0.5, ay * 0.5], dtype=np.float32)
                expected_verts = d1_base + expected_shift
                np.testing.assert_allclose(kf_verts, expected_verts, atol=1e-5,
                                           err_msg=f"Keyform ({ax}, {ay}) displacement mismatch")

        # Inspect Drawable 2: next 27 points (9 keyforms of 3 vertices each)
        d2_coords = coords[36:].reshape(9, 3, 2)
        d2_base = complex_9keyform_model.drawables[1].base_vertices

        for kf_idx, (ay, ax) in enumerate(kf_tuples):
            kf_verts = d2_coords[kf_idx]
            if ax == 0.0 and ay == 0.0:
                np.testing.assert_allclose(kf_verts, d2_base, atol=1e-5,
                                           err_msg="Drawable 2 identity keyform mismatch")
            else:
                expected_shift = np.array([ax * 1.2, ay * 1.2], dtype=np.float32)
                expected_verts = d2_base + expected_shift
                np.testing.assert_allclose(kf_verts, expected_verts, atol=1e-5,
                                           err_msg=f"Drawable 2 keyform ({ax}, {ay}) mismatch")

    def test_uv_and_indices_exact_fidelity(self, complex_9keyform_model):
        """Verifies UVs and Triangle index buffer exact fidelity in binary output."""
        raw = Moc3Writer.build_bytes(complex_9keyform_model)
        offsets = struct.unpack_from("<160I", raw, 0x0040)

        # UVs: Section 78
        uv_offset = offsets[78]
        total_uv_floats = 7 * 2  # 7 vertices * (u, v) = 14 floats
        raw_uvs = struct.unpack_from(f"<{total_uv_floats}f", raw, uv_offset)
        uv_array = np.array(raw_uvs, dtype=np.float32).reshape(-1, 2)

        # Check Drawable 1 UVs
        np.testing.assert_allclose(uv_array[:4], complex_9keyform_model.drawables[0].uvs_atlas, atol=1e-6)
        # Check Drawable 2 UVs
        np.testing.assert_allclose(uv_array[4:], complex_9keyform_model.drawables[1].uvs_atlas, atol=1e-6)

        # Indices: Section 79
        idx_offset = offsets[79]
        total_indices = 9  # 9 uint16 entries
        raw_indices = struct.unpack_from(f"<{total_indices}H", raw, idx_offset)
        assert list(raw_indices[:6]) == [0, 1, 2, 0, 2, 3]  # d1 tris
        assert list(raw_indices[6:]) == [0, 1, 2]           # d2 tris


# ============================================================================
# 4. ADVERSARIAL CORRUPTION & FUZZING TESTS
# ============================================================================

class TestAdversarialCorruptionAndFuzzing:
    """Tests resilience against malformed headers, invalid counts, bit corruption, and bad inputs."""

    def test_corrupt_magic_rejection(self, complex_9keyform_model):
        """Corrupting header magic bytes must trigger validation failure and deserialization error."""
        raw = bytearray(Moc3Writer.build_bytes(complex_9keyform_model))
        for bad_magic in [b"MOC4", b"LIVE", b"RIFF", b"\x00\x00\x00\x00", b"JPEG"]:
            raw[0:4] = bad_magic
            corrupted = bytes(raw)

            # Moc3Reader must raise ValueError
            with pytest.raises(ValueError, match="Invalid MOC3 magic header"):
                Moc3Reader.parse_bytes(corrupted)

            # validate_moc3_bytes must return is_valid=False
            res = validate_moc3_bytes(corrupted)
            assert res["is_valid"] is False
            assert any("Invalid MOC3 magic header" in err for err in res["errors"])

    def test_corrupt_endianness_rejection(self, complex_9keyform_model):
        """Big-endian (1) or invalid endian flag must be rejected."""
        raw = bytearray(Moc3Writer.build_bytes(complex_9keyform_model))
        raw[5] = 1  # Set big-endian
        corrupted = bytes(raw)

        with pytest.raises(ValueError, match="Unsupported endianness"):
            Moc3Reader.parse_bytes(corrupted)

    def test_truncated_binary_handling(self, complex_9keyform_model):
        """Truncated binary streams of various lengths must be cleanly handled without unhandled crashes."""
        raw = Moc3Writer.build_bytes(complex_9keyform_model)

        for trunc_len in [0, 1, 16, 63, 64, 128, 512, 703, 1024, 1855]:
            truncated = raw[:trunc_len]
            if trunc_len < 64:
                with pytest.raises(ValueError, match="too small"):
                    Moc3Reader.parse_bytes(truncated)
                res = validate_moc3_bytes(truncated)
                assert res["is_valid"] is False
            elif trunc_len < 704:
                # Header present, but section offset table truncated/missing
                parsed = Moc3Reader.parse_bytes(truncated)
                assert parsed["magic"] == "MOC3"
                assert parsed["version"] == 3
            else:
                # Partial payload: offsets pointing past EOF must be caught by validate_moc3_bytes
                res = validate_moc3_bytes(truncated)
                if trunc_len < len(raw):
                    assert res["is_valid"] is False
                    assert any("exceeds file size" in err for err in res["errors"])

    def test_unaligned_section_offsets_detection(self, complex_9keyform_model):
        """Misaligned section offsets must be flagged by validate_moc3_bytes."""
        raw = bytearray(Moc3Writer.build_bytes(complex_9keyform_model))

        # Corrupt section offset 0 (CountInfoTable) by adding 1 byte offset
        orig_off = struct.unpack_from("<I", raw, 0x0040)[0]
        struct.pack_into("<I", raw, 0x0040, orig_off + 1)  # 0x0741 is unaligned

        res = validate_moc3_bytes(bytes(raw))
        assert res["is_valid"] is False
        assert any("not 64-byte aligned" in err for err in res["errors"])

    def test_out_of_bounds_section_offset_detection(self, complex_9keyform_model):
        """Section offset pointing beyond EOF must be flagged."""
        raw = bytearray(Moc3Writer.build_bytes(complex_9keyform_model))
        struct.pack_into("<I", raw, 0x0040, len(raw) + 64)

        res = validate_moc3_bytes(bytes(raw))
        assert res["is_valid"] is False
        assert any("exceeds file size" in err for err in res["errors"])

    def test_random_bit_flip_fuzzing(self, complex_9keyform_model):
        """Fuzz 100 iterations of random bit flips across the binary; must not segfault or hang."""
        base_raw = Moc3Writer.build_bytes(complex_9keyform_model)
        rng = random.Random(42)

        for _ in range(100):
            corrupted = bytearray(base_raw)
            # Pick random position and flip random bit
            pos = rng.randint(0, len(corrupted) - 1)
            bit = rng.randint(0, 7)
            corrupted[pos] ^= (1 << bit)

            data = bytes(corrupted)
            try:
                val_res = validate_moc3_bytes(data)
                # Ensure validate_moc3_bytes returns structured dict with bool is_valid
                assert isinstance(val_res, dict)
                assert "is_valid" in val_res
            except Exception as e:
                # Should not raise unexpected unhandled exceptions
                pytest.fail(f"Unhandled exception during fuzzing: {type(e).__name__}: {e}")

    def test_invalid_keyform_table_inputs(self):
        """Ensure Moc3Writer.build_bytes strictly rejects bad table configurations."""
        # 1. No parameters
        empty_params_table = KeyformTable()
        d = DrawableKeyforms(
            "Mesh1",
            base_vertices=np.array([[0, 0]], dtype=np.float32),
            triangles=np.array([[0, 0, 0]], dtype=np.int32),
            uvs_atlas=np.array([[0, 0]], dtype=np.float32)
        )
        empty_params_table.add_drawable(d)
        with pytest.raises(ValueError, match="Invalid KeyformTable"):
            Moc3Writer.build_bytes(empty_params_table)

        # 2. No drawables
        empty_drawables_table = KeyformTable()
        empty_drawables_table.add_parameter(ParameterBinding("ParamAngleX"))
        with pytest.raises(ValueError, match="Invalid KeyformTable"):
            Moc3Writer.build_bytes(empty_drawables_table)

        # 3. Shape mismatch between keyform and base vertices
        mismatch_table = KeyformTable()
        mismatch_table.add_parameter(ParameterBinding("ParamAngleX"))
        d_bad_shape = DrawableKeyforms(
            "MeshBad",
            base_vertices=np.array([[0, 0], [1, 1]], dtype=np.float32),
            triangles=np.array([[0, 1, 0]], dtype=np.int32),
            uvs_atlas=np.array([[0, 0], [1, 1]], dtype=np.float32)
        )
        # Add keyform with 3 vertices instead of 2 (using direct dict assignment to test validation)
        d_bad_shape.deformed_positions[(0.0,)] = np.zeros((3, 2), dtype=np.float32)
        mismatch_table.add_drawable(d_bad_shape)
        with pytest.raises(ValueError, match="Invalid KeyformTable"):
            Moc3Writer.build_bytes(mismatch_table)


# ============================================================================
# 5. MANIFEST JSON SCHEMA & PATH SAFETY TESTS
# ============================================================================

class TestManifestJsonValidation:
    """Stress-tests .model3.json and .cdi3.json generation, schemas, and path normalizations."""

    def test_model3_json_schema_and_keys(self):
        """Verify strict adherence to Live2D Version 3 model3 manifest specification."""
        manifest = Model3Writer.generate_model3_json(
            model_name="TestChar",
            moc_rel_path="TestChar.moc3",
            texture_rel_paths=["textures/texture_00.png", "textures/texture_01.png"],
            physics_rel_path="TestChar.physics3.json",
            cdi_rel_path="TestChar.cdi3.json",
            pose_rel_path="TestChar.pose3.json"
        )

        assert manifest["Version"] == 3
        assert "FileReferences" in manifest
        fref = manifest["FileReferences"]
        assert fref["Moc"] == "TestChar.moc3"
        assert fref["Textures"] == ["textures/texture_00.png", "textures/texture_01.png"]
        assert fref["Physics"] == "TestChar.physics3.json"
        assert fref["DisplayInfo"] == "TestChar.cdi3.json"
        assert fref["Pose"] == "TestChar.pose3.json"

        # Verify Groups structure
        groups = manifest.get("Groups", [])
        assert len(groups) >= 2
        g_map = {g["Name"]: g for g in groups}
        assert "LipSync" in g_map
        assert "EyeBlink" in g_map
        assert g_map["LipSync"]["Target"] == "Parameter"
        assert "ParamMouthOpenY" in g_map["LipSync"]["Ids"]
        assert "ParamEyeLOpen" in g_map["EyeBlink"]["Ids"]

        # Verify Layout
        layout = manifest.get("Layout", {})
        assert layout.get("CenterX") == 0.0
        assert layout.get("CenterY") == 0.0
        assert layout.get("Width") == 2.0
        assert layout.get("Height") == 2.0

    def test_windows_backslash_eradication(self):
        """Adversarially pass Windows nested backslash paths and verify complete conversion to '/'."""
        win_moc = r"models\vtube\sub\model.moc3"
        win_textures = [r"textures\page_00\tex.png", r"textures\page_01\tex.png"]
        win_physics = r"physics\deep\physics.json"
        win_cdi = r"cdi\deep\display.json"

        manifest = Model3Writer.generate_model3_json(
            model_name="WinTest",
            moc_rel_path=win_moc,
            texture_rel_paths=win_textures,
            physics_rel_path=win_physics,
            cdi_rel_path=win_cdi
        )

        # JSON dump string must not contain double backslashes
        json_str = json.dumps(manifest)
        assert "\\\\" not in json_str
        assert "\\" not in manifest["FileReferences"]["Moc"]
        assert all("\\" not in t for t in manifest["FileReferences"]["Textures"])
        assert manifest["FileReferences"]["Moc"] == "models/vtube/sub/model.moc3"
        assert manifest["FileReferences"]["Textures"] == ["textures/page_00/tex.png", "textures/page_01/tex.png"]

    def test_cdi3_json_complete_structure(self):
        """Verify .cdi3.json contains Parameters, ParameterGroups, and Parts with correct metadata."""
        param_ids = [
            "ParamAngleX", "ParamAngleY", "ParamAngleZ",
            "ParamEyeLOpen", "ParamEyeROpen",
            "ParamMouthForm", "ParamMouthOpenY",
            "ParamBodyAngleX"
        ]
        cdi = Model3Writer.generate_cdi3_json(
            parameter_ids=param_ids,
            part_ids=["PartHead", "PartHair", "PartFace", "PartBody"]
        )

        assert cdi["Version"] == 3
        assert len(cdi["Parameters"]) == len(param_ids)

        p_map = {p["Id"]: p for p in cdi["Parameters"]}
        assert p_map["ParamAngleX"]["GroupId"] == "ParamGroupHead"
        assert p_map["ParamEyeLOpen"]["GroupId"] == "ParamGroupEyes"
        assert p_map["ParamMouthOpenY"]["GroupId"] == "ParamGroupMouth"
        assert p_map["ParamBodyAngleX"]["GroupId"] == "ParamGroupBody"

        # Check parameter groups are auto-created for active groups
        group_ids = [g["Id"] for g in cdi["ParameterGroups"]]
        assert "ParamGroupHead" in group_ids
        assert "ParamGroupEyes" in group_ids
        assert "ParamGroupMouth" in group_ids
        assert "ParamGroupBody" in group_ids

    def test_full_model_bundle_export_and_disk_verification(self, tmp_path, complex_9keyform_model):
        """Execute export_model_bundle and verify full directory hierarchy, JSONs, and binary files."""
        # Create 2 texture pages (512x512 RGBA)
        tex_page_0 = np.full((512, 512, 4), 128, dtype=np.uint8)
        tex_page_1 = np.full((512, 512, 4), 200, dtype=np.uint8)

        export_res = Model3Writer.export_model_bundle(
            output_dir=str(tmp_path),
            model_name="BundleAvatar",
            keyform_table=complex_9keyform_model,
            texture_pages=[tex_page_0, tex_page_1]
        )

        model_dir = Path(export_res["model_dir"])
        assert model_dir.exists()

        # 1. Verify .model3.json on disk
        model3_file = Path(export_res["model3_json"])
        assert model3_file.exists()
        with open(model3_file, "r", encoding="utf-8") as f:
            m3_json = json.load(f)
        assert m3_json["Version"] == 3
        assert len(m3_json["FileReferences"]["Textures"]) == 2
        assert all("/" in t for t in m3_json["FileReferences"]["Textures"])

        # 2. Verify .moc3 on disk
        moc_file = Path(export_res["moc3"])
        assert moc_file.exists()
        moc_bytes = moc_file.read_bytes()
        val_res = validate_moc3_bytes(moc_bytes)
        assert val_res["is_valid"] is True

        # 3. Verify .cdi3.json on disk
        cdi_file = Path(export_res["cdi3_json"])
        assert cdi_file.exists()
        with open(cdi_file, "r", encoding="utf-8") as f:
            cdi_json = json.load(f)
        assert cdi_json["Version"] == 3

        # 4. Verify textures on disk
        for tex_path in export_res["textures"]:
            t_file = Path(tex_path)
            assert t_file.exists()
            assert t_file.stat().st_size > 0
