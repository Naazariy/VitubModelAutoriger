# Comprehensive Survey & Specification: Live2D Cubism File Formats & Ecosystem Compatibility (R2)

**Author**: Explorer 2 (Live2D File Format & Ecosystem Specialist)  
**Date**: 2026-08-21  
**Target Project**: VitubModel (Automated Geometry-Driven VTuber Model Deformation Engine)  
**Working Directory**: `d:\VitubModel`  

---

## Executive Summary

To achieve **Live2D Ecosystem Compatibility (Requirement R2)**, the output of the automated deformation solver must be programmatically compiled into standard Live2D Cubism runtime assets.

1. **Target Runtime Format**: The standard Live2D runtime bundle consists of:
   - **`*.moc3`** (Model Object Cubism 3/4/5): Compiled flat binary file containing all model topology, meshes (ArtMeshes), deformers, parameter definitions, and deformed vertex keyforms.
   - **`*.model3.json`**: Model manifest JSON referencing the `.moc3`, texture atlases, display info, physics, and semantic groups.
   - **`*.cdi3.json`**: Combined Display Information mapping internal IDs to user-friendly UI display names and parameter groups.
   - **`*.physics3.json`** *(optional)*: Physics pendulum definition for dynamic hair/accessory sway.
   - **`textures/texture_00.png`**: RGBA8 power-of-two texture atlas containing all cropped art mesh textures packed with UV mappings.

2. **Programmatic Export Path**:
   - Generating source `.cmo3` (Cubism Editor Project) is **inadvisable** because `.cmo3` is an obfuscated, proprietary CAFF (Cubism Archive File Format) containing serialized Java internal objects.
   - In contrast, `.moc3` is a **direct flat C-structure memory-mapped binary** designed for zero-copy deserialization in `Live2DCubismCore`.
   - We can construct a lightweight, pure-Python **`.moc3` Binary Builder (`moc3_writer.py`)** with zero external C-dependencies that serializes the exact 64-byte aligned structs, section offset tables, and keyform arrays.
   - The resulting model package is directly loadable into **Live2D Cubism Viewer**, **VTube Studio**, **nizima LIVE**, **Animaze**, **PrprLive**, and any game engine using the **Cubism Native / Web / Unity SDK**.

---

## 1. Deep Dive: The `.moc3` Binary Format Specification

The `.moc3` format is the compiled binary runtime format used by Live2D Cubism 3.0 through 5.0. It is designed to be loaded directly into memory and "revived" in-place by the C library `Live2DCubismCore` via `csmReviveMocInPlace(void* address, unsigned int size)`.

### 1.1 Memory Alignment & Endianness
- **Endianness**: Little-Endian (Standard x86/ARM/WASM). Byte 5 of the header indicates `0` for Little-Endian.
- **MOC Alignment**: `ALIGN_OF_MOC = 64` bytes (`0x40`).
- **Model Alignment**: `ALIGN_OF_MODEL = 16` bytes (`0x10`).
- All major table offsets and string ID allocations are aligned to 4-byte or 64-byte boundaries.

### 1.2 Binary Layout Overview

```
+-------------------------------------------------------------+ 0x0000
| Header (64 bytes)                                           |
|   Magic: "MOC3" (4B) | Version (1B) | Endianness (1B) | Pad |
+-------------------------------------------------------------+ 0x0040
| Section Offset Table (u32 byte offsets to all sections)     |
+-------------------------------------------------------------+ 0x02C0
| Runtime Address Map Padding (0x480 / 1152 bytes)            |
|   (Reserved space overwritten at load-time by Cubism Core)  |
+-------------------------------------------------------------+ 0x0740
| Count Info Table (Counts of parts, meshes, params, keys...) |
+-------------------------------------------------------------+
| Canvas Info Table (pixelsPerUnit, originX, originY, W, H)   |
+-------------------------------------------------------------+
| Section Data Blocks (Offsets referenced by Section Offset)  |
|   - IDs (64-byte fixed char buffers)                        |
|   - Parameter ranges (min, max, default, keys)              |
|   - ArtMesh definitions & flags                             |
|   - UV Coordinates (float32 u, v pairs)                     |
|   - Position Indices (uint16 triangle vertex indices)       |
|   - Keyform Positions (float32 x, y deformed coordinates)   |
|   - Parameter & Keyform Bindings                            |
+-------------------------------------------------------------+ EOF
```

