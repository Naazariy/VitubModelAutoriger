import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
s71_off = offsets[71]
# Read first 160 floats of Section 71
floats = struct.unpack_from("<160f", data, s71_off)
print("First 36 (x,y) pairs (72 floats) in Sec 71:")
for i in range(0, 72, 2):
    print(f"  v{i//2:2d}: ({floats[i]:.4f}, {floats[i+1]:.4f})")

print(f"\nFloats 72..80 (padding?): {floats[72:80]}")
