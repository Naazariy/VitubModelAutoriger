import struct

with open("output/hiyori_vts/hiyori.moc3", "rb") as f:
    data = f.read()

offsets = struct.unpack_from("<160I", data, 64)
counts = struct.unpack_from("<23I", data, offsets[0])

non_zero = [(i, offsets[i]) for i in range(160) if offsets[i] != 0]

for idx, (sec_idx, off) in enumerate(non_zero[:15]):
    next_off = non_zero[idx+1][1] if idx+1 < len(non_zero) else len(data)
    sec_len = next_off - off
    sec_data = data[off:next_off]
    
    int4 = struct.unpack_from(f"<{min(4, len(sec_data)//4)}i", sec_data) if len(sec_data)>=4 else ()
    flt4 = struct.unpack_from(f"<{min(4, len(sec_data)//4)}f", sec_data) if len(sec_data)>=4 else ()
    first_str = ""
    try:
        first_str = sec_data.split(b"\x00", 1)[0].decode("utf-8")
    except:
        pass
    print(f"Sec {sec_idx:3d} (0x{sec_idx:02X}): off=0x{off:06X}, len={sec_len:6d} | i32: {int4} | f32: {[round(f, 3) for f in flt4]} | str: '{first_str[:25]}'")