---

### 1.3 Detailed Struct Specifications

#### 1. Header (Offset `0x0000`, 64 bytes)
```c
struct Header {
    char magic[4];          // "MOC3" (0x4D, 0x4F, 0x43, 0x33)
    uint8_t version;        // 1 = Cubism 3.0, 2 = 3.3, 3 = 4.0, 4 = 4.2, 5 = 5.0
    uint8_t isBigEndian;    // 0 = Little-Endian, 1 = Big-Endian
    uint8_t padding[58];    // All zeros (0x00)
};
```
*Recommendation*: Use `version = 3` (Cubism 4.0.00 standard), which provides universal compatibility across all modern viewers, VTube Studio, and Web SDKs without requiring complex Cubism 5 blend-shape tables.

---

#### 2. Canvas Info Table
```c
struct CanvasInfo {
    float pixelsPerUnit;    // Typically 1000.0f to 2000.0f (model unit scale)
    float originX;          // Center X in pixels (e.g., canvasWidth / 2.0f)
    float originY;          // Center Y in pixels (e.g., canvasHeight / 2.0f)
    float canvasWidth;      // Canvas width in pixels (e.g., 2048.0f)
    float canvasHeight;     // Canvas height in pixels (e.g., 2048.0f)
    uint8_t canvasFlags;    // Bit 0: reverseYCoordinate (0 or 1), Bits 1-7: reserved
    uint8_t padding[43];    // 43 zero bytes (aligns struct to 64 bytes)
};
```

---

#### 3. Count Info Table
Defines the element counts for all arrays in the model.
```c
struct CountInfoTable {
    uint8_t padding[128];               // 128 bytes reserved / runtime padding (256 for V5)
    uint32_t parts;                     // Total number of Parts
    uint32_t deformers;                 // Total number of Deformers
    uint32_t warpDeformers;             // Number of Warp Deformers
    uint32_t rotationDeformers;         // Number of Rotation Deformers
    uint32_t artMeshes;                 // Number of ArtMeshes (Drawables)
    uint32_t parameters;                // Number of Parameters (e.g. ParamAngleX/Y/Z)
    uint32_t partKeyforms;              // Number of Part keyforms
    uint32_t warpDeformerKeyforms;      // Number of Warp Deformer keyforms
    uint32_t rotationDeformerKeyforms;  // Number of Rotation Deformer keyforms
    uint32_t artMeshKeyforms;           // Number of ArtMesh keyforms
    uint32_t keyformPositions;          // Total vertex count in keyformPositions array
    uint32_t parameterBindingIndices;   // Number of parameter binding index entries
    uint32_t keyformBindings;           // Number of keyform binding entries
    uint32_t parameterBindings;         // Number of parameter binding entries
    uint32_t keys;                      // Number of key values (e.g. [-30, 0, 30])
    uint32_t uvs;                       // Total UV count (vertexCount * 2 float values)
    uint32_t positionIndices;           // Total triangle index count (triangleCount * 3)
    uint32_t drawableMasks;             // Number of drawable clipping mask references
    uint32_t drawOrderGroups;           // Number of draw order groups
    uint32_t drawOrderGroupObjects;     // Number of draw order group objects
    uint32_t glue;                      // Glue objects count (0 if not used)
    uint32_t glueInfo;                  // Glue info entries count (0 if not used)
    uint32_t glueKeyforms;              // Glue keyforms count (0 if not used)
};
```

---

#### 4. Section Offset Table (Offset `0x0040`)
Contains 32-bit byte offsets (relative to file start `0x0000`) pointing to each array in the data section:

