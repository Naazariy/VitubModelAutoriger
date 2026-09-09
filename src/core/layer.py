import base64
import io
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Any, List
import numpy as np
from PIL import Image

@dataclass
class LayerData:
    """
    Represents a single 2D layer extracted from PSD, PNG, or layer directory.
    """
    name: str                                  # Layer display name
    image: np.ndarray                          # RGBA uint8 array, shape (H, W, 4)
    offset_x: int = 0                          # X position on full canvas
    offset_y: int = 0                          # Y position on full canvas
    z_depth_hint: float = 0.0                  # Nominal depth hint in [-1.0, 1.0]
    category: str = "unknown"                  # Semantic category
    visible: bool = True                       # Visibility flag
    opacity: float = 1.0                       # Opacity multiplier in [0.0, 1.0]
    blend_mode: str = "normal"                 # Blend mode ('normal', 'multiply', 'screen', etc.)
    layer_id: str = ""                         # Unique ID string
    parent_group: Optional[str] = None         # Parent folder / group name
    mask: Optional[np.ndarray] = None          # Optional 1-channel clipping mask (H, W)
    clipped_to: Optional[str] = None           # ID of base layer if clipped
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.layer_id:
            self.layer_id = self.name
        if not isinstance(self.image, np.ndarray):
            self.image = np.array(self.image, dtype=np.uint8)
        if self.image.ndim != 3 or self.image.shape[2] != 4:
            raise ValueError(f"Layer '{self.name}' image must have shape (H, W, 4), got {self.image.shape}")
        if self.image.dtype != np.uint8:
            self.image = self.image.astype(np.uint8)
        self.opacity = float(max(0.0, min(1.0, self.opacity)))

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        """Returns (left, top, right, bottom) on full canvas."""
        return (self.offset_x, self.offset_y, self.offset_x + self.width, self.offset_y + self.height)

    @property
    def bounds(self) -> Tuple[int, int, int, int]:
        """Alias for bbox."""
        return self.bbox

    @property
    def alpha_mask(self) -> np.ndarray:
        """Returns 2D alpha channel (H, W) in uint8."""
        return self.image[:, :, 3]

    @property
    def alpha(self) -> np.ndarray:
        """Alias for alpha_mask."""
        return self.image[:, :, 3]

    @property
    def is_empty(self) -> bool:
        """Returns True if image is empty or has zero non-transparent pixels."""
        if self.image.size == 0:
            return True
        return not bool(np.any(self.image[:, :, 3] > 0))

    def crop_to_content(self, threshold: int = 1) -> 'LayerData':
        """
        Trims transparent padding around the layer content and updates offset_x / offset_y.
        """
        alpha = self.image[:, :, 3]
        non_zero = np.argwhere(alpha >= threshold)
        if len(non_zero) == 0:
            empty_img = np.zeros((1, 1, 4), dtype=np.uint8)
            empty_mask = np.zeros((1, 1), dtype=np.uint8) if self.mask is not None else None
            return LayerData(
                name=self.name,
                image=empty_img,
                offset_x=self.offset_x,
                offset_y=self.offset_y,
                z_depth_hint=self.z_depth_hint,
                category=self.category,
                visible=self.visible,
                opacity=self.opacity,
                blend_mode=self.blend_mode,
                layer_id=self.layer_id,
                parent_group=self.parent_group,
                mask=empty_mask,
                clipped_to=self.clipped_to,
                metadata=dict(self.metadata)
            )

        y_min, x_min = non_zero.min(axis=0)
        y_max, x_max = non_zero.max(axis=0) + 1

        cropped_img = self.image[y_min:y_max, x_min:x_max].copy()
        new_mask = self.mask[y_min:y_max, x_min:x_max].copy() if self.mask is not None else None

        return LayerData(
            name=self.name,
            image=cropped_img,
            offset_x=self.offset_x + int(x_min),
            offset_y=self.offset_y + int(y_min),
            z_depth_hint=self.z_depth_hint,
            category=self.category,
            visible=self.visible,
            opacity=self.opacity,
            blend_mode=self.blend_mode,
            layer_id=self.layer_id,
            parent_group=self.parent_group,
            mask=new_mask,
            clipped_to=self.clipped_to,
            metadata=dict(self.metadata)
        )

    def get_canvas_aligned_image(self, canvas_width: int, canvas_height: int) -> np.ndarray:
        """
        Renders this layer onto a full-sized (canvas_height, canvas_width, 4) canvas at (offset_x, offset_y).
        """
        canvas = np.zeros((canvas_height, canvas_width, 4), dtype=np.uint8)
        
        src_x1 = max(0, -self.offset_x)
        src_y1 = max(0, -self.offset_y)
        dst_x1 = max(0, self.offset_x)
        dst_y1 = max(0, self.offset_y)

        src_x2 = min(self.width, canvas_width - self.offset_x)
        src_y2 = min(self.height, canvas_height - self.offset_y)
        dst_x2 = dst_x1 + (src_x2 - src_x1)
        dst_y2 = dst_y1 + (src_y2 - src_y1)

        if src_x2 > src_x1 and src_y2 > src_y1:
            canvas[dst_y1:dst_y2, dst_x1:dst_x2] = self.image[src_y1:src_y2, src_x1:src_x2]

        return canvas

    def to_dict(self) -> Dict[str, Any]:
        """Serializes LayerData metadata to dictionary."""
        return {
            "name": self.name,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "width": self.width,
            "height": self.height,
            "z_depth_hint": self.z_depth_hint,
            "category": self.category,
            "visible": self.visible,
            "opacity": self.opacity,
            "blend_mode": self.blend_mode,
            "layer_id": self.layer_id,
            "parent_group": self.parent_group,
            "clipped_to": self.clipped_to,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], image: Optional[np.ndarray] = None) -> 'LayerData':
        """Deserializes LayerData from dictionary."""
        img = image if image is not None else np.zeros((data.get("height", 1), data.get("width", 1), 4), dtype=np.uint8)
        return cls(
            name=data["name"],
            image=img,
            offset_x=data.get("offset_x", 0),
            offset_y=data.get("offset_y", 0),
            z_depth_hint=data.get("z_depth_hint", 0.0),
            category=data.get("category", "unknown"),
            visible=data.get("visible", True),
            opacity=data.get("opacity", 1.0),
            blend_mode=data.get("blend_mode", "normal"),
            layer_id=data.get("layer_id", ""),
            parent_group=data.get("parent_group", None),
            clipped_to=data.get("clipped_to", None),
            metadata=data.get("metadata", {})
        )


