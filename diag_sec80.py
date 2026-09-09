import struct

with open("output/hiyori_vts/hiyori.moc3", "rb") as f:
    data = f.read()

offsets = struct.unpack_from("<160I", data, 64)
non_zero = [(i, offsets[i]) for i in range(160) if offsets[i] != 0]

def inspect_section(sec_idx):
    off = offsets[sec_idx]
    idx_in_nz = [i for i, (s, _) in enumerate(non_zero) if s == sec_idx][0]
    next_off = non_zero[idx_in_nz+1][1] if idx_in_nz+1 < len(non_zero) else len(data)
    sec_len = next_off - off
    s_data = data[off:next_off]
    return off, sec_len, s_data

print("=== REMAINING SECTIONS 80-100 ===")
for s in range(80, 105):
    if s >= len(offsets) or offsets[s] == 0:
        continue
    off, length, s_data = inspect_section(s)
    ints = struct.unpack_from(f"<{min(8, len(s_data)//4)}i", s_data) if len(s_data)>=4 else []
    floats = [round(x, 2) for x in struct.unpack_from(f"<{min(8, len(s_data)//4)}f", s_data)] if len(s_data)>=4 else []
    first_str = ""
    try:
        first_str = s_data[:64].split(b"\x00", 1)[0].decode("utf-8")
    except:
        pass
    print(f"Sec {s:3d} (off=0x{off:06X}, len={length:5d}): ints[:8]={ints} | floats[:8]={floats} | str='{first_str[:25]}'")
