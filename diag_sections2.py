import struct

with open("output/hiyori_vts/hiyori.moc3", "rb") as f:
    data = f.read()

offsets = struct.unpack_from("<160I", data, 64)
non_zero = [(i, offsets[i]) for i in range(160) if offsets[i] != 0]

counts = struct.unpack_from("<23I", data, offsets[0])

print("Counts:")
fields = [
    "Parts", "Deformers", "WarpDeformers", "RotationDeformers", "ArtMeshes", "Parameters",
    "PartKeyforms", "WarpKeyforms", "RotationKeyforms", "ArtMeshKeyforms", "KeyformPositions",
    "ParamBindingIndices", "KeyformBindings", "ParamBindings", "Keys", "UVs", "PositionIndices",
    "DrawableMasks", "DrawOrderGroups", "DrawOrderGroupObjects", "Glue", "GlueInfo", "GlueKeyforms"
]
for idx, (name, val) in enumerate(zip(fields, counts)):
    print(f"  {idx:2d}: {name:25s} = {val}")

print("\nAll non-zero sections in Hiyori:")
for idx, (sec_idx, off) in enumerate(non_zero):
    next_off = non_zero[idx+1][1] if idx+1 < len(non_zero) else len(data)
    sec_len = next_off - off
    # Determine element count if we can guess type
    sample = data[off:min(off+16, next_off)]
    # Check if strings
    str_sample = ""
    if sec_len >= 64:
        try:
            s = data[off:off+64].split(b"\x00", 1)[0].decode("utf-8")
            if len(s) > 1 and s.isprintable():
                str_sample = f"str='{s}'"
        except:
            pass
    print(f"Sec {sec_idx:3d} (0x{sec_idx:02X}): off=0x{off:06X}, len={sec_len:6d} (0x{sec_len:04X}) {str_sample}")
