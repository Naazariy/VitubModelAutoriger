import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_parts, n_deformers, n_warp, n_rot, n_art, n_params = counts[0:6]
n_part_kf, n_warp_kf, n_rot_kf, n_art_kf = counts[6:10]

deformer_ids = [data[offsets[11]+i*64:offsets[11]+(i+1)*64].split(b'\x00')[0].decode('utf-8', 'ignore') for i in range(n_deformers)]
s12 = struct.unpack_from(f"<{n_deformers}i", data, offsets[12])
s13 = struct.unpack_from(f"<{n_deformers}i", data, offsets[13])
s14 = struct.unpack_from(f"<{n_deformers}i", data, offsets[14])
s15 = struct.unpack_from(f"<{n_deformers}i", data, offsets[15])
s16 = struct.unpack_from(f"<{n_deformers}i", data, offsets[16])
s17 = struct.unpack_from(f"<{n_deformers}i", data, offsets[17])
s18 = struct.unpack_from(f"<{n_deformers}i", data, offsets[18])

print("Deformers Table (Slots 11..18):")
print("Index | Type | TypeIdx | ID | ParentPart (S15) | ParentDef (S16) | S12 | S13 | S14")
for i in range(min(15, n_deformers)):
    t_name = "Rot" if s17[i] == 1 else "Warp"
    print(f"{i:5d} | {t_name:4s} | {s18[i]:7d} | {deformer_ids[i]:20s} | {s15[i]:16d} | {s16[i]:15d} | {s12[i]:3d} | {s13[i]:3d} | {s14[i]:3d}")

print("\nLet's check Warp Deformer Specific Slots (19..24? or 25..28?) and Rotation Deformer Specific Slots:")
# In Hiyori, n_warp=57, n_rot=60.
# Let's check the length of Slots 19..28
for s in range(19, 29):
    off = offsets[s]
    next_offs = [o for o in offsets if o > off]
    next_o = min(next_offs) if next_offs else len(data)
    l = next_o - off
    print(f"Slot {s:2d}: byte_len={l:4d} (57*4={57*4}, 60*4={60*4})")
