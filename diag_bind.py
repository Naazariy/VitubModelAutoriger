import struct
import numpy as np

with open("output/hiyori_vts/hiyori.moc3", "rb") as f:
    data = f.read()

offsets = struct.unpack_from("<160I", data, 64)
counts = struct.unpack_from("<23I", data, offsets[0])

def read_ints(sec_idx, count):
    off = offsets[sec_idx]
    if off == 0: return []
    return list(struct.unpack_from(f"<{count}i", data, off))

def read_floats(sec_idx, count):
    off = offsets[sec_idx]
    if off == 0: return []
    return [round(x, 4) for x in struct.unpack_from(f"<{count}f", data, off)]

n_meshes = counts[4]
n_params = counts[5]
n_am_kf  = counts[9]
n_pbi    = counts[11]
n_kfb    = counts[12]
n_pb     = counts[13]
n_keys   = counts[14]

print("=== ARTMESH SECTIONS (first 10 of 133 meshes) ===")
# Sec 33: IDs
art_ids = [data[offsets[33]+i*64:offsets[33]+(i+1)*64].split(b"\x00",1)[0].decode("utf-8") for i in range(10)]
print("ArtMesh IDs:", art_ids)
print("Sec 34 (ArtMeshes.ParentPartIndices or similar):", read_ints(34, 10))
print("Sec 35 (ArtMeshes.KeyformSourcesBeginIndices):", read_ints(35, 10))
print("Sec 36 (ArtMeshes.KeyformSourcesCounts):", read_ints(36, 10))
print("Sec 37 (ArtMeshes.KeyformBindingsBeginIndices):", read_ints(37, 10))
print("Sec 38 (ArtMeshes.KeyformBindingsCounts):", read_ints(38, 10))
print("Sec 39 (ArtMeshes.ParentDeformerIndices):", read_ints(39, 10))
print("Sec 40 (ArtMeshes.ParentPartIndices):", read_ints(40, 10))
print("Sec 41 (ArtMeshes.TextureNos):", read_ints(41, 10))
print("Sec 42 (ArtMeshes.DrawableFlags):", list(data[offsets[42]:offsets[42]+10]))
print("Sec 43 (ArtMeshes.VertexCounts):", read_ints(43, 10))
print("Sec 44 (ArtMeshes.UvSourcesBeginIndices):", read_ints(44, 10))
print("Sec 45 (ArtMeshes.PositionIndexSourcesBeginIndices):", read_ints(45, 10))
print("Sec 46 (ArtMeshes.PositionIndexSourcesCounts):", read_ints(46, 10))
print("Sec 47 (ArtMeshes.MaskCounts):", read_ints(47, 10))
print("Sec 48 (ArtMeshes.MaskSourcesBeginIndices):", read_ints(48, 10))

print("\n=== PARAMETERS (first 10 of 74 params) ===")
param_ids = [data[offsets[50]+i*64:offsets[50]+(i+1)*64].split(b"\x00",1)[0].decode("utf-8") for i in range(10)]
print("Param IDs:", param_ids)
print("Sec 51 (Max):", read_floats(51, 10))
print("Sec 52 (Min):", read_floats(52, 10))
print("Sec 53 (Default):", read_floats(53, 10))
print("Sec 54 (IsRepeat):", read_ints(54, 10))
print("Sec 55 (DecimalPlaces):", read_ints(55, 10))
print("Sec 56 (KeySourcesBeginIndices):", read_ints(56, 10))
print("Sec 57 (KeySourcesCounts):", read_ints(57, 10))

print("\n=== KEYFORM BINDINGS & KEYS ===")
print("Sec 72 (ParamBindingIndices, total 97):", read_ints(72, 20))
print("Sec 73 (KeyformBindings.ParamBindingIndicesBeginIndices, total 80):", read_ints(73, 20))
print("Sec 74 (KeyformBindings.ParamBindingIndicesCounts, total 80):", read_ints(74, 20))
print("Sec 75 (KeyformBindings.KeySourcesBeginIndices, total 80):", read_ints(75, 20))
print("Sec 76 (KeyformBindings.KeySourcesCounts, total 80):", read_ints(76, 20))
print("Sec 77 (Keys.Values, total 233):", read_floats(77, 20))

print("\n=== ARTMESH KEYFORMS (first 10) ===")
print("Sec 68 (Opacities):", read_floats(68, 10))
print("Sec 69 (DrawOrders):", read_floats(69, 10))
print("Sec 70 (KeyformPositionSourcesBeginIndices):", read_ints(70, 10))
