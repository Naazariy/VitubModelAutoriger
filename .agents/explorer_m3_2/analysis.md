# Technical Analysis & Architecture Design: Live2D Texture Packer (`src/exporter/texture_packer.py`)

## 1. Executive Summary & Architectural Overview

The **Texture Atlas Packer** (`src/exporter/texture_packer.py`) is a critical pipeline component in Milestone 3 of the automated VTuber key deformation system. It sits between the 2D layer ingestion / 3D keyform deformation stages and the binary Live2D `.moc3` / `.model3.json` exporter.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Ingestion & Meshing Stage                       │
│  - LayerData (RGBA, canvas offsets, semantic categories, z_depth_hint) │
│  - Mesh (Vertices, CCW Triangles, Local Layer UVs [0, 1])              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 Texture Atlas Packer (src/exporter/)                   │
│                                                                        │
│  1. Pre-Processing & Anti-Bleed:                                       │
│     - Alpha crop / bounding box tightening                             │
│     - Edge color bleeding / Voronoi dilation (seam prevention)         │
│     - Configurable inter-texture border padding                        │
│                                                                        │
│  2. Dynamic Power-of-Two (POT) Atlas Sizing:                           │
│     - Area lower-bound estimation ($A_{padded} / \eta_{target}$)       │
│     - POT resolution selection: 512, 1024, 2048, 4096, 8192            │
│     - Multi-page atlas partitioning for high-complexity models         │
│                                                                        │
│  3. MaxRects 2D Bin Packing Engine:                                    │
│     - Heuristic sorting: MaxSide / Area / Height descending            │
│     - Free rectangle splitting & non-maximal pruning                   │
│     - Placement rule: Best Short Side Fit (BSSF) / Best Area Fit (BAF) │
│                                                                        │
│  4. UV Coordinate Transformation:                                      │
│     - Layer Local UV $[0, 1] \to$ Global Atlas UV $[0, 1]$             │
│     - Live2D Top-Left origin compliance (with optional OpenGL V-flip)  │
│     - Update ArtMesh `DrawableKeyforms` and `Mesh.uvs`                 │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   Live2D Exporter & Structural Validator               │
│  - .moc3 binary writer (Drawables with texture_index and uvs_atlas)    │
│  - .model3.json manifest (FileReferences.Textures)                     │
│  - textures/texture_00.png, texture_01.png ...                         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. MaxRects 2D Bin Packing Algorithm

### 2.1 Theoretical Foundations
The 2D Bin Packing Problem (2D-BPP) is NP-hard. Among geometric strip and bin packing algorithms (Shelf, Guillotine, Skyline, MaxRects), the **Maximal Rectangles (MaxRects)** algorithm developed by Jukka Jylänki is the industry standard for texture atlas generation due to:
1. **Zero arbitrary partitioning loss**: Unlike Guillotine packing, MaxRects maintains all *maximal* free rectangular areas, allowing future rects to span across potential guillotine cuts.
2. **High Packing Efficiency**: Consistently achieves **88% to 96%** surface utilization.
3. **Deterministic & Fast**: Sub-millisecond packing for standard 10–100 Live2D layers.

### 2.2 Free Rectangle Maintenance & Splitting Mechanics
At any step, the packer maintains a collection of maximal free rectangles $\mathcal{F} = \{R_f = (x_f, y_f, w_f, h_f)\}$.

When an item $R_i = (x_i, y_i, w_i, h_i)$ is placed:
1. For every free rectangle $R_f \in \mathcal{F}$ that intersects $R_i$:
   - The overlapping rectangle $R_f$ is split into up to 4 new candidate sub-rectangles:
     - **Top**: $(x_f, y_f, w_f, y_i - y_f)$ if $y_i > y_f$ and $y_i < y_f + h_f$
     - **Bottom**: $(x_f, y_i + h_i, w_f, y_f + h_f - (y_i + h_i))$ if $y_i + h_i < y_f + h_f$
     - **Left**: $(x_f, y_f, x_i - x_f, h_f)$ if $x_i > x_f$ and $x_i < x_f + w_f$
     - **Right**: $(x_i + w_i, y_f, x_f + w_f - (x_i + w_i), h_f)$ if $x_i + w_i < x_f + w_f$
   - Remove the original intersecting $R_f$ from $\mathcal{F}$ and add the valid generated sub-rectangles ($w > 0, h > 0$).
2. **Non-Maximal Pruning**:
   - For every pair of free rectangles $(R_a, R_b)$ in $\mathcal{F}$:
     If $R_a$ is completely contained within $R_b$ ($x_b \le x_a, y_b \le y_a, x_a + w_a \le x_b + w_b, y_a + h_a \le y_b + h_b$), remove $R_a$.
   - This prevents combinatorial explosion of redundant free sub-rectangles.

```
Free Rectangle Split Diagram:
┌───────────────────────────────────────────────┐
│                   Top Sub-Rect                │
├──────────────┬─────────────────┬──────────────┤
│              │                 │              │
│  Left        │   Placed Item   │  Right       │
│  Sub-Rect    │   (R_i)         │  Sub-Rect    │
│              │                 │              │
├──────────────┴─────────────────┴──────────────┤
│                 Bottom Sub-Rect               │
└───────────────────────────────────────────────┘
```

