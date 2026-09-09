# Asset Ingestion Architecture & Design Analysis (Milestone 1)

## Executive Summary
This document delivers the comprehensive technical investigation and engineering specification for the **Asset Ingestion Subsystem** of the Automated VTuber Rigging Tool. Asset Ingestion serves as the critical entry point of the pipeline, converting multi-layer Photoshop documents (`.psd`), single flat images (`.png`, `.jpg`), or directories of layered PNG slices into standardized `LayerData` objects with 2.5D semantic classification, nominal depth hints ($z \in [-1.0, 1.0]$), bounding boxes, opacity, and blend modes.

---

## 1. PSD Ingestion Architecture (`src/importer/psd_importer.py`)

### 1.1 `psd-tools` Library Capabilities & Technical Evaluation
The `psd-tools` Python library provides a robust, pure-Python parser for Adobe Photoshop PSD/PSB files without requiring Photoshop or external binary dependencies.

| Feature | `psd-tools` Property / Method | Behavior & Pipeline Integration |
|---|---|---|
| **Document Load** | `PSDImage.open(path_or_stream)` | Reads binary PSD/PSB header, color modes, canvas dimensions (`psd.width`, `psd.height`). |
| **Hierarchical Traversal** | `psd.descendants()` / `psd.layers` | Recursive generator traversing groups and nested layers in depth-first order. |
| **Group Detection** | `layer.is_group()` | Distinguishes folder containers from drawable raster layers. |
| **Visibility** | `layer.is_visible()` / `layer.visible` | Filters active vs hidden layers (`include_hidden` configuration parameter). |
| **Layer Bounding Box** | `layer.bbox` / `(left, top, right, bottom)` | Extracts canvas placement coordinates `(x1, y1, x2, y2)`. |
| **Dimensions & Offsets** | `layer.width`, `layer.height`, `layer.offset` | Local slice dimensions and $(x, y)$ canvas offsets. |
| **Opacity & Blend Mode** | `layer.opacity` (0-255), `layer.blend_mode` | Maps opacity to $[0.0, 1.0]$ float and maps `BlendMode` enums to standard strings (`normal`, `multiply`, `screen`, `overlay`). |
| **Layer Masks & Clipping** | `layer.has_mask()`, `layer.mask`, `layer.clip_to` | Evaluates alpha masks and clipping groups. |
| **Rasterization to PIL/RGBA** | `layer.topil()`, `layer.composite()` | `topil()` extracts raw pixel data; `composite()` renders layer with masks and clipping applied. |

### 1.2 Extraction Pipeline & Group Flattening
```
PSD File (.psd / .psb)
         │
         ▼
 ┌──────────────────────────────────────────────────────────┐
 │ PSDImage.open(filepath)                                  │
 │ Canvas Width, Height, Color Mode Validation              │
 └──────────────────────────┬───────────────────────────────┘
                            │
                            ▼
 ┌──────────────────────────────────────────────────────────┐
 │ Hierarchical Traversal (`psd.descendants()`)             │
 │ - Track group hierarchy paths (e.g. "Head/Eyes/Eye_L")   │
 │ - Skip empty layers (width == 0 or height == 0)          │
 │ - Evaluate visibility (filter hidden if flag set)        │
 │ - Resolve clipping masks (`layer.clip_to`)               │
 └──────────────────────────┬───────────────────────────────┘
                            │
                            ▼
 ┌──────────────────────────────────────────────────────────┐
 │ Raster Extraction & RGBA Normalization                   │
 │ - `layer.composite()` or `layer.topil()` -> PIL.Image    │
 │ - Convert mode to "RGBA" (uint8, shape (H, W, 4))        │
 │ - Extract bounding box: offset_x = left, offset_y = top  │
 └──────────────────────────┬───────────────────────────────┘
                            │
                            ▼
 ┌──────────────────────────────────────────────────────────┐
 │ Bilingual Semantic Classification & Z-Depth Assignment   │
 │ - Step 1: Hierarchical token matching (EN + JP)          │
 │ - Step 2: Ancestor group context inheritance             │
 │ - Step 3: Spatial bounding-box heuristic fallback        │
 │ - Step 4: Nominal depth assignment ($z \in [-1.0, 1.0]$)  │
 └──────────────────────────┬───────────────────────────────┘
                            │
                            ▼
                    List[LayerData]
```

