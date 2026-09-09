# Deep Technical Analysis: Live2D Model3 Manifest, CDI3 Display Info, and Milestone 3 Test Architecture

**Author**: Explorer Agent M3.3 (`explorer_m3_3`)  
**Working Directory**: `d:\VitubModel\.agents\explorer_m3_3`  
**Parent Conversation ID**: `e7dca846-4d99-4c6b-8292-c99ca268b1b9`  
**Date**: 2026-08-22  
**Milestone**: Milestone 3 (Live2D Binary Exporter & Texture Packer Pipeline)

---

## 1. Executive Summary & Core Objectives

This technical investigation delivers the definitive architectural design, data schemas, compatibility matrix, and comprehensive test suite specifications for:
1. **`src/exporter/model3_writer.py`**:
   - Master Live2D Cubism 3+ model manifest (`.model3.json`) specification.
   - Combined Display Info manifest (`.cdi3.json`) specification.
   - Full compatibility requirements across **Live2D Cubism Viewer**, **Live2D Cubism Editor**, and **VTube Studio**.
2. **Milestone 3 Test Architecture**:
   - Comprehensive test suite for **`tests/test_texture_packer.py`** covering empty layers, single layer, multi-layer MaxRects bin packing, power-of-two sizing, padding, edge bleeding, UV recalculation, and overlap detection.
   - Comprehensive test suite for **`tests/test_moc3_writer.py`** covering header magic bytes, 64-byte alignment, section offset tables, count tables, ArtMesh serialization, 9-keyform Cartesian grid displacement tensors, and round-trip binary validation.
   - Unit test suite for **`tests/test_model3_writer.py`** covering JSON schema validity, relative path formatting, parameter groupings (`LipSync`, `EyeBlink`), and bilingual display name mappings.

---

## 2. Deep Dive: `src/exporter/model3_writer.py` Architecture

The `Model3Writer` is responsible for generating the standardized JSON metadata files required by the Live2D runtime ecosystem. Without compliant JSON metadata, even a perfectly serialized `.moc3` binary cannot be loaded by VTube Studio, Cubism Viewer, or game engine SDKs.

```
                                KeyformTable & Texture Atlas
                                             │
                                             ▼
                                    Model3Writer Engine
                                             │
                   ┌─────────────────────────┴─────────────────────────┐
                   ▼                                                   ▼
         .model3.json Manifest                                .cdi3.json Display Info
         - Version: 3                                         - Version: 3
         - FileReferences:                                    - Parameters:
           * Moc: "<name>.moc3"                                 * Id: "ParamAngleX"
           * Textures: ["<dir>/texture_00.png"]                 * GroupId: "ParamGroupHead"
           * Physics: "<name>.physics3.json" (opt)              * Name: "Angle X" / "角度 X"
           * DisplayInfo: "<name>.cdi3.json"                  - ParameterGroups:
         - Groups:                                              * Head, Eyes, Mouth, Body
           * LipSync: ["ParamMouthOpenY", ...]                - Parts:
           * EyeBlink: ["ParamEyeLOpen", ...]                   * Head, Hair, Face, Body
         - HitAreas: [...]
```

---

### 2.1 Specification of `.model3.json` (Version 3 Format)

The `.model3.json` file is the master entry point loaded by Live2D Cubism SDK, Cubism Viewer, and tracking applications.

#### JSON Schema Structure:

```json
{
  "Version": 3,
  "FileReferences": {
    "Moc": "character.moc3",
    "Textures": [
      "character.4096/texture_00.png"
    ],
    "Physics": "character.physics3.json",
    "Pose": "character.pose3.json",
    "DisplayInfo": "character.cdi3.json",
    "Expressions": [],
    "Motions": {},
    "UserData": ""
  },
  "Groups": [
    {
      "Target": "Parameter",
      "Name": "LipSync",
      "Ids": [
        "ParamMouthOpenY",
        "ParamMouthForm"
      ]
    },
    {
      "Target": "Parameter",
      "Name": "EyeBlink",
      "Ids": [
        "ParamEyeLOpen",
        "ParamEyeROpen"
      ]
    }
  ],
  "HitAreas": [
    {
      "Id": "ArtMesh_Head",
      "Name": "Head"
    },
    {
      "Id": "ArtMesh_Body",
      "Name": "Body"
    }
  ],
  "Layout": {
    "CenterX": 0.0,
    "CenterY": 0.0,
    "Width": 2.0,
    "Height": 2.0
  }
}
```

