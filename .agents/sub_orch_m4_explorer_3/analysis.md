# Milestone 4 Analysis Report: Test Architecture & Walkthrough Documentation

**Explorer:** sub_orch_m4_explorer_3  
**Date:** 2026-08-22  
**Mission:** Design the comprehensive Unit & Integration test suite (`tests/test_validator.py`, `tests/test_cli.py`) and the full user verification guide (`WALKTHROUGH.md`) for Milestone 4.

---

## 1. Executive Summary

Milestone 4 delivers the user-facing interface, structural verification quality gate, and end-user documentation for the Automated VTuber Key Deformation & Live2D Export pipeline:
1. **6-Stage Structural Validator (`src/validator/structural_validator.py` / `validate_live2d.py`)**: Programmatic inspection of binary .moc3 headers, 64-byte aligned section tables, .model3.json / .cdi3.json schemas, tracking parameter keyform bounds, power-of-two texture atlases, and topological non-inversion across 3D head rotation keyforms.
2. **Headless Zero-Intervention CLI (`src/cli/main.py` / `export_live2d.py`)**: Single-command headless execution ingesting PSD/PNG inputs, executing mesh generation, 3D deformation solving, MaxRects texture packing, MOC3 serialization, and optional in-flight validation with standardized exit codes (0 to 5).
3. **User Manual Verification Walkthrough (`WALKTHROUGH.md`)**: Complete step-by-step guide for importing generated models into Live2D Cubism Viewer and VTube Studio, conducting parameter slider verification (ParamAngleX, ParamAngleY, ParamAngleZ), and troubleshooting visual artifacts.

This report establishes:
- The full test architecture and test matrices for `tests/test_validator.py` (covering all 6 stages with passing cases, corrupted fixtures, edge cases, and report schemas).
- The full test architecture and test matrices for `tests/test_cli.py` (argument parsing, exit codes 0-5, end-to-end mock export, `--validate` integration, and error trapping).
- The complete structural design and verbatim section-by-section draft for `WALKTHROUGH.md`.

---

## 2. Milestone 4 Interface Contracts

### 2.1 Structural Validator (`src/validator/structural_validator.py`)

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

@dataclass
class ValidationStageResult:
    """Represents the outcome of an individual validation stage."""
    stage_number: int
    stage_name: str
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ValidationReport:
    """Aggregated validation report across all 6 stages."""
    is_valid: bool
    model_path: str
    stages: List[ValidationStageResult] = field(default_factory=list)
    total_errors: int = 0
    total_warnings: int = 0

    def get_summary_text(self, colorize: bool = False) -> str:
        """Formats a human-readable console summary table."""
        ...

def validate_live2d_model(
    model_entry_path: Union[str, Path],
    strict: bool = True
) -> ValidationReport:
    """
    Executes all 6 validation stages on the specified .model3.json or model directory.
    Returns a ValidationReport detailing passes, errors, warnings, and metrics.
    """
    ...
```

### 2.2 CLI Runner (`src/cli/main.py`)

```python
import argparse
from typing import List, Optional, Dict, Any

# Standardized Exit Codes
EXIT_SUCCESS = 0               # Pipeline succeeded, valid output generated
EXIT_ERR_INVALID_ARGS = 1      # Missing/invalid CLI flags or arguments
EXIT_ERR_INPUT_NOT_FOUND = 2   # Input PSD/PNG/dir missing or unreadable
EXIT_ERR_PROCESSING_FAILED = 3 # Mesh generation or deformation solver failure
EXIT_ERR_EXPORT_FAILED = 4     # Texture packing, .moc3 writer, or IO failure
EXIT_ERR_VALIDATION_FAILED = 5 # --validate flag triggered and model failed checks

def build_arg_parser() -> argparse.ArgumentParser:
    """Constructs the full CLI argument parser."""
    ...

def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """Parses command-line arguments."""
    ...

def run_pipeline(args: argparse.Namespace) -> int:
    """
    Executes the end-to-end ingestion, mesh generation, deformation solving,
    texture packing, Live2D export, and optional validation.
    Returns exit code (0..5).
    """
    ...

def main() -> int:
    """CLI entry point for python -m src.cli."""
    ...
