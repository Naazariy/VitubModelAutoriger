import struct
import numpy as np
from src.core.keyform import KeyformTable, ParameterBinding, DrawableKeyforms

def align_to_64(offset: int) -> int:
    return (offset + 63) & ~63

def pad_buffer_to_64(buffer: bytearray) -> bytearray:
    remainder = len(buffer) % 64
    if remainder != 0:
        buffer.extend(b"\x00" * (64 - remainder))
    return buffer

def encode_id_64(name: str) -> bytes:
    encoded = name.encode("utf-8")[:63]
    return encoded.ljust(64, b"\x00")

def decode_id_64(data: bytes) -> str:
    return data.split(b"\x00", 1)[0].decode("utf-8", errors="replace")

# Let's test with sample keyform table
table = KeyformTable(canvas_width=2048, canvas_height=2048, model_name="TestModel")
table.add_parameter(ParameterBinding("ParamAngleX", -30.0, 0.0, 30.0, [-30.0, 0.0, 30.0], "Angle X"))
table.add_parameter(ParameterBinding("ParamAngleY", -30.0, 0.0, 30.0, [-30.0, 0.0, 30.0], "Angle Y"))
table.add_parameter(ParameterBinding("ParamAngleZ", -20.0, 0.0, 20.0, [-20.0, 0.0, 20.0], "Angle Z"))

v1 = np.array([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]], dtype=np.float32)
t1 = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
uv1 = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32)

d1 = DrawableKeyforms("ArtMesh_Body", 0, v1, t1, uv1, draw_order=500, opacity=1.0)
for ay in [-30.0, 0.0, 30.0]:
    for ax in [-30.0, 0.0, 30.0]:
        d1.add_keyform((ax, ay), v1 + np.array([ax*0.01, ay*0.01], dtype=np.float32))

table.add_drawable(d1)

print("KeyformTable valid:", table.validate())
