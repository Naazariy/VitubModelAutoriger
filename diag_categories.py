import struct
import numpy as np

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

def inspect_section(sec_idx):
    off = offsets[sec_idx]
    # find next
    idx_in_nz = [i for i, (s, _) in enumerate(non_zero) if s == sec_idx][0]
    next_off = non_zero[idx_in_nz+1][1] if idx_in_nz+1 < len(non_zero) else len(data)
    sec_len = next_off - off
    s_data = data[off:next_off]
    return off, sec_len, s_data

# Let's inspect sections grouped by concept
print("=== PARTS (Counts: parts=25, part_keyforms=25) ===")
for s in range(2, 10):
    if offsets[s] == 0:
        print(f"Sec {s}: (empty)")
        continue
    off, length, s_data = inspect_section(s)
    ints = struct.unpack_from(f"<{min(10, len(s_data)//4)}i", s_data) if len(s_data)>=4 else []
    print(f"Sec {s:2d} (off=0x{off:04X}, len={length:4d}): ints[:10]={ints}")

print("\n=== DEFORMERS (Counts: deformers=117, warp=57, rot=60, warp_kf=314, rot_kf=198) ===")
for s in range(10, 29):
    if offsets[s] == 0:
        print(f"Sec {s}: (empty)")
        continue
    off, length, s_data = inspect_section(s)
    ints = struct.unpack_from(f"<{min(10, len(s_data)//4)}i", s_data) if len(s_data)>=4 else []
    print(f"Sec {s:2d} (off=0x{off:04X}, len={length:4d}): ints[:10]={ints}")

print("\n=== ARTMESHES (Counts: art_meshes=133) ===")
for s in range(29, 49):
    if offsets[s] == 0:
        print(f"Sec {s}: (empty)")
        continue
    off, length, s_data = inspect_section(s)
    ints = struct.unpack_from(f"<{min(10, len(s_data)//4)}i", s_data) if len(s_data)>=4 else []
    print(f"Sec {s:2d} (off=0x{off:04X}, len={length:4d}): ints[:10]={ints}")

print("\n=== PARAMETERS (Counts: parameters=74) ===")
for s in range(49, 58):
    if offsets[s] == 0:
        print(f"Sec {s}: (empty)")
        continue
    off, length, s_data = inspect_section(s)
    ints = struct.unpack_from(f"<{min(10, len(s_data)//4)}i", s_data) if len(s_data)>=4 else []
    floats = [round(x, 2) for x in struct.unpack_from(f"<{min(10, len(s_data)//4)}f", s_data)] if len(s_data)>=4 else []
    print(f"Sec {s:2d} (off=0x{off:04X}, len={length:4d}): ints[:10]={ints} | floats[:10]={floats}")

print("\n=== KEYFORMS & GEOMETRY (Counts: artmesh_kf=1229, kf_pos=82304, uvs=5614, indices=10224) ===")
for s in range(58, 80):
    if offsets[s] == 0:
        print(f"Sec {s}: (empty)")
        continue
    off, length, s_data = inspect_section(s)
    ints = struct.unpack_from(f"<{min(8, len(s_data)//4)}i", s_data) if len(s_data)>=4 else []
    floats = [round(x, 2) for x in struct.unpack_from(f"<{min(8, len(s_data)//4)}f", s_data)] if len(s_data)>=4 else []
    print(f"Sec {s:2d} (off=0x{off:04X}, len={length:4d}): ints[:8]={ints} | floats[:8]={floats}")
