import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_warp = counts[2]
n_warp_kf = counts[7]

warp_s20 = struct.unpack_from(f"<{n_warp}i", data, offsets[20])
warp_s21 = struct.unpack_from(f"<{n_warp}i", data, offsets[21])
warp_s22 = struct.unpack_from(f"<{n_warp}i", data, offsets[22])
warp_s23 = struct.unpack_from(f"<{n_warp}i", data, offsets[23])
warp_s24 = struct.unpack_from(f"<{n_warp}i", data, offsets[24])

kf_start = warp_s20[9]
kf_count = warp_s21[9]
v_cnt = warp_s22[9]
rows = warp_s23[9]
cols = warp_s24[9]

s60 = struct.unpack_from(f"<{n_warp_kf}i", data, offsets[60])
pos_starts = [s60[kf_start + k] for k in range(kf_count)]

print(f"Warp 9: kf_count={kf_count}, v_cnt={v_cnt}, rows={rows}, cols={cols}")
print(f"pos_starts={pos_starts}")

s71_off = offsets[71]
for k in range(min(3, kf_count)):
    pos_off = pos_starts[k]
    xy = struct.unpack_from(f"<{v_cnt*2}f", data, s71_off + pos_off * 4)
    print(f"\nKF {k} grid (x,y):")
    for r in range(rows + 1):
        row_pts = [f"({xy[(r*(cols+1)+c)*2]:.1f}, {xy[(r*(cols+1)+c)*2+1]:.1f})" for c in range(cols + 1)]
        print(f"  row {r}: " + " | ".join(row_pts))