```

---

## 3. `tests/test_validator.py` Test Architecture

### 3.1 Test Fixture Factory Design

To achieve exhaustive validation testing without coupling to disk state, `test_validator.py` utilizes parameterized fixture factories that generate valid base Live2D model bundles and inject deliberate, isolated defects into each stage.

```python
# Fixture Factory Concept:
# 1. valid_bundle_factory(tmp_path) -> Path (creates fully compliant model directory)
# 2. Defect injection mutators targeting specific stages:
#    - mutate_moc3_magic(path, magic_bytes)
#    - mutate_moc3_alignment(path, bad_offset)
#    - mutate_model3_json(path, mutator_fn)
#    - mutate_cdi3_json(path, mutator_fn)
#    - mutate_texture_png(path, bad_dimensions, bad_mode)
#    - mutate_keyform_vertices(path, inverted_triangles, nan_coords)
```

### 3.2 6-Stage Validation Test Matrix

| Stage | Test Name | Injected Defect / Scenario | Expected Outcome | Assertions |
|---|---|---|---|---|
| **Stage 1** | `test_stage1_valid_header` | Compliant `.moc3` binary header | Stage 1 PASS | `stage.passed == True`, `magic == b"MOC3"`, `version == 3` |
| **Stage 1** | `test_stage1_corrupt_magic_bytes` | Header magic replaced with `b"MOC2"`, `b"ABCD"`, `b"\x00\x00\x00\x00"` | Stage 1 FAIL | `stage.passed == False`, error mentions "Magic bytes mismatch" |
| **Stage 1** | `test_stage1_unsupported_version` | Header version set to 1, 2, 4, or 99 | Stage 1 FAIL | `stage.passed == False`, error mentions "Unsupported version" |
| **Stage 1** | `test_stage1_truncated_file` | File size < 64 bytes (e.g. 16 bytes or 0 bytes) | Stage 1 FAIL | `stage.passed == False`, error mentions "File size too small" |
| **Stage 1** | `test_stage1_invalid_endianness` | Header byte 5 set to invalid flag (e.g. 0xFF) | Stage 1 FAIL/WARN | `stage.passed == False`, error mentions "Endianness" |
| **Stage 2** | `test_stage2_valid_section_table` | All offsets 64-byte aligned, monotonic, within file bounds | Stage 2 PASS | `stage.passed == True`, 64-byte alignment verified |
| **Stage 2** | `test_stage2_misaligned_offset` | Section offset set to 65, 130, or `align_to_64(x) + 1` | Stage 2 FAIL | `stage.passed == False`, error mentions "64-byte alignment" |
| **Stage 2** | `test_stage2_non_monotonic_offsets` | Section $N+1$ offset < Section $N$ offset | Stage 2 FAIL | `stage.passed == False`, error mentions "Monotonicity" |
| **Stage 2** | `test_stage2_offset_exceeds_eof` | Section offset points beyond binary file length | Stage 2 FAIL | `stage.passed == False`, error mentions "Exceeds binary size" |
| **Stage 2** | `test_stage2_corrupted_count_table` | Negative or astronomical counts (e.g. $2^{31}-1$ drawables) | Stage 2 FAIL | `stage.passed == False`, error mentions "Count table" |
| **Stage 3** | `test_stage3_valid_model3_and_cdi3` | Valid `.model3.json` & `.cdi3.json` with relative paths | Stage 3 PASS | `stage.passed == True`, all referenced files resolve |
| **Stage 3** | `test_stage3_invalid_json_syntax` | Truncated/corrupted JSON file (missing closing brace) | Stage 3 FAIL | `stage.passed == False`, error mentions "Invalid JSON syntax" |
| **Stage 3** | `test_stage3_missing_version_or_invalid` | `Version` field missing or set to `2` | Stage 3 FAIL | `stage.passed == False`, error mentions "Expected Version == 3" |
| **Stage 3** | `test_stage3_missing_moc_reference` | `FileReferences.Moc` omitted from `.model3.json` | Stage 3 FAIL | `stage.passed == False`, error mentions "Missing FileReferences.Moc" |
| **Stage 3** | `test_stage3_nonexistent_moc_file` | `FileReferences.Moc` references `"missing.moc3"` | Stage 3 FAIL | `stage.passed == False`, error mentions "Moc file does not exist" |
| **Stage 3** | `test_stage3_empty_or_missing_textures` | `FileReferences.Textures` is `[]` or omitted | Stage 3 FAIL | `stage.passed == False`, error mentions "Textures is empty" |
| **Stage 3** | `test_stage3_nonexistent_texture_file` | `FileReferences.Textures` contains `"missing.png"` | Stage 3 FAIL | `stage.passed == False`, error mentions "Texture file does not exist" |
| **Stage 3** | `test_stage3_backslash_path_normalization` | File references containing `\` (e.g. `"subdir\\avatar.moc3"`) | Stage 3 WARN/FAIL | Warning/Error flags Windows backslash in cross-platform manifest |
| **Stage 3** | `test_stage3_missing_cdi3_file` | `DisplayInfo` points to non-existent `.cdi3.json` | Stage 3 WARN/FAIL | Warning/Error flags missing display info manifest |
| **Stage 4** | `test_stage4_valid_parameters` | `ParamAngleX`, `ParamAngleY`, `ParamAngleZ` present with 3 keyforms | Stage 4 PASS | `stage.passed == True`, all 3 tracking parameters validated |
| **Stage 4** | `test_stage4_missing_required_param` | `ParamAngleX` or `ParamAngleY` omitted from model | Stage 4 FAIL | `stage.passed == False`, error mentions "Missing required parameter" |
| **Stage 4** | `test_stage4_inverted_parameter_range` | `ParamAngleX` min set to 30.0, max set to -30.0 (`min > max`) | Stage 4 FAIL | `stage.passed == False`, error mentions "Invalid parameter range" |
| **Stage 4** | `test_stage4_default_out_of_bounds` | `ParamAngleX` default set to 50.0 when range is `[-30, 30]` | Stage 4 FAIL | `stage.passed == False`, error mentions "Default value out of bounds" |
| **Stage 4** | `test_stage4_invalid_keyform_count` | Parameter has 1 or 2 keyforms instead of 3 | Stage 4 WARN/FAIL | Warning/Error mentions "Keyform count" |
| **Stage 5** | `test_stage5_valid_power_of_two_texture` | Texture PNG dimensions $1024 \times 1024$, 4-channel RGBA | Stage 5 PASS | `stage.passed == True`, POT verified, RGBA verified |
| **Stage 5** | `test_stage5_non_power_of_two_dimensions` | Texture PNG dimensions $500 \times 500$ or $1000 \times 1000$ | Stage 5 FAIL | `stage.passed == False`, error mentions "not power-of-two" |
| **Stage 5** | `test_stage5_corrupted_png_file` | Texture file containing random garbage bytes | Stage 5 FAIL | `stage.passed == False`, error mentions "Cannot load texture image" |
| **Stage 5** | `test_stage5_non_rgba_texture_mode` | Texture PNG saved in RGB (no alpha) or Grayscale 'L' | Stage 5 WARN | `stage.passed == True`, warning mentions "expected RGBA" |
| **Stage 5** | `test_stage5_out_of_bounds_uvs` | UV coordinates containing values $u = 1.25$ or $v = -0.1$ | Stage 5 FAIL | `stage.passed == False`, error mentions "UV coordinates out of bounds" |
| **Stage 6** | `test_stage6_valid_mesh_topology` | Positive signed triangle areas across all 9 keyforms | Stage 6 PASS | `stage.passed == True`, signed areas $> 0.0$ |
| **Stage 6** | `test_stage6_inverted_triangle_keyform` | Deformed keyform contains triangle with negative signed area $A < -1e-4$ | Stage 6 FAIL | `stage.passed == False`, error mentions "Inverted triangle" |
| **Stage 6** | `test_stage6_nan_vertex_coordinates` | Keyform positions table contains `NaN` or `Inf` | Stage 6 FAIL | `stage.passed == False`, error mentions "NaN or Inf vertex coordinates" |
| **Stage 6** | `test_stage6_out_of_bounds_indices` | Triangle index references vertex $idx \ge N$ | Stage 6 FAIL | `stage.passed == False`, error mentions "Index out of range" |
| **Report** | `test_validation_report_summary_formatting` | Report aggregates stage results into clean text table | Report Valid | Summary string contains stage numbers, status badges `[PASS]`/`[FAIL]` |

---

## 4. `tests/test_cli.py` Test Architecture

### 4.1 CLI Test Design & Fixtures

`tests/test_cli.py` tests both in-process entry points (`src.cli.main.run_pipeline`, `src.cli.main.parse_args`) and subprocess script invocations (`export_live2d.py`, `validate_live2d.py`).

```python
# Fixtures in test_cli.py:
# 1. mock_psd_file: Generates synthetic multi-layer PSD using psd-tools or fallback structure.
# 2. mock_png_file: Generates 512x512 synthetic RGBA character image.
# 3. mock_layer_dir: Generates directory with 3-5 character layer PNGs (hair_front, face, eyes, mouth, hair_back).
# 4. cli_temp_dir: Isolated output sandbox cleaned up after each test.
```

### 4.2 CLI Test Matrix

| Test Category | Test Name | Arguments / Invocation | Expected Exit Code | Expected Artifacts & Behavior |
|---|---|---|---|---|
| **Arg Parsing** | `test_cli_parse_defaults` | `["char.png"]` | N/A | `output="./output"`, `atlas_size=4096`, `grid_size=25`, `auto_depth=True`, `validate=False` |
| **Arg Parsing** | `test_cli_parse_custom_flags` | `["char.png", "-o", "./out", "-n", "Hero", "--resolution", "2048", "--grid-size", "15", "--validate"]` | N/A | `output="./out"`, `name="Hero"`, `atlas_size=2048`, `grid_size=15`, `validate=True` |
| **Arg Parsing** | `test_cli_parse_angle_ranges` | `["char.png", "--angle-x-range", "-25.0,25.0", "--angle-z-range", "-15.0,15.0"]` | N/A | Correctly parses min/max tuple ranges `(-25.0, 25.0)` |
| **Arg Parsing** | `test_cli_parse_unknown_flag` | `["char.png", "--non-existent-flag"]` | Exit 1 | `SystemExit` or exit code 1 raised, stderr contains usage |
| **Arg Parsing** | `test_cli_parse_missing_positional` | `[]` (no input given) | Exit 1 | `SystemExit` or exit code 1 raised |
| **Exit Code 2** | `test_cli_input_not_found` | `["nonexistent_image_12345.png"]` | Exit 2 | Returns `EXIT_ERR_INPUT_NOT_FOUND`, prints error message |
| **Exit Code 2** | `test_cli_unsupported_input_format` | `["corrupted.txt"]` (unsupported extension) | Exit 2 | Returns `EXIT_ERR_INPUT_NOT_FOUND` / format error |
| **Exit Code 3** | `test_cli_processing_error_degenerate` | Empty 0x0 or un-triangulable input | Exit 3 | Returns `EXIT_ERR_PROCESSING_FAILED` |
| **Exit Code 4** | `test_cli_export_error_unwritable_dir` | Read-only / invalid output path | Exit 4 | Returns `EXIT_ERR_EXPORT_FAILED` |
| **Exit Code 5** | `test_cli_validation_failure_flag` | Invocation with `--validate` where model deliberately fails Stage 5 | Exit 5 | Returns `EXIT_ERR_VALIDATION_FAILED` |
| **E2E Pipeline** | `test_cli_e2e_single_png_export` | `[str(png_path), "-o", str(out_dir), "-n", "TestModel"]` | Exit 0 | Creates `TestModel.model3.json`, `TestModel.moc3`, `TestModel.cdi3.json`, `TestModel.4096/texture_00.png` |
| **E2E Pipeline** | `test_cli_e2e_layer_dir_export` | `[str(layer_dir), "-o", str(out_dir), "-n", "LayerAvatar"]` | Exit 0 | Ingests all layers, packs atlas, builds keyforms, exports bundle |
| **E2E Pipeline** | `test_cli_e2e_with_in_flight_validation` | `[str(png_path), "-o", str(out_dir), "--validate"]` | Exit 0 | Runs full pipeline and runs validator; all 6 stages PASS |
| **E2E Pipeline** | `test_cli_e2e_custom_resolution_and_density` | `[str(png_path), "--resolution", "1024", "--grid-size", "35"]` | Exit 0 | Texture folder named `Model.1024`, texture image is $1024 \times 1024$ |
| **Subprocess** | `test_export_live2d_script_execution` | `python export_live2d.py sample.png -o out` | Exit 0 | Script executes cleanly via `subprocess.run`, returns code 0 |
| **Subprocess** | `test_validate_live2d_script_execution` | `python validate_live2d.py out/Model` | Exit 0 | Validator script executes cleanly, prints colored stage table |

---

## 5. `WALKTHROUGH.md` Complete Documentation Design

### 5.1 Document Structure Outline

```markdown
# Walkthrough: Live2D Model Generation & Verification Guide