### 1.3 Handling PSD Edge Cases & Error Modes
1. **Dynamic Import & Fallback**: `psd-tools` should be imported with dynamic fallback handling. If `psd-tools` is not installed in the environment, `PSDImporter` provides clear instructional error messages and supports synthetic/mock PSD structures for testing.
2. **Empty or Adjustment Layers**: Adjustment layers (curves, levels, brightness) and empty group nodes have zero pixel dimensions. The importer checks `if layer.width > 0 and layer.height > 0 and layer_image is not None` before instantiating `LayerData`.
3. **Clipping Masks**: In VTuber PSDs, highlights and pupil colors are frequently clipped to the sclera/eye base. Using `layer.composite()` automatically evaluates the clipping hierarchy into the RGBA buffer.
4. **Duplicate Layer Names**: PSD layers often have non-unique names (e.g., multiple layers named `束`, `ハイライト`, or `Layer 1`). The importer enforces uniqueness by combining the ancestor path with the layer index: `layer_id = f"{parent_path}/{clean_name}_{index}"`.

---

## 2. Bilingual Semantic Classification Engine (English & Japanese)

### 2.1 Standard VTuber Layer Taxonomy & Nominal Z-Depths
Live2D Cubism characters rely on a stratified 2.5D depth ordering to achieve proper perspective parallax without self-intersection or visual popping during head rotations ($Angle X, Angle Y, Angle Z$).

| Category Identifier | English Names & Keywords | Japanese Names & Keywords (Live2D Standard) | Nominal Z-Depth ($z$) | Parallax Scale Factor |
|---|---|---|---|---|
| `HAIR_FRONT` / `hair_front` | `hair_front`, `front_hair`, `bangs`, `forelock`, `ahoge`, `side_hair`, `sidelocks`, `hair_f`, `side_f` | 前髪, 前がみ, まえがみ, アホ毛, あほ毛, 横髪, よこがみ, サイドヘア, サイド, 横束, 触角, 鬢, もみあげ, 前髪_束, 前髪ベース, 前髪ハイライト | **$+0.50$** | $1.50$ |
| `EYEBROWS` / `eyebrows` | `eyebrow`, `eyebrows`, `brow`, `brow_l`, `brow_r`, `left_eyebrow`, `right_eyebrow`, `eye_brow` | 眉, 眉毛, まゆ, まゆげ, 右眉, 左眉, 眉_左, 眉_右, 眉_上, 眉_下, 眉毛_左, 眉毛_右 | **$+0.35$** | $1.25$ |
| `NOSE` / `nose` | `nose`, `nostril`, `nose_shadow`, `nose_tip`, `nose_bridge`, `nose_line` | 鼻, はな, 鼻筋, 鼻頭, 鼻_影, 鼻先, 小鼻 | **$+0.30$** | $1.20$ |
| `EYES` / `eyes` | `eye`, `eyes`, `eye_l`, `eye_r`, `pupil`, `iris`, `sclera`, `eyelash`, `eyeliner`, `highlight_eye`, `eye_highlight` | 目, め, 右目, 左目, 目_左, 目_右, 瞳, 瞳孔, 黒目, 白目, まつ毛, まつげ, 上まつげ, 下まつげ, アイライン, 二重, 目頭, 目尻, ハイライト, 目の光 | **$+0.25$** | $1.15$ |
| `MOUTH` / `mouth` | `mouth`, `lip`, `lips`, `upper_lip`, `lower_lip`, `teeth`, `tooth`, `tongue`, `mouth_interior`, `mouth_cavity` | 口, くち, 上唇, 下唇, 口唇, 唇, うわくちびる, したくちびる, 歯, 舌, 口内, 口の中, 口_上, 口_下, 口ライン, 口_閉じ, 口_開き | **$+0.20$** | $1.10$ |
| `FACE` / `face` | `face`, `face_skin`, `skin`, `face_outline`, `head`, `head_base`, `cheek`, `blush`, `face_base`, `contour`, `chin` | 顔, かお, 輪郭, りんかく, 肌, はだ, 顔肌, 顔_輪郭, 顔ベース, 頬, ほほ, ほっぺ, チーク, 照れ, 赤み, フェイス | **$0.00$** | $1.00$ (Reference Plane) |
| `EARS` / `ears` | `ear`, `ears`, `ear_l`, `ear_r`, `left_ear`, `right_ear`, `cat_ear`, `animal_ear`, `elf_ear` | 耳, みみ, 右耳, 左耳, 耳_左, 耳_右, ケモ耳, 獣耳, 猫耳, うさ耳, エルフ耳 | **$-0.15$** | $0.85$ |
| `NECK_BODY` / `body` | `neck`, `body`, `torso`, `chest`, `collar`, `shoulder`, `arm`, `clothes`, `clothing`, `shirt`, `dress`, `jacket` | 首, くび, 体, からだ, 胴体, 胴, 身体, 服, 衣装, 胸, 肩, 腕, 手, 襟, えり, ネクタイ, リボン_胸, 上着, シャツ, ボディ | **$-0.35$** | $0.65$ |
| `HAIR_BACK` / `hair_back` | `hair_back`, `back_hair`, `hair_behind`, `ponytail`, `twintail`, `pigtail`, `braid`, `backhair`, `rear_hair` | 後ろ髪, うしろ髪, 後髪, うしろがみ, 後ろ髪ベース, つむじ, ポニーテール, ツインテール, おさげ, 三つ編み, バックヘア, 襟足, えりあし | **$-0.60$** | $0.40$ |
| `ACCESSORIES` / `accessories`| `accessory`, `accessories`, `ribbon`, `glasses`, `hat`, `headband`, `hairpin`, `earring`, `tiara`, `horn`, `crown` | アクセサリー, 装飾, リボン, メガネ, 眼鏡, 帽子, カチューシャ, ヘアピン, ピアス, イヤリング, ティアラ, 角, つの | **$+0.45$** | $1.35$ |

