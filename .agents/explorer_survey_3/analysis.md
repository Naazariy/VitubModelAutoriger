# In-Depth Survey & Specifications: CLI, Validation System & E2E Testing Architecture

**Author**: Explorer 3 (CLI, Validation & E2E Testing Specialist)  
**Date**: 2026-08-21  
**Target Project**: Automated VTuber Deformation & Live2D Export Tool (`d:\VitubModel`)  
**Scope**: CLI Specification, Programmatic Validator Architecture, Live2D Viewer / VTube Studio Verification Guide, and 4-Tier E2E Testing Infrastructure.

---

## 1. Executive Summary & Codebase Audit

### 1.1 Project Context & Objective
The goal is to build an automated software tool that generates keyframe-free 3D-like head deformations (`AngleX`, `AngleY`, `AngleZ`) for 2D VTuber assets (PSD, PNG, or folder of layers) and exports a production-ready model bundle fully compatible with the **Live2D Cubism** standard (`.moc3`, `.model3.json`, texture atlas) and **VTube Studio**, requiring zero manual keyform rigging.

### 1.2 Current Codebase Audit Findings
An audit of the existing codebase (`src/` and `tests/`) revealed the following:
1. **Core Math Pipeline Implemented**:
   - `src/core/`: `Vertex` and `Mesh` data structures managing positions, normals, depths, stiffnesses, and connectivity.
   - `src/importer/`: `ImageImporter` providing PNG loading, alpha thresholding, contour extraction, and synthetic head generation.
   - `src/depth/`: `DepthModel` providing ellipsoidal proxy depth $z(x,y)$ and regional stratification.
   - `src/geometry/`: `GeometryEngine` computing 3D unit surface normals and mean surface curvatures.
   - `src/deformation/`: `DeformationSolver` implementing 3D rotation ($R_y, R_x$) and 2.5D parallax projection. *Note: currently only implements AngleX and AngleY; AngleZ (Roll $R_z$) must be added.*
   - `src/constraints/`: `MassSpringConstraintSolver` implementing As-Rigid-As-Possible (ARAP) + bending spring optimization with cached sparse LU factorization (`scipy.sparse.linalg.splu`).
   - `src/renderer/`: `MeshRenderer` for desktop preview with OpenGL depth testing.
   - `src/ai/`: `AIAssistant` heuristic distance transform depth & edge-density stiffness estimation.
   - `src/gui/`: `MainWindow` PySide6 desktop GUI with preview sliders.
2. **Missing Components Needed for Production Live2D Export**:
   - **Automated Zero-Intervention CLI**: No command-line interface exists for automated batch or headless model generation from PSD/PNG files.
   - **Live2D File Format Exporter**: The existing prototype contains only an export stub in GUI; no serialization exists for binary `.moc3`, `.model3.json`, `.cdi3.json`, or packed texture atlases.
   - **Programmatic Structural Validator**: No standalone or automated validation script exists to verify `.moc3` binary headers, JSON schemas, parameter bounds, UV bounds, and mesh non-inversion.
   - **Live2D Viewer & VTube Studio Verification Guide**: No formal step-by-step user testing guide exists.
   - **E2E Testing Harness**: Current unit tests cover internal math components, but lack end-to-end integration and multi-tier coverage (CLI, boundary conditions, cross-feature combinations, and full model lifecycle).
3. **Environment & Dependency Observation**:
   - Python 3.14.6 environment lacks compiled C-extensions for `triangle`. Attempting to run `pytest` fails with `ModuleNotFoundError: No module named 'triangle'`.
   - `scipy.spatial.Delaunay` is already installed and fully available (`scipy 1.18.0`). Replacing/providing fallback to `scipy.spatial.Delaunay` in `MeshGenerator` ensures 100% reliable execution without native compilation dependencies.

---

## 2. Automated Zero-Intervention CLI Specification

### 2.1 CLI Architecture & Invocations
The CLI must execute headlessly and complete the full asset ingestion, mesh generation, 3D deformation solving, texture packing, and Live2D model export without any interactive prompt or GUI window.

#### Supported Invocation Syntaxes:
```bash
# Package module invocation
python -m src.cli [OPTIONS] <input_path>

# Dedicated entry script invocation
python export_live2d.py [OPTIONS] <input_path>
```