1. Introduction & Overview
   - Automatic Key Deformation Technology
   - Supported Formats & Output Bundle Specification
2. Quick Start
   - System Prerequisites & Python Environment
   - 10-Second Headless CLI Command
   - Python API Integration
3. Command-Line Reference & Configuration
   - CLI Flags Table & Argument Descriptions
   - Resolution, Mesh Density & Parameter Range Tuning
   - Exit Codes Reference
4. Programmatic Structural Validation
   - Running `validate_live2d.py`
   - Detailed Stage Breakdown (Stages 1 through 6)
   - Sample Output & Error Resolution
5. Visual Verification in Live2D Cubism Viewer
   - Step 1: Launch Cubism Viewer & Drag-and-Drop Model
   - Step 2: Texture Atlas Inspection
   - Step 3: Parameter Slider Testing (Angle X, Y, Z)
   - Step 4: 2D Cartesian Yaw-Pitch Diagonal Drag
   - Step 5: Eye Blink & Lip Sync Groups
6. Model Deployment & Tracking in VTube Studio
   - Step 1: Locate VTube Studio StreamingAssets Directory
   - Step 2: Copy Model Bundle Folder
   - Step 3: Launch VTube Studio & Select Model
   - Step 4: Auto-Setup Tracking Parameters
   - Step 5: Webcam / iOS Tracking Calibration
