import struct
import numpy as np

with open("output/hiyori_vts/hiyori.moc3", "rb") as f:
    data = f.read()

offsets = struct.unpack_from("<160I", data, 64)
counts = struct.unpack_from("<23I", data, offsets[0])

# Let's verify each section's exact size against its element count
# and understand exactly what is stored.

def get_sec(s):
    off = offsets[s]
    if off == 0: return b""
    # find next offset > off
    next_offs = [o for o in offsets if o > off]
    next_o = min(next_offs) if next_offs else len(data)
    return data[off:next_o]

# Check ArtMesh sections 29..48:
n_meshes = counts[4] # 133
print(f"n_meshes = {n_meshes}")
for s in range(29, 49):
    b = get_sec(s)
    print(f"ArtMesh Sec {s:2d} (len={len(b):5d}): per mesh = {len(b)/n_meshes:.2f} bytes. int[:4] = {struct.unpack_from('<4i', b) if len(b)>=16 else 'small'}")

# Check Parameters sections 49..57:
n_params = counts[5] # 74
print(f"\nn_params = {n_params}")
for s in range(49, 58):
    b = get_sec(s)
    print(f"Param Sec {s:2d} (len={len(b):5d}): per param = {len(b)/n_params:.2f} bytes. int[:4] = {struct.unpack_from('<4i', b) if len(b)>=16 else 'small'}, flt[:4] = {[round(x,2) for x in struct.unpack_from('<4f', b)] if len(b)>=16 else 'small'}")

# Check Keyform sections 68..71:
n_am_kf = counts[9] # 1229
n_kf_pos = counts[10] # 82304
print(f"\nn_am_kf = {n_am_kf}, n_kf_pos = {n_kf_pos}")
for s in range(68, 72):
    b = get_sec(s)
    print(f"KF Sec {s:2d} (len={len(b):7d}): len / n_am_kf = {len(b)/n_am_kf:.2f}, len / n_kf_pos = {len(b)/n_kf_pos:.2f}. int[:4] = {struct.unpack_from('<4i', b) if len(b)>=16 else 'small'}, flt[:4] = {[round(x,2) for x in struct.unpack_from('<4f', b)] if len(b)>=16 else 'small'}")

# Check Param Bindings & Keys 72..77:
n_pbi = counts[11] # 97
n_kfb = counts[12] # 80
n_pb  = counts[13] # 78
n_keys = counts[14] # 233
print(f"\nn_pbi={n_pbi}, n_kfb={n_kfb}, n_pb={n_pb}, n_keys={n_keys}")
for s in range(72, 78):
    b = get_sec(s)
    print(f"Binding Sec {s:2d} (len={len(b):5d}): len/pbi={len(b)/n_pbi:.2f}, len/kfb={len(b)/n_kfb:.2f}, len/keys={len(b)/n_keys:.2f}. int[:4] = {struct.unpack_from('<4i', b) if len(b)>=16 else 'small'}, flt[:4] = {[round(x,2) for x in struct.unpack_from('<4f', b)] if len(b)>=16 else 'small'}")

# Check Geometry 78..79:
n_uvs = counts[15] # 5614
n_indices = counts[16] # 10224
print(f"\nn_uvs={n_uvs}, n_indices={n_indices}")
for s in [78, 79]:
    b = get_sec(s)
    print(f"Geom Sec {s:2d} (len={len(b):5d}): len/uvs={len(b)/n_uvs:.2f}, len/indices={len(b)/n_indices:.2f}. int[:4] = {struct.unpack_from('<4i', b) if len(b)>=16 else 'small'}, flt[:4] = {[round(x,2) for x in struct.unpack_from('<4f', b)] if len(b)>=16 else 'small'}")

