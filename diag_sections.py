import struct

with open("output/hiyori_vts/hiyori.moc3", "rb") as f:
    data = f.read()

offsets = struct.unpack_from("<160I", data, 64)

# Let's inspect Section 0 counts
counts = struct.unpack_from("<23I", data, offsets[0])
print("=== SECTION 0 COUNTS ===")
count_names = [
    "Parts (0)",
    "Deformers (1)",
    "Warp Deformers (2)",
    "Rotation Deformers (3)",
    "ArtMeshes (4)",
    "Parameters (5)",
    "Part Keyforms (6)",
    "Warp Deformer Keyforms (7)",
    "Rotation Deformer Keyforms (8)",
    "ArtMesh Keyforms (9)",
    "Keyform Positions (10)",
    "Param Binding Indices (11)",
    "Keyform Bindings (12)",
    "Param Bindings (13)",
    "Keys (14)",
    "UVs (15)",
    "Position Indices (16)",
    "Drawable Masks (17)",
    "Draw Order Groups (18)",
    "Draw Order Group Objects (19)",
    "Glue (20)",
    "Glue Info (21)",
    "Glue Keyforms (22)"
]
for i, name in enumerate(count_names):
    print(f"  [{i:2d}] {name:30s}: {counts[i]}")

# Let's check non-zero sections and their lengths
non_zero = [(i, offsets[i]) for i in range(160) if offsets[i] != 0]
print(f"\nTotal non-zero sections: {len(non_zero)}")

for idx, (sec_idx, off) in enumerate(non_zero):
    next_off = non_zero[idx+1][1] if idx+1 < len(non_zero) else len(data)
    sec_len = next_off - off
    # Check data sample
    sample = data[off:min(off+32, next_off)]
    print(f"Sec {sec_idx:3d} (0x{sec_idx:02X}): off=0x{off:06X}, len={sec_len:6d} (0x{sec_len:04X}) | sample: {sample.hex()[:40]}")