7. Troubleshooting Common Visual Artifacts
   - Texture Bleeding & Color Smears
   - Inverted Triangles & Black Geometry Gaps
   - Layer Clipping & Depth Discrepancies
   - Missing Textures / Path Errors
   - Live2D Cubism Loading Failures
```

### 5.2 Complete Draft Content for `WALKTHROUGH.md`

Below is the complete text and structure for `WALKTHROUGH.md`:

```markdown
# Walkthrough: Live2D Model Generation & Verification Guide

Welcome to the automated 2D-to-Live2D conversion pipeline. This tool automatically ingests 2D character artwork (layered PSDs, PNG images, or layer directories) and generates fully rigged, keyform-complete Live2D Cubism 3.0+ model bundles (`.moc3`, `.model3.json`, `.cdi3.json`, texture atlases) with mathematical 3D head rotation keyforms (`ParamAngleX`, `ParamAngleY`, `ParamAngleZ`). No manual rigging or keyframe placement in Cubism Editor is required.

---

## 1. Quick Start

### Prerequisites
- Python 3.10, 3.11, 3.12, 3.13, or 3.14
- Virtual environment with installed dependencies:
  ```bash
  # Windows
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

### Standardized Exit Codes

| Exit Code | Constant | Meaning | Troubleshooting |
|---|---|---|---|
| **0** | `EXIT_SUCCESS` | Model generated and validated successfully | Ready for Cubism Viewer / VTube Studio |
| **1** | `EXIT_ERR_INVALID_ARGS` | Invalid CLI syntax or arguments | Check `python export_live2d.py --help` |
| **2** | `EXIT_ERR_INPUT_NOT_FOUND` | Input file missing or unsupported format | Verify input image path exists |
| **3** | `EXIT_ERR_PROCESSING_FAILED` | Triangulation or deformation solver error | Adjust `--grid-size` or check alpha mask |
| **4** | `EXIT_ERR_EXPORT_FAILED` | Texture packer or `.moc3` writer IO failure | Check disk space and folder write permissions |
| **5** | `EXIT_ERR_VALIDATION_FAILED` | Structural validation failed (`--validate`) | Run `python validate_live2d.py <model_dir>` |

---

## 3. Programmatic Structural Validation

The standalone validator inspects the generated model bundle across 6 rigorous stages.

### Run Validation Manually
```bash
python validate_live2d.py ./output/Kohaku/Kohaku.model3.json
# or
python validate_live2d.py ./output/Kohaku/
```

### The 6 Validation Stages

1. **Stage 1: Binary MOC3 Header**:
   - Magic bytes `b"MOC3"` (0x4D 0x4F 0x43 0x33).
   - Version 3.0+ compliance and Little-Endian format indicator.
   - Header minimum size $\ge 64$ bytes.
2. **Stage 2: Section Table & 64-Byte Alignment**:
   - All section table offsets (Drawables, Parameters, Vertices, Keyforms, UVs) are strictly aligned to 64-byte boundaries (`offset % 64 == 0`).
   - Monotonic offset layout and internal buffer bound sanity.
3. **Stage 3: Metadata Schema & Path References**:
   - `.model3.json` and `.cdi3.json` conform to Cubism 3 JSON schema.
   - All relative file paths are forward-slash normalized (`/`) and point to existing files on disk.
4. **Stage 4: Parameter & Keyform Bounds**:
   - Required tracking parameters present: `ParamAngleX`, `ParamAngleY`, `ParamAngleZ`.
   - Bounds verification (`min <= default <= max`) with valid tracking ranges.
5. **Stage 5: Texture Atlas & UV Safety**:
   - Dimensions are exact powers-of-two (POT): $512 \le W, H \le 8192$.
   - 4-channel RGBA image format with non-corrupt PNG headers.
   - UV coordinates strictly normalized within $[0.0, 1.0]$.
6. **Stage 6: Topological Non-Inversion & Continuity**:
   - CCW triangle winding with strictly positive signed area ($A > -1e-4$) across all 9 Angle X/Y keyforms.
   - No `NaN` or `Inf` floating-point coordinates in vertex displacement tables.

### Sample Passing Console Output
```
======================================================================
 Live2D Structural Validator Report: Kohaku
