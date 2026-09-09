import os
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
import numpy as np
from PIL import Image

from src.core.layer import LayerData, LayerCollection
from src.importer.semantic_classifier import SemanticClassifier, SemanticCategory

try:
    import psd_tools
    from psd_tools import PSDImage
    HAS_PSD_TOOLS = True
except ImportError:
    HAS_PSD_TOOLS = False
    PSDImage = None


class PSDImporter:
    """
    Ingests Adobe Photoshop PSD/PSB files into structured LayerData objects
    and LayerCollection manifests with bilingual semantic classification.
    """

    @staticmethod
    def is_available() -> bool:
        """Returns True if psd-tools is installed and usable."""
        return HAS_PSD_TOOLS

    @classmethod
    def load_psd(cls, filepath: str, include_hidden: bool = False) -> List[LayerData]:
        """
        Extracts layers from a PSD file into a List of LayerData objects.

        Args:
            filepath: Path to the .psd or .psb file.
            include_hidden: If True, hidden layers are also extracted; otherwise filtered.

        Returns:
            List[LayerData]: Extracted raster layers with canvas offsets and semantic metadata.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"PSD file not found: {filepath}")

        if not HAS_PSD_TOOLS:
            raise ImportError(
                f"Cannot load PSD file '{filepath}': 'psd-tools' package is not installed. "
                "Install it via 'pip install psd-tools' or use ImageImporter for PNG/directory inputs."
            )

        psd = PSDImage.open(filepath)
        canvas_w, canvas_h = psd.width, psd.height

        # Collect all drawable layers in depth-first traversal
        extracted_layers: List[LayerData] = []
        raw_layers = list(psd.descendants())
        total_layers = len(raw_layers)

        for idx, layer in enumerate(raw_layers):
            # Skip group folder nodes
            if layer.is_group():
                continue

            # Skip hidden layers if not requested
            if not include_hidden and not layer.is_visible():
                continue

            # Skip layers with zero dimensions
            if layer.width <= 0 or layer.height <= 0:
                continue

            # Rasterize layer to PIL Image
            try:
                if hasattr(layer, 'composite') and callable(layer.composite):
                    layer_pil = layer.composite()
                elif hasattr(layer, 'topil') and callable(layer.topil):
                    layer_pil = layer.topil()
                else:
                    layer_pil = None
            except Exception:
                # Fallback to topil if composite fails (e.g. unsupported filter)
                try:
                    layer_pil = layer.topil() if hasattr(layer, 'topil') else None
                except Exception:
                    layer_pil = None

            if layer_pil is None:
                continue

            layer_rgba = np.array(layer_pil.convert("RGBA"), dtype=np.uint8)

            # Skip completely transparent layers
            if not np.any(layer_rgba[:, :, 3] > 0):
                continue

            # Bounding box & canvas offset
            offset_x = int(getattr(layer, 'left', 0))
            offset_y = int(getattr(layer, 'top', 0))
            bbox = (offset_x, offset_y, offset_x + layer.width, offset_y + layer.height)

            # Group hierarchy tracking
            ancestors = []
            curr = getattr(layer, 'parent', None)
            while curr is not None and hasattr(curr, 'name') and curr.name and not getattr(curr, 'is_root', False):
                ancestors.append(curr.name)
                curr = getattr(curr, 'parent', None)
            parent_group = "/".join(reversed(ancestors)) if ancestors else None

            # Layer opacity & blend mode
            raw_opacity = getattr(layer, 'opacity', 255)
            opacity = float(raw_opacity) / 255.0 if raw_opacity is not None else 1.0
            raw_blend = getattr(layer, 'blend_mode', 'normal')
            blend_mode = str(raw_blend).lower().replace('blendmode.', '')

            # Semantic classification
            cat, depth_hint = SemanticClassifier.classify(
                name=layer.name,
                parent_group=parent_group,
                bbox=bbox,
                canvas_size=(canvas_w, canvas_h),
                stack_index=idx,
                total_layers=total_layers
            )

            unique_id = f"{parent_group}/{layer.name}_{idx}" if parent_group else f"{layer.name}_{idx}"

            layer_data = LayerData(
                name=layer.name,
                image=layer_rgba,
                offset_x=offset_x,
                offset_y=offset_y,
                z_depth_hint=depth_hint,
                category=cat,
                visible=bool(layer.is_visible()),
                opacity=opacity,
                blend_mode=blend_mode,
                layer_id=unique_id,
                parent_group=parent_group,
                metadata={
                    "psd_index": idx,
                    "canvas_width": canvas_w,
                    "canvas_height": canvas_h
                }
            )
            extracted_layers.append(layer_data)

        return extracted_layers

    @classmethod
    def load_psd_as_collection(cls, filepath: str, include_hidden: bool = False) -> LayerCollection:
        """
        Loads a PSD file and packages all extracted layers into a LayerCollection.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"PSD file not found: {filepath}")

        if not HAS_PSD_TOOLS:
            raise ImportError(
                f"Cannot load PSD file '{filepath}': 'psd-tools' package is not installed."
            )

        psd = PSDImage.open(filepath)
        canvas_size = (psd.width, psd.height)
        layers = cls.load_psd(filepath, include_hidden=include_hidden)
        return LayerCollection(canvas_size=canvas_size, layers=layers)
