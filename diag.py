import struct
import numpy as np
from src.core.keyform import KeyformTable, ParameterBinding, DrawableKeyforms, WarpDeformerData, RotationDeformerData
from src.exporter.moc3_writer import Moc3Writer, Moc3Reader
from src.validator.structural_validator import validate_live2d_model

# Test creating a KeyformTable with Deformers
table = KeyformTable(
    canvas_width=2048,
    canvas_height=2048,
    model_name="DeformerTestModel"
)

table.add_parameter(ParameterBinding("ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]))
table.add_parameter(ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]))
table.add_parameter(ParameterBinding("ParamAngleZ", min_val=-20.0, default_val=0.0, max_val=20.0, key_values=[-20.0, 0.0, 20.0]))

# Rotation Deformer for AngleZ
rot_def = RotationDeformerData(
    deformer_id="RotationDeformer_Head",
    parent_part_id="PartRoot",
    parent_deformer_id=None,
    parameter_ids=["ParamAngleZ"],
    origin=(1024.0, 1024.0),
    keyforms={(-20.0,): -20.0, (0.0,): 0.0, (20.0,): 20.0}
)
table.add_rotation_deformer(rot_def)

# Warp Deformer for AngleX, AngleY
warp_cols, warp_rows = 5, 5
xs = np.linspace(500.0, 1500.0, warp_cols + 1)
ys = np.linspace(500.0, 1500.0, warp_rows + 1)
base_pts = np.array([[x, y] for y in ys for x in xs], dtype=np.float32)

warp_def = WarpDeformerData(
    deformer_id="WarpDeformer_Head",
    parent_part_id="PartRoot",
    parent_deformer_id="RotationDeformer_Head",
    parameter_ids=["ParamAngleX", "ParamAngleY"],
    rows=warp_rows,
    cols=warp_cols,
    base_points=base_pts
)

for ay in [-30.0, 0.0, 30.0]:
    for ax in [-30.0, 0.0, 30.0]:
        shift = np.array([ax * 2.0, ay * 2.0], dtype=np.float32)
        warp_def.deformed_positions[(ax, ay)] = base_pts + shift

table.add_warp_deformer(warp_def)

# ArtMesh (unbound, child of WarpDeformer)
base_v = np.array([[800, 800], [1200, 800], [1200, 1200], [800, 1200]], dtype=np.float32)
tris = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
uvs = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)

artmesh = DrawableKeyforms(
    drawable_id="ArtMesh_Face",
    texture_index=0,
    base_vertices=base_v,
    triangles=tris,
    uvs_atlas=uvs,
    parameter_ids=[], # No direct rotation parameters!
    parent_deformer_id="WarpDeformer_Head",
    draw_order=500
)
table.add_drawable(artmesh)

print("KeyformTable setup completed successfully.")