### 2.3 Heuristic Scoring Rules
For a candidate free rectangle $R_f$ and item $(w, h)$, let:
$$\Delta w = w_f - w, \quad \Delta h = h_f - h$$

The packer supports multiple heuristic rules:
1. **Best Short Side Fit (BSSF)** (Default & Recommended):
   $$\text{Score}_1 = \min(\Delta w, \Delta h), \quad \text{Score}_2 = \max(\Delta w, \Delta h)$$
   *Minimizes the leftover gap along the tighter dimension, packing rects snugly into corners.*
2. **Best Long Side Fit (BLSF)**:
   $$\text{Score}_1 = \max(\Delta w, \Delta h), \quad \text{Score}_2 = \min(\Delta w, \Delta h)$$
3. **Best Area Fit (BAF)**:
   $$\text{Score}_1 = (w_f \cdot h_f) - (w \cdot h), \quad \text{Score}_2 = \min(\Delta w, \Delta h)$$
   *Picks the smallest free rectangle that can accommodate the item.*
4. **Bottom-Left (BL)**:
   $$\text{Score}_1 = y_f + h, \quad \text{Score}_2 = x_f$$
   *Packs items strictly towards the top-left / bottom-left corner.*
5. **Contact Point Rule (CP)**:
   $$\text{Score}_1 = -(\text{boundary contact length with bin borders and placed neighbors})$$

### 2.4 Sorting Pre-Pass
Packing efficiency is heavily improved by sorting items prior to placement. The packer supports:
- `SORT_MAX_SIDE_DESC` (Default): Sort by $\max(w, h)$ descending, breaking ties by area.
- `SORT_AREA_DESC`: Sort by $w \cdot h$ descending.
- `SORT_HEIGHT_DESC`: Sort by $h$ descending.
- `SORT_WIDTH_DESC`: Sort by $w$ descending.

---

## 3. Power-of-Two (POT) Atlas Sizing & Multi-Atlas Allocation

### 3.1 Live2D and GPU POT Dimensions
Modern GPU samplers and Live2D Cubism runtime engines require textures with Power-of-Two (POT) dimensions:
$$S \in \{512, 1024, 2048, 4096, 8192\}$$

Why POT is mandatory:
1. **Mipmapping & Filtering**: Downsampling textures across mip levels requires clean halving ($4096 \to 2048 \to 1024 \dots \to 1$).
2. **Memory Alignment**: Hardware texture units align texel cache blocks along 64-byte / POT strides.
3. **Cubism Spec Compliance**: Live2D Cubism Viewer and VTube Studio strictly validate POT dimensions.

### 3.2 Dynamic Sizing Strategy
Instead of blindly allocating a massive $4096 \times 4096$ texture for a model with 3 small layers, the packer dynamically determines the optimal minimal POT size:

1. **Calculate Theoretical Padded Area**:
   $$A_{padded} = \sum_{i=1}^N (w_i + 2 \cdot \text{padding}) \cdot (h_i + 2 \cdot \text{padding})$$
   $$W_{max} = \max_i (w_i + 2 \cdot \text{padding}), \quad H_{max} = \max_i (h_i + 2 \cdot \text{padding})$$

2. **Estimate Initial Minimal Size**:
   Targeting an expected packing density $\eta \approx 0.70$:
   $$S_{init} = \max\left(W_{max}, H_{max}, \sqrt{A_{padded} / 0.70}\right)$$
   $$S_{pot} = \text{NextPOT}(S_{init}) = 2^{\lceil \log_2(S_{init}) \rceil}$$
   Clamped to $[\text{min\_atlas\_size}, \text{max\_atlas\_size}]$ (e.g. $[512, 4096]$).

3. **Trial Packing & Escalation Loop**:
   ```
   S = S_pot
   while S <= max_atlas_size:
       success, placements = try_pack(layers, width=S, height=S, padding=padding)
       if success:
           return S, placements (Optimal minimal POT atlas found!)
       S = S * 2
   ```

4. **Multi-Atlas Partitioning (Overflow Handling)**:
   If all layers cannot fit within a single page of `max_atlas_size`:
   - Page 0 is packed with as many sorted layers as fit in `max_atlas_size x max_atlas_size`.
   - Remaining unplaced layers are packed onto Page 1, Page 2, etc.
   - Each placed layer is assigned `texture_index` corresponding to its atlas page ($0, 1, 2\dots$).
   - Output texture files are saved as:
     - `textures/texture_00.png` (Page 0)
     - `textures/texture_01.png` (Page 1)

---

## 4. Border Padding & Edge Bleeding / Color Dilation (Anti-Seam Engine)

### 4.1 Root Cause of Bilinear Seams and Color Bleeding
In GPU rendering (Live2D Cubism Core, OpenGL, DirectX, Metal), bilinear texture filtering calculates pixel color as a weighted average of the $2 \times 2$ nearest texels:
$$C(u, v) = (1-s)(1-t)C_{00} + s(1-t)C_{10} + (1-s)tC_{01} + stC_{11}$$

