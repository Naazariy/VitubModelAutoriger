import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])

n_parts, n_deformers, n_warp, n_rot, n_art, n_params = counts[0:6]
n_part_kf, n_warp_kf, n_rot_kf, n_art_kf = counts[6:10]
n_pos, n_pbi, n_kfb, n_pb, n_keys, n_uvs, n_indices = counts[10:17]

print(f"Total deformers: {n_deformers} (warp={n_warp}, rot={n_rot})")

# Let's inspect each slot length and element type in detail
for s in range(10, 29):
    off = offsets[s]
    if off == 0:
        continue
    next_offs = [o for o in offsets if o > off]
    next_o = min(next_offs) if next_offs else len(data)
    l = next_o - off
    print(f"Slot {s:2d}: off=0x{off:04X}, len={l:5d} | /117={l/117:.2f}, /57={l/57:.2f}, /60={l/60:.2f}")

for s in range(59, 68):
    off = offsets[s]
    if off == 0:
        continue
    next_offs = [o for o in offsets if o > off]
    next_o = min(next_offs) if next_offs else len(data)
    l = next_o - off
    print(f"Slot {s:2d}: off=0x{off:04X}, len={l:5d} | /314={l/314:.2f}, /198={l/198:.2f}")