### 2.2 Classification Matching Algorithm
The classifier uses a multi-stage priority matcher:
1. **Normalization**: Clean input string: convert to lower-case, remove special characters, delimiters (`_`, `-`, `/`, `.`), and numbers (e.g. `顔_輪郭_01.png` $\to$ `顔輪郭`).
2. **Exact & Substring Matching**: Check against high-specificity tokens first (e.g., `eyebrow` before `eye`; `hair_front` and `前髪` before `hair`).
3. **Ancestor Context Resolution**: If the layer is named simply `Left` or `まつげ`, the classifier inspects parent group names (e.g. `Head/Eyes/Left` $\to$ `eyes`).
4. **Side & Part Tagging**: Automatically detects lateral qualifiers (`left`/`左`, `right`/`右`, `center`/`中`) and functional tags (`pupil`, `sclera`, `highlight`, `upper_lip`, etc.).

---

## 3. Spatial Bounding Box Heuristic Fallbacks

When layer names are non-descriptive (e.g., `Layer 1`, `Layer 2`, `Untitled`, `Bitmap 12`), the classifier transitions seamlessly to a **Spatial Bayesian Heuristic Classifier**.

### 3.1 Normalized Coordinate Space
Let the canvas have dimensions $(W_C, H_C)$. Any layer bounding box $(x_{min}, y_{min}, x_{max}, y_{max})$ is normalized to:
$$c_x = \frac{x_{min} + x_{max}}{2 W_C}, \quad c_y = \frac{y_{min} + y_{max}}{2 H_C}, \quad w_{norm} = \frac{x_{max} - x_{min}}{W_C}, \quad h_{norm} = \frac{y_{max} - y_{min}}{H_C}, \quad A_{norm} = w_{norm} \times h_{norm}$$

### 3.2 Spatial Decision Rules Matrix
```
                              Canvas Height (Y: 0.0 -> 1.0)
     0.0 ┌──────────────────────────────────────────────────┐
         │              [HAIR_BACK (top span)]              │
     0.2 │  [HAIR_FRONT]     [EYEBROWS (0.25-0.38)]         │
     0.3 │    [EARS]         [EYES (0.30-0.45)]      [EARS] │
     0.4 │                   [NOSE (0.42-0.55)]             │
     0.5 │     [FACE (Large Central Region, 0.20-0.70)]     │
     0.6 │                   [MOUTH (0.52-0.68)]            │
     0.7 │                                                  │
     0.8 │                   [NECK_BODY]                    │
     1.0 └──────────────────────────────────────────────────┘
         0.0                       0.5                    1.0
                         Canvas Width (X: 0.0 -> 1.0)
```