| Offset Field | Target Array Type | Element Count | Description |
| :--- | :--- | :--- | :--- |
| `countInfo` | `CountInfoTable` | 1 | Points to the CountInfoTable struct |
| `canvasInfo` | `CanvasInfo` | 1 | Points to the CanvasInfo struct |
| `parts.ids` | `char[64]` | `parts` | 64-byte null-padded string ID per Part |
| `parts.parentPartIndices` | `int32_t` | `parts` | Parent part index (-1 for root) |
| `artMeshes.ids` | `char[64]` | `artMeshes` | 64-byte string ID (e.g. `ArtMesh_Head`) |
| `artMeshes.parentPartIndices` | `int32_t` | `artMeshes` | Part index containing this ArtMesh |
| `artMeshes.parentDeformerIndices`| `int32_t` | `artMeshes` | Parent deformer index (-1 if direct) |
| `artMeshes.textureNos` | `uint32_t` | `artMeshes` | Texture Atlas Index (`0` for `texture_00.png`) |
| `artMeshes.drawableFlags` | `uint8_t` | `artMeshes` | Bit 0..1: BlendMode, Bit 2: DoubleSided, Bit 3: Inverted |
| `artMeshes.vertexCounts` | `int32_t` | `artMeshes` | Number of vertices in this ArtMesh ($V$) |
| `artMeshes.uvSourcesBeginIndices` | `int32_t` | `artMeshes` | Starting index in `UVs` array |
| `artMeshes.positionIndexSourcesBeginIndices` | `int32_t` | `artMeshes` | Starting index in `PositionIndices` array |
| `artMeshes.positionIndexSourcesCounts` | `int32_t` | `artMeshes` | Triangle indices count ($3 \times \text{Triangles}$) |
| `parameters.ids` | `char[64]` | `parameters` | Parameter IDs (e.g. `ParamAngleX`) |
| `parameters.minValues` | `float` | `parameters` | Minimum parameter value (e.g. `-30.0f`) |
| `parameters.maxValues` | `float` | `parameters` | Maximum parameter value (e.g. `+30.0f`) |
| `parameters.defaultValues` | `float` | `parameters` | Default parameter value (e.g. `0.0f`) |
| `parameters.isRepeat` | `uint32_t` | `parameters` | Repeat/loop flag (`0` for clamp) |
| `parameters.decimalPlaces` | `uint32_t` | `parameters` | Decimal places precision (`1`) |
| `artMeshKeyforms.opacities` | `float` | `artMeshKeyforms` | Opacity per keyform (`1.0f`) |
| `artMeshKeyforms.drawOrders` | `float` | `artMeshKeyforms` | Render depth order (`0.0f` to `1000.0f`) |
| `artMeshKeyforms.keyformPositionSourcesBeginIndices` | `int32_t` | `artMeshKeyforms` | Starting vertex offset in `KeyformPositions` |
| `keyformPositions.xys` | `float[2]` | `keyformPositions` | Pairs of $(x, y)$ deformed vertex positions |
| `uvs.uvs` | `float[2]` | `uvs` | Pairs of $(u, v)$ texture coordinates |
| `positionIndices.indices` | `uint16_t` | `positionIndices` | Triangle vertex connectivity indices |
| `keys.values` | `float` | `keys` | Key values for parameters (e.g. `-30.0, 0.0, 30.0`) |

---

### 1.4 How Keyform Deformations Are Bound to Parameters

Live2D uses a multi-dimensional keyform grid.
For a single ArtMesh controlled by 2 parameters (`ParamAngleX` and `ParamAngleY`):
- `ParamAngleX` has 3 keys: `[-30.0, 0.0, 30.0]` ($N_x = 3$)
- `ParamAngleY` has 3 keys: `[-30.0, 0.0, 30.0]` ($N_y = 3$)
- Total Keyforms for this ArtMesh = $N_x \times N_y = 3 \times 3 = 9$ keyforms.

The 9 keyforms are stored sequentially in the `artMeshKeyforms` array:

