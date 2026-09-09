# Walkthrough: Live2D Model Generation & Verification Guide

Welcome to the automated 2D-to-Live2D conversion pipeline. This tool automatically ingests 2D character artwork (layered PSDs, PNG images, or layer directories) and generates fully rigged, keyform-complete Live2D Cubism 3.0+ model bundles (`.moc3`, `.model3.json`, `.cdi3.json`, and packed texture atlases) with mathematical 3D head rotation keyforms (`ParamAngleX`, `ParamAngleY`, `ParamAngleZ`). No manual rigging or keyframe placement in Cubism Editor is required.

---

## 1. Quick Start & Prerequisites

### System Prerequisites
- Python 3.10, 3.11, 3.12, 3.13, or 3.14
- Virtual environment setup:
  ```powershell
  # Windows PowerShell
  python -m venv venv
  .\venv\Scripts\activate
  pip install -r requirements.txt
  ```

### Generate Live2D Model via CLI
To convert a single PNG or a layered PSD into a Live2D model bundle:

```bash
# Convert a single PNG image
python export_live2d.py sample_character.png -o ./output -n AvatarModel --validate

# Convert a layered Photoshop PSD
python export_live2d.py character.psd -o ./output -n Kohaku --resolution 4096 --validate

# Convert a folder of layer PNGs
python export_live2d.py ./character_layers/ -o ./output -n Kohaku --validate
```

### Python API Integration
```python
from pathlib import Path
from src.cli.main import PipelineConfig, PipelineRunner

# Configure pipeline
config = PipelineConfig(
    input_path="character.psd",
    output_dir="./output",
    model_name="Kohaku",
    atlas_size=4096,
    grid_size=25,
    validate=True
)

# Execute export
runner = PipelineRunner(config)
exit_code = runner.run()
assert exit_code == 0
```

### Generated Output Bundle Structure
The exporter outputs a clean, standards-compliant Live2D model directory:
```
output/
└── Kohaku/
    ├── Kohaku.model3.json      # Master runtime manifest
    ├── Kohaku.moc3             # Pure-Python compiled Live2D binary model
    ├── Kohaku.cdi3.json        # Display information & parameter groups
    └── Kohaku.4096/            # Texture atlas directory
        └── texture_00.png      # Power-of-two RGBA texture atlas
```

---

## 2. CLI Reference & Configuration

### Command-Line Arguments

| Flag | Shorthand | Type | Default | Description |
|---|---|---|---|---|
| `input_path` | Positional | `str` | *Required* | Path to input `.psd`, `.png`, or directory of layer PNGs |
| `--output` | `-o` | `str` | `./output` | Destination output root directory |
| `--name` | `-n` | `str` | `Input stem` | Character model name (used for file prefixes) |
| `--resolution` | `--atlas-size` | `int` | `4096` | Texture atlas dimension (POT: 512, 1024, 2048, 4096, 8192) |
| `--grid-size` | `--mesh-density`| `int` | `25` | Delaunay mesh triangulation grid spacing in pixels (smaller = finer mesh) |
| `--angle-x-range` | | `str` | `"-30.0,30.0"` | Yaw rotation angle range (min, max in degrees) |
| `--angle-y-range` | | `str` | `"-30.0,30.0"` | Pitch rotation angle range (min, max in degrees) |
| `--angle-z-range` | | `str` | `"-20.0,20.0"` | Roll rotation angle range (min, max in degrees) |
| `--keyforms-x` | | `int` | `3` | Number of keyforms along Angle X axis (default: 3 for min, 0, max) |
| `--keyforms-y` | | `int` | `3` | Number of keyforms along Angle Y axis (default: 3 for min, 0, max) |
| `--keyforms-z` | | `int` | `3` | Number of keyforms along Angle Z axis (default: 3 for min, 0, max) |
| `--auto-depth` | | `bool`| `True` | Automatically calculate 3D ellipsoidal depth maps |
| `--auto-stiffness`| | `bool`| `True` | Automatically compute ARAP regularization stiffness maps |
| `--validate` | | `flag`| `False` | Run full 6-stage structural validation post-export |
| `--quiet` | `-q` | `flag`| `False` | Suppress non-error console logs |
| `--verbose` | `-v` | `flag`| `False` | Print detailed debug tracing and timings |
| `--json-output` | | `flag`| `False` | Emit structured JSON execution summary |