### 2.2 CLI Argument Schema

| Flag / Option | Type | Default | Description |
|---|---|---|---|
| `<input_path>` (Positional) | `str` / `Path` | Required | Path to input PSD file (`.psd`, `.psb`), PNG image (`.png`), or folder of layer PNGs. |
| `-o`, `--output` | `str` / `Path` | `./output/<model_name>/` | Destination directory for the exported Live2D model bundle. |
| `-n`, `--name` | `str` | Filename stem | Name of the Live2D model (used for `.moc3`, `.model3.json`, and texture folder). |
| `--resolution`, `--atlas-size` | `int` | `4096` | Texture atlas resolution in pixels (e.g. `2048`, `4096`, `8192`). Must be power-of-two. |
| `--grid-size` | `int` | `25` | Target mesh triangle grid spacing in pixels (lower = denser mesh). |
| `--angle-x-range` | `float,float` | `-30.0,30.0` | Min and Max yaw rotation angles in degrees. |
| `--angle-y-range` | `float,float` | `-30.0,30.0` | Min and Max pitch rotation angles in degrees. |
| `--angle-z-range` | `float,float` | `-20.0,20.0` | Min and Max roll rotation angles in degrees. |
| `--keyforms-x` | `int` | `3` | Keyform division count for AngleX (e.g. 3 -> `[-30, 0, +30]`). |
| `--keyforms-y` | `int` | `3` | Keyform division count for AngleY (e.g. 3 -> `[-30, 0, +30]`). |
| `--keyforms-z` | `int` | `3` | Keyform division count for AngleZ (e.g. 3 -> `[-20, 0, +20]`). |
| `--auto-depth` | `bool` flag | `True` | Automatically estimate 3D depth from silhouette distance transform and layer semantic tags. |
| `--auto-stiffness` | `bool` flag | `True` | Automatically derive edge-based ARAP stiffness map from image features. |
| `--validate` | `bool` flag | `False` | Run programmatic structural validation automatically upon export completion. |
| `-q`, `--quiet` | `bool` flag | `False` | Suppress all stdout logging except errors. |
| `-v`, `--verbose` | `bool` flag | `False` | Output detailed step-by-step diagnostic information. |
| `--json-report` | `str` / `Path` | `None` | Optional path to export execution and validation summary as a JSON report. |

### 2.3 Output Bundle Directory Layout
For an input model named `SampleModel`, the CLI produces:

```
output/SampleModel/
├── SampleModel.moc3                # Live2D Cubism 3/4 binary model format
├── SampleModel.model3.json         # Live2D model configuration and runtime descriptors
├── SampleModel.cdi3.json           # Parameter and Part display information
├── SampleModel.physics3.json       # Live2D standard physics definitions (hair/accessory sway)
└── SampleModel.4096/               # Texture atlas directory (or textures/)
    └── texture_00.png              # RGBA 32-bit packed power-of-two texture atlas
```

### 2.4 CLI Execution Exit Codes

| Exit Code | Constant Name | Meaning / Condition |
|---|---|---|
| `0` | `SUCCESS` | Pipeline completed successfully; output bundle created and validated (if `--validate`). |
| `1` | `ERR_INVALID_ARGS` | Invalid CLI flags, missing required positional arguments, or unparseable ranges. |
| `2` | `ERR_INPUT_NOT_FOUND` | Input file/directory does not exist, is unreadable, or contains no valid images. |
| `3` | `ERR_PROCESSING_FAILED` | Internal mesh generation, Delaunay triangulation, or constraint solver failed. |
| `4` | `ERR_EXPORT_FAILED` | Failed to write `.moc3`, `.model3.json`, or texture atlas to output disk destination. |
| `5` | `ERR_VALIDATION_FAILED` | Exported bundle failed programmatic structural validation rules. |

---

## 3. Programmatic Structural Validation Framework

### 3.1 Validator Architecture & Dual Entry
The validator is designed as a self-contained, standalone inspection tool with both programmatic Python API and command-line execution:

```bash
# Standalone CLI execution
python validate_live2d.py path/to/model_directory_or_model3_json

# Programmatic Python API
from src.validator import validate_live2d_model, ValidationResult
result = validate_live2d_model("output/SampleModel/SampleModel.model3.json")
assert result.is_valid
```