| Keyform Index | ParamAngleX | ParamAngleY | State Description | Keyform Vertex Positions |
| :---: | :---: | :---: | :--- | :--- |
| **0** | $-30^\circ$ | $-30^\circ$ | Looking Bottom-Left | $\mathbf{P}' = \mathbf{R}(-30, -30) \mathbf{V}$ |
| **1** | $-30^\circ$ | $0^\circ$ | Looking Left | $\mathbf{P}' = \mathbf{R}(-30, 0) \mathbf{V}$ |
| **2** | $-30^\circ$ | $+30^\circ$ | Looking Top-Left | $\mathbf{P}' = \mathbf{R}(-30, +30) \mathbf{V}$ |
| **3** | $0^\circ$ | $-30^\circ$ | Looking Down | $\mathbf{P}' = \mathbf{R}(0, -30) \mathbf{V}$ |
| **4** | $0^\circ$ | $0^\circ$ | **Rest / Neutral Pose** | $\mathbf{P}' = \mathbf{V}^{(0)}$ (Original 2D Mesh) |
| **5** | $0^\circ$ | $+30^\circ$ | Looking Up | $\mathbf{P}' = \mathbf{R}(0, +30) \mathbf{V}$ |
| **6** | $+30^\circ$ | $-30^\circ$ | Looking Bottom-Right | $\mathbf{P}' = \mathbf{R}(+30, -30) \mathbf{V}$ |
| **7** | $+30^\circ$ | $0^\circ$ | Looking Right | $\mathbf{P}' = \mathbf{R}(+30, 0) \mathbf{V}$ |
| **8** | $+30^\circ$ | $+30^\circ$ | Looking Top-Right | $\mathbf{P}' = \mathbf{R}(+30, +30) \mathbf{V}$ |

For each of the 9 keyforms, the mathematical engine calculates the $(x_i, y_i)$ 2D projected coordinates for all $V$ vertices and writes them into `keyformPositions`. During runtime, Cubism Core performs bilinear/bicubic polynomial interpolation between these 9 states smoothly in real time.

---

## 2. Specification of Model Configuration & Metadata Files

### 2.1 `.model3.json` Specification

The `.model3.json` file is the master manifest read by VTube Studio, Cubism Viewer, and SDK runtimes.

```json
{
  "Version": 3,
  "FileReferences": {
    "Moc": "character.moc3",
    "Textures": [
      "textures/texture_00.png"
    ],
    "Physics": "character.physics3.json",
    "DisplayInfo": "character.cdi3.json",
    "UserData": ""
  },
  "Groups": [
    {
      "Target": "Parameter",
      "Name": "EyeBlink",
      "Ids": [
        "ParamEyeLOpen",
        "ParamEyeROpen"
      ]
    },
    {
      "Target": "Parameter",
      "Name": "LipSync",
      "Ids": [
        "ParamMouthOpenY"
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
  ]
}
```

---

### 2.2 `.cdi3.json` Specification (Combined Display Information)

The `.cdi3.json` file provides human-readable labels and UI categorization for Cubism Editor, Cubism Viewer, and VTube Studio settings palettes:

```json
{
  "Version": 3,
  "Parameters": [
    {
      "Id": "ParamAngleX",
      "GroupId": "ParamGroupHead",
      "Name": "Head Angle X"
    },
    {
      "Id": "ParamAngleY",
      "GroupId": "ParamGroupHead",
      "Name": "Head Angle Y"
    },
    {
      "Id": "ParamAngleZ",
      "GroupId": "ParamGroupHead",
      "Name": "Head Angle Z"
    },
    {
      "Id": "ParamEyeLOpen",
      "GroupId": "ParamGroupEyes",
      "Name": "Left Eye Open"
    },
    {
      "Id": "ParamEyeROpen",
      "GroupId": "ParamGroupEyes",
      "Name": "Right Eye Open"
    },
    {
      "Id": "ParamMouthOpenY",
      "GroupId": "ParamGroupMouth",
      "Name": "Mouth Open Y"
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
    }
  ],
  "Parts": [
    {
      "Id": "PartHead",
      "Name": "Head & Face"
    },
    {
      "Id": "PartHair",
      "Name": "Hair"
    },
    {
      "Id": "PartBody",
      "Name": "Body"
    }
  ]
}
```

