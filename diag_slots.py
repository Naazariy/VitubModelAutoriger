import struct
import numpy as np

with open("output/hiyori_vts/hiyori.moc3", "rb") as f:
    data = f.read()

offsets = struct.unpack_from("<160I", data, 64)
counts = struct.unpack_from("<23I", data, offsets[0])

count_dict = {
    0: ("Parts", counts[0]),
    1: ("Deformers", counts[1]),
    2: ("WarpDeformers", counts[2]),
    3: ("RotationDeformers", counts[3]),
    4: ("ArtMeshes", counts[4]),
    5: ("Parameters", counts[5]),
    6: ("PartKeyforms", counts[6]),
    7: ("WarpKeyforms", counts[7]),
    8: ("RotationKeyforms", counts[8]),
    9: ("ArtMeshKeyforms", counts[9]),
    10: ("KeyformPositions", counts[10]),
    11: ("ParamBindingIndices", counts[11]),
    12: ("KeyformBindings", counts[12]),
    13: ("ParamBindings", counts[13]),
    14: ("Keys", counts[14]),
    15: ("UVs", counts[15]),
    16: ("PositionIndices", counts[16]),
    17: ("DrawableMasks", counts[17]),
    18: ("DrawOrderGroups", counts[18]),
    19: ("DrawOrderGroupObjects", counts[19]),
    20: ("Glue", counts[20]),
    21: ("GlueInfo", counts[21]),
    22: ("GlueKeyforms", counts[22])
}

# Let's inspect each section and figure out its exact element type and count formula:
non_zero = [(i, offsets[i]) for i in range(160) if offsets[i] != 0]

print(f"{'Slot':4s} | {'Offset':8s} | {'Length':7s} | {'Elements':10s} | {'Type/Size':15s} | {'Description/Values'}")
print("-" * 100)

for idx, (s, off) in enumerate(non_zero):
    next_off = non_zero[idx+1][1] if idx+1 < len(non_zero) else len(data)
    sec_len = next_off - off
    sec_data = data[off:next_off]
    
    # Try to find which count matches
    best_match = ""
    for cid, (cname, cval) in count_dict.items():
        if cval == 0: continue
        for el_sz, el_name in [(1, "uint8/int8"), (2, "uint16/int16"), (4, "uint32/int32/f32"), (8, "uint64/ptr/vec2"), (12, "vec3"), (16, "vec4"), (64, "string64")]:
            raw_sz = cval * el_sz
            pad_sz = (raw_sz + 63) & ~63
            if sec_len == pad_sz or sec_len == raw_sz:
                best_match = f"{cname}[{cval}] x {el_name}"
                break
        if best_match:
            break
            
    # Sample display
    desc = ""
    if "string64" in best_match:
        names = []
        for i in range(0, min(len(sec_data), 192), 64):
            names.append(sec_data[i:i+64].split(b"\x00", 1)[0].decode("utf-8", errors="replace"))
        desc = f"IDs: {names}"
    elif len(sec_data) >= 4:
        i_vals = struct.unpack_from(f"<{min(4, len(sec_data)//4)}i", sec_data)
        f_vals = [round(x, 2) for x in struct.unpack_from(f"<{min(4, len(sec_data)//4)}f", sec_data)]
        if all(abs(f) < 1e5 and not np.isnan(f) for f in f_vals) and any('.' in str(f) and f != 0.0 for f in f_vals):
            desc = f"Floats: {f_vals}"
        else:
            desc = f"Ints: {i_vals}"
            
    print(f"[{s:2d}]  | 0x{off:06X} | {sec_len:7d} | {best_match:30s} | {desc}")