### 3.2 Six-Stage Validation Rule Hierarchy

```
┌────────────────────────────────────────────────────────────────────────┐
│                      Stage 1: File Bundle Integrity                     │
│  - Directory existence  - FileReferences presence  - Relative paths   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   Stage 2: model3.json Schema & Semantics               │
│  - JSON syntax  - Version == 3  - Canvas dimensions  - Part list       │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 Stage 3: .moc3 Binary Header & Structure                │
│  - Magic bytes: 'MOC3' (0x4D 0x4F 0x43 0x33)  - Section table offsets  │
│  - File size consistency  - Count of Drawables, Parts, Parameters     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│              Stage 4: Parameter & Keyform Bounds Verification           │
│  - ParamAngleX/Y/Z defined  - Min/Max/Default in range  - Key bindings │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                 Stage 5: Texture Atlas & UV Coordinate Safety          │
│  - PNG readability  - 32-bit RGBA  - Power-of-two  - UVs in [0.0, 1.0] │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│           Stage 6: Vertex Deformation & Topological Non-Inversion       │
│  - No NaN/Inf  - Valid index bounds  - Signed Triangle Area > 0        │
│  - Bounded displacement  - ARAP rigidity preservation                   │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.3 Detailed Validation Checkpoints

#### Stage 1 & 2: JSON Schema & File References
- `model3.json` must parse cleanly as standard JSON.
- `Version` must be integer `3` (Cubism 3.0+ format).
- `FileReferences.Moc` must point to an existing `.moc3` file relative to the `model3.json` directory.
- `FileReferences.Textures` must be a list containing at least 1 existing texture image path.
- If present, `FileReferences.Physics` and `FileReferences.DisplayInfo` must resolve to existing valid JSON files.

#### Stage 3: `.moc3` Binary Header & Section Table
- First 4 bytes must match exact magic bytes: `0x4D 0x4F 0x43 0x33` (`MOC3` ASCII).
- File size must be greater than header minimum (64 bytes) and match internal section offsets.
- Section table pointers for Parts, Drawables, Deformers, Parameters, and Keyforms must not exceed physical file length.

#### Stage 4: Parameter Bounds & Keyforms
- Must define standard Live2D tracking parameters:
  - `ParamAngleX`: `min <= -20.0`, `max >= 20.0`, `default == 0.0`
  - `ParamAngleY`: `min <= -20.0`, `max >= 20.0`, `default == 0.0`
  - `ParamAngleZ`: `min <= -15.0`, `max >= 15.0`, `default == 0.0`
- Keyform grid coordinates must be monotonically increasing and cover the parameter interval.

#### Stage 5: Texture Atlas & UV Mapping
- Atlas image must be readable by PIL/OpenCV with format RGBA (4 channels).
- Width and Height must be power-of-two ($512, 1024, 2048, 4096, 8192$).
- For every drawable mesh, all UV coordinate pairs $(u, v)$ must satisfy:
  $$0.0 \le u \le 1.0 \quad \text{and} \quad 0.0 \le v \le 1.0$$
- No degenerated UV triangles (UV area $> 0$).

#### Stage 6: Geometrical & Topological Integrity (Non-Inversion)
- Vertex positions across rest pose and all deformed keyforms must contain no `NaN` or `Infinity`.
- Triangle index array: every index $i$ must satisfy $0 \le i < N_{\text{vertices}}$.
- **Signed Triangle Area Check**: For every triangle $(v_0, v_1, v_2)$ across all keyforms:
  $$A_{\text{signed}} = 0.5 \cdot \left((x_1 - x_0)(y_2 - y_0) - (x_2 - x_0)(y_1 - y_0)\right) > -10^{-4}$$
  Any triangle flipping ($A_{\text{signed}} \le -10^{-4}$) is flagged as a critical geometrical deformation failure.
- **Displacement Bounds**: No vertex displacement exceeds $2.5 \times \text{model\_radius}$.

---

## 4. User Verification Walkthrough Instructions

### 4.1 Testing in Live2D Cubism Viewer

#### Prerequisites
- Live2D Cubism Viewer (Official Live2D application for OW / Unity / Native runtime verification, available with Live2D Cubism SDK).

#### Step-by-Step Verification Procedure
1. **Launch Viewer**: Open Live2D Cubism Viewer.
2. **Load Model Bundle**:
   - Drag and drop the generated `output/SampleModel/SampleModel.model3.json` file into the Viewer canvas.
   - Alternatively, use `File -> Open` and select the `.model3.json` file.
3. **Inspect Rest Appearance**:
   - Verify that the model appears centered in the canvas.
   - Verify textures are rendered cleanly with sharp alpha contours, no black borders, and no missing texture artifacts.
4. **Test Parameter Sliders**:
   - Open the **Parameter Palette** on the right sidebar.
   - **`ParamAngleX` (Yaw)**: Drag slider from `-30.0` to `+30.0`.
     - *Verify*: The face turns smoothly left and right in 3D perspective.
     - *Verify*: Far features (e.g. far ear) occlude naturally behind face contour.
     - *Verify*: Near features (nose, near eye) expand slightly due to parallax.
   - **`ParamAngleY` (Pitch)**: Drag slider from `-30.0` to `+30.0`.
     - *Verify*: The head tilts up and down smoothly with perspective shortening.
   - **`ParamAngleZ` (Roll)**: Drag slider from `-20.0` to `+20.0`.
     - *Verify*: The head tilts left and right without shearing or planar distortion.
5. **Test Diagonal Compound Angles**:
   - Move `ParamAngleX = 25.0` and `ParamAngleY = -20.0` simultaneously.
   - *Verify*: Mesh remains completely smooth, without spiky vertices, jagged edges, or inverted triangles.

---

### 4.2 Testing in VTube Studio (PC / Steam / Mac)

#### Prerequisites
- VTube Studio installed via Steam or standalone.

#### Step-by-Step Deployment & Tracking Setup
1. **Locate VTube Studio Model Directory**:
   - On Windows:
     ```
     <SteamDirectory>\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels\
     ```
2. **Copy Model Folder**:
   - Copy the entire exported folder `output/SampleModel/` into the `Live2DModels/` directory:
     ```
     Live2DModels/SampleModel/
     ├── SampleModel.moc3
     ├── SampleModel.model3.json
     ├── SampleModel.cdi3.json
     └── SampleModel.4096/
     ```
3. **Load Model in VTube Studio**:
   - Launch VTube Studio.
   - Click the **Avatar / Model Icon** (top-left menu).
   - Locate and click `SampleModel` in the model selection tray.
4. **Auto-Setup Tracking Parameters**:
   - When the pop-up appears asking *"Auto-setup Live2D model?"*, select **Auto Setup**.
   - Navigate to **Model Settings (Gear Icon) -> Parameter Mapping**:
     - Verify `Head Yaw` is mapped to `ParamAngleX` (Input: `FaceAngleX` -> Output: `ParamAngleX`).
     - Verify `Head Pitch` is mapped to `ParamAngleY` (Input: `FaceAngleY` -> Output: `ParamAngleY`).
     - Verify `Head Roll` is mapped to `ParamAngleZ` (Input: `FaceAngleZ` -> Output: `ParamAngleZ`).
5. **Live Tracking Test**:
   - Enable Webcam tracking or connect iOS / Android camera.
   - Rotate your head in real life (yaw, pitch, roll).
   - *Verify*: The VTuber avatar responds in real-time with continuous 3D head rotation.

---

### 4.3 Visual Defect & Anomaly Troubleshooting Matrix

| Symptom / Defect | Root Cause | Diagnosis & Resolution |
|---|---|---|
| **Black quad / Pink missing texture box** | Relative path in `model3.json` does not match texture folder name or texture file is missing. | Verify `FileReferences.Textures` points exactly to `SampleModel.4096/texture_00.png`. Re-run validator. |
| **Model fails to load / Viewer crashes** | Corrupted `.moc3` binary header or invalid section offset table. | Run `python validate_live2d.py output/SampleModel/` to pinpoint corrupt byte offsets. |
| **Spiky vertices / exploding mesh during rotation** | ARAP spring stiffness too low or inverted triangle in constraint solver. | Increase ARAP solver iterations (e.g. 4-5) and check signed triangle area preservation. |
| **Ears/Hair render in front of face when turned away** | Missing Z-buffer depth sorting or incorrect peripheral stratification. | Verify depth model layer stratification offsets: Hair (-0.15), Ears/Peripheral (-0.4), Face (0.0). |
| **Jagged / pixelated texture edges** | Texture atlas packed at low resolution or bilinear filtering disabled. | Increase `--atlas-size 4096` during export. |

---

## 5. Comprehensive 4-Tier E2E Testing Architecture

```
═══════════════════════════════════════════════════════════════════════════════
                      4-TIER E2E TEST ARCHITECTURE