#### Detailed Field Requirements:

1. **`Version` (integer)**:
   - Must strictly be `3` (Cubism 3.0 / 4.0 / 5.0 standard).
2. **`FileReferences` (object)**:
   - **`Moc` (string, required)**: Relative path to the `.moc3` binary file. Must use forward slashes `/`.
   - **`Textures` (array of strings, required)**: Ordered list of relative paths to texture atlas PNG files (e.g. `["character.4096/texture_00.png"]`).
     * The index in this array corresponds directly to `ArtMeshes.TextureNos` in the `.moc3` binary.
     * Texture paths must strictly exist and be valid power-of-two PNG files.
   - **`Physics` (string, optional)**: Relative path to `.physics3.json`. If physics is not generated, omit or exclude key.
   - **`DisplayInfo` (string, optional/recommended)**: Relative path to `.cdi3.json`.
   - **`Pose` (string, optional)**: Relative path to `.pose3.json` for multi-part visibility swapping.
   - **`Expressions` (array, optional)**: List of expression definitions (`{"Name": str, "File": str}`).
   - **`Motions` (object, optional)**: Dictionary mapping motion group names (e.g. `"Idle"`, `"TapBody"`) to motion file arrays.
3. **`Groups` (array of objects)**:
   - Automatic parameter bindings for facial tracking and physics simulation.
   - **`LipSync`**:
     * `Target`: `"Parameter"`
     * `Name`: `"LipSync"`
     * `Ids`: `["ParamMouthOpenY", "ParamMouthForm"]`
   - **`EyeBlink`**:
     * `Target`: `"Parameter"`
     * `Name`: `"EyeBlink"`
     * `Ids`: `["ParamEyeLOpen", "ParamEyeROpen"]`
4. **`HitAreas` (array of objects)**:
   - Interactive touch/click zones mapped to ArtMeshes:
     * `Id`: `"ArtMesh_Head"`, `Name`: `"Head"`
5. **`Layout` (object, optional)**:
   - Canvas coordinate layout properties (`CenterX`, `CenterY`, `Width`, `Height`).

---

### 2.2 Specification of `.cdi3.json` (Combined Display Info Format)

The `.cdi3.json` file supplies user-facing display names, slider categories, parameter groups, and part trees.

#### JSON Schema Structure:

```json
{
  "Version": 3,
  "Parameters": [
    {
      "Id": "ParamAngleX",
      "GroupId": "ParamGroupHead",
      "Name": "Angle X"
    },
    {
      "Id": "ParamAngleY",
      "GroupId": "ParamGroupHead",
      "Name": "Angle Y"
    },
    {
      "Id": "ParamAngleZ",
      "GroupId": "ParamGroupHead",
      "Name": "Angle Z"
    },
    {
      "Id": "ParamEyeLOpen",
      "GroupId": "ParamGroupEyes",
      "Name": "Eye L Open"
    },
    {
      "Id": "ParamEyeROpen",
      "GroupId": "ParamGroupEyes",
      "Name": "Eye R Open"
    },
    {
      "Id": "ParamMouthOpenY",
      "GroupId": "ParamGroupMouth",
      "Name": "Mouth Open"
    },
    {
      "Id": "ParamMouthForm",
      "GroupId": "ParamGroupMouth",
      "Name": "Mouth Form"
    },
    {
      "Id": "ParamBodyAngleX",
      "GroupId": "ParamGroupBody",
      "Name": "Body Angle X"
    }
  ],
  "ParameterGroups": [
    {
      "Id": "ParamGroupHead",
      "GroupId": "",
      "Name": "Head Rotation"
    },
    {
      "Id": "ParamGroupEyes",
      "GroupId": "",
      "Name": "Eyes"
    },
    {
      "Id": "ParamGroupMouth",
      "GroupId": "",
      "Name": "Mouth"
    },
    {
      "Id": "ParamGroupBody",
      "GroupId": "",
      "Name": "Body"
    }
  ],
  "Parts": [
    {
      "Id": "PartHead",
      "Name": "Head"
    },
    {
      "Id": "PartHair",
      "Name": "Hair"
    },
    {
      "Id": "PartFace",
      "Name": "Face"
    },
    {
      "Id": "PartEyes",
      "Name": "Eyes"
    },
    {
      "Id": "PartMouth",
      "Name": "Mouth"
    },
    {
      "Id": "PartBody",
      "Name": "Body"
    }
  ]
}
```

