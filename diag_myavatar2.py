import struct

with open("output/MyAvatar2/MyAvatar2.moc3", "rb") as f:
    data = f.read()

print(f"MyAvatar2 size: {len(data)}")
print(f"Magic: {data[:4]}, Version: {data[4]}, Endian: {data[5]}")

offsets = struct.unpack_from("<160I", data, 64)
print("\nNon-zero offsets in MyAvatar2:")
for i, off in enumerate(offsets):
    if off != 0:
        print(f"  Sec [{i:2d}]: 0x{off:04X} ({off})")
