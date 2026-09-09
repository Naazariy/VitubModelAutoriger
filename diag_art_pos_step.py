import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_art = counts[4]
n_art_kf = counts[9]

v_counts = struct.unpack_from(f"<{n_art}i", data, offsets[43])
kf_starts = struct.unpack_from(f"<{n_art}i", data, offsets[35])
kf_counts = struct.unpack_from(f"<{n_art}i", data, offsets[36])
s70 = struct.unpack_from(f"<{n_art_kf}i", data, offsets[70])

print("ArtMeshes first 10:")
for i in range(10):
    k_start = kf_starts[i]
    k_count = kf_counts[i]
    pos_starts = [s70[k] for k in range(k_start, k_start + k_count)]
    diffs = [pos_starts[j+1] - pos_starts[j] for j in range(len(pos_starts)-1)] if len(pos_starts) > 1 else []
    print(f"ArtMesh {i}: v_count={v_counts[i]} (floats={v_counts[i]*2}), k_count={k_count}, pos_starts={pos_starts[:3]}, diffs={diffs[:3]}")