#### Parameter Name Dictionary:

| Parameter ID (`Id`) | Parameter Group (`GroupId`) | English Display Name | Japanese Display Name |
| :--- | :--- | :--- | :--- |
| `ParamAngleX` | `ParamGroupHead` | Angle X | 角度 X |
| `ParamAngleY` | `ParamGroupHead` | Angle Y | 角度 Y |
| `ParamAngleZ` | `ParamGroupHead` | Angle Z | 角度 Z |
| `ParamEyeLOpen` | `ParamGroupEyes` | Eye L Open | 左目 開閉 |
| `ParamEyeROpen` | `ParamGroupEyes` | Eye R Open | 右目 開閉 |
| `ParamEyeLSmile` | `ParamGroupEyes` | Eye L Smile | 左目 笑顔 |
| `ParamEyeRSmile` | `ParamGroupEyes` | Eye R Smile | 右目 笑顔 |
| `ParamEyeBallX` | `ParamGroupEyes` | Eyeball X | 目玉 X |
| `ParamEyeBallY` | `ParamGroupEyes` | Eyeball Y | 目玉 Y |
| `ParamBrowLY` | `ParamGroupEyebrows` | Eyebrow L Y | 左眉 上下 |
| `ParamBrowRY` | `ParamGroupEyebrows` | Eyebrow R Y | 右眉 上下 |
| `ParamMouthForm` | `ParamGroupMouth` | Mouth Form | 口 変形 |
| `ParamMouthOpenY`| `ParamGroupMouth` | Mouth Open | 口 開閉 |
| `ParamBodyAngleX`| `ParamGroupBody` | Body Angle X | 体の回転 X |
| `ParamBodyAngleY`| `ParamGroupBody` | Body Angle Y | 体の回転 Y |
| `ParamBodyAngleZ`| `ParamGroupBody` | Body Angle Z | 体の回転 Z |
| `ParamBreath` | `ParamGroupBody` | Breath | 呼吸 |

---

### 2.3 Compatibility Requirements Matrix

