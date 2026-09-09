import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_pos, n_pbi, n_kfb, n_pb, n_keys = counts[10:15]

pbi = struct.unpack_from(f"<{n_pbi}i", data, offsets[72])
kfb_pbi_starts = struct.unpack_from(f"<{n_kfb}i", data, offsets[73])
kfb_pbi_counts = struct.unpack_from(f"<{n_kfb}i", data, offsets[74])
kfb_key_starts = struct.unpack_from(f"<{n_kfb}i", data, offsets[75])
kfb_key_counts = struct.unpack_from(f"<{n_kfb}i", data, offsets[76])

print(f"KFB 0: pbi_start={kfb_pbi_starts[0]}, pbi_count={kfb_pbi_counts[0]}, key_start={kfb_key_starts[0]}, key_count={kfb_key_counts[0]}")
print(f"KFB 1: pbi_start={kfb_pbi_starts[1]}, pbi_count={kfb_pbi_counts[1]}, key_start={kfb_key_starts[1]}, key_count={kfb_key_counts[1]}")