```
Seam Hazard Scenario:
┌──────────────┬──────────────┐
│  Opaque Texel│  Transparent │
│  (255,200,180│  Black Texel │
│   Alpha=255) │  (0,0,0, a=0)│
└──────────────┴──────────────┘
       ▲
       │ Boundary Sampling Tap (u = 0.99)
       └─ Result: (128, 100, 90, a=128) -> Dark Gray/Black Fringe Seam!
```

If the border outside an ArtMesh contains `(0, 0, 0, 0)`, the interpolation pulls black color into the visible perimeter, creating an ugly dark outline. Furthermore, if two layers are packed with 0 padding, color from Layer B bleeds directly into Layer A!

### 4.2 Two-Stage Anti-Bleed Solution

#### Stage 1: Color Bleed / Voronoi Dilation (Per Layer)
Before packing, each layer's RGB channels are dilated outward into surrounding transparent texels:
1. Identify opaque pixels where $\alpha(x, y) > 0$.
2. For all transparent pixels $(x, y)$ where $\alpha(x, y) = 0$ within a radius $R_{bleed}$ (default: $2$ to $4$ pixels) of the opaque boundary:
   - Find the closest opaque pixel $(x_0, y_0)$.
   - Copy $(R, G, B)$ from $(x_0, y_0)$ to $(x, y)$.
   - Keep $\alpha(x, y) = 0$.
3. **Implementation Strategy**:
   - **Accelerated path (SciPy / OpenCV)**:
     Use `scipy.ndimage.distance_transform_edt(alpha == 0, return_indices=True)` or `cv2.distanceTransformWithLabels`.
     This evaluates the exact Euclidean Voronoi nearest-neighbor map in $O(H \cdot W)$ time.
   - **Pure-Python fallback**:
     Iterative morphological 8-neighbor dilation for $K$ steps.

```
Voronoi Dilation Effect:
Source RGBA:               After Voronoi RGB Dilation (Alpha kept 0):
┌──────┬──────┬──────┐    ┌──────┬──────┬──────┐
│ Skin │ Skin │ Trans│    │ Skin │ Skin │ Skin │ (Alpha=0, RGB=Skin)
│(255) │(255) │ (0)  │ ─► │(255) │(255) │ (0)  │
└──────┴──────┴──────┘    └──────┴──────┴──────┘
                           Bilinear tap now samples (Skin * a), eliminating black seams!
```

#### Stage 2: Atlas Placement Padding
Leave a protective gap of `padding` pixels (default: $4$ pixels) between adjacent layer bounding boxes on the atlas. Combined with Stage 1's bleed radius, this guarantees:
- Mipmap levels 0, 1, 2 remain completely isolated from neighboring textures.
- Zero color cross-talk across drawables.

---

## 5. UV Coordinate Transformation & Coordinate Conventions

### 5.1 Mathematical Transformation
Let:
- Layer $L_i$ have image dimensions $(W_{layer}, H_{layer})$.
- Layer $L_i$ be placed on atlas page $P_i$ at integer pixel coordinates $(X_{placed}, Y_{placed})$.
- Atlas page $P_i$ have dimensions $(W_{atlas}, H_{atlas})$.
- A vertex $v$ on ArtMesh $i$ have local normalized coordinates $(u_{local}, v_{local}) \in [0.0, 1.0]$.

The global atlas UV coordinates $(u_{atlas}, v_{atlas})$ are computed as:
$$u_{atlas} = \frac{X_{placed} + u_{local} \cdot W_{layer}}{W_{atlas}}$$
$$v_{atlas} = \frac{Y_{placed} + v_{local} \cdot H_{layer}}{H_{atlas}}$$

Or in terms of the layer's normalized atlas bounding box $[u_{min}, v_{min}, u_{max}, v_{max}]$:
$$u_{min} = \frac{X_{placed}}{W_{atlas}}, \quad u_{max} = \frac{X_{placed} + W_{layer}}{W_{atlas}}$$
$$v_{min} = \frac{Y_{placed}}{H_{atlas}}, \quad v_{max} = \frac{Y_{placed} + H_{layer}}{H_{atlas}}$$
$$u_{atlas} = u_{min} + u_{local} \cdot (u_{max} - u_{min})$$
$$v_{atlas} = v_{min} + v_{local} \cdot (v_{max} - v_{min})$$

### 5.2 Coordinate System Conventions & V-Axis Orientation
- **Live2D Cubism Standard**:
  - UV Origin: **Top-Left** $(0.0, 0.0)$.
  - $+U$ points Right ($0 \to 1$).
  - $+V$ points Down ($0 \to 1$).
  - This directly corresponds to standard 2D image raster space and DirectX/Vulkan/Metal/WebGL conventions.
- **OpenGL Standard**:
  - UV Origin: **Bottom-Left** $(0.0, 0.0)$.
  - $+V$ points Up.
  - Transformation if OpenGL format is requested: $v_{gl} = 1.0 - v_{atlas}$.
- **Design Decision**:
  - Default to Live2D standard Top-Left ($V=0$ at top).
  - Include `flip_v: bool = False` configuration flag for OpenGL-specific consumers.

### 5.3 Numerical Clamping & Sub-Pixel Safety
To protect against floating point rounding errors (e.g. $1.00000005$):
$$u_{atlas} = \text{clip}(u_{atlas}, 0.0, 1.0)$$
$$v_{atlas} = \text{clip}(v_{atlas}, 0.0, 1.0)$$

