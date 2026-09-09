import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])

n_parts, n_deformers, n_warp, n_rot, n_art, n_params = counts[0:6]
n_part_kf, n_warp_kf, n_rot_kf, n_art_kf = counts[6:10]
n_pos, n_pbi, n_kfb, n_pb, n_keys, n_uvs, n_indices = counts[10:17]

print(f"n_parts={n_parts}, n_deformers={n_deformers} (warp={n_warp}, rot={n_rot}), n_art={n_art}")
print(f"n_warp_kf={n_warp_kf}, n_rot_kf={n_rot_kf}")

print("\n--- Slots 10..18 (Deformers general table) ---")
for s in range(10, 19):
    off = offsets[s]
    if s == 10:
        print(f"Slot {s} (IdPointers?): {struct.unpack_from('<5Q', data, off)}")
    elif s == 11:
        ids = [data[off+i*64:off+(i+1)*64].split(b'\x00')[0].decode('utf-8', 'ignore') for i in range(min(5, n_deformers))]
        print(f"Slot {s} (IDs): {ids}")
    else:
        vals = struct.unpack_from(f"<{min(10, n_deformers)}i", data, off)
        fvals = [round(x, 2) for x in struct.unpack_from(f"<{min(10, n_deformers)}f", data, off)]
        print(f"Slot {s}: int={vals} | float={fvals}")

print("\n--- Slots 19..28 (Rotation/Warp specific tables?) ---")
for s in range(19, 29):
    off = offsets[s]
    vals = struct.unpack_from(f"<{min(10, n_deformers)}i", data, off)
    fvals = [round(x, 2) for x in struct.unpack_from(f"<{min(10, n_deformers)}f", data, off)]
    print(f"Slot {s}: int={vals} | float={fvals}")

print("\n--- Slots 59..63 (WarpDeformerKeyforms) ---")
for s in range(59, 64):
    off = offsets[s]
    vals = struct.unpack_from(f"<{min(10, n_warp_kf)}i", data, off)
    fvals = [round(x, 2) for x in struct.unpack_from(f"<{min(10, n_warp_kf)}f", data, off)]
    print(f"Slot {s}: int={vals} | float={fvals}")

print("\n--- Slots 64..67 (RotationDeformerKeyforms) ---")
for s in range(64, 68):
    off = offsets[s]
    vals = struct.unpack_from(f"<{min(10, n_rot_kf)}i", data, off)
    fvals = [round(x, 2) for x in struct.unpack_from(f"<{min(10, n_rot_kf)}f", data, off)]
    print(f"Slot {s}: int={vals} | float={fvals}")
