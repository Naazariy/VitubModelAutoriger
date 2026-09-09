import struct

with open("output/hiyori_vts/hiyori.moc3", "rb") as f:
    data = f.read()

offsets = struct.unpack_from("<160I", data, 64)
counts = struct.unpack_from("<23I", data, offsets[0])

count_dict = {
    "Parts": counts[0],               # 25
    "Deformers": counts[1],           # 117
    "WarpDeformers": counts[2],       # 57
    "RotationDeformers": counts[3],   # 60
    "ArtMeshes": counts[4],           # 133
    "Parameters": counts[5],          # 74
    "PartKeyforms": counts[6],        # 25
    "WarpKeyforms": counts[7],        # 314
    "RotationKeyforms": counts[8],    # 198
    "ArtMeshKeyforms": counts[9],     # 1229
    "KeyformPositions": counts[10],   # 82304
    "ParamBindingIndices": counts[11],# 97
    "KeyformBindings": counts[12],    # 80
    "ParamBindings": counts[13],      # 78
    "Keys": counts[14],               # 233
    "UVs": counts[15],                # 5614
    "PositionIndices": counts[16],    # 10224
    "DrawableMasks": counts[17],      # 8
    "DrawOrderGroups": counts[18],    # 1
    "DrawOrderGroupObjects": counts[19], # 133
    "Glue": counts[20],               # 26
    "GlueInfo": counts[21],           # 470
    "GlueKeyforms": counts[22]        # 26
}

non_zero = [(i, offsets[i]) for i in range(160) if offsets[i] != 0]

for idx, (sec_idx, off) in enumerate(non_zero):
    if sec_idx > 50: break
    next_off = non_zero[idx+1][1] if idx+1 < len(non_zero) else len(data)
    sec_len = next_off - off
    sec_data = data[off:next_off]
    
    # Check matching count * size
    matches = []
    for count_name, c_val in count_dict.items():
        if c_val == 0: continue
        for size in [1, 2, 4, 8, 12, 16, 24, 32, 64]:
            if sec_len == c_val * size:
                matches.append(f"{count_name}*{size}B")
            # Also check padded to 64:
            elif (c_val * size + 63) & ~63 == sec_len and (c_val * size) != sec_len:
                matches.append(f"{count_name}*{size}B(pad)")
            
    # Sample first few values
    int4 = struct.unpack_from(f"<{min(4, len(sec_data)//4)}i", sec_data) if len(sec_data)>=4 else ()
    flt4 = struct.unpack_from(f"<{min(4, len(sec_data)//4)}f", sec_data) if len(sec_data)>=4 else ()
    
    first_str = ""
    try:
        first_str = sec_data.split(b"\x00", 1)[0].decode("utf-8")
    except:
        pass

    print(f"Sec {sec_idx:3d} (0x{sec_idx:02X}): off=0x{off:06X}, len={sec_len:6d} | Match: {', '.join(matches)} | i32: {int4} | f32: {[round(f, 3) for f in flt4]} | str: '{first_str[:25]}'")
