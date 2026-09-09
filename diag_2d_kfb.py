import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_parts, n_deformers, n_warp, n_rot, n_art, n_params = counts[0:6]
n_pos, n_pbi, n_kfb, n_pb, n_keys = counts[10:15]

pbi = struct.unpack_from(f"<{n_pbi}i", data, offsets[72])
kfb_pbi_starts = struct.unpack_from(f"<{n_kfb}i", data, offsets[73])
kfb_pbi_counts = struct.unpack_from(f"<{n_kfb}i", data, offsets[74])
kfb_key_starts = struct.unpack_from(f"<{n_kfb}i", data, offsets[75])
kfb_key_counts = struct.unpack_from(f"<{n_kfb}i", data, offsets[76])
param_ids = [data[offsets[50]+i*64:offsets[50]+(i+1)*64].split(b'\x00')[0].decode('utf-8', 'ignore') for i in range(n_params)]
keys = struct.unpack_from(f"<{n_keys}f", data, offsets[77])

print(f"Total KeyformBindings: {n_kfb}, Total PBI: {n_pbi}, Total Keys: {n_keys}")

for i in range(n_kfb):
    p_cnt = kfb_pbi_counts[i]
    p_start = kfb_pbi_starts[i]
    p_idxs = [pbi[p_start + j] for j in range(p_cnt)]
    p_names = [param_ids[pid] for pid in p_idxs]
    k_start = kfb_key_starts[i]
    k_cnt = kfb_key_counts[i]
    if p_cnt >= 2:
        print(f"KFB {i:2d}: params={p_names} (p_indices={p_idxs}), key_start={k_start}, key_count={k_cnt}")
        # print keys
        for pid in p_idxs:
            print(f"    Param {param_ids[pid]}: keys={keys[k_start:k_start+k_cnt]}")
