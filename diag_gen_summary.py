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

with open("sections_summary.txt", "w", encoding="utf-8") as out:
    for idx, (sec_idx, off) in enumerate(non_zero):
        next_off = non_zero[idx+1][1] if idx+1 < len(non_zero) else len(data)
        sec_len = next_off - off
        sec_data = data[off:next_off]
        
        sample_i32 = [x for x in struct.unpack_from(f"<{min(6, len(sec_data)//4)}i", sec_data)] if len(sec_data)>=4 else []
        sample_f32 = [round(x, 3) for x in struct.unpack_from(f"<{min(6, len(sec_data)//4)}f", sec_data)] if len(sec_data)>=4 else []
        sample_u16 = [x for x in struct.unpack_from(f"<{min(6, len(sec_data)//2)}H", sec_data)] if len(sec_data)>=2 else []
        sample_u8  = [x for x in sec_data[:min(6, len(sec_data))]]
        
        # Check string
        str_val = ""
        try:
            if sec_len >= 64:
                s = sec_data[:64].split(b"\x00", 1)[0].decode("utf-8")
                if len(s) > 0 and s.isprintable():
                    str_val = f"'{s}'"
        except:
            pass

        # Identify entity and type
        candidates = []
        for c_name, c_val in count_dict.items():
            if c_val == 0: continue
            for sz in [1, 2, 4, 8, 12, 16, 24, 32, 64]:
                if c_val * sz == sec_len:
                    candidates.append(f"{c_name}[{c_val}]*{sz}B")
                elif (c_val * sz + 63) & ~63 == sec_len:
                    candidates.append(f"{c_name}[{c_val}]*{sz}B(padded {c_val*sz}->{sec_len})")
                    
        out.write(f"Sec {sec_idx:3d} (0x{sec_idx:02X}): off=0x{off:06X}, len={sec_len:6d} | Cand: {', '.join(candidates)}\n")
        if str_val:
            out.write(f"       str: {str_val}\n")
        out.write(f"       i32: {sample_i32}\n")
        out.write(f"       f32: {sample_f32}\n")
        out.write(f"       u16: {sample_u16}\n")
        out.write(f"       u8:  {sample_u8}\n\n")

print("Wrote sections_summary.txt")
