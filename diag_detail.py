import struct
import numpy as np

with open("output/hiyori_vts/hiyori.moc3", "rb") as f:
    data = f.read()

offsets = struct.unpack_from("<160I", data, 64)
counts = struct.unpack_from("<23I", data, offsets[0])

count_dict = {
    "Parts": counts[0],
    "Deformers": counts[1],
    "WarpDeformers": counts[2],
    "RotationDeformers": counts[3],
    "ArtMeshes": counts[4],
    "Parameters": counts[5],
    "PartKeyforms": counts[6],
    "WarpKeyforms": counts[7],
    "RotationKeyforms": counts[8],
    "ArtMeshKeyforms": counts[9],
    "KeyformPositions": counts[10],
    "ParamBindingIndices": counts[11],
    "KeyformBindings": counts[12],
    "ParamBindings": counts[13],
    "Keys": counts[14],
    "UVs": counts[15],
    "PositionIndices": counts[16],
    "DrawableMasks": counts[17],
    "DrawOrderGroups": counts[18],
    "DrawOrderGroupObjects": counts[19],
    "Glue": counts[20],
    "GlueInfo": counts[21],
    "GlueKeyforms": counts[22]
}

print("Counts dictionary:")
for k, v in count_dict.items():
    print(f"  {k:25s}: {v}")

non_zero = [(i, offsets[i]) for i in range(160) if offsets[i] != 0]

print("\n--- Detailed Analysis of each section in Hiyori ---")

for idx, (sec_idx, off) in enumerate(non_zero):
    next_off = non_zero[idx+1][1] if idx+1 < len(non_zero) else len(data)
    sec_len = next_off - off
    sec_data = data[off:next_off]
    
    # Let's test different interpretations:
    # 1. Null-terminated string list (64B each? or variable length?)
    # 2. int32 list
    # 3. uint32 list
    # 4. float32 list
    # 5. int16 / uint16 list
    # 6. uint8 / byte list
    
    # Check string list (64B aligned)
    # Check if section length matches count_dict * item_size
    matches = []
    for count_name, c_val in count_dict.items():
        if c_val == 0: continue
        if sec_len == c_val * 64:
            matches.append(f"{count_name} * 64B (strings)")
        if sec_len == c_val * 4:
            matches.append(f"{count_name} * 4B (int/float/uint)")
        if sec_len == c_val * 2:
            matches.append(f"{count_name} * 2B (short/ushort)")
        if sec_len == c_val * 1:
            matches.append(f"{count_name} * 1B (byte/flags)")
        if sec_len == c_val * 8:
            matches.append(f"{count_name} * 8B (float2/double/int2)")
        if sec_len == c_val * 12:
            matches.append(f"{count_name} * 12B")
        if sec_len == c_val * 16:
            matches.append(f"{count_name} * 16B")
            
    # Sample first few values as float and int
    int4 = struct.unpack_from(f"<{min(4, len(sec_data)//4)}i", sec_data) if len(sec_data)>=4 else ()
    flt4 = struct.unpack_from(f"<{min(4, len(sec_data)//4)}f", sec_data) if len(sec_data)>=4 else ()
    
    # String check
    first_str = ""
    try:
        if len(sec_data) >= 64:
            first_str = sec_data[:64].split(b"\x00", 1)[0].decode("utf-8")
        elif len(sec_data) > 0:
            first_str = sec_data.split(b"\x00", 1)[0].decode("utf-8")
    except:
        pass

    print(f"Sec {sec_idx:3d} (0x{sec_idx:02X}): off=0x{off:06X}, len={sec_len:6d} | Matches: {', '.join(matches)} | i32: {int4} | f32: {[round(f, 3) for f in flt4]} | str: '{first_str[:30]}'")