### Standardized Exit Codes

| Exit Code | Constant | Meaning | Troubleshooting |
|---|---|---|---|
| **0** | `EXIT_SUCCESS` | Model generated and validated successfully | Ready for Cubism Viewer / VTube Studio |
| **1** | `EXIT_ERR_INPUT` | Invalid CLI syntax, missing args, or missing input file | Check input file path and arguments |
| **2** | `EXIT_ERR_MESH` | Mesh triangulation or contour extraction error | Adjust `--grid-size` or alpha mask threshold |
| **3** | `EXIT_ERR_DEFORMATION`| 3D deformation solve or ARAP regularization failure | Check layer depth settings and angle ranges |
| **4** | `EXIT_ERR_EXPORT` | Texture packer or `.moc3` writer IO failure | Check disk space and folder write permissions |
| **5** | `EXIT_ERR_VALIDATION`| Structural validation failed (`--validate`) | Run `python validate_live2d.py <model_dir>` |

---

## 3. Programmatic 6-Stage Structural Validation

The standalone validator inspects the generated model bundle across 6 rigorous quality gates.

### Run Validation Manually
```bash
# Validate specific .model3.json manifest
python validate_live2d.py ./output/Kohaku/Kohaku.model3.json

# Validate entire model folder
python validate_live2d.py ./output/Kohaku/

# Output JSON report
python validate_live2d.py ./output/Kohaku/ -o report.json --quiet
```

### The 6 Validation Stages

1. **Stage 1: Binary MOC3 Header Integrity**:
   - Magic bytes `b"MOC3"` (0x4D 0x4F 0x43 0x33).
   - Version 3.0+ compliance and Little-Endian format indicator (byte 5 == 0).
   - Header minimum size $\ge 64$ bytes.

2. **Stage 2: Section Table Offsets & Count Table Sanity**:
   - All active section offsets in the 160-entry table at 0x40 are strictly aligned to 64-byte boundaries (`offset % 64 == 0`).
   - Monotonic offset ordering and physical file boundary bounds.
   - CountInfoTable at 0x0740: non-zero counts for art meshes, parameters, UVs, and triangle position indices.