---

## 6. Class Architecture & Interface Specification

### 6.1 Data Structures (`src/exporter/texture_packer.py`)

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Dict, Optional, Any
import numpy as np
from PIL import Image

from src.core.layer import LayerData
from src.core.mesh import Mesh
from src.core.keyform import DrawableKeyforms, KeyformTable

class PackingHeuristic(Enum):
    BSSF = "BestShortSideFit"
    BLSF = "BestLongSideFit"
    BAF = "BestAreaFit"
    BL = "BottomLeft"
    CP = "ContactPoint"

class SortOrder(Enum):
    MAX_SIDE_DESC = "max_side_desc"
    AREA_DESC = "area_desc"
    HEIGHT_DESC = "height_desc"
    WIDTH_DESC = "width_desc"
    NONE = "none"

@dataclass
class PackingConfig:
    """Configuration options for MaxRects texture packing."""
    max_atlas_size: int = 4096
    min_atlas_size: int = 512
    padding: int = 4
    bleed_radius: int = 2
    heuristic: PackingHeuristic = PackingHeuristic.BSSF
    sort_order: SortOrder = SortOrder.MAX_SIDE_DESC
    allow_rotation: bool = False
    power_of_two: bool = True
    square: bool = True
    flip_v: bool = False
    crop_transparent: bool = False

@dataclass
class LayerPlacement:
    """Represents the placement result of a single layer."""
    layer_id: str
    page_index: int
    x: int
    y: int
    width: int
    height: int
    uv_rect: Tuple[float, float, float, float]  # (u_min, v_min, u_max, v_max) in [0, 1]
    rotated: bool = False

@dataclass
class PackingStats:
    """Statistics on packing efficiency and atlas layout."""
    total_layers: int
    num_pages: int
    page_dimensions: List[Tuple[int, int]]
    total_layer_area: int
    total_atlas_area: int
    efficiency: float  # (total_layer_area / total_atlas_area)

@dataclass
class PackingResult:
    """Complete result returned by TextureAtlasPacker."""
    pages: List[np.ndarray]                          # List of RGBA arrays (H, W, 4) uint8
    placements: Dict[str, LayerPlacement]            # Layer ID -> Placement metadata
    uv_rects: Dict[str, Tuple[float, float, float, float]] # Layer ID -> (u_min, v_min, u_max, v_max)
    remapped_meshes: Dict[str, Mesh] = field(default_factory=dict)
    drawables: List[DrawableKeyforms] = field(default_factory=list)
    stats: Optional[PackingStats] = None

    @property
    def primary_atlas(self) -> np.ndarray:
        """Convenience property for single-page atlas."""
        return self.pages[0] if self.pages else np.zeros((512, 512, 4), dtype=np.uint8)
```

### 6.2 Primary Class API (`TextureAtlasPacker`)

```python
class TextureAtlasPacker:
    """
    Production-grade MaxRects 2D Texture Atlas Packer for Live2D Cubism Models.
    """

    @classmethod
    def pack(
        cls,
        layers: List[LayerData],
        meshes: Optional[Dict[str, Mesh]] = None,
        config: Optional[PackingConfig] = None
    ) -> PackingResult:
        """
        Main entrypoint: Packs layers into power-of-two texture atlases,
        applies edge color bleeding, and remaps mesh UV coordinates to global atlas space.
        """
        ...

    @classmethod
    def pack_layers(
        cls,
        layers: List[LayerData],
        max_atlas_size: int = 4096,
        padding: int = 4,
        bleed_radius: int = 2
    ) -> Tuple[np.ndarray, Dict[str, Tuple[float, float, float, float]]]:
        """
        High-level backwards-compatible API matching existing E2E fixtures:
        Returns (atlas_img, uv_rects).
        """
        ...

    @classmethod
    def remap_mesh_uvs(
        cls,
        mesh: Mesh,
        uv_rect: Tuple[float, float, float, float],
        flip_v: bool = False
    ) -> Mesh:
        """
        Remaps a Mesh's local [0, 1] UV coordinates to global atlas UV space.
        """
        ...

    @classmethod
    def apply_color_bleed(
        cls,
        rgba_image: np.ndarray,
        radius: int = 2
    ) -> np.ndarray:
        """
        Dilates RGB colors of opaque pixels into transparent border pixels (alpha=0),
        preventing dark seams during bilinear GPU texture filtering.
        """
        ...
```

---

## 7. Concrete Code Blueprint for `src/exporter/texture_packer.py`

Below is the design implementation structure for the packer:

```python
"""
src/exporter/texture_packer.py
Production-Grade MaxRects Power-of-Two 2D Texture Atlas Packer for Live2D Cubism.
"""

from typing import List, Tuple, Dict, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum
import math
import numpy as np

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import scipy.ndimage
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from src.core.layer import LayerData
from src.core.mesh import Mesh
from src.core.keyform import DrawableKeyforms


class PackingHeuristic(Enum):
    BSSF = "BestShortSideFit"
    BLSF = "BestLongSideFit"
    BAF = "BestAreaFit"
    BL = "BottomLeft"
    CP = "ContactPoint"