---

### 2.3 `.physics3.json` Specification (Dynamic Sway / Physics)

Enables automatic physics reactions (e.g. hair strands swinging when head turns).

```json
{
  "Version": 3,
  "Meta": {
    "PhysicsSettingCount": 1,
    "TotalInputCount": 2,
    "TotalOutputCount": 1,
    "VertexCount": 2,
    "EffectiveForces": {
      "Gravity": { "X": 0.0, "Y": -1.0 },
      "Wind": { "X": 0.0, "Y": 0.0 }
    },
    "Fps": 60.0
  },
  "PhysicsSettings": [
    {
      "Id": "PhysicsHairFront",
      "Input": [
        {
          "Source": { "Target": "Parameter", "Id": "ParamAngleX" },
          "Weight": 60.0,
          "Type": "X",
          "Reflect": false
        },
        {
          "Source": { "Target": "Parameter", "Id": "ParamAngleZ" },
          "Weight": 40.0,
          "Type": "Angle",
          "Reflect": false
        }
      ],
      "Output": [
        {
          "Destination": { "Target": "Parameter", "Id": "ParamHairFront" },
          "VertexIndex": 1,
          "Scale": 1.0,
          "Weight": 100.0,
          "Type": "Angle",
          "Reflect": false
        }
      ],
      "Vertices": [
        {
          "Position": { "X": 0.0, "Y": 0.0 },
          "Mobility": 1.0,
          "Delay": 0.8,
          "Acceleration": 1.5,
          "Radius": 20.0
        },
        {
          "Position": { "X": 0.0, "Y": 15.0 },
          "Mobility": 0.95,
          "Delay": 0.85,
          "Acceleration": 1.5,
          "Radius": 20.0
        }
      ],
      "Normalization": {
        "Position": { "Minimum": -10.0, "Default": 0.0, "Maximum": 10.0 },
        "Angle": { "Minimum": -10.0, "Default": 0.0, "Maximum": 10.0 }
      }
    }
  ]
}
```

---

## 3. Standard Live2D Parameter Dictionary & VTube Studio Mapping

To ensure **zero-configuration auto-detection** in VTube Studio, nizima LIVE, and Animaze, the generated model must adhere to the standard parameter naming convention:

| Standard Parameter ID | Name | Min | Default | Max | VTube Studio Tracking Input |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **`ParamAngleX`** | Head Angle X | -30.0 | 0.0 | +30.0 | Face Yaw (Head Left/Right) |
| **`ParamAngleY`** | Head Angle Y | -30.0 | 0.0 | +30.0 | Face Pitch (Head Up/Down) |
| **`ParamAngleZ`** | Head Angle Z | -30.0 | 0.0 | +30.0 | Face Roll (Head Tilt) |
| **`ParamEyeLOpen`** | Left Eye Open | 0.0 | 1.0 | 1.0 | Eye Open Left |
| **`ParamEyeROpen`** | Right Eye Open | 0.0 | 1.0 | 1.0 | Eye Open Right |
| **`ParamEyeBallX`** | Eye Ball X | -1.0 | 0.0 | +1.0 | Eye Gaze X |
| **`ParamEyeBallY`** | Eye Ball Y | -1.0 | 0.0 | +1.0 | Eye Gaze Y |
| **`ParamBrowLY`** | Left Eyebrow Y | -1.0 | 0.0 | +1.0 | Eyebrow Height Left |
| **`ParamBrowRY`** | Right Eyebrow Y | -1.0 | 0.0 | +1.0 | Eyebrow Height Right |
| **`ParamMouthForm`** | Mouth Form | -1.0 | 0.0 | +1.0 | Mouth Smile / Frown |
| **`ParamMouthOpenY`**| Mouth Open Y | 0.0 | 0.0 | 1.0 | Mouth Open (Jaw Drop / Voice Lip-sync) |
| **`ParamBodyAngleX`**| Body Angle X | -10.0 | 0.0 | +10.0 | Body Yaw |
| **`ParamBodyAngleY`**| Body Angle Y | -10.0 | 0.0 | +10.0 | Body Pitch |
| **`ParamBodyAngleZ`**| Body Angle Z | -10.0 | 0.0 | +10.0 | Body Roll |
| **`ParamBreath`** | Breathing | 0.0 | 0.0 | 1.0 | Idle Breathing Cycle |
| **`ParamHairFront`** | Hair Front Sway | -1.0 | 0.0 | +1.0 | Physics Hair Sway |

