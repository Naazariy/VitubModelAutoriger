"""
tests/test_moc3_writer.py
Unit and Binary Validation Test Suite for Moc3Writer & Moc3Reader.
"""

import math
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


@pytest.fixture
def sample_keyform_table():
    """Generates a complete KeyformTable with 9-keyform Cartesian grid deformations."""
    table = KeyformTable(
        canvas_width=2048,
        canvas_height=2048,
        model_name="TestAvatar"
    )

    table.add_parameter(ParameterBinding(
        param_id="ParamAngleX",
        min_val=-30.0,
        default_val=0.0,
        max_val=30.0,
        key_values=[-30.0, 0.0, 30.0],
        name="Angle X"
    ))
    table.add_parameter(ParameterBinding(
        param_id="ParamAngleY",
        min_val=-30.0,
        default_val=0.0,
        max_val=30.0,
        key_values=[-30.0, 0.0, 30.0],
        name="Angle Y"
    ))
    table.add_parameter(ParameterBinding(
        param_id="ParamAngleZ",
        min_val=-20.0,
        default_val=0.0,
        max_val=20.0,
        key_values=[-20.0, 0.0, 20.0],
        name="Angle Z"
    ))

    # Add 2 drawables
    base_v1 = np.array([
        [-0.5, -0.5],
        [0.5, -0.5],
        [0.5, 0.5],
        [-0.5, 0.5]
    ], dtype=np.float32)
    tris1 = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
    uvs1 = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32)

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

    # 3x3 = 9 keyforms
    for ay in [-30.0, 0.0, 30.0]:
        for ax in [-30.0, 0.0, 30.0]:
            shift_x = ax * 0.005
            shift_y = ay * 0.005
            deformed = base_v1 + np.array([shift_x, shift_y], dtype=np.float32)
            d1.add_keyform((ax, ay), deformed)

    table.add_drawable(d1)

    # Add second drawable (Hair Front)
    base_v2 = np.array([
        [-0.4, -0.6],
        [0.4, -0.6],
        [0.0, -0.1]
    ], dtype=np.float32)
    tris2 = np.array([[0, 1, 2]], dtype=np.int32)
    uvs2 = np.array([[0.1, 0.1], [0.9, 0.1], [0.5, 0.8]], dtype=np.float32)

    d2 = DrawableKeyforms(
        drawable_id="ArtMesh_HairFront",
        texture_index=0,
        base_vertices=base_v2,
        triangles=tris2,
        uvs_atlas=uvs2,
        draw_order=600,
        opacity=1.0,
        blend_mode=0
    )
    for ay in [-30.0, 0.0, 30.0]:
        for ax in [-30.0, 0.0, 30.0]:
            shift_x = ax * 0.008
            shift_y = ay * 0.008
            deformed = base_v2 + np.array([shift_x, shift_y], dtype=np.float32)
            d2.add_keyform((ax, ay), deformed)

    table.add_drawable(d2)
    return table


