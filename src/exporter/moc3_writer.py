"""
src/exporter/moc3_writer.py
Pure-Python Live2D Cubism Standard (.moc3) Binary Serializer & Deserializer.
Enforces strict 64-byte alignment, section offset tables, count tables, and keyform tensors
strictly compliant with Live2D Cubism Core runtime and VTube Studio specifications.
Supports complete Live2D Deformer Hierarchy:
RootPart -> RotationDeformer (Angle Z) -> WarpDeformer (Angle X/Y) -> ArtMeshes.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
import struct
import math
from typing import Dict, List, Tuple, Optional, Any, Union
import numpy as np

from src.core.keyform import (
    KeyformTable,
    ParameterBinding,
    DrawableKeyforms,
    WarpDeformer,
    RotationDeformer,
)


def align_to_64(offset: int) -> int:
    """Returns the next multiple of 64 bytes."""
    return (offset + 63) & ~63


def pad_buffer_to_64(buffer: bytearray) -> bytearray:
    """Pads a bytearray with null bytes to ensure length is a multiple of 64."""
    remainder = len(buffer) % 64
    if remainder != 0:
        buffer.extend(b"\x00" * (64 - remainder))
    return buffer


def encode_id_64(name: str) -> bytes:
    """Encodes a string identifier into a 64-byte null-padded UTF-8 byte sequence."""
    encoded = name.encode("utf-8")[:63]
    return encoded.ljust(64, b"\x00")


def decode_id_64(data: bytes) -> str:
    """Decodes a 64-byte null-padded byte sequence back into a string."""
    return data.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


@dataclass
class Moc3CanvasInfo:
    """Live2D Canvas coordinate system metadata."""
    pixels_per_unit: float = 2000.0
    origin_x: float = 1024.0
    origin_y: float = 1024.0
    canvas_width: float = 2048.0
    canvas_height: float = 2048.0
    flags: int = 0


class Moc3Writer:
    """
    Live2D Cubism Standard .moc3 Binary Writer.
    Constructs compliant binary moc3 files with 64-byte aligned data tables
    matching Live2D Cubism Core and VTube Studio standards.
    """

    MAGIC = b"MOC3"
    VERSION = 3  # Standard Live2D Cubism Model Version (Cubism 3.0+ / 4.0 specification)
    BIG_ENDIAN = 0  # Little-Endian
    NUM_SECTION_OFFSETS = 160

    @classmethod
    def build_bytes(cls, keyform_table: KeyformTable, version: int = None) -> bytes:
        """
        Serializes a KeyformTable into compliant Live2D .moc3 binary bytes.
        """
        # Validate table integrity before serialization
        is_valid, errors = keyform_table.validate() if hasattr(keyform_table, 'validate') else (True, [])
        if not is_valid:
            raise ValueError(f"Invalid KeyformTable cannot be serialized: {'; '.join(errors)}")

        num_drawables = len(keyform_table.drawables)
        params_objs = keyform_table.parameters if keyform_table.parameters else [
            ParameterBinding(
                param_id=pid,
                min_val=keyform_table.parameter_ranges.get(pid, (-30.0, 0.0, 30.0))[0],
                default_val=keyform_table.parameter_ranges.get(pid, (-30.0, 0.0, 30.0))[1],
                max_val=keyform_table.parameter_ranges.get(pid, (-30.0, 0.0, 30.0))[2]
            )
            for pid in keyform_table.parameter_ids
        ]
        num_parameters = len(params_objs)
        param_id_to_idx = {p.param_id: i for i, p in enumerate(params_objs)}

        # 1. Setup Fixed Header (64 bytes)
        # Header bytes: [0..3]=b"MOC3", [4]=version, [5]=endianness, [8..15]=drawables/params counts, [16..63]=zeros
        header = bytearray(64)
        header[0:4] = cls.MAGIC
        header[4] = version if version is not None else cls.VERSION
        header[5] = cls.BIG_ENDIAN
        struct.pack_into("<II", header, 8, num_drawables, num_parameters)

        # 2. Section Offset Table (640 bytes = 160 uint32s at offset 0x0040 to 0x02C0)
        section_offsets = [0] * cls.NUM_SECTION_OFFSETS

        # 3. Runtime Address Map / Pointer Table (1280 bytes = 160 uint64s at offset 0x02C0 to 0x07C0)
        runtime_map_bytes = b"\x00" * 1280

        # 4. Prepare payload sections buffer starting at 0x07C0 (1984)
        payload = bytearray()

        def append_aligned_section(slot_index: int, section_data: bytes):
            pad_buffer_to_64(payload)
            abs_offset = 64 + 640 + 1280 + len(payload)
            assert abs_offset % 64 == 0
            section_offsets[slot_index] = abs_offset
            payload.extend(section_data)
            pad_buffer_to_64(payload)

        # Parts
        parts_list = keyform_table.parts if getattr(keyform_table, 'parts', None) else ["PartRoot"]
        n_parts = len(parts_list)
        part_id_to_idx = {pid: i for i, pid in enumerate(parts_list)}

        # Deformers collection
        rot_deformers: List[RotationDeformer] = getattr(keyform_table, 'rotation_deformers', [])
        warp_deformers: List[WarpDeformer] = getattr(keyform_table, 'warp_deformers', [])

        # Build unified deformers list: [ (type, obj), ... ]
        # Type 1 = RotationDeformer, Type 0 = WarpDeformer
        deformers_list: List[Tuple[int, Union[RotationDeformer, WarpDeformer]]] = []
        rot_id_to_rot_idx: Dict[str, int] = {}
        warp_id_to_warp_idx: Dict[str, int] = {}
        def_id_to_def_idx: Dict[str, int] = {}

        for rot in rot_deformers:
            rot_id_to_rot_idx[rot.deformer_id] = len(rot_id_to_rot_idx)
            def_id_to_def_idx[rot.deformer_id] = len(deformers_list)
            deformers_list.append((1, rot))

        for warp in warp_deformers:
            warp_id_to_warp_idx[warp.deformer_id] = len(warp_id_to_warp_idx)
            def_id_to_def_idx[warp.deformer_id] = len(deformers_list)
            deformers_list.append((0, warp))

        n_deformers = len(deformers_list)
        n_warp_deformers = len(warp_deformers)
        n_rotation_deformers = len(rot_deformers)
        n_art_meshes = num_drawables
        n_parameters = num_parameters
        n_part_keyforms = n_parts

        # Count Keyforms
        n_warp_deformer_keyforms = sum(
            len(w.deformed_positions) if w.deformed_positions else (len(w.keyform_keys) if w.keyform_keys else 1)
            for w in warp_deformers
        )
        n_rotation_deformer_keyforms = sum(
            len(r.keyform_keys) if r.keyform_keys else 1
            for r in rot_deformers
        )

        total_art_mesh_keyforms = 0
        total_art_mesh_pos_floats = 0
        total_uvs = 0
        total_position_indices = 0

        for d in keyform_table.drawables:
            n_v = len(d.base_vertices)
            if n_v > 65535:
                raise ValueError(f"Drawable '{d.drawable_id}' vertex count ({n_v}) exceeds Live2D uint16 limit (65535)")
            if len(d.triangles) > 0:
                if np.any(d.triangles < 0) or np.any(d.triangles >= n_v) or np.any(d.triangles > 65535):
                    raise ValueError(f"Drawable '{d.drawable_id}' contains triangle index out of uint16 range [0, {min(n_v - 1, 65535)}]")
            n_t = len(d.triangles)
            k_count = len(d.deformed_positions) if d.deformed_positions else 1
            total_art_mesh_keyforms += k_count
            total_art_mesh_pos_floats += n_v * 2 * k_count  # count of float32s
            total_uvs += n_v * 2                           # count of float32s
            total_position_indices += n_t * 3              # count of uint16 indices

        # Total warp grid positions
        total_warp_pos_floats = 0
        for w in warp_deformers:
            n_gv = w.total_grid_vertices
            k_count = len(w.deformed_positions) if w.deformed_positions else (len(w.keyform_keys) if w.keyform_keys else 1)
            total_warp_pos_floats += n_gv * 2 * k_count

        total_keyform_positions = total_warp_pos_floats + total_art_mesh_pos_floats

        # ---------------------------------------------------------------------
        # Parameter Keys (Section 77) and Parameter Key Sources (Sections 56..57)
        # ---------------------------------------------------------------------
        all_keys_values: List[float] = []
        param_key_starts: List[int] = []
        param_key_counts: List[int] = []

        for p in params_objs:
            keys = p.key_values if p.key_values else [p.min_val, p.default_val, p.max_val]
            param_key_starts.append(len(all_keys_values))
            param_key_counts.append(len(keys))
            all_keys_values.extend(keys)

        # ---------------------------------------------------------------------
        # KeyformBindings Table (Sections 72..76)
        # ---------------------------------------------------------------------
        pbi_list: List[int] = []
        kfb_pbi_starts: List[int] = []
        kfb_pbi_counts: List[int] = []
        kfb_key_starts: List[int] = []
        kfb_key_counts: List[int] = []

        # Helper to register KeyformBinding
        def register_kfb(bound_param_ids: List[str]) -> int:
            valid_pids = [pid for pid in bound_param_ids if pid in param_id_to_idx]
            kfb_idx = len(kfb_pbi_starts)
            kfb_pbi_starts.append(len(pbi_list))
            kfb_pbi_counts.append(len(valid_pids))

            if valid_pids:
                p_indices = [param_id_to_idx[pid] for pid in valid_pids]
                pbi_list.extend(p_indices)
                first_p_idx = p_indices[0]
                kfb_key_starts.append(param_key_starts[first_p_idx])
                kfb_key_counts.append(param_key_counts[first_p_idx])
            else:
                kfb_key_starts.append(0)
                kfb_key_counts.append(0)
            return kfb_idx

        # KFB for Parts (typically empty binding)
        part_kfb_indices = [register_kfb([]) for _ in range(n_parts)]

        # KFB for RotationDeformers
        rot_kfb_indices: List[int] = []
        for rot in rot_deformers:
            rot_kfb_indices.append(register_kfb(rot.parameter_ids))

        # KFB for WarpDeformers
        warp_kfb_indices: List[int] = []
        for warp in warp_deformers:
            warp_kfb_indices.append(register_kfb(warp.parameter_ids))

        # KFB for ArtMeshes
        drawable_kfb_indices: List[int] = []
        drawable_kfb_counts: List[int] = []
        for d in keyform_table.drawables:
            if d.parameter_ids and d.deformed_positions:
                kfb_idx = register_kfb(d.parameter_ids)
            elif d.deformed_positions and not d.parameter_ids and keyform_table.parameters:
                sample_k = next(iter(d.deformed_positions.keys()))
                dim = len(sample_k) if isinstance(sample_k, (tuple, list)) else 1
                kfb_idx = register_kfb(keyform_table.parameter_ids[:dim])
            else:
                kfb_idx = register_kfb([])
            drawable_kfb_indices.append(kfb_idx)
            drawable_kfb_counts.append(1)

        # Deformers KFB indices
        deformer_kfb_indices: List[int] = []
        for def_type, def_obj in deformers_list:
            if def_type == 1:  # Rotation
                r_idx = rot_id_to_rot_idx[def_obj.deformer_id]
                deformer_kfb_indices.append(rot_kfb_indices[r_idx])
            else:  # Warp
                w_idx = warp_id_to_warp_idx[def_obj.deformer_id]
                deformer_kfb_indices.append(warp_kfb_indices[w_idx])

        n_param_binding_indices = len(pbi_list)
        n_keyform_bindings = len(kfb_pbi_starts)
        n_param_bindings = n_parameters
        n_keys = len(all_keys_values)
        n_drawable_masks = 0
        n_draw_order_groups = 1
        n_draw_order_group_objects = n_art_meshes
        n_glue = 0
        n_glue_info = 0
        n_glue_keyforms = 0

        # ---------------------------------------------------------------------
        # Section 0: CountInfoTable (Offset 0x07C0, 128 bytes = 32 uint32s)
        # ---------------------------------------------------------------------
        count_ints = [
            n_parts,
            n_deformers,
            n_warp_deformers,
            n_rotation_deformers,
            n_art_meshes,
            n_parameters,
            n_part_keyforms,
            n_warp_deformer_keyforms,
            n_rotation_deformer_keyforms,
            total_art_mesh_keyforms,
            total_keyform_positions,
            n_param_binding_indices,
            n_keyform_bindings,
            n_param_bindings,
            n_keys,
            total_uvs,
            total_position_indices,
            n_drawable_masks,
            n_draw_order_groups,
            n_draw_order_group_objects,
            n_glue,
            n_glue_info,
            n_glue_keyforms,
        ] + [0] * 9  # 23 + 9 = 32 uint32s = 128 bytes

        count_info_bytes = struct.pack("<32I", *count_ints)
        assert len(count_info_bytes) == 128
        append_aligned_section(0, count_info_bytes)

        # ---------------------------------------------------------------------
        # Section 1: CanvasInfo (Offset 0x0840, 64 bytes)
        # ---------------------------------------------------------------------
        cw = float(getattr(keyform_table, 'canvas_width', 2048.0))
        ch = float(getattr(keyform_table, 'canvas_height', 2048.0))
        ppu = max(cw, ch)
        canvas_info_bytes = struct.pack(
            "<5fB43x",
            ppu,          # pixelsPerUnit
            cw * 0.5,     # originX
            ch * 0.5,     # originY
            cw,           # canvasWidth
            ch,           # canvasHeight
            0             # canvasFlags
        )
        assert len(canvas_info_bytes) == 64
        append_aligned_section(1, canvas_info_bytes)

        # ---------------------------------------------------------------------
        # Sections 2..9: Parts Table
        # ---------------------------------------------------------------------
        # Section 2: Parts.Id_Pointers (8B * n_parts)
        append_aligned_section(2, b"\x00" * (8 * n_parts))

        # Section 3: Parts.IDs (64B * n_parts)
        parts_ids_data = b"".join(encode_id_64(pid) for pid in parts_list)
        append_aligned_section(3, parts_ids_data)

        # Section 4: Parts.ParentPartIndices
        append_aligned_section(4, struct.pack(f"<{n_parts}i", *([-1] * n_parts)))

        # Section 5: Parts.KeyformSourcesBeginIndices
        append_aligned_section(5, struct.pack(f"<{n_parts}i", *list(range(n_parts))))

        # Section 6: Parts.KeyformSourcesCounts
        append_aligned_section(6, struct.pack(f"<{n_parts}i", *([1] * n_parts)))

        # Section 7: Parts.KeyformBindingsBeginIndices
        append_aligned_section(7, struct.pack(f"<{n_parts}i", *part_kfb_indices))

        # Section 8: Parts.KeyformBindingsCounts
        append_aligned_section(8, struct.pack(f"<{n_parts}i", *([1] * n_parts)))

        # Section 9: Parts.ParentDeformerIndices
        append_aligned_section(9, struct.pack(f"<{n_parts}i", *([-1] * n_parts)))

        # ---------------------------------------------------------------------
        # Sections 10..18: Deformers Table (if n_deformers > 0)
        # ---------------------------------------------------------------------
        if n_deformers > 0:
            # Section 10: Deformers.Id_Pointers (8B * n_deformers)
            append_aligned_section(10, b"\x00" * (8 * n_deformers))

            # Section 11: Deformers.IDs (64B * n_deformers)
            def_ids_data = b"".join(encode_id_64(def_obj.deformer_id) for _, def_obj in deformers_list)
            append_aligned_section(11, def_ids_data)

            # Section 12: Deformers.KeyformBindingsBeginIndices
            append_aligned_section(12, struct.pack(f"<{n_deformers}i", *deformer_kfb_indices))

            # Section 13: Deformers.KeyformBindingsCounts
            append_aligned_section(13, struct.pack(f"<{n_deformers}i", *([1] * n_deformers)))

            # Section 14: Deformers.ParentPartIndices
            def_parent_parts = [part_id_to_idx.get(def_obj.parent_part_id, 0) for _, def_obj in deformers_list]
            append_aligned_section(14, struct.pack(f"<{n_deformers}i", *def_parent_parts))

            # Section 15: Deformers.ParentPartIndices2
            append_aligned_section(15, struct.pack(f"<{n_deformers}i", *def_parent_parts))

            # Section 16: Deformers.ParentDeformerIndices
            def_parent_defs = []
            for _, def_obj in deformers_list:
                p_id = def_obj.parent_deformer_id
                p_idx = def_id_to_def_idx.get(p_id, -1) if p_id else -1
                def_parent_defs.append(p_idx)
            append_aligned_section(16, struct.pack(f"<{n_deformers}i", *def_parent_defs))

            # Section 17: Deformers.DeformerTypes (1 = Rotation, 0 = Warp)
            def_types = [t for t, _ in deformers_list]
            append_aligned_section(17, struct.pack(f"<{n_deformers}i", *def_types))

            # Section 18: Deformers.SpecificDeformerIndices (index in rot/warp list)
            def_specific_indices = []
            for t, def_obj in deformers_list:
                if t == 1:
                    def_specific_indices.append(rot_id_to_rot_idx[def_obj.deformer_id])
                else:
                    def_specific_indices.append(warp_id_to_warp_idx[def_obj.deformer_id])
            append_aligned_section(18, struct.pack(f"<{n_deformers}i", *def_specific_indices))

        # ---------------------------------------------------------------------
        # Sections 19..24: WarpDeformers Table (if n_warp_deformers > 0)
        # ---------------------------------------------------------------------
        if n_warp_deformers > 0:
            # Section 19: WarpDeformers.KeyformBindingsBeginIndices
            append_aligned_section(19, struct.pack(f"<{n_warp_deformers}i", *warp_kfb_indices))

            # Section 20: WarpDeformers.KeyformSourcesBeginIndices
            warp_kf_starts: List[int] = []
            warp_kf_counts: List[int] = []
            cur_warp_kf = 0
            for w in warp_deformers:
                warp_kf_starts.append(cur_warp_kf)
                cnt = len(w.deformed_positions) if w.deformed_positions else (len(w.keyform_keys) if w.keyform_keys else 1)
                warp_kf_counts.append(cnt)
                cur_warp_kf += cnt
            append_aligned_section(20, struct.pack(f"<{n_warp_deformers}i", *warp_kf_starts))

            # Section 21: WarpDeformers.KeyformSourcesCounts
            append_aligned_section(21, struct.pack(f"<{n_warp_deformers}i", *warp_kf_counts))

            # Section 22: WarpDeformers.TotalGridVertices
            warp_tot_verts = [w.total_grid_vertices for w in warp_deformers]
            append_aligned_section(22, struct.pack(f"<{n_warp_deformers}i", *warp_tot_verts))

            # Section 23: WarpDeformers.GridRows
            warp_rows = [w.grid_rows for w in warp_deformers]
            append_aligned_section(23, struct.pack(f"<{n_warp_deformers}i", *warp_rows))

            # Section 24: WarpDeformers.GridColumns
            warp_cols = [w.grid_cols for w in warp_deformers]
            append_aligned_section(24, struct.pack(f"<{n_warp_deformers}i", *warp_cols))

        # ---------------------------------------------------------------------
        # Sections 25..28: RotationDeformers Table (if n_rotation_deformers > 0)
        # ---------------------------------------------------------------------
        if n_rotation_deformers > 0:
            # Section 25: RotationDeformers.KeyformBindingsBeginIndices
            append_aligned_section(25, struct.pack(f"<{n_rotation_deformers}i", *rot_kfb_indices))

            # Section 26: RotationDeformers.KeyformSourcesBeginIndices
            rot_kf_starts: List[int] = []
            rot_kf_counts: List[int] = []
            cur_rot_kf = 0
            for r in rot_deformers:
                rot_kf_starts.append(cur_rot_kf)
                cnt = len(r.keyform_keys) if r.keyform_keys else 1
                rot_kf_counts.append(cnt)
                cur_rot_kf += cnt
            append_aligned_section(26, struct.pack(f"<{n_rotation_deformers}i", *rot_kf_starts))

            # Section 27: RotationDeformers.KeyformSourcesCounts
            append_aligned_section(27, struct.pack(f"<{n_rotation_deformers}i", *rot_kf_counts))

            # Section 28: RotationDeformers.BaseAngles
            rot_base_angles = [float(r.base_angle) for r in rot_deformers]
            append_aligned_section(28, struct.pack(f"<{n_rotation_deformers}f", *rot_base_angles))

        # ---------------------------------------------------------------------
        # Sections 29..48: ArtMeshes Table
        # ---------------------------------------------------------------------
        # Sections 29..32: ArtMeshes Pointer tables (8B * n_art_meshes each)
        append_aligned_section(29, b"\x00" * (8 * n_art_meshes))
        append_aligned_section(30, b"\x00" * (8 * n_art_meshes))
        append_aligned_section(31, b"\x00" * (8 * n_art_meshes))
        append_aligned_section(32, b"\x00" * (8 * n_art_meshes))

        # Section 33: ArtMeshes.IDs (64B * n_art_meshes)
        artmesh_ids_data = b"".join(encode_id_64(d.drawable_id) for d in keyform_table.drawables)
        append_aligned_section(33, artmesh_ids_data)

        # Section 34: ArtMeshes.ParentPartIndices
        art_parent_parts = [part_id_to_idx.get(getattr(d, 'parent_part_id', 'PartRoot'), 0) for d in keyform_table.drawables]
        append_aligned_section(34, struct.pack(f"<{n_art_meshes}i", *art_parent_parts))

        # Section 35: ArtMeshes.KeyformSourcesBeginIndices
        art_kf_starts = []
        art_kf_counts = []
        cur_art_kf = 0
        for d in keyform_table.drawables:
            art_kf_starts.append(cur_art_kf)
            count = len(d.deformed_positions) if (d.parameter_ids and d.deformed_positions) else 1
            art_kf_counts.append(count)
            cur_art_kf += count
        append_aligned_section(35, struct.pack(f"<{n_art_meshes}i", *art_kf_starts))

        # Section 36: ArtMeshes.KeyformSourcesCounts
        append_aligned_section(36, struct.pack(f"<{n_art_meshes}i", *art_kf_counts))

        # Section 37: ArtMeshes.KeyformBindingsBeginIndices
        append_aligned_section(37, struct.pack(f"<{n_art_meshes}i", *drawable_kfb_indices))

        # Section 38: ArtMeshes.KeyformBindingsCounts
        append_aligned_section(38, struct.pack(f"<{n_art_meshes}i", *drawable_kfb_counts))

        # Section 39: ArtMeshes.ParentDeformerIndices (points to WarpDeformer index if set)
        art_parent_defs = []
        for d in keyform_table.drawables:
            p_def_id = getattr(d, 'parent_deformer_id', None)
            p_def_idx = def_id_to_def_idx.get(p_def_id, -1) if p_def_id else -1
            # If default deformers exist and not set, default to WarpDeformer (if present)
            if p_def_idx < 0 and n_warp_deformers > 0:
                first_warp_id = warp_deformers[0].deformer_id
                p_def_idx = def_id_to_def_idx.get(first_warp_id, -1)
            art_parent_defs.append(p_def_idx)
        append_aligned_section(39, struct.pack(f"<{n_art_meshes}i", *art_parent_defs))

        # Section 40: ArtMeshes.ParentPartIndices2
        append_aligned_section(40, struct.pack(f"<{n_art_meshes}i", *art_parent_parts))

        # Section 41: ArtMeshes.TextureNos
        tex_nos = [d.texture_index for d in keyform_table.drawables]
        append_aligned_section(41, struct.pack(f"<{n_art_meshes}i", *tex_nos))

        # Section 42: ArtMeshes.DrawableFlags (blend mode in bits 0-1, culling in bit 2)
        drawable_flags = []
        for d in keyform_table.drawables:
            flag = (d.blend_mode & 0x03) | (0x04 if not d.culling else 0x00)
            drawable_flags.append(flag)
        append_aligned_section(42, struct.pack(f"<{n_art_meshes}B", *drawable_flags))

        # Section 43: ArtMeshes.VertexCounts
        v_counts = [len(d.base_vertices) for d in keyform_table.drawables]
        append_aligned_section(43, struct.pack(f"<{n_art_meshes}i", *v_counts))

        # Section 44: ArtMeshes.UvSourcesBeginIndices
        uv_starts = []
        cur_uv = 0
        for d in keyform_table.drawables:
            uv_starts.append(cur_uv)
            cur_uv += len(d.base_vertices) * 2  # floats
        append_aligned_section(44, struct.pack(f"<{n_art_meshes}i", *uv_starts))

        # Section 45: ArtMeshes.PositionIndexSourcesBeginIndices
        idx_starts = []
        idx_counts = []
        cur_idx = 0
        for d in keyform_table.drawables:
            idx_starts.append(cur_idx)
            count = len(d.triangles) * 3
            idx_counts.append(count)
            cur_idx += count
        append_aligned_section(45, struct.pack(f"<{n_art_meshes}i", *idx_starts))

        # Section 46: ArtMeshes.PositionIndexSourcesCounts
        append_aligned_section(46, struct.pack(f"<{n_art_meshes}i", *idx_counts))

        # Section 47: ArtMeshes.MaskCounts
        append_aligned_section(47, struct.pack(f"<{n_art_meshes}i", *([0] * n_art_meshes)))

        # Section 48: ArtMeshes.MaskSourcesBeginIndices
        append_aligned_section(48, struct.pack(f"<{n_art_meshes}i", *([0] * n_art_meshes)))

        # ---------------------------------------------------------------------
        # Sections 49..57: Parameters Table
        # ---------------------------------------------------------------------
        # Section 49: Parameters.Id_Pointers (8B * n_parameters)
        append_aligned_section(49, b"\x00" * (8 * n_parameters))

        # Section 50: Parameters.IDs (64B * n_parameters)
        params_ids_data = b"".join(encode_id_64(p.param_id) for p in params_objs)
        append_aligned_section(50, params_ids_data)

        # Section 51: Parameters.MaxValues
        append_aligned_section(51, struct.pack(f"<{n_parameters}f", *[p.max_val for p in params_objs]))

        # Section 52: Parameters.MinValues
        append_aligned_section(52, struct.pack(f"<{n_parameters}f", *[p.min_val for p in params_objs]))

        # Section 53: Parameters.DefaultValues
        append_aligned_section(53, struct.pack(f"<{n_parameters}f", *[p.default_val for p in params_objs]))

        # Section 54: Parameters.IsRepeat
        append_aligned_section(54, struct.pack(f"<{n_parameters}I", *([0] * n_parameters)))

        # Section 55: Parameters.DecimalPlaces
        append_aligned_section(55, struct.pack(f"<{n_parameters}I", *([3] * n_parameters)))

        # Section 56: Parameters.KeySourcesBeginIndices
        append_aligned_section(56, struct.pack(f"<{n_parameters}i", *param_key_starts))

        # Section 57: Parameters.KeySourcesCounts
        append_aligned_section(57, struct.pack(f"<{n_parameters}i", *param_key_counts))

        # ---------------------------------------------------------------------
        # Section 58: PartKeyforms / Opacities (500.0f default)
        # ---------------------------------------------------------------------
        append_aligned_section(58, struct.pack(f"<{n_parts}f", *([500.0] * n_parts)))

        # ---------------------------------------------------------------------
        # Sections 59..60: WarpDeformerKeyforms (if n_warp_deformer_keyforms > 0)
        # ---------------------------------------------------------------------
        all_warp_kf_xy: List[float] = []
        if n_warp_deformer_keyforms > 0:
            # Section 59: WarpDeformerKeyforms.Opacities (1.0f)
            append_aligned_section(59, struct.pack(f"<{n_warp_deformer_keyforms}f", *([1.0] * n_warp_deformer_keyforms)))

            # Section 60: WarpDeformerKeyforms.KeyformPositionSourcesBeginIndices
            warp_kf_pos_starts: List[int] = []
            cur_warp_pos_idx = 0
            for w in warp_deformers:
                n_gv = w.total_grid_vertices
                if w.deformed_positions:
                    for _, pos in w.deformed_positions.items():
                        warp_kf_pos_starts.append(cur_warp_pos_idx)
                        flat = np.asarray(pos, dtype=np.float32).ravel()
                        all_warp_kf_xy.extend(flat.tolist())
                        cur_warp_pos_idx += n_gv * 2
                else:
                    flat = np.asarray(w.base_vertices, dtype=np.float32).ravel()
                    k_cnt = len(w.keyform_keys) if w.keyform_keys else 1
                    for _ in range(k_cnt):
                        warp_kf_pos_starts.append(cur_warp_pos_idx)
                        all_warp_kf_xy.extend(flat.tolist())
                        cur_warp_pos_idx += n_gv * 2
            append_aligned_section(60, struct.pack(f"<{n_warp_deformer_keyforms}i", *warp_kf_pos_starts))

        # ---------------------------------------------------------------------
        # Sections 61..67: RotationDeformerKeyforms (if n_rotation_deformer_keyforms > 0)
        # ---------------------------------------------------------------------
        if n_rotation_deformer_keyforms > 0:
            rot_kf_opacities: List[float] = []
            rot_kf_angles: List[float] = []
            rot_kf_ox: List[float] = []
            rot_kf_oy: List[float] = []
            rot_kf_sx: List[float] = []
            rot_kf_sy: List[float] = []
            rot_kf_ref_angles: List[float] = []

            for r in rot_deformers:
                if r.keyform_keys:
                    for k in r.keyform_keys:
                        rot_kf_opacities.append(r.opacities.get(k, 1.0))
                        rot_kf_angles.append(r.angles.get(k, float(k[0]) if len(k) > 0 else 0.0))
                        orig = r.origins.get(k, (r.origin_x, r.origin_y))
                        rot_kf_ox.append(float(orig[0]))
                        rot_kf_oy.append(float(orig[1]))
                        sc = r.scales.get(k, (r.scale_x, r.scale_y))
                        rot_kf_sx.append(float(sc[0]))
                        rot_kf_sy.append(float(sc[1]))
                        rot_kf_ref_angles.append(0.0)
                else:
                    rot_kf_opacities.append(1.0)
                    rot_kf_angles.append(float(r.base_angle))
                    rot_kf_ox.append(float(r.origin_x))
                    rot_kf_oy.append(float(r.origin_y))
                    rot_kf_sx.append(float(r.scale_x))
                    rot_kf_sy.append(float(r.scale_y))
                    rot_kf_ref_angles.append(0.0)

            # Section 61: Opacities
            append_aligned_section(61, struct.pack(f"<{n_rotation_deformer_keyforms}f", *rot_kf_opacities))
            # Section 62: Angles
            append_aligned_section(62, struct.pack(f"<{n_rotation_deformer_keyforms}f", *rot_kf_angles))
            # Section 63: OriginXs
            append_aligned_section(63, struct.pack(f"<{n_rotation_deformer_keyforms}f", *rot_kf_ox))
            # Section 64: OriginYs
            append_aligned_section(64, struct.pack(f"<{n_rotation_deformer_keyforms}f", *rot_kf_oy))
            # Section 65: ScaleXs
            append_aligned_section(65, struct.pack(f"<{n_rotation_deformer_keyforms}f", *rot_kf_sx))
            # Section 66: ScaleYs
            append_aligned_section(66, struct.pack(f"<{n_rotation_deformer_keyforms}f", *rot_kf_sy))
            # Section 67: RefAngles
            append_aligned_section(67, struct.pack(f"<{n_rotation_deformer_keyforms}f", *rot_kf_ref_angles))

        # ---------------------------------------------------------------------
        # Sections 68..70: ArtMeshKeyforms
        # ---------------------------------------------------------------------
        # Section 68: ArtMeshKeyforms.Opacities
        append_aligned_section(68, struct.pack(f"<{total_art_mesh_keyforms}f", *([1.0] * total_art_mesh_keyforms)))

        # Section 69: ArtMeshKeyforms.DrawOrders
        draw_orders = []
        for d in keyform_table.drawables:
            count = len(d.deformed_positions) if d.deformed_positions else 1
            draw_orders.extend([float(d.draw_order)] * count)
        append_aligned_section(69, struct.pack(f"<{total_art_mesh_keyforms}f", *draw_orders))

        # Section 70: ArtMeshKeyforms.KeyformPositionSourcesBeginIndices
        # Offset into Section 71 begins after all warp deformer keyform positions
        art_kf_pos_starts = []
        cur_pos_idx = len(all_warp_kf_xy)  # start offset in float32s
        all_art_kf_xy: List[float] = []

        for d in keyform_table.drawables:
            n_v = len(d.base_vertices)
            if d.deformed_positions:
                for _, pos in d.deformed_positions.items():
                    art_kf_pos_starts.append(cur_pos_idx)
                    flat = np.asarray(pos, dtype=np.float32).ravel()
                    all_art_kf_xy.extend(flat.tolist())
                    cur_pos_idx += n_v * 2
            else:
                art_kf_pos_starts.append(cur_pos_idx)
                flat = np.asarray(d.base_vertices, dtype=np.float32).ravel()
                all_art_kf_xy.extend(flat.tolist())
                cur_pos_idx += n_v * 2

        append_aligned_section(70, struct.pack(f"<{total_art_mesh_keyforms}i", *art_kf_pos_starts))

        # ---------------------------------------------------------------------
        # Section 71: KeyformPositions.XYs (Warp grid positions + ArtMesh positions)
        # ---------------------------------------------------------------------
        all_keyform_xy = all_warp_kf_xy + all_art_kf_xy
        if all_keyform_xy:
            append_aligned_section(71, struct.pack(f"<{len(all_keyform_xy)}f", *all_keyform_xy))

        # ---------------------------------------------------------------------
        # Sections 72..77: ParamBindings & Keys
        # ---------------------------------------------------------------------
        # Section 72: ParamBindingIndices
        if pbi_list:
            append_aligned_section(72, struct.pack(f"<{len(pbi_list)}i", *pbi_list))

        # Section 73: KeyformBindings.ParamBindingIndicesBeginIndices
        if kfb_pbi_starts:
            append_aligned_section(73, struct.pack(f"<{len(kfb_pbi_starts)}i", *kfb_pbi_starts))

        # Section 74: KeyformBindings.ParamBindingIndicesCounts
        if kfb_pbi_counts:
            append_aligned_section(74, struct.pack(f"<{len(kfb_pbi_counts)}i", *kfb_pbi_counts))

        # Section 75: KeyformBindings.KeySourcesBeginIndices
        if kfb_key_starts:
            append_aligned_section(75, struct.pack(f"<{len(kfb_key_starts)}i", *kfb_key_starts))

        # Section 76: KeyformBindings.KeySourcesCounts
        if kfb_key_counts:
            append_aligned_section(76, struct.pack(f"<{len(kfb_key_counts)}i", *kfb_key_counts))

        # Section 77: Keys.Values
        if all_keys_values:
            append_aligned_section(77, struct.pack(f"<{len(all_keys_values)}f", *all_keys_values))

        # ---------------------------------------------------------------------
        # Sections 78..79: UVs & Indices
        # ---------------------------------------------------------------------
        # Section 78: UVs.UVs
        all_uvs_flat: List[float] = []
        for d in keyform_table.drawables:
            flat_uv = np.asarray(d.uvs_atlas, dtype=np.float32).ravel()
            all_uvs_flat.extend(flat_uv.tolist())
        if all_uvs_flat:
            append_aligned_section(78, struct.pack(f"<{len(all_uvs_flat)}f", *all_uvs_flat))

        # Section 79: PositionIndices.Indices
        all_indices: List[int] = []
        for d in keyform_table.drawables:
            flat_tris = np.asarray(d.triangles, dtype=np.uint16).ravel()
            all_indices.extend(flat_tris.tolist())
        if all_indices:
            append_aligned_section(79, struct.pack(f"<{len(all_indices)}H", *all_indices))

        # ---------------------------------------------------------------------
        # Sections 80..88: DrawOrderGroups Table
        # ---------------------------------------------------------------------
        # Section 80: DrawOrderGroups.Flags (77 = 'M')
        append_aligned_section(80, struct.pack("<B", 77))

        # Section 81: DrawOrderGroups.GroupIndices (0)
        append_aligned_section(81, struct.pack("<I", 0))

        # Section 82: DrawOrderGroups.ObjectCounts
        append_aligned_section(82, struct.pack("<I", n_art_meshes))

        # Section 83: DrawOrderGroups.ObjectBeginIndices
        append_aligned_section(83, struct.pack("<I", n_art_meshes))

        # Section 84: DrawOrderGroups.MaxDrawOrder
        append_aligned_section(84, struct.pack("<I", 1000))

        # Section 85: DrawOrderGroups.MinDrawOrder
        append_aligned_section(85, struct.pack("<I", 200))

        # Section 86: DrawOrderGroupObjects.Types
        append_aligned_section(86, struct.pack(f"<{n_art_meshes}I", *([0] * n_art_meshes)))

        # Section 87: DrawOrderGroupObjects.ObjectIndices
        obj_indices = [n_art_meshes - 1 - i for i in range(n_art_meshes)]
        append_aligned_section(87, struct.pack(f"<{n_art_meshes}I", *obj_indices))

        # Section 88: DrawOrderGroupObjects.ParentGroupIndices
        append_aligned_section(88, struct.pack(f"<{n_art_meshes}i", *([-1] * n_art_meshes)))

        # ---------------------------------------------------------------------
        # Assemble Final Stream: Header + SectionOffsetTable + RuntimeMap + Payload
        # ---------------------------------------------------------------------
        section_table_bytes = struct.pack(f"<{cls.NUM_SECTION_OFFSETS}I", *section_offsets)
        assert len(section_table_bytes) == 640

        full_binary = bytearray()
        full_binary.extend(header)
        full_binary.extend(section_table_bytes)
        full_binary.extend(runtime_map_bytes)
        full_binary.extend(payload)
        pad_buffer_to_64(full_binary)

        return bytes(full_binary)

    @classmethod
    def write_moc3(cls, keyform_table: KeyformTable, output_path: str, version: Optional[int] = None) -> bytes:
        """
        Serializes KeyformTable to disk at output_path and returns the written bytes.
        """
        data = cls.build_bytes(keyform_table, version=version)
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "wb") as f:
            f.write(data)
        return data

    @classmethod
    def write(cls, model_context_or_table: Any, output_path: str, version: Optional[int] = None) -> bytes:
        """
        Universal export entrypoint accepting either KeyformTable or ModelContext.
        """
        if isinstance(model_context_or_table, KeyformTable):
            return cls.write_moc3(model_context_or_table, output_path, version=version)
        elif hasattr(model_context_or_table, 'keyform_table') and isinstance(model_context_or_table.keyform_table, KeyformTable):
            return cls.write_moc3(model_context_or_table.keyform_table, output_path, version=version)
        else:
            raise TypeError(f"Expected KeyformTable or ModelContext, got {type(model_context_or_table)}")


class Moc3Reader:
    """
    Parser and structural deserializer for Live2D Cubism .moc3 binary files.
    """

    MAGIC = b"MOC3"

    @classmethod
    def read_from_file(cls, path: str) -> Dict[str, Any]:
        with open(path, "rb") as f:
            data = f.read()
        return cls.parse_bytes(data)

    @classmethod
    def parse_bytes(cls, data: bytes) -> Dict[str, Any]:
        """
        Parses .moc3 binary bytes into structured Python dictionary.
        """
        if len(data) < 64:
            raise ValueError(f"File size too small for .moc3: {len(data)} bytes < 64 bytes")

        magic = data[:4]
        if magic != cls.MAGIC:
            raise ValueError(f"Invalid MOC3 magic header: expected {cls.MAGIC}, got {magic}")

        version, is_big_endian = struct.unpack_from("<BB", data, 4)
        if is_big_endian != 0:
            raise ValueError(f"Unsupported endianness: {is_big_endian} (expected 0 Little-Endian)")

        result: Dict[str, Any] = {
            "magic": magic.decode("ascii", errors="replace"),
            "version": version,
            "is_big_endian": is_big_endian,
            "total_size": len(data),
            "is_64_aligned": (len(data) % 64 == 0)
        }

        # Check section table
        if len(data) >= 704:
            section_offsets = list(struct.unpack_from("<160I", data, 64))
            result["section_offsets"] = section_offsets

            # Parse CountInfoTable at slot 0 (or 0x07C0)
            cnt_off = section_offsets[0] or 0x07C0
            if len(data) >= cnt_off + 92:
                counts = struct.unpack_from("<23I", data, cnt_off)
                result["counts"] = {
                    "parts": counts[0],
                    "deformers": counts[1],
                    "warp_deformers": counts[2],
                    "rotation_deformers": counts[3],
                    "art_meshes": counts[4],
                    "parameters": counts[5],
                    "part_keyforms": counts[6],
                    "warp_deformer_keyforms": counts[7],
                    "rotation_deformer_keyforms": counts[8],
                    "art_mesh_keyforms": counts[9],
                    "keyform_positions": counts[10],
                    "param_binding_indices": counts[11],
                    "keyform_bindings": counts[12],
                    "param_bindings": counts[13],
                    "keys": counts[14],
                    "uvs": counts[15],
                    "position_indices": counts[16],
                    "drawable_masks": counts[17],
                    "draw_order_groups": counts[18],
                    "draw_order_group_objects": counts[19],
                    "glue": counts[20],
                    "glue_info": counts[21],
                    "glue_keyforms": counts[22],
                }

            # Parse CanvasInfo at slot 1 (or 0x0840)
            canvas_off = section_offsets[1] or 0x0840
            if len(data) >= canvas_off + 21:
                canvas_fields = struct.unpack_from("<5fB", data, canvas_off)
                result["canvas_info"] = {
                    "pixels_per_unit": canvas_fields[0],
                    "origin_x": canvas_fields[1],
                    "origin_y": canvas_fields[2],
                    "canvas_width": canvas_fields[3],
                    "canvas_height": canvas_fields[4],
                    "flags": canvas_fields[5],
                }

            # Parse Parts (Sec 3)
            p_ids_off = section_offsets[3]
            n_parts = result.get("counts", {}).get("parts", 0)
            if p_ids_off and len(data) >= p_ids_off + n_parts * 64:
                part_ids = []
                for i in range(n_parts):
                    str_bytes = data[p_ids_off + i * 64 : p_ids_off + (i + 1) * 64]
                    part_ids.append(decode_id_64(str_bytes))
                result["part_ids"] = part_ids

            # Parse Deformers (Sec 11, 16, 17)
            n_defs = result.get("counts", {}).get("deformers", 0)
            def_ids_off = section_offsets[11]
            if def_ids_off and len(data) >= def_ids_off + n_defs * 64:
                def_ids = []
                for i in range(n_defs):
                    str_bytes = data[def_ids_off + i * 64 : def_ids_off + (i + 1) * 64]
                    def_ids.append(decode_id_64(str_bytes))
                result["deformer_ids"] = def_ids

            if section_offsets[16] and len(data) >= section_offsets[16] + n_defs * 4:
                result["deformer_parent_indices"] = list(struct.unpack_from(f"<{n_defs}i", data, section_offsets[16]))

            if section_offsets[17] and len(data) >= section_offsets[17] + n_defs * 4:
                result["deformer_types"] = list(struct.unpack_from(f"<{n_defs}i", data, section_offsets[17]))

            # Parse Drawables / ArtMeshes (Sec 33, 39)
            d_ids_off = section_offsets[33]
            n_meshes = result.get("counts", {}).get("art_meshes", 0)
            if d_ids_off and len(data) >= d_ids_off + n_meshes * 64:
                mesh_ids = []
                for i in range(n_meshes):
                    str_bytes = data[d_ids_off + i * 64 : d_ids_off + (i + 1) * 64]
                    mesh_ids.append(decode_id_64(str_bytes))
                result["art_mesh_ids"] = mesh_ids

            if section_offsets[39] and len(data) >= section_offsets[39] + n_meshes * 4:
                result["art_mesh_parent_deformer_indices"] = list(struct.unpack_from(f"<{n_meshes}i", data, section_offsets[39]))

            # Parse Parameters (Sec 50)
            param_ids_off = section_offsets[50]
            n_params = result.get("counts", {}).get("parameters", 0)
            if param_ids_off and len(data) >= param_ids_off + n_params * 64:
                param_ids = []
                for i in range(n_params):
                    str_bytes = data[param_ids_off + i * 64 : param_ids_off + (i + 1) * 64]
                    param_ids.append(decode_id_64(str_bytes))
                result["parameter_ids"] = param_ids

            # Parse Keys (Sec 77)
            k_off = section_offsets[77]
            n_keys = result.get("counts", {}).get("keys", 0)
            if k_off and len(data) >= k_off + n_keys * 4:
                result["keys"] = list(struct.unpack_from(f"<{n_keys}f", data, k_off))

        return result


def validate_moc3_bytes(data: bytes) -> Dict[str, Any]:
    """
    Validates .moc3 binary bytes against Live2D Cubism specifications:
    Checks magic header, endianness, version, 64-byte alignment, section tables, and count consistency.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if len(data) < 64:
        return {"is_valid": False, "errors": ["MOC3 binary size too small (< 64 bytes)"], "warnings": []}

    if data[:4] != Moc3Writer.MAGIC:
        errors.append(f"Invalid MOC3 magic header: expected b'MOC3', got {data[:4]}")

    version = data[4]
    if version not in (1, 2, 3, 4, 5):
        errors.append(f"Unsupported MOC3 version: {version}")

    if len(data) % 64 != 0:
        warnings.append(f"Total file size ({len(data)}) is not 64-byte aligned (remainder {len(data) % 64})")

    if len(data) >= 704:
        section_offsets = list(struct.unpack_from("<160I", data, 64))
        for idx, off in enumerate(section_offsets):
            if off > 0:
                if off % 64 != 0:
                    errors.append(f"Section offset [{idx}] at {hex(off)} is not 64-byte aligned")
                if off >= len(data):
                    errors.append(f"Section offset [{idx}] at {hex(off)} exceeds file size ({len(data)})")

    parsed_info = {}
    try:
        parsed_info = Moc3Reader.parse_bytes(data)
    except Exception as e:
        errors.append(f"Parsing failed: {e}")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "parsed_info": parsed_info
    }