| Software / Ecosystem | Key Requirements | Verification Checklist | Common Failure Modes & Mitigations |
| :--- | :--- | :--- | :--- |
| **Live2D Cubism Viewer** (Official Tool) | 1. `"Version": 3`<br>2. Forward slashes `/` only in relative paths<br>3. Non-empty `Textures` array<br>4. 32-bit RGBA PNG texture atlas with power-of-two dimensions (512..8192)<br>5. Valid `.moc3` binary header (magic `b"MOC3"`, version 3, 64-byte aligned offsets)<br>6. Standard `LipSync` and `EyeBlink` groups | - Open `.model3.json` directly in Cubism Viewer<br>- Sliders for `ParamAngleX`, `ParamAngleY`, `ParamAngleZ` respond smoothly<br>- No OpenGL texture binding warnings | *Failure*: Windows backslash `\` causes path not found on Linux/macOS/WebGL SDKs.<br>*Mitigation*: Force `posixpath` or `.replace('\\', '/')` in `model3_writer.py`.<br>*Failure*: Corrupted `.moc3` offset crashes `csmReviveMocInPlace`.<br>*Mitigation*: Enforce strict 64-byte alignment (`0x40`) in `moc3_writer.py`. |
| **Live2D Cubism Editor** | 1. Reads `.cdi3.json` to restore friendly parameter labels and part hierarchy tree<br>2. String IDs must not exceed 64 chars (`char[64]`)<br>3. Parameter range values (`min`, `default`, `max`) must match discrete key values | - Import model in Cubism Editor<br>- Parameter palette displays grouped tree (`Head Rotation`, `Eyes`, etc.) | *Failure*: Missing `.cdi3.json` causes parameter palette to display unorganized raw ID strings (`ParamAngleX`).<br>*Mitigation*: Always generate matching `.cdi3.json`. |
| **VTube Studio** | 1. Model folder placed in `VTube Studio/Live2DModels/<ModelName>/`<br>2. `.model3.json` present in root of model directory<br>3. Standard parameter naming (`ParamAngleX`, `ParamAngleY`, `ParamAngleZ`, `ParamEyeLOpen`, `ParamEyeROpen`, `ParamMouthOpenY`, `ParamMouthForm`)<br>4. Auto-setup utilizes `EyeBlink` and `LipSync` groups | - Load model into VTube Studio<br>- Run Auto Setup to link webcam head tracking to `ParamAngleX`, `ParamAngleY`, `ParamAngleZ`<br>- Test audio lip-sync and auto-blink | *Failure*: Non-standard parameter IDs (e.g. `Param_AngleX` or `ParamHeadYaw`) will not be recognized by VTS auto-setup, requiring tedious manual binding.<br>*Mitigation*: Strictly standardize on official Live2D Cubism parameter IDs. |

---

### 2.4 Reference Code Architecture: `src/exporter/model3_writer.py`

```python
"""
src/exporter/model3_writer.py
Live2D Cubism 3.0+ Metadata Generator (.model3.json and .cdi3.json).
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional


class Model3Writer:
    """
    Generates standardized Live2D Cubism 3+ metadata:
    - .model3.json: Master runtime manifest for Cubism Viewer, SDKs, and VTube Studio.
    - .cdi3.json: Combined Display Information manifest for Live2D editors and tracking palettes.
    """

    DEFAULT_PARAM_NAMES: Dict[str, Dict[str, str]] = {
        "ParamAngleX": {"name": "Angle X", "group": "ParamGroupHead"},
        "ParamAngleY": {"name": "Angle Y", "group": "ParamGroupHead"},
        "ParamAngleZ": {"name": "Angle Z", "group": "ParamGroupHead"},
        "ParamEyeLOpen": {"name": "Eye L Open", "group": "ParamGroupEyes"},
        "ParamEyeROpen": {"name": "Eye R Open", "group": "ParamGroupEyes"},
        "ParamEyeLSmile": {"name": "Eye L Smile", "group": "ParamGroupEyes"},
        "ParamEyeRSmile": {"name": "Eye R Smile", "group": "ParamGroupEyes"},
        "ParamEyeBallX": {"name": "Eyeball X", "group": "ParamGroupEyes"},
        "ParamEyeBallY": {"name": "Eyeball Y", "group": "ParamGroupEyes"},
        "ParamBrowLY": {"name": "Eyebrow L Y", "group": "ParamGroupEyebrows"},
        "ParamBrowRY": {"name": "Eyebrow R Y", "group": "ParamGroupEyebrows"},
        "ParamMouthForm": {"name": "Mouth Form", "group": "ParamGroupMouth"},
        "ParamMouthOpenY": {"name": "Mouth Open", "group": "ParamGroupMouth"},
        "ParamBodyAngleX": {"name": "Body Angle X", "group": "ParamGroupBody"},
        "ParamBodyAngleY": {"name": "Body Angle Y", "group": "ParamGroupBody"},
        "ParamBodyAngleZ": {"name": "Body Angle Z", "group": "ParamGroupBody"},
        "ParamBreath": {"name": "Breath", "group": "ParamGroupBody"},
    }

    DEFAULT_GROUP_NAMES: Dict[str, str] = {
        "ParamGroupHead": "Head Rotation",
        "ParamGroupEyes": "Eyes",
        "ParamGroupEyebrows": "Eyebrows",
        "ParamGroupMouth": "Mouth",
        "ParamGroupBody": "Body",
    }

    @classmethod
    def generate_model3_json(
        cls,
        model_name: str,
        moc_rel_path: str,
        texture_rel_paths: List[str],
        physics_rel_path: Optional[str] = None,
        cdi_rel_path: Optional[str] = None,
        pose_rel_path: Optional[str] = None,
        output_path: Optional[str] = None,
        hit_areas: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Generates .model3.json manifest dictionary and optionally writes it to disk.
        """
        # Ensure forward-slash relative paths
        clean_moc = moc_rel_path.replace("\\", "/")
        clean_textures = [t.replace("\\", "/") for t in texture_rel_paths]

        file_references: Dict[str, Any] = {
            "Moc": clean_moc,
            "Textures": clean_textures,
        }

        if physics_rel_path:
            file_references["Physics"] = physics_rel_path.replace("\\", "/")
        if cdi_rel_path:
            file_references["DisplayInfo"] = cdi_rel_path.replace("\\", "/")
        if pose_rel_path:
            file_references["Pose"] = pose_rel_path.replace("\\", "/")

        # Standard LipSync and EyeBlink Groups
        groups = [
            {
                "Target": "Parameter",
                "Name": "LipSync",
                "Ids": ["ParamMouthOpenY", "ParamMouthForm"],
            },
            {
                "Target": "Parameter",
                "Name": "EyeBlink",
                "Ids": ["ParamEyeLOpen", "ParamEyeROpen"],
            },
        ]

        # Standard Hit Areas
        areas = hit_areas if hit_areas is not None else [
            {"Id": "ArtMesh_Head", "Name": "Head"}
        ]

        data = {
            "Version": 3,
            "FileReferences": file_references,
            "Groups": groups,
            "HitAreas": areas,
            "Layout": {
                "CenterX": 0.0,
                "CenterY": 0.0,
                "Width": 2.0,
                "Height": 2.0,
            },
        }

        if output_path:
            out_file = Path(output_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        return data

    @classmethod
    def generate_cdi3_json(
        cls,
        parameter_ids: List[str],
        part_ids: Optional[List[str]] = None,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generates .cdi3.json display info dictionary and optionally writes it to disk.
        """
        params_meta = []
        active_group_ids = set()

        for pid in parameter_ids:
            meta = cls.DEFAULT_PARAM_NAMES.get(pid, {"name": pid, "group": ""})
            gid = meta.get("group", "")
            if gid:
                active_group_ids.add(gid)
            params_meta.append({
                "Id": pid,
                "GroupId": gid,
                "Name": meta.get("name", pid),
            })

        param_groups_meta = []
        for gid in sorted(list(active_group_ids)):
            gname = cls.DEFAULT_GROUP_NAMES.get(gid, gid)
            param_groups_meta.append({
                "Id": gid,
                "GroupId": "",
                "Name": gname,
            })

        parts_list = part_ids if part_ids is not None else ["PartHead", "PartHair", "PartFace", "PartBody"]
        parts_meta = []
        for pid in parts_list:
            display_name = pid.replace("Part_", "").replace("Part", "") or pid
            parts_meta.append({
                "Id": pid,
                "Name": display_name,
            })

        data = {
            "Version": 3,
            "Parameters": params_meta,
            "ParameterGroups": param_groups_meta,
            "Parts": parts_meta,
        }

        if output_path:
            out_file = Path(output_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        return data
```

---

## 3. Deep Dive: Milestone 3 Test Architecture

A robust, multi-tier test suite is essential for preventing regressions, validating binary compliance, and hardening the pipeline against corrupt or edge-case inputs.

```
                                Milestone 3 Test Suite
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            ▼                             ▼                             ▼
tests/test_texture_packer.py    tests/test_moc3_writer.py    tests/test_model3_writer.py
- Empty layer handling          - Header magic & version     - .model3.json schema v3
- Single layer packing          - 64-byte alignment check    - Forward slash path format
- Multi-layer MaxRects binning  - SectionOffsetTable offsets - LipSync & EyeBlink groups
- Power-of-two dimensions       - CountInfoTable counters    - .cdi3.json parameter tree
- Border padding enforcement    - ArtMesh drawables encode   - Parameter group hierarchy
- Edge bleed dilation           - 9-keyform grid tensor      - Non-existent dir creation
- UV recalculation in [0, 1]    - Round-trip parsing         - Error handling & validation
- Pairwise disjointness check   - Invalid input rejection
```

---

### 3.1 Test Architecture for `tests/test_texture_packer.py`

The test suite for `texture_packer.py` verifies the MaxRects 2D bin-packing algorithm, border padding, edge bleed dilation, and UV coordinate remapping.

#### Test Cases Inventory:

| # | Test Method Name | Scenario & Input Condition | Verification Criteria |
| :--- | :--- | :--- | :--- |
| **TP-01** | `test_empty_layer_list_handling` | `layers = []` | Returns valid blank power-of-two RGBA atlas (e.g. $512 \times 512$) and empty UV dict `{}` without crash or zero-division. |
| **TP-02** | `test_transparent_zero_pixel_layers` | Layers with 100% alpha == 0 | Handles gracefully, does not allocate redundant texture area or crash. |
| **TP-03** | `test_single_layer_packing_and_uvs` | Single layer ($128 \times 128$) | Packed with padding; UV rect $(u_{\min}, v_{\min}, u_{\max}, v_{\max}) \in [0.0, 1.0]$; spans match layer aspect ratio. |
| **TP-04** | `test_multi_layer_maxrects_packing` | 5 distinct character layers (Hair, Face, Eyes, Mouth, HairBack) | All 5 layers packed; output atlas width & height $\le \text{max\_atlas\_size}$. |
| **TP-05** | `test_power_of_two_dimension_invariant` | Parametrized across atlas sizes: $512, 1024, 2048, 4096, 8192$ | Atlas width $W$ and height $H$ strictly satisfy $(W \& (W-1) == 0)$ and $(H \& (H-1) == 0)$. |
| **TP-06** | `test_border_padding_enforcement` | Configurable padding $0, 2, 4, 8$ px | Pixel distance between any two placed layer bounding boxes is $\ge \text{padding}$. |
| **TP-07** | `test_edge_bleed_dilation` | Layer with opaque shape surrounded by alpha | 1-2 pixel border outside opaque silhouette duplicates nearest edge color to prevent bilinear filtering black fringe. |
| **TP-08** | `test_uv_coordinate_remapping_precision` | Known local vertex coords $(x_l, y_l)$ mapped to atlas $(u, v)$ | $u = (x_{\text{offset}} + x_l) / W_{\text{atlas}}$, $v = (y_{\text{offset}} + y_l) / H_{\text{atlas}}$; all UVs within $[0.0, 1.0]$. |
| **TP-09** | `test_pairwise_disjointness_overlap_check` | 10 layers with varied aspect ratios | $\forall i \neq j: \text{Rect}_i \cap \text{Rect}_j = \emptyset$ (no overlapping rectangles). |
| **TP-10** | `test_pixel_data_fidelity_transfer` | Distinct colored blocks/gradients | Atlas pixels sampled at mapped UV coordinates exactly match input layer image pixels. |
| **TP-11** | `test_atlas_overflow_handling` | Total layer area exceeds `max_atlas_size` | Raises informative `ValueError` or rescales without memory fault. |

---

### 3.2 Test Architecture for `tests/test_moc3_writer.py`

The test suite for `moc3_writer.py` verifies pure-Python binary serialization, 64-byte alignment, section offset integrity, and 9-keyform Cartesian grid displacement encoding.

#### Test Cases Inventory:

| # | Test Method Name | Scenario & Input Condition | Verification Criteria |
| :--- | :--- | :--- | :--- |
| **MOC-01** | `test_moc3_header_magic_and_version` | Valid `KeyformTable` written to file/bytes | First 4 bytes are `b"MOC3"`, byte 4 is `3` (version 3.0), byte 5 is `0` (Little Endian), header size is 64 bytes. |
| **MOC-02** | `test_64_byte_memory_alignment` | Model with varying number of drawables & vertices | Total binary file size is multiple of 64 (`len(data) % 64 == 0`); all non-zero section offsets in `SectionOffsetTable` satisfy `offset % 64 == 0`. |
| **MOC-03** | `test_section_offset_table_and_bounds` | `SectionOffsetTable` (160 uint32 entries at `0x0040`) | Offsets are non-overlapping and point within the file boundary (`64 <= offset < len(data)`). |
| **MOC-04** | `test_count_info_table_counters` | `CountInfoTable` (23 uint32 entries at `0x0740`) | Counts for `artMeshes`, `parameters`, `artMeshKeyforms`, `keyformPositions`, `uvs`, `positionIndices` match input `KeyformTable` exactly. |
| **MOC-05** | `test_canvas_info_section_parameters` | `CanvasInfo` (at `0x0840`) | Canvas width, height, pixelsPerUnit, originX, originY match canvas configuration. |
| **MOC-06** | `test_artmesh_drawable_serialization` | Drawables with IDs, custom blend modes, draw orders, and culling flags | ArtMesh ID encoded as 64-byte null-padded UTF-8; vertex count, index count, and flags correctly encoded. |
| **MOC-07** | `test_9_keyform_grid_displacement_tensors` | $3 \times 3$ $(\text{Angle X}, \text{Angle Y})$ grid with 9 keyforms | All 9 $(N, 2)$ vertex arrays encoded contiguously; neutral pose $(0, 0)$ matches `base_vertices` exactly. |
| **MOC-08** | `test_parameter_ranges_and_keys_serialization` | `ParamAngleX` $[-30, 0, 30]$, `ParamAngleY` $[-30, 0, 30]$, `ParamAngleZ` $[-20, 0, 20]$ | Parameter IDs, min/default/max bounds, and discrete key arrays correctly written to Parameter and Keys sections. |
| **MOC-09** | `test_round_trip_binary_deserialization_and_validation` | Read back generated `.moc3` binary via parser | Deserialized vertices, UVs, triangle indices, and parameter bounds match input with zero error ($< 10^{-6}$). |
| **MOC-10** | `test_empty_or_corrupt_keyform_table_rejection` | KeyformTable with 0 drawables, NaN coordinates, or invalid UVs | Writer or validator raises `ValueError` before serializing corrupt binary. |

---

### 3.3 Test Architecture for `tests/test_model3_writer.py`

The test suite for `model3_writer.py` verifies master manifest and display info generation.

#### Test Cases Inventory:

| # | Test Method Name | Scenario & Input Condition | Verification Criteria |
| :--- | :--- | :--- | :--- |
| **M3-01** | `test_model3_json_version_and_references` | Standard model name, moc path, texture paths | `Version == 3`, `FileReferences.Moc` and `FileReferences.Textures` properly populated. |
| **M3-02** | `test_strict_forward_slash_path_normalization` | Paths provided with Windows backslashes `\` | Output JSON contains only forward slashes `/` across all references. |
| **M3-03** | `test_standard_lipsync_and_eyeblink_groups` | Default manifest generation | `Groups` array contains `LipSync` with `ParamMouthOpenY` and `EyeBlink` with `ParamEyeLOpen`, `ParamEyeROpen`. |
| **M3-04** | `test_cdi3_json_parameter_hierarchy` | List of standard parameter IDs (`ParamAngleX`, `ParamEyeLOpen`, etc.) | `Version == 3`, parameters mapped to correct `GroupId` and friendly `Name`, `ParameterGroups` populated. |
| **M3-05** | `test_cdi3_json_part_hierarchy` | List of Part IDs (`PartHead`, `PartHair`, `PartFace`) | `Parts` array populated with clean display names. |
| **M3-06** | `test_disk_write_and_directory_creation` | Output path in non-existent nested directory | Creates directory hierarchy automatically and writes valid UTF-8 JSON files. |

---

## 4. Integration Verification & Implementation Plan

### 4.1 Implementation Strategy for M3.2
1. **Module 1 (`src/exporter/texture_packer.py`)**:
   - Implement `MaxRectsPacker` / shelf-packing algorithm.
   - Implement `dilate_edge_bleed(image, mask, radius=2)` to prevent edge filtering seams.
   - Implement UV remapping: $(x_{\text{local}}, y_{\text{local}}) \to (u_{\text{atlas}}, v_{\text{atlas}})$.
2. **Module 2 (`src/exporter/moc3_writer.py`)**:
   - Implement 64-byte Header, SectionOffsetTable (160 uint32 entries), RuntimeAddressMap (1152 bytes null padding), CountInfoTable (256 bytes), CanvasInfo (64 bytes).
   - Implement data arrays: Parts, ArtMeshes, Parameters, Keys, ArtMeshKeyforms, KeyformPositions, UVs, PositionIndices.
   - Enforce 64-byte alignment on all data sections via `pad_buffer_to_64()`.
3. **Module 3 (`src/exporter/model3_writer.py`)**:
   - Implement `generate_model3_json()` and `generate_cdi3_json()` with forward-slash normalization and standard tracking group definitions.
4. **Module 4 (Tests)**:
   - Create `tests/test_texture_packer.py`, `tests/test_moc3_writer.py`, and `tests/test_model3_writer.py`.

---

## 5. Summary of Deliverables & Output Files

| File Path | Component | Status |
| :--- | :--- | :--- |
| `src/exporter/model3_writer.py` | .model3.json & .cdi3.json Metadata Writer | Fully Specified |
| `src/exporter/moc3_writer.py` | Pure-Python .moc3 Binary Writer (64-byte aligned) | Fully Specified |
| `src/exporter/texture_packer.py` | MaxRects Texture Atlas Packer & UV Remapper | Fully Specified |
| `tests/test_texture_packer.py` | Unit & Edge Case Test Suite for Texture Packer | Fully Designed |
| `tests/test_moc3_writer.py` | Unit & Binary Validation Test Suite for Moc3 Writer | Fully Designed |
| `tests/test_model3_writer.py` | Unit Test Suite for Model3 / CDI3 Manifests | Fully Designed |
