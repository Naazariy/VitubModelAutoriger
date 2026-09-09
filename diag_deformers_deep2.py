import struct
import numpy as np

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_parts, n_deformers, n_warp, n_rot, n_art, n_params = counts[0:6]
n_part_kf, n_warp_kf, n_rot_kf, n_art_kf = counts[6:10]

print("=== ROTATION DEFORMER KEYFORMS (Slots 64..67) ===")
s64 = struct.unpack_from(f"<{n_rot_kf}f", data, offsets[64])
s65 = struct.unpack_from(f"<{n_rot_kf}f", data, offsets[65])
s66 = struct.unpack_from(f"<{n_rot_kf}f", data, offsets[66])
s67 = struct.unpack_from(f"<{n_rot_kf}f", data, offsets[67])

print(f"Slot 64: min={min(s64):.4f}, max={max(s64):.4f}, first 12={s64[:12]}")
print(f"Slot 65: min={min(s65):.4f}, max={max(s65):.4f}, first 12={s65[:12]}")
print(f"Slot 66: min={min(s66):.4f}, max={max(s66):.4f}, first 12={s66[:12]}")
print(f"Slot 67: min={min(s67):.4f}, max={max(s67):.4f}, first 12={s67[:12]}")

print("\n=== ROTATION DEFORMERS (Slots 25..28) ===")
s25 = struct.unpack_from(f"<{n_rot}i", data, offsets[25])
s26 = struct.unpack_from(f"<{n_rot}i", data, offsets[26])
s27 = struct.unpack_from(f"<{n_rot}i", data, offsets[27])
# Check if s28 is float or int
s28_f = struct.unpack_from(f"<{n_rot}f", data, offsets[28])
s28_i = struct.unpack_from(f"<{n_rot}i", data, offsets[28])
print(f"Slot 25 (KeyformBindingsBeginIndices): {s25[:10]}")
print(f"Slot 26 (KeyformSourcesBeginIndices): {s26[:10]}")
print(f"Slot 27 (KeyformSourcesCounts): {s27[:10]}")
print(f"Slot 28 (Base Angle or Origin?): f={s28_f[:10]} | i={s28_i[:10]}")

print("\n=== WARP DEFORMER KEYFORMS (Slots 59..63) ===")
s59 = struct.unpack_from(f"<{n_warp_kf}f", data, offsets[59])
s60 = struct.unpack_from(f"<{n_warp_kf}i", data, offsets[60])
s61 = struct.unpack_from(f"<{n_warp_kf}f", data, offsets[61])
s62 = struct.unpack_from(f"<{n_warp_kf}f", data, offsets[62])
s63 = struct.unpack_from(f"<{n_warp_kf}f", data, offsets[63])

print(f"Slot 59 (Opacities?): {s59[:10]}")
print(f"Slot 60 (KeyformPositionSourcesBeginIndices): {s60[:10]}")
print(f"Slot 61: {s61[:10]}")
print(f"Slot 62: {s62[:10]}")
print(f"Slot 63: {s63[:10]}")
