import struct

with open('output/hiyori_vts/hiyori.moc3', 'rb') as f:
    data = f.read()

offsets = struct.unpack_from('<160I', data, 64)
counts = struct.unpack_from('<23I', data, offsets[0])
n_parts, n_deformers, n_warp, n_rot, n_art, n_params = counts[0:6]
n_part_kf, n_warp_kf, n_rot_kf, n_art_kf = counts[6:10]

print(f"n_warp={n_warp}, n_rot={n_rot}")

# Check Slot 19..28 values for first 10 elements and element 57..60
for s in range(19, 29):
    off = offsets[s]
    # Check if length matches n_warp or n_rot
    # In Hiyori, n_warp=57, n_rot=60
    # Let's inspect raw ints/floats
    raw_ints = struct.unpack_from("<60i", data, off)
    raw_floats = [round(x, 2) for x in struct.unpack_from("<60f", data, off)]
    print(f"\nSlot {s}:")
    print(f"  raw_ints[:10]  = {raw_ints[:10]}")
    print(f"  raw_floats[:10]= {raw_floats[:10]}")
    print(f"  raw_ints[50:60]= {raw_ints[50:60]}")

print("\n--- Slots 59..63 (Warp Keyforms, count=314) ---")
for s in range(59, 64):
    off = offsets[s]
    raw_ints = struct.unpack_from("<10i", data, off)
    raw_floats = [round(x, 2) for x in struct.unpack_from("<10f", data, off)]
    print(f"Slot {s}: ints[:10]={raw_ints} | floats[:10]={raw_floats}")

print("\n--- Slots 64..67 (Rotation Keyforms, count=198) ---")
for s in range(64, 68):
    off = offsets[s]
    raw_ints = struct.unpack_from("<10i", data, off)
    raw_floats = [round(x, 2) for x in struct.unpack_from("<10f", data, off)]
    print(f"Slot {s}: ints[:10]={raw_ints} | floats[:10]={raw_floats}")
