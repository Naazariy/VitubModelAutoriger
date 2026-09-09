import struct

with open("output/hiyori_vts/hiyori.moc3", "rb") as f:
    data = f.read()

offsets = struct.unpack_from("<160I", data, 64)

# Sec 2 & Sec 3 (Parts)
s2 = data[offsets[2]:offsets[3]]
s3 = data[offsets[3]:offsets[4]]

print("--- Sec 2 (Parts ID Table) ---")
print(f"Sec 2 len: {len(s2)}")
for i in range(0, len(s2), 8):
    u64 = struct.unpack_from("<Q", s2, i)[0]
    u32_pair = struct.unpack_from("<II", s2, i)
    print(f"  [{i//8:2d}]: u64={u64:016X}, u32s={u32_pair}")

print("\n--- Sec 3 (Parts Strings) ---")
print(f"Sec 3 len: {len(s3)}")
print("Sec 3 raw:")
print(s3[:200])
# Let's see strings in Sec 3
strs = s3.split(b"\x00")
print("Split by null:", [s.decode("utf-8", errors="replace") for s in strs if s])