3. **Stage 3: JSON Manifest & File Reference Conformance**:
   - `.model3.json` and `.cdi3.json` conform to Cubism 3 JSON schema.
   - All relative file paths are forward-slash normalized (`/`) without Windows backslashes (`\`).
   - Referenced `.moc3` binary and all texture `.png` files exist on disk.

4. **Stage 4: Parameter & Keyform Bounds Verification**:
   - Standard tracking parameters present: `ParamAngleX`, `ParamAngleY`, `ParamAngleZ`.
   - Bounds invariant check: `min <= default <= max`.
   - Monotonic key value sequences and 3x3=9 keyform grid tensors.

5. **Stage 5: Texture Atlas & UV Coordinate Safety**:
   - Dimensions are exact powers-of-two (POT): $512 \le W, H \le 8192$.
   - 4-channel 32-bit RGBA image format with valid PNG headers.
   - UV coordinates strictly normalized within $[0.0, 1.0]$.

6. **Stage 6: Topological Non-Inversion & Deformation Continuity**:
   - Strictly positive signed triangle areas ($A_{\text{signed}} > -10^{-4}$) across all 9 Angle X/Y keyforms.
   - Zero `NaN` or `Inf` floating-point coordinates in vertex displacement tables.
   - Bounded displacement limits without geometric explosion.

### Sample Console Output
```
======================================================================
             LIVE2D 6-STAGE STRUCTURAL VALIDATION REPORT              
======================================================================
Model Target : d:\VitubModel\output\Kohaku\Kohaku.model3.json
Model Name   : Kohaku
Overall Status: [PASSED] (Errors: 0, Warnings: 0)
----------------------------------------------------------------------
 Stage 1: [PASS] Binary MOC3 Header Integrity
   ✔ Details: magic=MOC3, version=3, endianness=little-endian, file_size_bytes=184576
 Stage 2: [PASS] Section Table Offsets & Count Table Sanity
   ✔ Details: active_sections=18, parts=1, art_meshes=14, parameters=3
 Stage 3: [PASS] JSON Manifest & File Reference Conformance
   ✔ Details: version=3, moc_file=Kohaku.moc3, texture_count=1
 Stage 4: [PASS] Parameter & Keyform Bounds Verification
   ✔ Details: parameters_found=['ParamAngleX', 'ParamAngleY', 'ParamAngleZ']
 Stage 5: [PASS] Texture Atlas & UV Coordinate Safety
   ✔ Details: texture_dimensions=[(4096, 4096)]
 Stage 6: [PASS] Topological Non-Inversion & Deformation Continuity
   ✔ Details: total_triangles_checked=23760, inverted_triangles_found=0
======================================================================
```

---

## 4. Visual Verification in Live2D Cubism Viewer

Live2D Cubism Viewer (for OW) is the official tool for testing Live2D runtime models.

### Step 1: Load the Model
1. Launch **Live2D Cubism Viewer (for OW)**.
2. Open File Explorer and navigate to your exported model folder (e.g. `output/Kohaku/`).
3. Drag and drop `Kohaku.model3.json` directly into the Cubism Viewer viewport.
4. The model will load immediately.

### Step 2: Verify Initial Rendering
- Confirm that character textures render cleanly without black fringes or missing parts.
- Check layer sorting: front hair should occlude eyebrows/eyes, eyes occlude face skin, and hair back renders behind.

### Step 3: Parameter Slider Verification
In the **Parameter Palette** (left sidebar):

1. **`ParamAngleX` (Head Yaw: Left $\leftrightarrow$ Right)**:
   - Drag the slider between `-30.0` and `+30.0`.
   - **Expected behavior**: The head turns horizontally. The turned-away cheek compresses due to anime foreshortening, and foreground hair exhibits depth parallax over the face skin.
2. **`ParamAngleY` (Head Pitch: Down $\leftrightarrow$ Up)**:
   - Drag the slider between `-30.0` and `+30.0`.
   - **Expected behavior**: The face tilts up and down smoothly with perspective scaling.
3. **`ParamAngleZ` (Head Roll: Tilt Left $\leftrightarrow$ Tilt Right)**:
   - Drag the slider between `-20.0` and `+20.0`.
   - **Expected behavior**: The head tilts smoothly clockwise and counter-clockwise.

### Step 4: 2D Cartesian Yaw-Pitch Diagonal Sweep
- Click and drag inside the 2D parameter box linking Angle X and Angle Y across all four diagonal corners:
  * Top-Left (`AngleX = -30°, AngleY = +30°`)
  * Top-Right (`AngleX = +30°, AngleY = +30°`)
  * Bottom-Left (`AngleX = -30°, AngleY = -30°`)
  * Bottom-Right (`AngleX = +30°, AngleY = -30°`)
- **Expected behavior**: Smooth bilinear deformation interpolation without mesh folding or triangle inversion.

---

## 5. Model Deployment & Tracking in VTube Studio

VTube Studio is the industry-standard VTuber face-tracking application.

### Step 1: Locate the Live2D Models Directory
Navigate to the VTube Studio streaming assets directory on your system:
- **Windows (Steam default)**:
  `C:\Program Files (x86)\Steam\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels\`
- **Windows (Standalone)**:
  `<VTube Studio Folder>\VTube Studio_Data\StreamingAssets\Live2DModels\`
- **macOS**:
  `~/Library/Application Support/Steam/steamapps/common/VTube Studio/VTube Studio.app/Contents/Resources/Data/StreamingAssets/Live2DModels/`

### Step 2: Install Model Folder
1. Copy the entire model folder (`output/Kohaku/`) into `Live2DModels/`.
2. Ensure the internal directory structure is intact:
   ```
   Live2DModels/
   └── Kohaku/
       ├── Kohaku.model3.json
       ├── Kohaku.moc3
       ├── Kohaku.cdi3.json
       └── Kohaku.4096/
           └── texture_00.png
   ```

### Step 3: Load Model in VTube Studio
1. Launch **VTube Studio**.
2. Double-click the screen to open the menu, then click the **Avatar Icon** (top left).
3. Select your model (`Kohaku`) from the list.
4. When prompted: *"Auto-setup default tracking parameters?"*, click **Yes (Auto-Setup)**.

### Step 4: Verify Face Tracking
1. Open the **Settings (Gear Icon)** $\rightarrow$ **Camera Tracking Tab**.
2. Start your webcam or connect your iOS device via VTube Studio Mobile.
3. Turn your head left/right, up/down, and tilt left/right.
4. Verify that:
   - `FaceAngleX` drives `ParamAngleX`.
   - `FaceAngleY` drives `ParamAngleY`.
   - `FaceAngleZ` drives `ParamAngleZ`.

---

## 6. Parameter Slider Verification Matrix

| Parameter ID | Display Name | Value Range | Default | Expected Visual Deformation Behavior |
|---|---|---|---|---|
| `ParamAngleX` | Angle X (Yaw) | `[-30.0, 30.0]` | `0.0` | Horizontal head rotation with depth parallax and foreshortening |
| `ParamAngleY` | Angle Y (Pitch) | `[-30.0, 30.0]` | `0.0` | Vertical head tilt with facial feature perspective shift |
| `ParamAngleZ` | Angle Z (Roll) | `[-20.0, 20.0]` | `0.0` | In-plane head roll rotation clockwise and counter-clockwise |
| `ParamEyeLOpen` | Eye L Open | `[0.0, 1.0]` | `1.0` | Left eye blink / open parameter mapping |
| `ParamEyeROpen` | Eye R Open | `[0.0, 1.0]` | `1.0` | Right eye blink / open parameter mapping |
| `ParamMouthOpenY`| Mouth Open | `[0.0, 1.0]` | `0.0` | Mouth vertical opening for LipSync |

---

## 7. Visual Defect Troubleshooting Guide

### 1. Texture Bleeding / Dark Border Lines
- **Symptom**: Dark or discolored outlines around layer contours.
- **Cause**: UV coordinates sampling transparent pixels outside the layer content due to bilinear filtering.
- **Solution**: The exporter automatically applies **Voronoi Color Bleed Dilation** (`--bleed-radius 2`). If needed, increase padding:
  ```bash
  python export_live2d.py character.psd --padding 8 --bleed-radius 4
  ```

### 2. Inverted Polygons / Black Geometry Glitches
- **Symptom**: Triangles flip or pinch during extreme head rotations (AngleX = ±30°).
- **Cause**: Mesh vertex displacement exceeded the local triangle geometry limit.
- **Solution**: Increase triangulation mesh density (smaller grid spacing):
  ```bash
  python export_live2d.py character.psd --grid-size 15 --angle-x-range "-25.0,25.0"
  ```

### 3. Layer Clipping / Incorrect Z-Order
- **Symptom**: Eyeballs render behind face skin, or bangs render behind the head.
- **Cause**: Semantic layer name was not recognized, causing incorrect Z-depth stratification.
- **Solution**: Use standard layer names in your PSD:
  - Hair Front: `Hair_Front`, `Bangs`, `前髪`
  - Eyes: `Eye_L`, `Eye_R`, `左目`, `右目`
  - Face: `Face`, `Skin`, `顔`, `輪郭`
  - Hair Back: `Hair_Back`, `後ろ髪`

### 4. Model Appears Black or Texture Missing
- **Symptom**: Model loads as a black/white silhouette without textures.
- **Cause**: Texture dimensions are not powers-of-two, or `.model3.json` used Windows backslashes (`\`).
- **Solution**: The pipeline strictly enforces power-of-two textures (512, 1024, 2048, 4096, 8192) and forward-slash paths (`/`). Run `python validate_live2d.py <model_dir>` to check Stage 3 and Stage 5.