---

## 4. Texture Atlas Generation & UV Coordinate Mapping

Live2D renders ArtMeshes by sampling from one or more 2D texture atlases.

### 4.1 Requirements & Best Practices
1. **Dimensions**: Power-of-two dimensions (e.g., $2048 \times 2048$ or $4096 \times 4096$).
2. **Color Format**: 32-bit RGBA PNG (`PNG8` with Alpha or 32-bit TrueColor RGBA).
3. **Bleed / Padding Margin**: 2 to 4 pixels of dilation (extending edge colors into transparent borders) around each bounding box. This prevents dark or transparent fringing during bilinear/trilinear texture filtering and mipmapping.
4. **Packing Algorithm**: MaxRects 2D Bin Packing (BSSF - Best Short Side Fit) or Guillotine shelf bin packing to maximize packing efficiency ($> 85\%$).

### 4.2 UV Coordinate Conversion Math

Let an ArtMesh bounding box be placed in the texture atlas at pixel coordinates $(X_{\text{atlas}}, Y_{\text{atlas}})$ with width $W_{\text{box}}$ and height $H_{\text{box}}$ inside an atlas of size $W_{\text{tex}} \times H_{\text{tex}}$.

For a local vertex $(x_i, y_i)$ normalized within the bounding box $[0, 1] \times [0, 1]$:
$$u_i = \frac{X_{\text{atlas}} + x_i \cdot W_{\text{box}}}{W_{\text{tex}}}$$
$$v_i = \frac{Y_{\text{atlas}} + y_i \cdot H_{\text{box}}}{H_{\text{tex}}}$$

*Note on Live2D UV Orientation*: Live2D Cubism uses top-left origin for UV coordinates ($u \in [0, 1]$ left-to-right, $v \in [0, 1]$ top-to-bottom), which matches standard image/PIL pixel coordinates directly without vertical inversion.

---

## 5. Evaluation of Tooling & Ecosystem Libraries

| Solution / Library | Language | Read Support | Write / Generate Support | Assessment for VitubModel |
| :--- | :---: | :---: | :---: | :--- |
| **Official Live2D Cubism Core C SDK** | C / C++ | ✅ Full | ❌ Read-Only runtime | Proprietary closed-source binary blob. Can be used for runtime validation and headless verification. Cannot write `.moc3`. |
| **`live2d-py`** (Arkueid) | Python / C++ | ✅ Full | ❌ Read-Only | Excellent wrapper around Cubism Native SDK for loading, parameter setting, and OpenGL rendering tests in Python. |
| **`MOC3ingbird` / `moc3.hexpat`** | ImHex Pattern | ✅ Complete | N/A (Spec) | Provides exact binary layout and struct definitions for .moc3 v3/v4/v5 reverse engineering. |
| **Inochi2D (`.inp`)** | D / Rust / C | ✅ Full | ✅ Full | Open-source alternative 2D puppet format. Not natively supported by Live2D Cubism Viewer or standard VTube Studio without custom plugins. |
| **Editor `.cmo3` Exporter** | Java / CAFF | ❌ Proprietary | ❌ Complex / Obfuscated | CAFF encrypted archive with serialized Java UI objects. Reverse engineering .cmo3 is extremely brittle and unnecessary. |
| **Pure-Python `.moc3` Binary Builder (`moc3_writer.py`)** | Python (Standard Library + NumPy) | ✅ Full | ✅ **Full Direct Generation** | **Recommended Optimal Path**: Clean, fast, zero C++ build dependencies, directly serializes exact .moc3 structs and outputs files loaded natively by VTube Studio and Cubism Viewer. |