| Inferred Category | Vertical Center ($c_y$) | Horizontal Center ($c_x$) | Normalized Area ($A_{norm}$) | Aspect Ratio ($w/h$) | Stacking Hint (PSD Index) |
|---|---|---|---|---|---|
| `body` / `neck_body` | $c_y > 0.65$ or $y_{max} > 0.85$ | Any ($|c_x - 0.5| < 0.25$) | $A > 0.15$ | $w/h \ge 0.8$ | Low to Mid Stack |
| `hair_back` | $c_y \in [0.10, 0.60]$ | Centered ($|c_x - 0.5| < 0.20$) | $A > 0.25$ | $w/h \ge 0.7$ | Bottom of Stack ($idx < 0.2 N$) |
| `face` | $c_y \in [0.30, 0.60]$ | Centered ($|c_x - 0.5| < 0.12$) | $0.12 \le A \le 0.45$ | $0.7 \le w/h \le 1.3$ | Mid Stack |
| `hair_front` | $c_y \in [0.10, 0.45]$ | Centered ($|c_x - 0.5| < 0.25$) | $0.08 \le A \le 0.35$ | $w/h \ge 0.8$ | Top of Stack ($idx > 0.7 N$) |
| `eyebrows` | $c_y \in [0.25, 0.38]$ | Bilateral ($|c_x - 0.5| \in [0.05, 0.25]$) | $A < 0.04$, $h_{norm} < 0.08$ | $w/h > 1.4$ (Elongated) | Upper Mid Stack |
| `eyes` | $c_y \in [0.30, 0.45]$ | Bilateral ($|c_x - 0.5| \in [0.06, 0.28]$) | $0.005 \le A \le 0.06$ | $0.6 \le w/h \le 1.8$ | Upper Mid Stack |
| `nose` | $c_y \in [0.42, 0.55]$ | Centered ($|c_x - 0.5| < 0.08$) | $A < 0.02$, $w_{norm} < 0.10$ | $0.5 \le w/h \le 1.5$ | Upper Mid Stack |
| `mouth` | $c_y \in [0.52, 0.68]$ | Centered ($|c_x - 0.5| < 0.12$) | $0.005 \le A \le 0.05$ | $w/h \ge 1.2$ (Horizontal) | Upper Mid Stack |
| `ears` | $c_y \in [0.32, 0.55]$ | Lateral ($|c_x - 0.5| > 0.25$) | $0.01 \le A \le 0.08$ | $0.4 \le w/h \le 1.4$ | Lower Mid Stack |

---

## 4. PNG & Directory Ingestion Engine (`src/importer/image_importer.py`)

### 4.1 Single Image Ingestion
- Loads `.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp` files via Pillow (`PIL.Image.open`).
- Standardizes color channels to uint8 RGBA $(H, W, 4)$.
- If no alpha channel exists (e.g. RGB JPEG), creates a full-opacity 255 alpha channel.

### 4.2 Directory Layer Ingestion (`load_directory`)
- Scans target folder for raster image files.
- Sorts filenames naturally/numerically (e.g., `01_hair_back.png`, `02_neck.png`, ..., `10_hair_front.png`).
- Computes individual layer bounds, transparent padding trims, and canvas offsets.
- Applies the Bilingual Semantic Classifier to each filename.
- Returns `List[LayerData]`.

### 4.3 Synthetic Multi-Layer Character Generator (`create_synthetic_layered_head`)
To enable 100% self-contained unit, integration, and E2E testing without external assets, `ImageImporter` provides `create_synthetic_layered_head(width=512, height=512) -> List[LayerData]`:

```python
# Generated Synthetic Layers:
1.  "Hair_Back"     (z = -0.60, Dark hair silhouette extending behind head)
2.  "Neck_Body"     (z = -0.35, Neck column and clothing collar)
3.  "Ear_L"         (z = -0.15, Left ear lobe)
4.  "Ear_R"         (z = -0.15, Right ear lobe)
5.  "Face"          (z =  0.00, Smooth anime skin oval with jaw taper)
6.  "Blush_L"       (z = +0.05, Left cheek blush)
7.  "Blush_R"       (z = +0.05, Right cheek blush)
8.  "Mouth"         (z = +0.20, Upper lip line, oral cavity, teeth, lower lip)
9.  "Eye_L"         (z = +0.25, Left sclera, iris, pupil, highlight, lash)
10. "Eye_R"         (z = +0.25, Right sclera, iris, pupil, highlight, lash)
11. "Nose"          (z = +0.30, Delicate anime nose contour)
12. "Eyebrow_L"     (z = +0.35, Left expressive eyebrow arc)
13. "Eyebrow_R"     (z = +0.35, Right expressive eyebrow arc)
14. "Hair_Front"    (z = +0.50, Anime bangs, front strands, and ahoge)
```

### 4.4 Robust Pure-Python Contour Extraction Fallback
To ensure zero dependency crashes on systems lacking OpenCV (`cv2`), `ImageImporter.extract_contour` is designed with a two-tier strategy:
1. **Primary (Fast)**: If `cv2` is available, uses `cv2.findContours` + `cv2.approxPolyDP`.
2. **Pure-Python Fallback (Zero-Dependency)**: Uses Pillow edge filtering (`PIL.ImageFilter.FIND_EDGES`) or NumPy boundary scanning + `scipy.spatial.ConvexHull` / polygon reduction to extract boundary vertices $(K, 2)$.