class SortOrder(Enum):
    MAX_SIDE_DESC = "max_side_desc"
    AREA_DESC = "area_desc"
    HEIGHT_DESC = "height_desc"
    WIDTH_DESC = "width_desc"
    NONE = "none"


@dataclass
class PackingConfig:
    max_atlas_size: int = 4096
    min_atlas_size: int = 512
    padding: int = 4
    bleed_radius: int = 2
    heuristic: PackingHeuristic = PackingHeuristic.BSSF
    sort_order: SortOrder = SortOrder.MAX_SIDE_DESC
    allow_rotation: bool = False
    power_of_two: bool = True
    square: bool = True
    flip_v: bool = False
    crop_transparent: bool = False


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def contains(self, other: 'Rect') -> bool:
        return (self.x <= other.x and self.y <= other.y and
                self.right >= other.right and self.bottom >= other.bottom)

    def intersects(self, other: 'Rect') -> bool:
        return not (self.right <= other.x or other.right <= self.x or
                    self.bottom <= other.y or other.bottom <= self.y)


@dataclass
class LayerPlacement:
    layer_id: str
    page_index: int
    x: int
    y: int
    width: int
    height: int
    uv_rect: Tuple[float, float, float, float]
    rotated: bool = False


@dataclass
class PackingStats:
    total_layers: int
    num_pages: int
    page_dimensions: List[Tuple[int, int]]
    total_layer_area: int
    total_atlas_area: int
    efficiency: float


@dataclass
class PackingResult:
    pages: List[np.ndarray]
    placements: Dict[str, LayerPlacement]
    uv_rects: Dict[str, Tuple[float, float, float, float]]
    remapped_meshes: Dict[str, Mesh] = field(default_factory=dict)
    drawables: List[DrawableKeyforms] = field(default_factory=list)
    stats: Optional[PackingStats] = None

    @property
    def primary_atlas(self) -> np.ndarray:
        return self.pages[0] if self.pages else np.zeros((512, 512, 4), dtype=np.uint8)


class MaxRectsBin:
    """Maintains free rectangles for a single atlas page."""
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.free_rectangles: List[Rect] = [Rect(0, 0, width, height)]
        self.used_rectangles: List[Rect] = []

    def score_rect(self, width: int, height: int, free_rect: Rect, method: PackingHeuristic) -> Tuple[int, int]:
        if free_rect.w < width or free_rect.h < height:
            return (float('inf'), float('inf'))

        rem_w = free_rect.w - width
        rem_h = free_rect.h - height

        if method == PackingHeuristic.BSSF:
            score1 = min(rem_w, rem_h)
            score2 = max(rem_w, rem_h)
        elif method == PackingHeuristic.BLSF:
            score1 = max(rem_w, rem_h)
            score2 = min(rem_w, rem_h)
        elif method == PackingHeuristic.BAF:
            score1 = free_rect.w * free_rect.h - width * height
            score2 = min(rem_w, rem_h)
        elif method == PackingHeuristic.BL:
            score1 = free_rect.y + height
            score2 = free_rect.x
        else:
            score1 = min(rem_w, rem_h)
            score2 = max(rem_w, rem_h)

        return (score1, score2)

    def find_position_for_new_node(
        self,
        width: int,
        height: int,
        method: PackingHeuristic,
        allow_rotation: bool = False
    ) -> Tuple[Optional[Rect], bool]:
        best_rect = None
        best_score1 = float('inf')
        best_score2 = float('inf')
        best_rotated = False

        for free_rect in self.free_rectangles:
            # Unrotated check
            s1, s2 = self.score_rect(width, height, free_rect, method)
            if s1 < best_score1 or (s1 == best_score1 and s2 < best_score2):
                best_score1 = s1
                best_score2 = s2
                best_rect = Rect(free_rect.x, free_rect.y, width, height)
                best_rotated = False

            # Rotated check
            if allow_rotation and width != height:
                s1_rot, s2_rot = self.score_rect(height, width, free_rect, method)
                if s1_rot < best_score1 or (s1_rot == best_score1 and s2_rot < best_score2):
                    best_score1 = s1_rot
                    best_score2 = s2_rot
                    best_rect = Rect(free_rect.x, free_rect.y, height, width)
                    best_rotated = True

        return best_rect, best_rotated

    def place_rect(self, node: Rect) -> None:
        num_free = len(self.free_rectangles)
        i = 0
        while i < num_free:
            if self._split_free_node(self.free_rectangles[i], node):
                self.free_rectangles.pop(i)
                num_free -= 1
            else:
                i += 1

        self._prune_free_list()
        self.used_rectangles.append(node)

    def _split_free_node(self, free_node: Rect, used_node: Rect) -> bool:
        if not free_node.intersects(used_node):
            return False

        # New top sub-rect
        if used_node.y > free_node.y and used_node.y < free_node.bottom:
            self.free_rectangles.append(Rect(free_node.x, free_node.y, free_node.w, used_node.y - free_node.y))

        # New bottom sub-rect
        if used_node.bottom < free_node.bottom:
            self.free_rectangles.append(Rect(free_node.x, used_node.bottom, free_node.w, free_node.bottom - used_node.bottom))

        # New left sub-rect
        if used_node.x > free_node.x and used_node.x < free_node.right:
            self.free_rectangles.append(Rect(free_node.x, free_node.y, used_node.x - free_node.x, free_node.h))

        # New right sub-rect
        if used_node.right < free_node.right:
            self.free_rectangles.append(Rect(used_node.right, free_node.y, free_node.right - used_node.right, free_node.h))

        return True

    def _prune_free_list(self) -> None:
        i = 0
        while i < len(self.free_rectangles):
            j = i + 1
            while j < len(self.free_rectangles):
                if self.free_rectangles[j].contains(self.free_rectangles[i]):
                    self.free_rectangles.pop(i)
                    i -= 1
                    break
                if self.free_rectangles[i].contains(self.free_rectangles[j]):
                    self.free_rectangles.pop(j)
                else:
                    j += 1
            i += 1