═══════════════════════════════════════════════════════════════════════════════

  ┌─────────────────────────────────────────────────────────────────────────┐
  │ TIER 1: Feature Coverage (Atomic & Functional Core)                     │
  │ • CLI Argument Parsing & Defaults                                       │
  │ • PSD / PNG Ingestion & Contour Extraction                              │
  │ • Adaptive Delaunay Mesh Generator (with Scipy fallback)                │
  │ • 3D AngleX / AngleY / AngleZ Rotation & Parallax Math                  │
  │ • ARAP Mass-Spring Constraint Solver Convergence                        │
  │ • Texture Atlas Packing & UV Rect Coordinates                           │
  │ • model3.json Serializer & Format Specifications                        │
  │ • moc3 Binary Header & Section Serialization                            │
  └─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ TIER 2: Boundary & Corner Cases (Robustness & Extreme Limits)           │
  │ • Minimal / Micro Images (16x16, 64x64)                                 │
  │ • Odd / Asymmetric Dimensions (513x729, 301x301)                        │
  │ • Large Ultra-HD Assets (4096x4096 PSD with 20+ layers)                 │
  │ • Extreme Deformation Angles (AngleX=±60°, AngleY=±45°, AngleZ=±45°)    │
  │ • Multi-Island Disconnected Contours (separated hair ribbons)           │
  │ • Fully Transparent / Blank Layers (graceful bypass)                    │
  │ • Missing CLI Arguments / Nonexistent Input Files                       │
  └─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ TIER 3: Cross-Feature Combinations (Pairwise & Multi-Feature)           │
  │ • Multi-Layer PSD + Simultaneous Compound XYZ Rotation (X=25°, Y=-20°)  │
  │ • High-Density Mesh (Grid=10) + 8192x8192 Texture Atlas                 │
  │ • AI Auto-Depth & Stiffness + Full Live2D Export Pipeline               │
  │ • Batch Folder Processing (Multiple Models in 1 Run)                    │
  │ • CLI Export with `--validate` Active (In-flight self-check)            │
  └─────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │ TIER 4: Real-World Application Scenarios (System E2E Lifecycle)         │
  │ • Full Synthetic VTuber Lifecycle (Generation -> Export -> Validate)   │
  │ • Full Multi-Layer PSD Character Model Lifecycle                        │
  │ • 100-Point Parameter Space Sweep (Continuous Motion & Non-Inversion)   │
  │ • Adversarial Corruption Suite (Corrupted MOC3/JSON/UVs Rejection)      │
  └─────────────────────────────────────────────────────────────────────────┘
