import struct
import numpy as np
from src.core.keyform import KeyformTable, ParameterBinding, DrawableKeyforms

def align_to_64(offset: int) -> int:
    return (offset + 63) & ~63

def pad_buffer_to_64(buffer: bytearray) -> bytearray:
    remainder = len(buffer) % 64
    if remainder != 0:
        buffer.extend(b"\x00" * (64 - remainder))
    return buffer

def encode_id_64(name: str) -> bytes:
    encoded = name.encode("utf-8")[:63]
    return encoded.ljust(64, b"\x00")

def decode_id_64(data: bytes) -> str:
    return data.split(b"\x00", 1)[0].decode("utf-8", errors="replace")


def build_moc3(keyform_table: KeyformTable, version: int = 1) -> bytes:
    num_drawables = len(keyform_table.drawables)
    params_objs = keyform_table.parameters if keyform_table.parameters else [
        ParameterBinding(param_id=pid, min_val=keyform_table.parameter_ranges.get(pid, (-30.0, 0.0, 30.0))[0],
                         default_val=keyform_table.parameter_ranges.get(pid, (-30.0, 0.0, 30.0))[1],
                         max_val=keyform_table.parameter_ranges.get(pid, (-30.0, 0.0, 30.0))[2])
        for pid in keyform_table.parameter_ids
    ]
    num_parameters = len(params_objs)
    param_id_to_idx = {p.param_id: i for i, p in enumerate(params_objs)}

    # 1. Fixed Header (64 bytes)
    header = bytearray(64)
    header[0:4] = b"MOC3"
    header[4] = version
    header[5] = 0  # Little-Endian

    # 2. Section offsets table (160 uint32s = 640B)
    section_offsets = [0] * 160

    # 3. Runtime pointer table (160 uint64s = 1280B)
    runtime_map = b"\x00" * 1280

    payload = bytearray()

    def append_aligned_section(slot_index: int, section_data: bytes):
        pad_buffer_to_64(payload)
        abs_offset = 64 + 640 + 1280 + len(payload)
        assert abs_offset % 64 == 0
        section_offsets[slot_index] = abs_offset
        payload.extend(section_data)
        pad_buffer_to_64(payload)

    # Gather data
    parts_list = ["PartRoot"]
    n_parts = len(parts_list)
    n_deformers = 0
    n_warp_deformers = 0
    n_rotation_deformers = 0
    n_art_meshes = num_drawables
    n_parameters = num_parameters
    n_part_keyforms = n_parts
    n_warp_deformer_keyforms = 0
    n_rotation_deformer_keyforms = 0

    total_art_mesh_keyforms = 0
    total_keyform_positions = 0
    total_uvs = 0
    total_position_indices = 0

    for d in keyform_table.drawables:
        n_v = len(d.base_vertices)
        n_t = len(d.triangles)
        k_count = len(d.deformed_positions) if d.deformed_positions else 1
        total_art_mesh_keyforms += k_count
        total_keyform_positions += n_v * 2 * k_count
        total_uvs += n_v * 2
        total_position_indices += n_t * 3

    # Parameter keys and keyform bindings
    all_keys_values = []
    param_key_starts = []
    param_key_counts = []

    for p in params_objs:
        keys = p.key_values if p.key_values else [p.min_val, p.default_val, p.max_val]
        param_key_starts.append(len(all_keys_values))
        param_key_counts.append(len(keys))
        all_keys_values.extend(keys)

    # Build KeyformBindings for drawables
    pbi_list = []
    kfb_pbi_starts = []
    kfb_pbi_counts = []
    kfb_key_starts = []
    kfb_key_counts = []

    drawable_kfb_indices = []
    drawable_kfb_counts = []

    for d in keyform_table.drawables:
        d_pids = [pid for pid in d.parameter_ids if pid in param_id_to_idx]
        if d_pids and d.deformed_positions:
            kfb_idx = len(kfb_pbi_starts)
            kfb_pbi_starts.append(len(pbi_list))
            kfb_pbi_counts.append(len(d_pids))
            
            p_indices = [param_id_to_idx[pid] for pid in d_pids]
            pbi_list.extend(p_indices)
            
            first_p_idx = p_indices[0]
            kfb_key_starts.append(param_key_starts[first_p_idx])
            kfb_key_counts.append(param_key_counts[first_p_idx])
            
            drawable_kfb_indices.append(kfb_idx)
            drawable_kfb_counts.append(1)
        else:
            kfb_idx = len(kfb_pbi_starts)
            kfb_pbi_starts.append(len(pbi_list))
            kfb_pbi_counts.append(0)
            kfb_key_starts.append(0)
            kfb_key_counts.append(0)
            
            drawable_kfb_indices.append(kfb_idx)
            drawable_kfb_counts.append(1)

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
    ] + [0] * 9

    count_info_bytes = struct.pack("<32I", *count_ints)
    assert len(count_info_bytes) == 128
    append_aligned_section(0, count_info_bytes)

    cw = float(getattr(keyform_table, 'canvas_width', 2048.0))
    ch = float(getattr(keyform_table, 'canvas_height', 2048.0))
    ppu = max(cw, ch)
    canvas_info_bytes = struct.pack(
        "<5fB43x",
        ppu,
        cw * 0.5,
        ch * 0.5,
        cw,
        ch,
        0
    )
    assert len(canvas_info_bytes) == 64
    append_aligned_section(1, canvas_info_bytes)

    append_aligned_section(2, b"\x00" * (8 * n_parts))
    parts_ids_data = b"".join(encode_id_64(pid) for pid in parts_list)
    append_aligned_section(3, parts_ids_data)
    append_aligned_section(4, struct.pack(f"<{n_parts}i", *([-1] * n_parts)))
    append_aligned_section(5, struct.pack(f"<{n_parts}i", *list(range(n_parts))))
    append_aligned_section(6, struct.pack(f"<{n_parts}i", *([1] * n_parts)))
    append_aligned_section(7, struct.pack(f"<{n_parts}i", *([0] * n_parts)))
    append_aligned_section(8, struct.pack(f"<{n_parts}i", *([1] * n_parts)))
    append_aligned_section(9, struct.pack(f"<{n_parts}i", *([-1] * n_parts)))

    append_aligned_section(29, b"\x00" * (8 * n_art_meshes))
    append_aligned_section(30, b"\x00" * (8 * n_art_meshes))
    append_aligned_section(31, b"\x00" * (8 * n_art_meshes))
    append_aligned_section(32, b"\x00" * (8 * n_art_meshes))

    artmesh_ids_data = b"".join(encode_id_64(d.drawable_id) for d in keyform_table.drawables)
    append_aligned_section(33, artmesh_ids_data)
    append_aligned_section(34, struct.pack(f"<{n_art_meshes}i", *([0] * n_art_meshes)))

    kf_starts = []
    kf_counts = []
    cur_kf = 0
    for d in keyform_table.drawables:
        kf_starts.append(cur_kf)
        count = len(d.deformed_positions) if d.deformed_positions else 1
        kf_counts.append(count)
        cur_kf += count
    append_aligned_section(35, struct.pack(f"<{n_art_meshes}i", *kf_starts))
    append_aligned_section(36, struct.pack(f"<{n_art_meshes}i", *kf_counts))
    append_aligned_section(37, struct.pack(f"<{n_art_meshes}i", *drawable_kfb_indices))
    append_aligned_section(38, struct.pack(f"<{n_art_meshes}i", *drawable_kfb_counts))
    append_aligned_section(39, struct.pack(f"<{n_art_meshes}i", *([-1] * n_art_meshes)))
    append_aligned_section(40, struct.pack(f"<{n_art_meshes}i", *([0] * n_art_meshes)))

    tex_nos = [d.texture_index for d in keyform_table.drawables]
    append_aligned_section(41, struct.pack(f"<{n_art_meshes}i", *tex_nos))

    drawable_flags = []
    for d in keyform_table.drawables:
        flag = (d.blend_mode & 0x03) | (0x04 if not d.culling else 0x00)
        drawable_flags.append(flag)
    append_aligned_section(42, struct.pack(f"<{n_art_meshes}B", *drawable_flags))

    v_counts = [len(d.base_vertices) for d in keyform_table.drawables]
    append_aligned_section(43, struct.pack(f"<{n_art_meshes}i", *v_counts))

    uv_starts = []
    cur_uv = 0
    for d in keyform_table.drawables:
        uv_starts.append(cur_uv)
        cur_uv += len(d.base_vertices) * 2
    append_aligned_section(44, struct.pack(f"<{n_art_meshes}i", *uv_starts))

    idx_starts = []
    idx_counts = []
    cur_idx = 0
    for d in keyform_table.drawables:
        idx_starts.append(cur_idx)
        count = len(d.triangles) * 3
        idx_counts.append(count)
        cur_idx += count
    append_aligned_section(45, struct.pack(f"<{n_art_meshes}i", *idx_starts))
    append_aligned_section(46, struct.pack(f"<{n_art_meshes}i", *idx_counts))
    append_aligned_section(47, struct.pack(f"<{n_art_meshes}i", *([0] * n_art_meshes)))
    append_aligned_section(48, struct.pack(f"<{n_art_meshes}i", *([0] * n_art_meshes)))

    append_aligned_section(49, b"\x00" * (8 * n_parameters))
    params_ids_data = b"".join(encode_id_64(p.param_id) for p in params_objs)
    append_aligned_section(50, params_ids_data)
    append_aligned_section(51, struct.pack(f"<{n_parameters}f", *[p.max_val for p in params_objs]))
    append_aligned_section(52, struct.pack(f"<{n_parameters}f", *[p.min_val for p in params_objs]))
    append_aligned_section(53, struct.pack(f"<{n_parameters}f", *[p.default_val for p in params_objs]))
    append_aligned_section(54, struct.pack(f"<{n_parameters}I", *([0] * n_parameters)))
    append_aligned_section(55, struct.pack(f"<{n_parameters}I", *([3] * n_parameters)))
    append_aligned_section(56, struct.pack(f"<{n_parameters}i", *param_key_starts))
    append_aligned_section(57, struct.pack(f"<{n_parameters}i", *param_key_counts))

    append_aligned_section(58, struct.pack(f"<{n_parts}f", *([500.0] * n_parts)))
    append_aligned_section(68, struct.pack(f"<{total_art_mesh_keyforms}f", *([1.0] * total_art_mesh_keyforms)))

    draw_orders = []
    for d in keyform_table.drawables:
        count = len(d.deformed_positions) if d.deformed_positions else 1
        draw_orders.extend([float(d.draw_order)] * count)
    append_aligned_section(69, struct.pack(f"<{total_art_mesh_keyforms}f", *draw_orders))

    kf_pos_starts = []
    cur_pos_idx = 0
    for d in keyform_table.drawables:
        n_v = len(d.base_vertices)
        count = len(d.deformed_positions) if d.deformed_positions else 1
        for _ in range(count):
            kf_pos_starts.append(cur_pos_idx)
            cur_pos_idx += n_v * 2
    append_aligned_section(70, struct.pack(f"<{total_art_mesh_keyforms}i", *kf_pos_starts))

    all_keyform_xy = []
    for d in keyform_table.drawables:
        if d.deformed_positions:
            for _, pos in d.deformed_positions.items():
                flat = np.asarray(pos, dtype=np.float32).ravel()
                all_keyform_xy.extend(flat.tolist())
        else:
            flat = np.asarray(d.base_vertices, dtype=np.float32).ravel()
            all_keyform_xy.extend(flat.tolist())
    if all_keyform_xy:
        append_aligned_section(71, struct.pack(f"<{len(all_keyform_xy)}f", *all_keyform_xy))

    if pbi_list:
        append_aligned_section(72, struct.pack(f"<{len(pbi_list)}i", *pbi_list))
    if kfb_pbi_starts:
        append_aligned_section(73, struct.pack(f"<{len(kfb_pbi_starts)}i", *kfb_pbi_starts))
    if kfb_pbi_counts:
        append_aligned_section(74, struct.pack(f"<{len(kfb_pbi_counts)}i", *kfb_pbi_counts))
    if kfb_key_starts:
        append_aligned_section(75, struct.pack(f"<{len(kfb_key_starts)}i", *kfb_key_starts))
    if kfb_key_counts:
        append_aligned_section(76, struct.pack(f"<{len(kfb_key_counts)}i", *kfb_key_counts))
    if all_keys_values:
        append_aligned_section(77, struct.pack(f"<{len(all_keys_values)}f", *all_keys_values))

    all_uvs_flat = []
    for d in keyform_table.drawables:
        flat_uv = np.asarray(d.uvs_atlas, dtype=np.float32).ravel()
        all_uvs_flat.extend(flat_uv.tolist())
    if all_uvs_flat:
        append_aligned_section(78, struct.pack(f"<{len(all_uvs_flat)}f", *all_uvs_flat))

    all_indices = []
    for d in keyform_table.drawables:
        flat_tris = np.asarray(d.triangles, dtype=np.uint16).ravel()
        all_indices.extend(flat_tris.tolist())
    if all_indices:
        append_aligned_section(79, struct.pack(f"<{len(all_indices)}H", *all_indices))

    append_aligned_section(80, struct.pack("<B", 77))
    append_aligned_section(81, struct.pack("<I", 0))
    append_aligned_section(82, struct.pack("<I", n_art_meshes))
    append_aligned_section(83, struct.pack("<I", n_art_meshes))
    append_aligned_section(84, struct.pack("<I", 1000))
    append_aligned_section(85, struct.pack("<I", 200))
    append_aligned_section(86, struct.pack(f"<{n_art_meshes}I", *([0] * n_art_meshes)))
    obj_indices = [n_art_meshes - 1 - i for i in range(n_art_meshes)]
    append_aligned_section(87, struct.pack(f"<{n_art_meshes}I", *obj_indices))
    append_aligned_section(88, struct.pack(f"<{n_art_meshes}i", *([-1] * n_art_meshes)))

    section_table_bytes = struct.pack(f"<160I", *section_offsets)
    assert len(section_table_bytes) == 640

    full_binary = bytearray()
    full_binary.extend(header)
    full_binary.extend(section_table_bytes)
    full_binary.extend(runtime_map)
    full_binary.extend(payload)
    pad_buffer_to_64(full_binary)

    return bytes(full_binary)