class TextureAtlasPacker:
    """Production MaxRects texture atlas packer."""

    @staticmethod
    def next_power_of_two(val: int) -> int:
        if val <= 0:
            return 1
        return 1 << (val - 1).bit_length()

    @classmethod
    def apply_color_bleed(cls, rgba: np.ndarray, radius: int = 2) -> np.ndarray:
        """Dilates RGB values of opaque pixels into transparent pixels (alpha=0)."""
        if radius <= 0 or rgba.size == 0:
            return rgba.copy()

        h, w = rgba.shape[:2]
        result = rgba.copy()
        alpha = result[:, :, 3]
        opaque_mask = alpha > 0

        if np.all(opaque_mask) or not np.any(opaque_mask):
            return result

        if HAS_SCIPY:
            # Vectorized Euclidean Distance Transform Voronoi mapping
            indices = scipy.ndimage.distance_transform_edt(
                ~opaque_mask, return_distances=False, return_indices=True
            )
            # Clip dilation to radius
            dist = scipy.ndimage.distance_transform_edt(~opaque_mask)
            bleed_mask = (~opaque_mask) & (dist <= radius)

            nearest_y = indices[0][bleed_mask]
            nearest_x = indices[1][bleed_mask]
            result[bleed_mask, :3] = rgba[nearest_y, nearest_x, :3]
            return result

        # Pure-Python morphological dilation fallback
        for _ in range(radius):
            current_opaque = result[:, :, 3] > 0
            new_rgb = result[:, :, :3].copy()
            new_marked = np.zeros((h, w), dtype=bool)

            for dy, dx in [(-1,0), (1,0), (0,-1), (0,1), (-1,-1), (-1,1), (1,-1), (1,1)]:
                sy = np.clip(np.arange(h) + dy, 0, h - 1)
                sx = np.clip(np.arange(w) + dx, 0, w - 1)
                neighbor_opaque = current_opaque[np.ix_(sy, sx)]
                candidate_mask = (~current_opaque) & neighbor_opaque & (~new_marked)
                if np.any(candidate_mask):
                    new_rgb[candidate_mask] = result[sy, :][:, sx][:3][candidate_mask]
                    new_marked[candidate_mask] = True

            result[:, :, :3] = new_rgb

        return result

    @classmethod
    def remap_mesh_uvs(
        cls,
        mesh: Mesh,
        uv_rect: Tuple[float, float, float, float],
        flip_v: bool = False
    ) -> Mesh:
        """Transforms mesh local UVs into global atlas UV space."""
        u_min, v_min, u_max, v_max = uv_rect
        span_u = u_max - u_min
        span_v = v_max - v_min

        remapped_mesh = mesh.copy()
        if len(mesh.uvs) > 0:
            local_u = np.clip(mesh.uvs[:, 0], 0.0, 1.0)
            local_v = np.clip(mesh.uvs[:, 1], 0.0, 1.0)

            global_u = u_min + local_u * span_u
            global_v = v_min + local_v * span_v

            if flip_v:
                global_v = 1.0 - global_v

            remapped_mesh.uvs = np.column_stack([
                np.clip(global_u, 0.0, 1.0),
                np.clip(global_v, 0.0, 1.0)
            ]).astype(np.float32)

        return remapped_mesh

    @classmethod
    def pack(
        cls,
        layers: List[LayerData],
        meshes: Optional[Dict[str, Mesh]] = None,
        config: Optional[PackingConfig] = None
    ) -> PackingResult:
        cfg = config if config is not None else PackingConfig()
        pad = max(0, cfg.padding)

        valid_layers = [l for l in layers if l.image.shape[0] > 0 and l.image.shape[1] > 0]
        if not valid_layers:
            empty_atlas = np.zeros((cfg.min_atlas_size, cfg.min_atlas_size, 4), dtype=np.uint8)
            return PackingResult(
                pages=[empty_atlas],
                placements={},
                uv_rects={},
                remapped_meshes={},
                drawables=[],
                stats=PackingStats(0, 1, [(cfg.min_atlas_size, cfg.min_atlas_size)], 0, cfg.min_atlas_size**2, 0.0)
            )

        # Sort layers
        if cfg.sort_order == SortOrder.MAX_SIDE_DESC:
            sorted_layers = sorted(valid_layers, key=lambda l: max(l.image.shape[0], l.image.shape[1]), reverse=True)
        elif cfg.sort_order == SortOrder.AREA_DESC:
            sorted_layers = sorted(valid_layers, key=lambda l: l.image.shape[0] * l.image.shape[1], reverse=True)
        elif cfg.sort_order == SortOrder.HEIGHT_DESC:
            sorted_layers = sorted(valid_layers, key=lambda l: l.image.shape[0], reverse=True)
        else:
            sorted_layers = list(valid_layers)

        # Determine POT atlas dimension
        total_padded_area = sum((l.image.shape[1] + 2 * pad) * (l.image.shape[0] + 2 * pad) for l in sorted_layers)
        max_dim = max(max(l.image.shape[1] + 2 * pad, l.image.shape[0] + 2 * pad) for l in sorted_layers)
        
        target_size = max(cfg.min_atlas_size, max_dim, int(math.sqrt(total_padded_area / 0.70)))
        pot_size = min(cfg.max_atlas_size, max(cfg.min_atlas_size, cls.next_power_of_two(target_size)))

        # Sizing escalation loop
        pages_bins: List[MaxRectsBin] = []
        layer_page_placements: Dict[str, Tuple[int, Rect, bool, LayerData]] = {}

        cur_size = pot_size
        while cur_size <= cfg.max_atlas_size:
            bin_candidate = MaxRectsBin(cur_size, cur_size)
            fits = True
            trial_placements = {}
            for l in sorted_layers:
                lw, lh = l.image.shape[1] + 2 * pad, l.image.shape[0] + 2 * pad
                pos, rot = bin_candidate.find_position_for_new_node(lw, lh, cfg.heuristic, cfg.allow_rotation)
                if pos is None:
                    fits = False
                    break
                bin_candidate.place_rect(pos)
                trial_placements[l.layer_id] = (0, pos, rot, l)
            if fits:
                pages_bins = [bin_candidate]
                layer_page_placements = trial_placements
                break
            cur_size *= 2

        # Multi-page fallback if single page overflowed max_atlas_size
        if not pages_bins:
            remaining = list(sorted_layers)
            page_idx = 0
            while remaining:
                bin_page = MaxRectsBin(cfg.max_atlas_size, cfg.max_atlas_size)
                unplaced = []
                for l in remaining:
                    lw, lh = l.image.shape[1] + 2 * pad, l.image.shape[0] + 2 * pad
                    pos, rot = bin_page.find_position_for_new_node(lw, lh, cfg.heuristic, cfg.allow_rotation)
                    if pos is not None:
                        bin_page.place_rect(pos)
                        layer_page_placements[l.layer_id] = (page_idx, pos, rot, l)
                    else:
                        unplaced.append(l)
                pages_bins.append(bin_page)
                if len(unplaced) == len(remaining):
                    # Hard single layer exceeds max_atlas_size -> force place in dedicated page
                    l = unplaced.pop(0)
                    forced_size = max(cfg.max_atlas_size, cls.next_power_of_two(max(l.image.shape[1] + 2*pad, l.image.shape[0] + 2*pad)))
                    forced_bin = MaxRectsBin(forced_size, forced_size)
                    pos = Rect(0, 0, l.image.shape[1] + 2*pad, l.image.shape[0] + 2*pad)
                    forced_bin.place_rect(pos)
                    layer_page_placements[l.layer_id] = (len(pages_bins), pos, False, l)
                    pages_bins.append(forced_bin)
                remaining = unplaced
                page_idx += 1

        # Render atlas pages & calculate UVs
        pages_imgs: List[np.ndarray] = []
        for b in pages_bins:
            pages_imgs.append(np.zeros((b.height, b.width, 4), dtype=np.uint8))

        placements: Dict[str, LayerPlacement] = {}
        uv_rects: Dict[str, Tuple[float, float, float, float]] = {}

        for layer_id, (p_idx, rect, rot, layer) in layer_page_placements.items():
            atlas_img = pages_imgs[p_idx]
            aw, ah = atlas_img.shape[1], atlas_img.shape[0]

            # Apply color bleed dilation to layer image
            bled_img = cls.apply_color_bleed(layer.image, radius=cfg.bleed_radius)
            if rot:
                bled_img = np.rot90(bled_img, -1).copy()

            # Content placement (inset by padding)
            px = rect.x + pad
            py = rect.y + pad
            lw = bled_img.shape[1]
            lh = bled_img.shape[0]

            atlas_img[py:py + lh, px:px + lw] = bled_img

            u_min = px / float(aw)
            v_min = py / float(ah)
            u_max = (px + lw) / float(aw)
            v_max = (py + lh) / float(ah)

            uv_rect = (u_min, v_min, u_max, v_max)
            uv_rects[layer.name] = uv_rect
            uv_rects[layer_id] = uv_rect

            placements[layer_id] = LayerPlacement(
                layer_id=layer_id,
                page_index=p_idx,
                x=px,
                y=py,
                width=lw,
                height=lh,
                uv_rect=uv_rect,
                rotated=rot
            )

        # Remap meshes & construct drawables
        remapped_meshes: Dict[str, Mesh] = {}
        drawables: List[DrawableKeyforms] = []

        if meshes:
            for name, mesh in meshes.items():
                rect = uv_rects.get(name) or uv_rects.get(mesh.layer_id)
                p_meta = placements.get(name) or placements.get(mesh.layer_id)
                tex_idx = p_meta.page_index if p_meta else 0

                if rect:
                    rm_mesh = cls.remap_mesh_uvs(mesh, rect, flip_v=cfg.flip_v)
                else:
                    rm_mesh = mesh.copy()

                remapped_meshes[name] = rm_mesh
                drawables.append(DrawableKeyforms(
                    drawable_id=f"ArtMesh_{name}",
                    texture_index=tex_idx,
                    base_vertices=rm_mesh.get_positions().astype(np.float32),
                    triangles=rm_mesh.triangles.astype(np.int32),
                    uvs_atlas=rm_mesh.uvs.astype(np.float32)
                ))

        total_layer_area = sum(l.image.shape[0] * l.image.shape[1] for l in valid_layers)
        total_atlas_area = sum(img.shape[0] * img.shape[1] for img in pages_imgs)
        stats = PackingStats(
            total_layers=len(valid_layers),
            num_pages=len(pages_imgs),
            page_dimensions=[(img.shape[1], img.shape[0]) for img in pages_imgs],
            total_layer_area=total_layer_area,
            total_atlas_area=total_atlas_area,
            efficiency=total_layer_area / float(total_atlas_area) if total_atlas_area > 0 else 0.0
        )

        return PackingResult(
            pages=pages_imgs,
            placements=placements,
            uv_rects=uv_rects,
            remapped_meshes=remapped_meshes,
            drawables=drawables,
            stats=stats
        )

    @classmethod
    def pack_layers(
        cls,
        layers: List[LayerData],
        max_atlas_size: int = 4096,
        padding: int = 4,
        bleed_radius: int = 2
    ) -> Tuple[np.ndarray, Dict[str, Tuple[float, float, float, float]]]:
        config = PackingConfig(
            max_atlas_size=max_atlas_size,
            padding=padding,
            bleed_radius=bleed_radius
        )
        result = cls.pack(layers=layers, config=config)
        return result.primary_atlas, result.uv_rects