class TestMoc3WriterUnit:
    """Unit tests for Moc3Writer binary serialization."""

    def test_id_encoding_and_decoding(self):
        """Verify 64-byte ID string encoding and decoding."""
        test_id = "ArtMesh_EyeL_Open"
        encoded = encode_id_64(test_id)
        assert len(encoded) == 64
        assert encoded.startswith(b"ArtMesh_EyeL_Open\x00")

        decoded = decode_id_64(encoded)
        assert decoded == test_id

    def test_align_to_64(self):
        """Verify 64-byte alignment arithmetic."""
        assert align_to_64(0) == 0
        assert align_to_64(1) == 64
        assert align_to_64(63) == 64
        assert align_to_64(64) == 64
        assert align_to_64(65) == 128

    def test_moc3_header_magic_and_version(self, sample_keyform_table):
        """Verify header magic bytes 'MOC3', version 3, and Little-Endian byte."""
        raw_bytes = Moc3Writer.build_bytes(sample_keyform_table)
        assert len(raw_bytes) >= 2176
        assert raw_bytes[:4] == b"MOC3"
        assert raw_bytes[4] == 3
        assert raw_bytes[5] == 0

    def test_64_byte_memory_alignment(self, sample_keyform_table):
        """Verify total binary length and all section offsets are multiples of 64 bytes."""
        raw_bytes = Moc3Writer.build_bytes(sample_keyform_table)
        assert len(raw_bytes) % 64 == 0, f"Binary size {len(raw_bytes)} is not a multiple of 64"

        section_offsets = struct.unpack_from("<160I", raw_bytes, 64)
        for idx, off in enumerate(section_offsets):
            if off > 0:
                assert off % 64 == 0, f"Section offset [{idx}] = {hex(off)} is not 64-byte aligned"
                assert off < len(raw_bytes), f"Section offset [{idx}] = {hex(off)} exceeds binary size"

    def test_count_info_table_counters(self, sample_keyform_table):
        """Verify CountInfoTable counters match the input KeyformTable."""
        raw_bytes = Moc3Writer.build_bytes(sample_keyform_table)
        parsed = Moc3Reader.parse_bytes(raw_bytes)
        counts = parsed.get("counts", {})

        assert counts.get("art_meshes") == 2
        assert counts.get("parameters") == 3
        # 2 drawables * 9 keyforms each = 18 art_mesh_keyforms
        assert counts.get("art_mesh_keyforms") == 18
        # d1 (4 verts * 9 kf = 36) + d2 (3 verts * 9 kf = 27) = 63 keyform positions (126 float32 coordinates)
        assert counts.get("keyform_positions") == 126
        # d1 (4 verts) + d2 (3 verts) = 7 uvs (14 float32 coordinates)
        assert counts.get("uvs") == 14
        # d1 (2 tris * 3 = 6) + d2 (1 tri * 3 = 3) = 9 indices
        assert counts.get("position_indices") == 9

    def test_canvas_info_section_parameters(self, sample_keyform_table):
        """Verify CanvasInfo section correctly stores canvas dimensions."""
        raw_bytes = Moc3Writer.build_bytes(sample_keyform_table)
        parsed = Moc3Reader.parse_bytes(raw_bytes)
        canvas = parsed.get("canvas_info", {})

        assert canvas.get("canvas_width") == 2048.0
        assert canvas.get("canvas_height") == 2048.0
        assert canvas.get("origin_x") == 1024.0
        assert canvas.get("origin_y") == 1024.0

    def test_artmesh_drawable_serialization(self, sample_keyform_table):
        """Verify ArtMesh IDs are serialized and deserializable."""
        raw_bytes = Moc3Writer.build_bytes(sample_keyform_table)
        parsed = Moc3Reader.parse_bytes(raw_bytes)
        art_mesh_ids = parsed.get("art_mesh_ids", [])

        assert "ArtMesh_Face" in art_mesh_ids
        assert "ArtMesh_HairFront" in art_mesh_ids

    def test_parameter_ranges_and_keys_serialization(self, sample_keyform_table):
        """Verify parameter IDs and keys are serialized."""
        raw_bytes = Moc3Writer.build_bytes(sample_keyform_table)
        parsed = Moc3Reader.parse_bytes(raw_bytes)
        param_ids = parsed.get("parameter_ids", [])

        assert "ParamAngleX" in param_ids
        assert "ParamAngleY" in param_ids
        assert "ParamAngleZ" in param_ids

    def test_round_trip_validation(self, sample_keyform_table):
        """Verify validate_moc3_bytes approves the generated binary."""
        raw_bytes = Moc3Writer.build_bytes(sample_keyform_table)
        val_res = validate_moc3_bytes(raw_bytes)
        assert val_res["is_valid"] is True
        assert len(val_res["errors"]) == 0

    def test_file_writing_to_disk(self, tmp_path, sample_keyform_table):
        """Verify write_moc3 writes valid file to disk."""
        out_file = tmp_path / "avatar.moc3"
        written = Moc3Writer.write_moc3(sample_keyform_table, str(out_file))
        assert out_file.exists()
        assert len(written) == out_file.stat().st_size

        read_back = Moc3Reader.read_from_file(str(out_file))
        assert read_back["magic"] == "MOC3"
        assert read_back["version"] == 3

    def test_empty_or_corrupt_table_rejection(self):
        """Verify writer rejects invalid KeyformTable containing NaNs or missing drawables."""
        bad_table = KeyformTable()
        d_bad = DrawableKeyforms(
            drawable_id="BadMesh",
            base_vertices=np.array([[np.nan, 0.0]], dtype=np.float32),
            triangles=np.array([[0, 0, 0]], dtype=np.int32),
            uvs_atlas=np.array([[0.0, 0.0]], dtype=np.float32),
        )
        bad_table.add_drawable(d_bad)

        with pytest.raises(ValueError, match="Invalid KeyformTable"):
            Moc3Writer.build_bytes(bad_table)