```

---

### 5.1 Tier 1: Feature Coverage (Test Specifications)

1. **`test_cli_argument_parsing`**:
   - Verify CLI parser handles all flags (`--input`, `--output`, `--name`, `--resolution`, `--grid-size`, `--angle-x-range`, `--keyforms-x`, `--auto-depth`, `--validate`).
   - Verify defaults are populated when flags are omitted.
   - Verify invalid arguments return exit code `1`.
2. **`test_asset_ingestion_png_and_psd`**:
   - Test loading PNG image and extracting RGBA channels and alpha mask.
   - Test loading multi-layer PSD file, extracting individual layers, layer names, and layer bounds.
3. **`test_adaptive_mesh_generation_scipy`**:
   - Verify `MeshGenerator` produces valid Delaunay triangulation inside silhouette contour.
   - Verify mesh contains vertices, triangles, unique edges, and normalized UV coordinates.
   - Verify rest triangle signed areas are all positive.
4. **`test_3d_deformation_math_xyz`**:
   - Verify 3D rotation matrix calculation for `AngleX` (Yaw), `AngleY` (Pitch), and `AngleZ` (Roll).
   - Verify identity rotation ($0^\circ, 0^\circ, 0^\circ$) yields identical vertex coordinates.
   - Verify parallax shift scales proportionally with vertex depth $z$.
5. **`test_arap_constraint_solver_convergence`**:
   - Verify ARAP energy $E(V)$ decreases monotonically across solver iterations.
   - Verify signed triangle areas remain non-negative (no triangle inversion).
6. **`test_texture_atlas_packing`**:
   - Test packing multiple layer textures into a single power-of-two PNG.
   - Verify layer UV coordinates are correctly offset and scaled into atlas space $[0, 1] \times [0, 1]$.
7. **`test_model3_json_serialization`**:
   - Verify generated JSON complies with Cubism 3.0+ schema.
   - Verify `FileReferences.Moc` and `FileReferences.Textures` paths are valid relative strings.
8. **`test_moc3_binary_serialization`**:
   - Verify serialized binary starts with `MOC3` header bytes.
   - Verify section table and vertex buffer offsets.

---

### 5.2 Tier 2: Boundary & Corner Cases (Test Specifications)

1. **`test_minimal_image_dimensions`**:
   - Input: $16 \times 16$ and $64 \times 64$ minimal images.
   - Assert: Mesh generation does not divide by zero; exports valid minimal model.
2. **`test_odd_and_non_square_dimensions`**:
   - Input: $513 \times 729$ and $301 \times 301$ non-standard dimensions.
   - Assert: Coordinate normalization $[-1, 1]$ and UV mapping $[0, 1]$ remain exact without rounding distortion.
3. **`test_large_highres_asset`**:
   - Input: $4096 \times 4096$ multi-layer asset.
   - Assert: Memory usage remains bounded, sparse LU factorization executes in $< 1.5$ seconds, atlas packs cleanly.
4. **`test_extreme_deformation_angles`**:
   - Input: AngleX $= \pm 60^\circ$, AngleY $= \pm 45^\circ$, AngleZ $= \pm 45^\circ$.
   - Assert: ARAP solver prevents topological collapse; signed triangle areas remain $> -10^{-4}$.
5. **`test_disconnected_multi_island_contours`**:
   - Input: Layer containing 2 separated accessory parts (e.g. left and right hair ribbons in one layer).
   - Assert: Triangulation handles disconnected components cleanly without creating cross-island bridging artifacts.
6. **`test_empty_or_transparent_layers`**:
   - Input: 100% transparent PNG or PSD layer with 0 non-zero alpha pixels.
   - Assert: Pipeline skips empty layers gracefully without error, logging a notice.
7. **`test_missing_input_and_invalid_paths`**:
   - Input: Non-existent file path `missing_file.psd`.
   - Assert: CLI exits cleanly with code `2` (`ERR_INPUT_NOT_FOUND`) and clear stderr message.

---

### 5.3 Tier 3: Cross-Feature Combinations (Test Specifications)

1. **`test_multi_layer_simultaneous_xyz_deformation`**:
   - Input: 5-layer PSD (HairFront, Eyes, Face, HairBack, Accessories).
   - Deform simultaneously: AngleX $= 25.0^\circ$, AngleY $= -20.0^\circ$, AngleZ $= 15.0^\circ$.
   - Assert: All layers deform synchronously; relative depth parallax prevents layering collisions.
2. **`test_custom_atlas_size_with_high_density_mesh`**:
   - Options: `--grid-size 12 --atlas-size 8192`.
   - Assert: High-density mesh ($> 1500$ vertices) successfully packs into $8192 \times 8192$ atlas; UV precision validated.
3. **`test_ai_depth_stiffness_integrated_export`**:
   - Pipeline: Run `AIAssistant.auto_assign_mesh_properties` -> `DeformationSolver` -> `MassSpringConstraintSolver` -> `Live2DExporter`.
   - Assert: Exported bundle passes all 6 validation stages programmatically.
4. **`test_cli_batch_folder_export`**:
   - Input: Directory containing 3 distinct character models.
   - Assert: CLI generates 3 separate, fully formed model bundle directories; each passes structural validation.
5. **`test_cli_with_validate_flag`**:
   - Invocation: `python -m src.cli input.png --validate`.
   - Assert: Process returns exit code `0` and outputs validation report summary.

---

### 5.4 Tier 4: Real-World Application Scenarios (Test Specifications)

1. **`test_e2e_synthetic_vtuber_full_lifecycle`**:
   - Workflow:
     1. Ingest synthetic character head ($512 \times 512$ with eyes, ears, mouth, hair).
     2. Run automated mesh generation.
     3. Generate 3D depth field and ARAP stiffness.
     4. Calculate keyforms across AngleX ($[-30, 0, 30]$), AngleY ($[-30, 0, 30]$), AngleZ ($[-20, 0, 20]$).
     5. Pack texture atlas and serialize `.moc3`, `.model3.json`, `.cdi3.json`.
     6. Run standalone programmatic validator on the resulting directory.
   - Assert: 100% of validation rules pass (Headers, JSON schema, Parameter bounds, UV bounds, Non-inversion).
2. **`test_e2e_parameter_space_sweep_continuous_deformation`**:
   - Sample 100 pseudo-random angle vectors $(\theta_x, \theta_y, \theta_z)$ across tracking space $[-30, 30] \times [-30, 30] \times [-20, 20]$.
   - Evaluate interpolated vertex positions at each sample.
   - Assert:
     - No vertex coordinate jumps or discontinuities ($\max \|\Delta v\| < \text{threshold}$).
     - All signed triangle areas remain positive across the entire parameter envelope.
3. **`test_e2e_validator_adversarial_rejection`**:
   - Intentionally inject 5 distinct faults into generated bundles:
     1. Corrupt `.moc3` magic bytes (`BAD3`).
     2. Missing texture atlas PNG file.
     3. Out-of-bounds UV coordinates ($u = 1.25$).
     4. Inverted triangle with negative signed area ($A = -0.5$).
     5. `NaN` vertex coordinate in parameter keyform.
   - Assert: Programmatic validator detects and flags each defect with specific error diagnostics and rejects invalid models.

---

## 6. Implementation Recommendations & Dependency Strategy

### 6.1 Fixing Mesh Triangulation Dependency (`triangle` vs `scipy.spatial.Delaunay`)
- **Problem**: In Python 3.14 on Windows, `triangle` requires native C++ compilation which may fail if MSVC build tools are absent.
- **Solution**: Enhance `src/generator/mesh_generator.py` to:
  1. Try `import triangle as tr` if available.
  2. If `triangle` is not installed or fails, automatically fallback to `scipy.spatial.Delaunay` with contour filtering (e.g. `cv2.pointPolygonTest`).
  3. This ensures all tests and CLI executions run 100% reliably out of the box in standard Python environments with existing `scipy`.

### 6.2 Recommended New Source & Test File Structure

```
d:\VitubModel\
├── src\
│   ├── cli.py                    # Zero-intervention CLI entry point (argparse)
│   ├── exporter\                 # Live2D export engine
│   │   ├── __init__.py
│   │   ├── moc3_writer.py        # Binary .moc3 serialization
│   │   ├── model3_writer.py      # model3.json / cdi3.json / physics3.json serialization
│   │   └── texture_packer.py     # Texture atlas packing & UV remapping
│   └── validator\                # Programmatic structural validator
│       ├── __init__.py
│       ├── validator.py          # 6-Stage structural validation engine
│       └── rules.py              # Schema, binary, bounds, and topology rule checks
├── export_live2d.py              # Root convenience script for CLI export
├── validate_live2d.py            # Root convenience script for model validation
└── tests\
    ├── test_tier1_features.py    # Tier 1: Functional feature coverage
    ├── test_tier2_boundary.py    # Tier 2: Boundary and corner cases
    ├── test_tier3_combinations.py# Tier 3: Cross-feature pairwise combinations
    └── test_tier4_e2e.py         # Tier 4: Real-world application scenarios
```

---

## 7. Conclusion & Next Steps
This survey provides complete specifications for:
1. Automated zero-intervention CLI with full flag definitions and exit codes.
2. Programmatic structural validation framework with 6 verification stages.
3. User verification instructions for Live2D Cubism Viewer and VTube Studio.
4. Comprehensive 4-tier E2E testing architecture covering 25+ distinct test conditions.

All findings and specifications are ready for the Orchestrator and Implementation tracks.