---

## 6. End-to-End Programmatic Export Pipeline

The complete export pipeline for VitubModel connects the Geometry Engine directly to the Live2D runtime exporter:

```
[Input: PSD / PNG Layers]
         │
         ▼
[Mesh Generator (Delaunay 2D Triangulation)] ──► Vertices V, Triangles T
         │
         ▼
[Depth Model + Geometry Engine] ───────────────► 3D Surface Normals N, Curvature, Depth Z
         │
         ▼
[Deformation Solver + Constraint Solver] ──────► 9 Keyform Coordinate Sets P'(AngleX, AngleY)
         │
         ├───────────────────────────────────────────────────────┐
         ▼                                                       ▼
[Texture Atlas Packer (texture_packer.py)]           [Moc3 Serializer (moc3_writer.py)]
  - Packs layer textures into 2048x2048 PNG             - Writes 64B Header & 0x480 Pad
  - Generates normalized UV coords                     - Writes Section Offset Table
  - Outputs `textures/texture_00.png`                   - Writes CountInfo & CanvasInfo
         │                                              - Writes ArtMeshes & 9 Keyforms
         │                                              - Outputs `model.moc3`
         └───────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
                    [JSON Writers (json_writer.py)]
                      - Outputs `model.model3.json`
                      - Outputs `model.cdi3.json`
                      - Outputs `model.physics3.json`
                                 │
                                 ▼
                     [Model Output Directory]
                      ├── model.model3.json
                      ├── model.moc3
                      ├── model.cdi3.json
                      ├── model.physics3.json
                      └── textures/
                          └── texture_00.png
                                 │
                                 ▼
               [Verification & Direct User Loading]
                - Automated schema & binary validation script
                - Load directly in Live2D Cubism Viewer
                - Drop into VTube Studio `Live2DModels/` folder
```

---

## 7. Verification Method & Acceptance Criteria

### 7.1 Automated Structural Validation Script (`validate_model.py`)
The verification script checks:
1. **Magic & Header Integrity**: Verifies first 4 bytes are `'M','O','C','3'`, version $\in \{1, 2, 3, 4, 5\}$, endianness is `0`, and padding is zeroed.
2. **Alignment & Padding**: Verifies file size is multiple of 4 bytes, runtime padding table at `0x02C0` spans `0x480` bytes.
3. **Offset Bounds Checking**: Verifies all offsets in `SectionOffsetTable` point to valid memory locations within the file.
4. **Vertex & Keyform Consistency**: Confirms `keyformPositions` count equals $\text{artMeshes} \times 9 \times V$.
5. **JSON Schema Compliance**: Validates `.model3.json` and `.cdi3.json` syntax and relative file references.
6. **Live2DCubismCore Headless Load** *(when `live2d-py` or SDK is present)*: Executes `csmReviveMocInPlace` and `csmInitializeModel` to ensure zero runtime errors.

### 7.2 Manual Visual Inspection Guide for End User
1. **Cubism Viewer**:
   - Launch **Live2D Cubism Viewer (for OW)**.
   - Drag and drop `model.model3.json` into the viewer window.
   - Adjust `ParamAngleX` ($-30^\circ \dots +30^\circ$) and `ParamAngleY` ($-30^\circ \dots +30^\circ$) sliders to confirm seamless 3D head rotation.
2. **VTube Studio**:
   - Copy the output model folder to `C:\Users\<User>\AppData\LocalLow\DenchiSoft\VTube Studio\Live2DModels\<ModelFolder>`.
   - Start VTube Studio, select the model from the model picker, and choose "Auto-setup".
   - Turn head left/right/up/down in front of the webcam; VTube Studio automatically tracks head movement using `ParamAngleX` and `ParamAngleY`.

---
