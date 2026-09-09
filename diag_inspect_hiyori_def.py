import struct
import math

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_parts, n_deformers, n_warp, n_rot, n_art, n_params = counts[0:6]
n_part_kf, n_warp_kf, n_rot_kf, n_art_kf = counts[6:10]

# Let's inspect deformer 0 (Rotation27) and deformer 5 (Warp1)
deformer_ids = [data[offsets[11]+i*64:offsets[11]+(i+1)*64].split(b'\x00')[0].decode('utf-8', 'ignore') for i in range(n_deformers)]
s17 = struct.unpack_from(f"<{n_deformers}i", data, offsets[17])
s18 = struct.unpack_from(f"<{n_deformers}i", data, offsets[18])
s15 = struct.unpack_from(f"<{n_deformers}i", data, offsets[15])
s16 = struct.unpack_from(f"<{n_deformers}i", data, offsets[16])

print(f"Def 0: ID={deformer_ids[0]}, Type={s17[0]}, TypeIdx={s18[0]}, ParentPart={s15[0]}, ParentDef={s16[0]}")
print(f"Def 1: ID={deformer_ids[1]}, Type={s17[1]}, TypeIdx={s18[1]}, ParentPart={s15[1]}, ParentDef={s16[1]}")
print(f"Def 5: ID={deformer_ids[5]}, Type={s17[5]}, TypeIdx={s18[5]}, ParentPart={s15[5]}, ParentDef={s16[5]}")

# RotDef 0 keyforms
rot_s25 = struct.unpack_from(f"<{n_rot}i", data, offsets[25])
rot_s26 = struct.unpack_from(f"<{n_rot}i", data, offsets[26])
rot_s27 = struct.unpack_from(f"<{n_rot}i", data, offsets[27])
rot_s28 = struct.unpack_from(f"<{n_rot}f", data, offsets[28])

print(f"\nRotDef 0 (TypeIdx 0): kfb_idx={rot_s25[0]}, kf_start={rot_s26[0]}, kf_count={rot_s27[0]}, s28={rot_s28[0]}")

# Check keyforms for RotDef 0 (indices kf_start .. kf_start + kf_count)
start, count = rot_s26[0], rot_s27[0]
s64 = struct.unpack_from(f"<{n_rot_kf}f", data, offsets[64])
s65 = struct.unpack_from(f"<{n_rot_kf}f", data, offsets[65])
s66 = struct.unpack_from(f"<{n_rot_kf}f", data, offsets[66])
s67 = struct.unpack_from(f"<{n_rot_kf}f", data, offsets[67])

print(f"RotDef 0 Keyforms (count={count}):")
for k in range(start, start + count):
    print(f"  KF {k}: s64={s64[k]:.4f} (deg={math.degrees(s64[k]):.2f}), s65={s65[k]:.4f}, s66={s66[k]:.4f}, s67={s67[k]:.4f}")

# WarpDef 0 (Def 5, TypeIdx 0)
warp_s19 = struct.unpack_from(f"<{n_warp}i", data, offsets[19])
warp_s20 = struct.unpack_from(f"<{n_warp}i", data, offsets[20])
warp_s21 = struct.unpack_from(f"<{n_warp}i", data, offsets[21])
warp_s22 = struct.unpack_from(f"<{n_warp}i", data, offsets[22])
warp_s23 = struct.unpack_from(f"<{n_warp}i", data, offsets[23])
warp_s24 = struct.unpack_from(f"<{n_warp}i", data, offsets[24])

print(f"\nWarpDef 0 (TypeIdx 0): kfb_idx={warp_s19[0]}, kf_start={warp_s20[0]}, kf_count={warp_s21[0]}, v_count={warp_s22[0]}, rows={warp_s23[0]}, cols={warp_s24[0]}")

start_w, count_w = warp_s20[0], warp_s21[0]
s59 = struct.unpack_from(f"<{n_warp_kf}f", data, offsets[59])
s60 = struct.unpack_from(f"<{n_warp_kf}i", data, offsets[60])
s61 = struct.unpack_from(f"<{n_warp_kf}f", data, offsets[61])
s62 = struct.unpack_from(f"<{n_warp_kf}f", data, offsets[62])
s63 = struct.unpack_from(f"<{n_warp_kf}f", data, offsets[63])

print(f"WarpDef 0 Keyforms (count={count_w}):")
for k in range(start_w, start_w + count_w):
    print(f"  KF {k}: s59(opac)={s59[k]:.2f}, s60(pos_start)={s60[k]}, s61={s61[k]:.2f}, s62={s62[k]:.2f}, s63={s63[k]:.2f}")
