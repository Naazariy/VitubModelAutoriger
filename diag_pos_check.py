import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_parts, n_deformers, n_warp, n_rot, n_art, n_params = counts[0:6]
n_part_kf, n_warp_kf, n_rot_kf, n_art_kf = counts[6:10]
total_pos = counts[10]

s60_warp_pos_idx = struct.unpack_from(f"<{n_warp_kf}i", data, offsets[60])
s70_art_pos_idx = struct.unpack_from(f"<{n_art_kf}i", data, offsets[70])

print(f"total_pos in CountInfoTable = {total_pos}")
print(f"Warp KF Pos Index range: min={min(s60_warp_pos_idx)}, max={max(s60_warp_pos_idx)}")
print(f"ArtMesh KF Pos Index range: min={min(s70_art_pos_idx)}, max={max(s70_art_pos_idx)}")
print(f"First 5 Warp Pos Starts: {s60_warp_pos_idx[:5]}")
print(f"First 5 ArtMesh Pos Starts: {s70_art_pos_idx[:5]}")
