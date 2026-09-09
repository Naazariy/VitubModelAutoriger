import struct
import numpy as np
from src.core.keyform import KeyformTable, ParameterBinding, DrawableKeyforms

# Let's inspect hiyori section offsets table
with open("output/hiyori_vts/hiyori.moc3", "rb") as f:
    h_data = f.read()

h_offsets = list(struct.unpack_from("<160I", h_data, 64))
h_counts = list(struct.unpack_from("<23I", h_data, h_offsets[0]))

print(f"Hiyori header magic: {h_data[:4]}, version: {h_data[4]}, endian: {h_data[5]}")
print(f"Hiyori section 0 offset: 0x{h_offsets[0]:04X}")
print(f"Hiyori section 1 offset: 0x{h_offsets[1]:04X}")

# Let's check non-zero section slots in Hiyori:
h_non_zero_slots = [i for i, off in enumerate(h_offsets) if off != 0]
print(f"Hiyori non-zero slots ({len(h_non_zero_slots)} slots):")
print(h_non_zero_slots)