======================================================================
 [PASS] Stage 1: Binary MOC3 Header (Version 3, Little-Endian)
 [PASS] Stage 2: Section Table (64-byte alignment, 18 keyforms verified)
 [PASS] Stage 3: Metadata Manifest (.model3.json & .cdi3.json valid)
 [PASS] Stage 4: Tracking Parameters (ParamAngleX, ParamAngleY, ParamAngleZ)
 [PASS] Stage 5: Texture Atlas (4096x4096 RGBA8, POT verified)
 [PASS] Stage 6: Topological Non-Inversion (100% positive signed triangle area)
----------------------------------------------------------------------
 RESULT: ALL 6 STAGES PASSED (0 Errors, 0 Warnings)
======================================================================
```

---

## 4. Visual Verification in Live2D Cubism Viewer

Live2D Cubism Viewer (for OW) is the official tool for testing Live2D runtime models.

### Step 1: Load the Model
1. Open **Live2D Cubism Viewer**.
2. Locate your exported model folder (e.g. `output/Kohaku/`).
3. Drag and drop `Kohaku.model3.json` directly onto the Cubism Viewer window.
4. The model will load instantly into the 3D viewport.

### Step 2: Verify Initial Rendering
- Check that the model texture appears sharp and crisp.
- Verify that character layers (hair, face, eyes, mouth) are rendered in the correct front-to-back occlusion order.

### Step 3: Parameter Slider Verification
In the **Parameter Palette** (left sidebar), test the sliders:

1. **`ParamAngleX` (Head Yaw: Left $\leftrightarrow$ Right)**:
   - Drag the slider from `-30.0` to `+30.0`.
   - **Expected behavior**: The face turns horizontally. The turned-away cheek compresses due to anime foreshortening, and foreground hair exhibits depth parallax over the face skin.
2. **`ParamAngleY` (Head Pitch: Down $\leftrightarrow$ Up)**:
   - Drag the slider from `-30.0` to `+30.0`.
   - **Expected behavior**: The face pitches upward and downward. The chin recedes on upward tilt and expands on downward tilt.
3. **`ParamAngleZ` (Head Roll: Tilt Left $\leftrightarrow$ Tilt Right)**:
   - Drag the slider from `-20.0` to `+20.0`.
   - **Expected behavior**: The head tilts smoothly clockwise and counter-clockwise.
4. **2D Combined Yaw-Pitch Sweep**:
   - In the 2D parameter box (Angle X $\times$ Angle Y), drag the cursor across all four diagonal corners:
     * Top-Left (`AngleX = -30°, AngleY = +30°`)
     * Top-Right (`AngleX = +30°, AngleY = +30°`)
     * Bottom-Left (`AngleX = -30°, AngleY = -30°`)
     * Bottom-Right (`AngleX = +30°, AngleY = -30°`)
   - **Expected behavior**: Smooth bilinear interpolation without popping, polygon pinching, or triangle flipping.

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
2. The folder structure inside `Live2DModels/` must look like:
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

## 6. Troubleshooting Common Visual Artifacts

### Issue 1: Texture Bleeding or Dark Outline Edges
- **Symptom**: Thin dark lines or color smears around the borders of layers (e.g. hair strands or eye pupils).
- **Cause**: UV coordinates sampling pixels outside the layer content due to linear texture filtering in the GPU.
- **Solution**: The exporter automatically applies **Edge Bleed Color Dilation** and padding. If issues persist, re-export with higher padding:
  ```bash
  python export_live2d.py character.psd --resolution 4096
  ```

### Issue 2: Inverted Polygons / Black Geometry Pinching
- **Symptom**: Triangle mesh folds over itself, creating a black glitch or jagged edge during extreme rotations (AngleX = 30°).
- **Cause**: Mesh vertex displacement exceeded the local triangle geometry limit.
- **Solution**: Decrease mesh grid spacing for higher density, or decrease angle range:
  ```bash
  python export_live2d.py character.psd --grid-size 15 --angle-x-range "-25.0,25.0"
  ```

### Issue 3: Layer Clipping / Incorrect Z-Order
- **Symptom**: Eyes render behind the face skin, or front hair renders behind the ears.
- **Cause**: Layer semantic naming was not recognized, causing incorrect Z-depth stratification.
- **Solution**: Ensure layer names follow standard naming conventions:
  - Hair Front: `Hair_Front`, `Bangs`, `前髪`
  - Eyes: `Eye_L`, `Eye_R`, `左目`, `右目`
  - Face: `Face`, `Skin`, `顔`, `輪郭`
  - Hair Back: `Hair_Back`, `後ろ髪`

### Issue 4: Black / Missing Textures in Viewer
- **Symptom**: The model loads as a white or black silhouette with no textures.
- **Cause**: Texture atlas dimension is not a power of two, or relative paths in `.model3.json` used Windows backslashes (`\`).
- **Solution**: The exporter strictly normalizes all paths to forward slashes (`/`) and enforces power-of-two dimensions (512, 1024, 2048, 4096, 8192). Run `python validate_live2d.py <model_dir>` to verify Stage 3 and Stage 5.
```

