import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_warp = counts[2]

warp_s19 = struct.unpack_from(f"<{n_warp}i", data, offsets[19])
warp_s20 = struct.unpack_from(f"<{n_warp}i", data, offsets[20])
warp_s21 = struct.unpack_from(f"<{n_warp}i", data, offsets[21])
warp_s22 = struct.unpack_from(f"<{n_warp}i", data, offsets[22])
warp_s23 = struct.unpack_from(f"<{n_warp}i", data, offsets[23])
warp_s24 = struct.unpack_from(f"<{n_warp}i", data, offsets[24])

print(f"Total WarpDeformers: {n_warp}")
for i in range(min(10, n_warp)):
    print(f"Warp {i:2d}: kfb={warp_s19[i]:2d}, kf_start={warp_s20[i]:3d}, kf_cnt={warp_s21[i]:2d}, v_cnt={warp_s22[i]:3d}, rows={warp_s23[i]:2d}, cols={warp_s24[i]:2d} | (r+1)*(c+1)={(warp_s23[i]+1)*(warp_s24[i]+1)}")