```

---

## 8. Corner Boundaries, Edge Cases & Mitigation Strategies

| Edge Case | Risk / Failure Mode | Mitigation Strategy |
|---|---|---|
| **$1 \times 1$ Micro Layer** | Division by zero or negative dimension | Clamp minimum side to 1px; allocate valid $[0, 1]$ sub-pixel UV rectangle |
| **$100\%$ Transparent Layer** | Wasted atlas area / empty bounding box | Alpha mask check `is_empty`; allocate minimal $1 \times 1$ dummy slot or bypass |
| **Layer larger than `max_atlas_size`** | Infinite sizing loop / crash | Auto-allocate dedicated POT page equal to $\text{NextPOT}(\max(W, H))$ |
| **Non-square Odd/Prime Layer ($513 \times 729$)** | UV distortion or misaligned sampling | Calculate exact normalized scale factors $(W_{layer} / W_{atlas})$ and $(H_{layer} / H_{atlas})$ |
| **$100+$ Layers (Complex Model)** | Atlas overflow on single 4096 page | Dynamic multi-page allocation ($N$ pages with `texture_index` $0, 1, 2\dots$) |
| **Zero Layers Passed `[]`** | IndexError / Unbound local variable | Early exit returning blank $512 \times 512$ POT image and empty dict |
| **Extreme Aspect Ratio ($2048 \times 32$)** | Extreme fragmentation in shelf packer | MaxRects-BSSF splits remaining vertical span into maximal rectangles |
| **Bilinear Seam at Mesh Boundary** | Dark fringe halo around silhouette | 2-stage Anti-Bleed: Voronoi RGB color dilation + $4\text{px}$ inter-layer padding |

---

## 9. Verification & Unit Testing Strategy

To guarantee full test suite passes (including Tiers 1-4), the test plan includes:
1. `test_atlas_power_of_two_dimensions`: Checks $W = 2^k, H = 2^m \ge 512$.
2. `test_atlas_uv_rect_normalized_bounds`: Checks all UV rects satisfy $0 \le u_{min} < u_{max} \le 1.0$ and $0 \le v_{min} < v_{max} \le 1.0$.
3. `test_atlas_non_overlapping_rectangles`: Checks that for all pairs $(i, j)$, $R_i \cap R_j = \emptyset$.
4. `test_atlas_pixel_data_transfer`: Checks that non-zero RGB pixel values are faithfully preserved.
5. `test_color_bleeding_preserves_rgb_and_alpha`: Verifies Voronoi dilation expands RGB into transparent margins while keeping $\alpha = 0$.
6. `test_remap_mesh_uvs`: Verifies mesh vertex UVs map linearly from $[0, 1]$ into $[u_{min}, u_{max}] \times [v_{min}, v_{max}]$.
7. `test_multi_page_atlas_overflow`: Verifies packing 10 large layers allocates multiple atlas pages with correct `page_index`.
8. `test_pure_python_fallback_without_scipy_cv2`: Mocks `HAS_SCIPY = False` and `HAS_CV2 = False` to verify deterministic pure-Python execution.
