import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])

n_parts, n_deformers, n_warp, n_rot, n_art, n_params = counts[0:6]
n_part_kf, n_warp_kf, n_rot_kf, n_art_kf = counts[6:10]
n_pos, n_pbi, n_kfb, n_pb, n_keys, n_uvs, n_indices = counts[10:17]

print(f"Parts: {n_parts}, Deformers: {n_deformers} (Warp: {n_warp}, Rot: {n_rot}), ArtMeshes: {n_art}")
print(f"WarpKF: {n_warp_kf}, RotKF: {n_rot_kf}")

print("\n--- Deformers (Slots 10..18) ---")
# Slot 11: Deformer IDs
deformer_ids = [data[offsets[11]+i*64:offsets[11]+(i+1)*64].split(b'\x00')[0].decode('utf-8', 'ignore') for i in range(n_deformers)]
for s in range(12, 19):
    arr = struct.unpack_from(f"<{n_deformers}i", data, offsets[s])
    print(f"Slot {s:2d} (len={len(arr)}): min={min(arr)}, max={max(arr)}, first10={arr[:10]}")

print("\n--- Slots 19..28 (Warp/Rot specific) ---")
for s in range(19, 29):
    # Could be n_warp (57) or n_rot (60)
    # Let's inspect as both float and int
    i_arr = struct.unpack_from(f"<{min(n_warp, n_rot)}i", data, offsets[s])
    f_arr = [round(x, 2) for x in struct.unpack_from(f"<{min(n_warp, n_rot)}f", data, offsets[s])]
    print(f"Slot {s:2d}: ints[:10]={i_arr[:10]} | floats[:10]={f_arr[:10]}")

print("\n--- WarpKeyforms (Slots 59..63) ---")
for s in range(59, 64):
    i_arr = struct.unpack_from(f"<{n_warp_kf}i", data, offsets[s])
    f_arr = [round(x, 2) for x in struct.unpack_from(f"<{n_warp_kf}f", data, offsets[s])]
    print(f"Slot {s:2d}: ints[:10]={i_arr[:10]} | floats[:10]={f_arr[:10]}")

print("\n--- RotKeyforms (Slots 64..67) ---")
for s in range(64, 68):
    i_arr = struct.unpack_from(f"<{n_rot_kf}i", data, offsets[s])
    f_arr = [round(x, 2) for x in struct.unpack_from(f"<{n_rot_kf}f", data, offsets[s])]
    print(f"Slot {s:2d}: ints[:10]={i_arr[:10]} | floats[:10]={f_arr[:10]}")
