import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_warp_kf = counts[7]  # 314
n_rot_kf = counts[8]   # 198

print(f"In Hiyori: n_warp_kf = {n_warp_kf}, n_rot_kf = {n_rot_kf}")

for s in range(59, 68):
    off = offsets[s]
    next_offs = [o for o in offsets if o > off]
    next_o = min(next_offs) if next_offs else len(data)
    byte_len = next_o - off
    # Unpack as floats and ints
    f_cnt = byte_len // 4
    print(f"Slot {s:2d}: off=0x{off:04X}, byte_len={byte_len:5d}, float32_elements={f_cnt} | matches warp_kf({n_warp_kf})? {f_cnt >= n_warp_kf} | matches rot_kf({n_rot_kf})? {f_cnt >= n_rot_kf}")
