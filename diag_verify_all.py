import struct

with open("output/hiyori_vts/hiyori.moc3", "rb") as f:
    data = f.read()

offsets = struct.unpack_from("<160I", data, 64)
counts = struct.unpack_from("<23I", data, offsets[0])

def inspect_all(sec_range):
    for s in sec_range:
        if offsets[s] == 0:
            print(f"Sec {s:2d}: empty")
            continue
        off = offsets[s]
        next_offs = [o for o in offsets if o > off]
        next_o = min(next_offs) if next_offs else len(data)
        s_data = data[off:next_o]
        n_elems = len(s_data) // 4
        ints = struct.unpack_from(f"<{min(10, n_elems)}i", s_data) if n_elems else []
        floats = [round(x, 2) for x in struct.unpack_from(f"<{min(10, n_elems)}f", s_data)] if n_elems else []
        u8s = list(s_data[:10])
        print(f"Sec {s:2d} (off=0x{off:04X}, len={len(s_data):5d}): ints[:10]={ints} | floats[:10]={floats} | u8[:10]={u8s}")

print("--- Sections 2..9 (Parts) ---")
inspect_all(range(2, 10))

print("\n--- Sections 34..48 (ArtMeshes) ---")
inspect_all(range(34, 49))

print("\n--- Sections 51..57 (Parameters) ---")
inspect_all(range(51, 58))

print("\n--- Sections 68..71 (ArtMesh Keyforms) ---")
inspect_all(range(68, 72))

print("\n--- Sections 72..77 (Bindings/Keys) ---")
inspect_all(range(72, 78))

print("\n--- Sections 80..88 (DrawOrderGroups) ---")
inspect_all(range(80, 89))
