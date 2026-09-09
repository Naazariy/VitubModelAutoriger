import struct
import math

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_rot_kf = counts[8]

# Check slot 64 (or slot 62) in Hiyori
# Remember: in Hiyori, RotationDeformerKeyforms are at Slot 64..67
s64 = struct.unpack_from(f"<{n_rot_kf}f", data, offsets[64])
print("All unique angles in Hiyori (first 30):")
print([round(x, 4) for x in s64[:30]])
print(f"Min angle: {min(s64):.4f} rad ({math.degrees(min(s64)):.2f} deg), Max angle: {max(s64):.4f} rad ({math.degrees(max(s64)):.2f} deg)")
