import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_art = counts[4]

kfb_beg = struct.unpack_from(f"<{n_art}i", data, offsets[37])
kfb_cnt = struct.unpack_from(f"<{n_art}i", data, offsets[38])
kfs_beg = struct.unpack_from(f"<{n_art}i", data, offsets[35])
kfs_cnt = struct.unpack_from(f"<{n_art}i", data, offsets[36])
parent_def = struct.unpack_from(f"<{n_art}i", data, offsets[39])
v_counts = struct.unpack_from(f"<{n_art}i", data, offsets[43])

# Find ArtMeshes with 1 keyform
single_kf_indices = [i for i in range(n_art) if kfs_cnt[i] == 1]
print(f"Total ArtMeshes with 1 keyform: {len(single_kf_indices)} / {n_art}")
for i in single_kf_indices[:10]:
    print(f"ArtMesh {i:3d}: ParentDef={parent_def[i]:2d}, kfs_beg={kfs_beg[i]:4d}, kfs_cnt={kfs_cnt[i]}, kfb_beg={kfb_beg[i]:2d}, kfb_cnt={kfb_cnt[i]}, v_cnt={v_counts[i]}")