---

## 6. Synthesis & Concrete Implementation Plan

### 6.1 Deliverables for Milestone 4 Workers

1. **`src/validator/structural_validator.py`** & **`validate_live2d.py`**:
   - Full 6-stage validator implementation with `ValidationStageResult`, `ValidationReport`, and `validate_live2d_model()`.
   - Rich CLI console reporter with ANSI color formatting.
2. **`src/cli/main.py`** & **`export_live2d.py`**:
   - CLI argument parser with all required flags and options.
   - End-to-end pipeline runner connecting Ingestion -> Mesh -> Deformation -> Packing -> MOC3 -> Validator.
   - Standardized exit codes (0..5).
3. **`tests/test_validator.py`**:
   - Full test suite covering all 6 stages with positive and negative corrupted fixtures (corrupt magic, misaligned sections, invalid json schema, out-of-range params, non-power-of-two texture, inverted triangles).
4. **`tests/test_cli.py`**:
   - Full CLI test suite covering argument parsing, exit codes 0-5, end-to-end mock export, `--validate` integration, and error trapping.
5. **`WALKTHROUGH.md`**:
   - Complete user verification guide placed in workspace root.

---

## 7. Conclusion

Milestone 4 test architecture and walkthrough documentation have been completely designed and specified with exhaustive test matrices, fixture factories, interface contracts, and verbatim user manuals. The implementation path is clear, deterministic, and fully compatible with the existing Milestone 1, 2, and 3 codebase.