---

## 5. Core Data Model (`src/core/layer.py`)

### 5.1 `LayerData` Model Specification
```python
from dataclasses import dataclass, field
from typing import Optional, Tuple, Dict, Any
import numpy as np

@dataclass
class LayerData:
    name: str                                  # Layer display name
    image: np.ndarray                          # RGBA uint8 array, shape (H, W, 4)
    offset_x: int = 0                          # X position on full canvas
    offset_y: int = 0                          # Y position on full canvas
    z_depth_hint: float = 0.0                  # Depth hint in [-1.0, 1.0]
    category: str = "unknown"                  # Semantic category
    visible: bool = True                       # Visibility flag
    opacity: float = 1.0                       # Opacity in [0.0, 1.0]
    blend_mode: str = "normal"                 # Blend mode string
    layer_id: str = ""                         # Unique ID string
    parent_group: Optional[str] = None         # Parent folder name
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def bbox(self) -> Tuple[int, int, int, int]:
        return (self.offset_x, self.offset_y, self.offset_x + self.width, self.offset_y + self.height)

    @property
    def alpha_mask(self) -> np.ndarray:
        return self.image[:, :, 3]
```

---

## 6. Comprehensive Test Suite Design (`tests/test_importer.py`)

The test suite validates every functional requirement, edge case, and error condition:

| Test Case | Target Subsystem | Validation Criteria |
|---|---|---|
| `test_psd_importer_layer_extraction` | `psd_importer.py` | Extracts multiple layers, verifies dimensions, RGBA shape, opacity, and blend modes. |
| `test_psd_importer_group_hierarchy` | `psd_importer.py` | Validates nested group paths (`Head/Eyes/Eye_L`) and unique `layer_id` generation. |
| `test_psd_importer_hidden_layer_filtering` | `psd_importer.py` | Confirms hidden layers are excluded when `include_hidden=False`. |
| `test_bilingual_classification_japanese` | Semantic Classifier | Classifies `前髪`, `右目_瞳`, `眉毛`, `輪郭`, `上唇`, `後ろ髪`, `首`, `ケモ耳` with 100% precision. |
| `test_bilingual_classification_english` | Semantic Classifier | Classifies `bangs`, `eye_l`, `eyebrow_r`, `nose`, `mouth`, `body`, `hair_back` with 100% precision. |
| `test_mixed_naming_and_case_insensitivity`| Semantic Classifier | Handles mixed strings (`Hair_Front_01`, `顔_赤み(乗算)`, `R_EYE_pupil`). |
| `test_nominal_z_depth_stratification` | Semantic Classifier | Confirms $z(\text{hair\_front}) > z(\text{face}) > z(\text{hair\_back})$. |
| `test_spatial_heuristic_fallbacks` | Spatial Classifier | Correctly identifies unnamed layers (`Layer 1` at top $\to$ `hair_front`, `Layer 2` at bottom $\to$ `body`). |
| `test_load_single_flat_png` | `image_importer.py` | Loads single PNG, returns shape $(H, W, 4)$ and uint8 alpha mask. |
| `test_load_directory_png_layers` | `image_importer.py` | Ingests directory of PNGs, preserves layer ordering and metadata. |
| `test_synthetic_layered_head_generator` | `image_importer.py` | Produces $\ge 10$ distinct layers with valid RGBA buffers and semantic tags. |
| `test_contour_extraction_robustness` | `image_importer.py` | Extracts valid closed polygon with $\ge 3$ vertices; handles empty masks cleanly without `cv2`. |
| `test_error_handling_missing_files` | Error Handling | Raises `FileNotFoundError` with descriptive message on missing files. |

---

## 7. Implementation Roadmap & File Modification Guide

### 7.1 Proposed Files to Create / Update:
1. `src/core/layer.py`: Define `LayerData` dataclass with full metadata, bounding boxes, and alpha mask properties.
2. `src/importer/psd_importer.py`: Full `PSDImporter` implementation with `psd-tools` integration, fallback handling, group tree traversal, and clipping mask composition.
3. `src/importer/semantic_classifier.py`: Dedicated `SemanticClassifier` module containing bilingual dictionaries, regex rule matching, and spatial bounding box heuristics.
4. `src/importer/image_importer.py`: Updated `ImageImporter` with pure-Python/OpenCV contour extraction, directory layer loading, and multi-layer synthetic head generator.
5. `src/importer/__init__.py`: Export `PSDImporter`, `ImageImporter`, `SemanticClassifier`, and `LayerData`.
6. `tests/test_importer.py`: Comprehensive test suite containing all 13 test specifications.