# Setup sample table
table = KeyformTable(canvas_width=2048, canvas_height=2048, model_name="TestModel")
table.add_parameter(ParameterBinding("ParamAngleX", -30.0, 0.0, 30.0, [-30.0, 0.0, 30.0], "Angle X"))
table.add_parameter(ParameterBinding("ParamAngleY", -30.0, 0.0, 30.0, [-30.0, 0.0, 30.0], "Angle Y"))
table.add_parameter(ParameterBinding("ParamAngleZ", -20.0, 0.0, 20.0, [-20.0, 0.0, 20.0], "Angle Z"))

v1 = np.array([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]], dtype=np.float32)
t1 = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
uv1 = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32)

d1 = DrawableKeyforms("ArtMesh_Body", 0, v1, t1, uv1, draw_order=500, opacity=1.0)
for ay in [-30.0, 0.0, 30.0]:
    for ax in [-30.0, 0.0, 30.0]:
        d1.add_keyform((ax, ay), v1 + np.array([ax*0.01, ay*0.01], dtype=np.float32))

table.add_drawable(d1)

b = build_moc3(table)
print(f"Generated moc3 size: {len(b)} bytes")
offsets = struct.unpack_from("<160I", b, 64)
for i, off in enumerate(offsets):
    if off != 0:
        print(f"  Sec [{i:2d}]: 0x{off:04X} ({off})")

counts = struct.unpack_from("<23I", b, offsets[0])
print("\nGenerated Counts:")
field_names = [
    "Parts", "Deformers", "WarpDeformers", "RotationDeformers", "ArtMeshes", "Parameters",
    "PartKeyforms", "WarpKeyforms", "RotationKeyforms", "ArtMeshKeyforms", "KeyformPositions",
    "ParamBindingIndices", "KeyformBindings", "ParamBindings", "Keys", "UVs", "PositionIndices",
    "DrawableMasks", "DrawOrderGroups", "DrawOrderGroupObjects", "Glue", "GlueInfo", "GlueKeyforms"
]
for idx, (name, val) in enumerate(zip(field_names, counts)):
    print(f"  {idx:2d}: {name:25s} = {val}")
