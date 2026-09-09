"""
src/exporter/
Live2D Binary Exporter & Texture Packer Pipeline:
- texture_packer: MaxRects Power-of-Two 2D texture atlas packer with edge bleed anti-seaming & UV remapping.
- moc3_writer: Pure-Python Live2D Cubism 4.0 .moc3 binary builder with 64-byte alignment & keyform tensors.
- model3_writer: .model3.json manifest and .cdi3.json display info generators.
"""

from src.exporter.texture_packer import (
    TextureAtlasPacker,
    PackingResult,
    PackedLayer,
    LayerPlacement,
    PackingStats,
    PackingConfig,
    PackingHeuristic,
    SortOrder,
)
from src.exporter.moc3_writer import (
    Moc3Writer,
    Moc3Reader,
    validate_moc3_bytes,
    Moc3CanvasInfo,
    align_to_64,
    pad_buffer_to_64,
    encode_id_64,
    decode_id_64,
)
from src.exporter.model3_writer import Model3Writer

__all__ = [
    "TextureAtlasPacker",
    "PackingResult",
    "PackedLayer",
    "LayerPlacement",
    "PackingStats",
    "PackingConfig",
    "PackingHeuristic",
    "SortOrder",
    "Moc3Writer",
    "Moc3Reader",
    "validate_moc3_bytes",
    "Moc3CanvasInfo",
    "align_to_64",
    "pad_buffer_to_64",
    "encode_id_64",
    "decode_id_64",
    "Model3Writer",
]