class LayerCollection:
    """
    Manages a collection of LayerData objects representing a multi-layer 2D character model.
    """
    def __init__(self, canvas_size: Tuple[int, int] = (2048, 2048), layers: Optional[List[LayerData]] = None):
        self.canvas_width, self.canvas_height = canvas_size
        self.layers: List[LayerData] = list(layers) if layers is not None else []

    def add_layer(self, layer: LayerData) -> None:
        self.layers.append(layer)

    def get_layer(self, layer_id: str) -> Optional[LayerData]:
        for layer in self.layers:
            if layer.layer_id == layer_id or layer.name == layer_id:
                return layer
        return None

    def get_by_category(self, category: str) -> List[LayerData]:
        return [l for l in self.layers if l.category == category]

    def sort_by_z_depth(self, reverse: bool = False) -> List[LayerData]:
        """Sorts layers back-to-front (default) or front-to-back."""
        return sorted(self.layers, key=lambda l: l.z_depth_hint, reverse=reverse)

    def get_total_bounds(self) -> Tuple[int, int, int, int]:
        """Returns enclosing bounding box (min_x, min_y, max_x, max_y) across all layers."""
        if not self.layers:
            return (0, 0, 0, 0)
        min_x = min(l.offset_x for l in self.layers)
        min_y = min(l.offset_y for l in self.layers)
        max_x = max(l.offset_x + l.width for l in self.layers)
        max_y = max(l.offset_y + l.height for l in self.layers)
        return (min_x, min_y, max_x, max_y)

    def composite(self) -> np.ndarray:
        """
        Composites visible layers onto a single RGBA canvas using back-to-front alpha blending.
        """
        canvas = np.zeros((self.canvas_height, self.canvas_width, 4), dtype=np.float32)
        sorted_layers = self.sort_by_z_depth(reverse=False)

        for layer in sorted_layers:
            if not layer.visible or layer.opacity <= 0.0 or layer.is_empty:
                continue

            layer_canvas = layer.get_canvas_aligned_image(self.canvas_width, self.canvas_height).astype(np.float32)
            src_rgb = layer_canvas[:, :, :3]
            src_a = (layer_canvas[:, :, 3:4] / 255.0) * layer.opacity

            dst_rgb = canvas[:, :, :3]
            dst_a = canvas[:, :, 3:4] / 255.0

            out_a = src_a + dst_a * (1.0 - src_a)
            safe_out_a = np.where(out_a > 1e-6, out_a, 1.0)
            out_rgb = (src_rgb * src_a + dst_rgb * dst_a * (1.0 - src_a)) / safe_out_a

            canvas[:, :, :3] = np.where(out_a > 1e-6, out_rgb, 0.0)
            canvas[:, :, 3:4] = out_a * 255.0

        return np.clip(canvas, 0, 255).astype(np.uint8)

    def __len__(self) -> int:
        return len(self.layers)

    def __iter__(self):
        return iter(self.layers)

    def __getitem__(self, idx: int) -> LayerData:
        return self.layers[idx]
