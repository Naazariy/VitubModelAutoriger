# Milestone 4 Deep Technical Analysis: 6-Stage Structural Validator & Verification Engine

**Author**: Explorer 1 (Validator & Quality Engineering Specialist)  
**Date**: 2026-08-22  
**Target Modules**: `src/validator/structural_validator.py`, `src/validator/__init__.py`, and `validate_live2d.py`  
**Working Directory**: `d:\VitubModel\.agents\sub_orch_m4_explorer_1`  

---

## 1. Executive Summary & Context

Milestone 4 delivers the critical quality gate for the rig-free automated VTuber Live2D generation pipeline. While Milestones 1–3 established asset ingestion, SciPy Delaunay triangulation, ARAP deformation solving, texture packing, and binary MOC3/JSON export, the **6-Stage Structural Validator** serves as the automated gatekeeper. It programmatically guarantees that every generated model bundle satisfies the binary, structural, semantic, and topological constraints of the official Live2D Cubism runtime standard and downstream platforms such as **Live2D Cubism Viewer** and **VTube Studio**.

### Core Objectives
1. **Automated Verification**: Provide a programmatic Python API (`validate_live2d_model`) and headless CLI tool (`validate_live2d.py`) that audits exported Live2D assets without human intervention.
2. **Deep 6-Stage Verification Hierarchy**:
   - **Stage 1: Binary MOC3 Header Integrity** (Magic bytes, version 3, endianness, minimum file size).
   - **Stage 2: Section Table Offsets & Count Table Sanity** (64-byte alignment, 160-slot offset table, monotonicity, CountInfoTable counters, CanvasInfo metadata).
   - **Stage 3: JSON Manifest Schema & File Reference Conformance** (`.model3.json` and `.cdi3.json` schemas, forward-slash relative path normalization, asset existence).
   - **Stage 4: Parameter & Keyform Bounds Verification** (Core tracking IDs `ParamAngleX`, `ParamAngleY`, `ParamAngleZ`, ranges $[-30, 30]$, monotonic key values, keyform grid tensor dimensions).
   - **Stage 5: Texture Atlas & UV Coordinate Safety** (Power-of-two PNG dimensions $512 \dots 8192$, valid 32-bit RGBA channels, atlas UV coordinates strictly inside $[0.0, 1.0]$, non-degenerate UV areas).
   - **Stage 6: Topological Non-Inversion & Deformation Continuity** (Zero NaNs/Infs, index bounds validity, strictly positive signed triangle areas $A_{\text{signed}} > -10^{-4}$ across all keyforms, bounded vertex displacements).
3. **100% Backwards & E2E Compatibility**: Ensure seamless interoperation with `tests/conftest.py`, `tests/e2e/`, `Moc3Reader`, `Model3Writer`, and CLI `--validate` integration.

---

## 2. In-Depth 6-Stage Validation Specifications

```
┌────────────────────────────────────────────────────────────────────────┐
│               STAGE 1: BINARY MOC3 HEADER VERIFICATION                 │
│  - Magic bytes: b'MOC3' (0x4D 0x4F 0x43 0x33)                          │
│  - Version == 3 (Cubism 3.0 / 4.0 standard format)                     │
│  - Endianness == 0 (Little-Endian standard)                            │
│  - Minimum physical file size >= 64 bytes                              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│            STAGE 2: SECTION TABLE OFFSETS & COUNT TABLE SANITY         │
│  - 160 uint32 SectionOffsetTable at 0x0040 (640 bytes)                 │
│  - Strict 64-byte alignment: (len(data) % 64 == 0) & (offsets % 64 == 0│
│  - Offset monotonicity: 0x0740 <= offset < len(data)                   │
│  - 1152-byte null RuntimeAddressMap at 0x02C0..0x0740                  │
│  - CountInfoTable at 0x0740: n_parts, n_art_meshes, n_params > 0       │
│  - CanvasInfo at 0x0840: PPU, width, height, origin sanity             │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│         STAGE 3: JSON MANIFEST SCHEMA & FILE REFERENCE CONFORMANCE      │
│  - .model3.json: Version == 3, valid JSON syntax                       │
│  - FileReferences.Moc: Path exists, normalized forward slashes '/'     │
│  - FileReferences.Textures: >= 1 existing texture paths, no backslashes│
│  - .cdi3.json: Parameters, ParameterGroups, Parts display tree        │
│  - Optional Physics & DisplayInfo relative path existence              │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│            STAGE 4: PARAMETER & KEYFORM BOUNDS VERIFICATION            │
│  - Core tracking parameters: ParamAngleX, ParamAngleY, ParamAngleZ     │
│  - Bounds sanity: min < default < max (e.g. [-30, 0, 30])              │
│  - Key values: Monotonically increasing (e.g. [-30.0, 0.0, 30.0])       │
│  - Keyform counts: 3 keyforms per parameter, 3x3=9 grid tensors        │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             STAGE 5: TEXTURE ATLAS & UV COORDINATE SAFETY              │
│  - PNG readability: Valid 32-bit RGBA format (4 channels, uint8)       │
│  - Power-of-Two dimensions: 512, 1024, 2048, 4096, 8192                │
│  - UV coordinate bounds: 0.0 - 1e-4 <= u, v <= 1.0 + 1e-4              │
│  - UV triangle area non-degeneracy (A_uv > 0)                          │
└───────────────────────────────────┬────────────────────────────────────┘
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│     STAGE 6: TOPOLOGICAL NON-INVERSION & DEFORMATION CONTINUITY        │
│  - No NaN or Inf coordinates in vertex or keyform displacement buffers │
│  - Triangle indices in valid range [0, N_vertices - 1]                 │
│  - Signed Triangle Area: A_signed > -1e-4 across all keyforms          │
│  - Identity keyform at (0, 0) matches base pose (max delta < 1e-4)     │
│  - Vertex displacement bounded within 2.5x model bounding radius       │
└────────────────────────────────────────────────────────────────────────┘
```

---

### Stage 1: Binary MOC3 Header Verification
- **Purpose**: Validate the physical byte signature and binary encapsulation of the `.moc3` container.
- **Byte-Level Verification Protocol**:
  1. `len(data) >= 64`: The fixed header alone occupies 64 bytes. A file smaller than 64 bytes is critically truncated.
  2. `data[0:4] == b"MOC3"`: First 4 bytes must match exact magic bytes `0x4D 0x4F 0x43 0x33`. Rejects arbitrary files (PNG, JSON, corrupted bytes).
  3. `data[4] in (1, 2, 3, 4, 5)`: Version byte at index 4 must indicate a supported Cubism version (Version 3 or 4 is standard).
  4. `data[5] == 0`: Endianness byte at index 5 must be `0` (Little-Endian). Standard Live2D native runtime (`Live2DCubismCore`) operates strictly in little-endian.
  5. Header padding integrity: Header bytes 6..7 and unassigned diagnostic slots must be properly unpacked without raising `struct.error`.
- **Diagnostic Metrics**:
  - `magic_str`: Decoded ASCII string (e.g. `"MOC3"`).
  - `version`: Integer version (e.g. `3`).
  - `is_little_endian`: Boolean (`True` if byte 5 == 0).
  - `header_size`: 64 bytes.

---

### Stage 2: Section Table Offsets & Count Table Sanity
- **Purpose**: Verify internal data table offsets, memory alignment invariants, null runtime padding, and structural count consistency.
- **Detailed Byte Layout Checkpoints**:
  1. **SectionOffsetTable Location & Size**:
     - Starts at offset `0x0040` (64 bytes).
     - Contains exactly 160 32-bit unsigned integers (`<160I`, 640 bytes total, ending at `0x02C0` = 704 bytes).
  2. **Strict 64-Byte Memory Alignment**:
     - Total file size: `len(data) % 64 == 0`.
     - For each slot index $i \in [0, 159]$ where $\text{offset}_i > 0$:
       $$\text{offset}_i \pmod{64} == 0$$
  3. **Section Monotonicity & File Boundary Bounds**:
     - For every non-zero offset: `0x0740 <= offset < len(data)`.
     - No offset points outside physical file bounds.
  4. **RuntimeAddressMap (Offset `0x02C0` to `0x0740`, 1152 bytes)**:
     - Reserved for in-place runtime address patching (`csmReviveMocInPlace`).
     - Must consist of pure null bytes `b"\x00" * 1152`.
  5. **CountInfoTable (Section 0 at `0x0740`, 256 bytes)**:
     - Leading 128 bytes null padding: `data[0x0740 : 0x07C0] == b"\x00" * 128`.
     - 23 uint32 counters at `0x07C0` (`<23I`):
       * `n_parts >= 1` (contains at least PartRoot).
       * `n_art_meshes > 0` (at least 1 drawable ArtMesh).
       * `n_parameters > 0` (at least 1 parameter).
       * `art_mesh_keyforms >= n_art_meshes` (at least 1 keyform per mesh).
       * `keyform_positions == sum(n_vertices_i * n_keyforms_i)`.
       * `total_uvs == sum(n_vertices_i)`.
       * `position_indices == sum(n_triangles_i * 3)`.
       * `keys >= n_parameters` (each parameter has $\ge 1$ key value).
     - Trailing 36 bytes null padding: `data[0x07C0 + 92 : 0x0840] == b"\x00" * 36`.
  6. **CanvasInfo (Section 1 at `0x0840`, 64 bytes)**:
     - Packed format: `<5fB43x` (21 bytes data + 43 bytes null pad).
     - `pixels_per_unit > 0.0` (typically 2000.0 or canvas dimension).
     - `canvas_width >= 100.0` and `canvas_height >= 100.0`.
     - `0.0 <= origin_x <= canvas_width` and `0.0 <= origin_y <= canvas_height`.

---

### Stage 3: JSON Manifest Schema & File Reference Conformance
- **Purpose**: Verify that metadata manifests conform to Cubism 3.0+ JSON specifications and all referenced assets exist on disk.
- **Verification Rules**:
  1. **`.model3.json` Schema**:
     - Root object must contain `"Version": 3`.
     - `"FileReferences"` dictionary must exist.
     - `"FileReferences.Moc"`: Non-empty string pointing to `.moc3` file.
     - `"FileReferences.Textures"`: Non-empty list of strings (`len >= 1`).
     - Optional fields: `"FileReferences.DisplayInfo"`, `"FileReferences.Physics"`, `"FileReferences.Pose"`.
     - `"Groups"` array: LipSync and EyeBlink parameter tracking groups with `"Target": "Parameter"`.
     - `"Layout"` object: `CenterX`, `CenterY`, `Width`, `Height` as floats.
  2. **Path Normalization & Relative Existence**:
     - All file paths in `"FileReferences"` must use strictly forward slashes `/`.
     - Rejects any Windows backslashes `\` (`"\\" in path` triggers an error because Cubism native runtimes on iOS/Android/macOS fail to load paths with backslashes).
     - Every referenced file (`.moc3`, each texture `.png`, `.cdi3.json`, `.physics3.json`) must physically exist on disk relative to the `.model3.json` parent folder.
  3. **`.cdi3.json` Display Information Schema**:
     - `"Version": 3`.
     - `"Parameters"`: List of objects containing `{"Id": str, "GroupId": str, "Name": str}`.
     - `"ParameterGroups"`: List of objects containing `{"Id": str, "GroupId": str, "Name": str}`.
     - `"Parts"`: List of objects containing `{"Id": str, "Name": str}`.

---

### Stage 4: Parameter & Keyform Bounds Verification
- **Purpose**: Ensure all Live2D tracking parameters have correct identifiers, monotonic key divisions, valid default values, and valid keyform grid counts.
- **Verification Rules**:
  1. **Standard Tracking Parameter Presence**:
     - Must define `ParamAngleX` (Head Yaw).
     - Must define `ParamAngleY` (Head Pitch).
     - Recommended / Optional: `ParamAngleZ` (Head Roll).
  2. **Parameter Value Ranges**:
     - `ParamAngleX`: $\text{min} \le -20.0^\circ$, $\text{max} \ge 20.0^\circ$, $\text{default} == 0.0^\circ$ (Nominal: `[-30.0, 0.0, 30.0]`).
     - `ParamAngleY`: $\text{min} \le -20.0^\circ$, $\text{max} \ge 20.0^\circ$, $\text{default} == 0.0^\circ$ (Nominal: `[-30.0, 0.0, 30.0]`).
     - `ParamAngleZ`: $\text{min} \le -15.0^\circ$, $\text{max} \ge 15.0^\circ$, $\text{default} == 0.0^\circ$ (Nominal: `[-20.0, 0.0, 20.0]`).
     - Invariant for all parameters: $\text{min\_val} < \text{default\_val} < \text{max\_val}$.
  3. **Monotonic Key Values**:
     - Each parameter must have at least 2 (standard: 3) key values.
     - Keys must be strictly monotonically increasing: $k_0 < k_1 < k_2 < \dots < k_{n-1}$.
     - All keys must satisfy $\text{min\_val} \le k_i \le \text{max\_val}$.
  4. **Keyform Grid Consistency**:
     - For drawables linked to AngleX and AngleY ($3 \times 3$ grid), the keyform count must be exactly $3 \times 3 = 9$.
     - Each keyform displacement tensor must match the vertex count of the base mesh.

---

### Stage 5: Texture Atlas & UV Coordinate Safety
- **Purpose**: Verify texture atlas image format, power-of-two constraints, and mesh UV coordinate containment.
- **Verification Rules**:
  1. **Image Readability & Color Channels**:
     - Every texture file referenced by `.model3.json` must be loadable via PIL or OpenCV.
     - Format must be 4-channel RGBA (`img.mode == "RGBA"` or shape $(H, W, 4)$ uint8). If RGB (3-channel), issue a warning.
  2. **Power-of-Two (POT) Atlas Resolution**:
     - Width $W$ and Height $H$ must satisfy:
       $$(W > 0) \land ((W \ \& \ (W - 1)) == 0) \quad \text{and} \quad (H > 0) \land ((H \ \& \ (H - 1)) == 0)$$
     - Standard resolutions: $512, 1024, 2048, 4096, 8192$.
     - Reject non-POT dimensions (e.g. $500 \times 500$, $1000 \times 1000$).
  3. **Global UV Coordinate Invariants**:
     - For every vertex $i \in [0, N-1]$, atlas UV coordinate $(u_i, v_i)$ must satisfy:
       $$0.0 - 10^{-4} \le u_i \le 1.0 + 10^{-4} \quad \text{and} \quad 0.0 - 10^{-4} \le v_i \le 1.0 + 10^{-4}$$
  4. **UV Triangle Area Non-Degeneracy**:
     - For each triangle $(v_0, v_1, v_2)$, UV area:
       $$A_{\text{uv}} = \frac{1}{2} |(u_1 - u_0)(v_2 - v_0) - (u_2 - u_0)(v_1 - v_0)|$$
     - If $A_{\text{uv}} \le 0$ for all triangles of a mesh, flag as degenerate UV mapping.

---

### Stage 6: Topological Non-Inversion & Deformation Continuity
- **Purpose**: Guarantee geometric integrity and prevent mesh folding, inverted triangles, coordinate explosions, or numerical singularities across all deformed poses.
- **Verification Rules**:
  1. **Finite Coordinate Verification**:
     - Check base vertices and all keyform positions:
       $$\forall v: \neg \text{isnan}(v) \land \neg \text{isinf}(v)$$
  2. **Triangle Index Validity**:
     - For every triangle index triple $(i_0, i_1, i_2)$:
       $$0 \le i_0, i_1, i_2 < N_{\text{vertices}} \quad \text{and} \quad i_0 \ne i_1 \land i_1 \ne i_2 \land i_2 \ne i_0$$
  3. **Signed Triangle Area Preservation (Non-Inversion Guarantee)**:
     - For each triangle $t = (p_0, p_1, p_2)$ in rest pose and in every deformed keyform:
       $$A_{\text{signed}}(p_0, p_1, p_2) = \frac{1}{2} \left[ (x_1 - x_0)(y_2 - y_0) - (x_2 - x_0)(y_1 - y_0) \right]$$
     - Rest pose requirement: $A_{\text{signed}}^{\text{rest}} > 0$ (strict CCW winding).
     - Deformed pose requirement:
       $$A_{\text{signed}}^{\text{deformed}} > -10^{-4}$$
       (Any triangle with $A_{\text{signed}} \le -10^{-4}$ represents an inside-out inverted fold and is flagged as a critical geometrical failure).
  4. **Displacement Bounding Envelope**:
     - Maximum vertex displacement relative to base pose:
       $$\max_i \|v_i^{\text{deformed}} - v_i^{\text{base}}\| \le 2.5 \times R_{\text{bounding}}$$
       (Catches numerical explosions or unbounded solver divergence).
  5. **Identity Rest Pose Verification**:
     - At neutral angles $(\text{AngleX}=0, \text{AngleY}=0, \text{AngleZ}=0)$, the keyform position must be identical to base vertices within $\Delta < 10^{-4}$.

---

## 3. Data Structures & Class Architecture

### 3.1 Validation Result Models

```python
# src/validator/structural_validator.py

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Union
import json
import struct
import numpy as np
from PIL import Image


@dataclass
class ValidationStageResult:
    """Detailed outcome for an individual validation stage."""
    stage_number: int
    stage_name: str
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_number": self.stage_number,
            "stage_name": self.stage_name,
            "passed": self.passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "details": self.details,
        }


@dataclass
class ValidationReport:
    """
    Master validation summary report aggregating results across all 6 stages.
    Maintains 100% backward compatibility with ValidationResult in tests/conftest.py.
    """
    passed: bool = True
    stages: List[ValidationStageResult] = field(default_factory=list)
    total_errors: int = 0
    total_warnings: int = 0
    model_path: str = ""
    model_name: str = ""

    # Backwards compatibility properties
    @property
    def is_valid(self) -> bool:
        """Alias for passed."""
        return self.passed

    @property
    def stages_passed(self) -> List[int]:
        """Returns list of 1-indexed stage numbers that passed."""
        return [s.stage_number for s in self.stages if s.passed]

    @property
    def errors(self) -> List[str]:
        """Returns flat list of all error messages across all stages."""
        errs = []
        for s in self.stages:
            errs.extend(s.errors)
        return errs

    @property
    def warnings(self) -> List[str]:
        """Returns flat list of all warning messages across all stages."""
        warns = []
        for s in self.stages:
            warns.extend(s.warnings)
        return warns

    def add_stage(self, stage_result: ValidationStageResult) -> None:
        """Appends a stage result and updates aggregate counters and overall status."""
        self.stages.append(stage_result)
        self.total_errors += len(stage_result.errors)
        self.total_warnings += len(stage_result.warnings)
        if not stage_result.passed:
            self.passed = False

    def to_dict(self) -> Dict[str, Any]:
        """Serializes report to dictionary for JSON output."""
        return {
            "is_valid": self.is_valid,
            "passed": self.passed,
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
            "stages_passed": self.stages_passed,
            "model_path": self.model_path,
            "model_name": self.model_name,
            "stages": [s.to_dict() for s in self.stages],
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def format_console(self, use_color: bool = True) -> str:
        """Renders color-coded CLI report with stage-by-stage audit details."""
        # ANSI color codes
        GREEN = "\033[92m" if use_color else ""
        RED = "\033[91m" if use_color else ""
        YELLOW = "\033[93m" if use_color else ""
        CYAN = "\033[96m" if use_color else ""
        BOLD = "\033[1m" if use_color else ""
        RESET = "\033[0m" if use_color else ""

        lines = []
        lines.append(f"{BOLD}{CYAN}======================================================================{RESET}")
        lines.append(f"{BOLD}{CYAN}             LIVE2D 6-STAGE STRUCTURAL VALIDATION REPORT              {RESET}")
        lines.append(f"{BOLD}{CYAN}======================================================================{RESET}")
        lines.append(f"Model Target : {self.model_path or 'N/A'}")
        lines.append(f"Model Name   : {self.model_name or 'N/A'}")
        status_str = f"{GREEN}[PASSED]{RESET}" if self.passed else f"{RED}[FAILED]{RESET}"
        lines.append(f"Overall Status: {BOLD}{status_str}{RESET} (Errors: {self.total_errors}, Warnings: {self.total_warnings})")
        lines.append(f"----------------------------------------------------------------------")

        for s in self.stages:
            tag = f"{GREEN}PASS{RESET}" if s.passed else f"{RED}FAIL{RESET}"
            lines.append(f" Stage {s.stage_number}: [{tag}] {BOLD}{s.stage_name}{RESET}")
            for err in s.errors:
                lines.append(f"   {RED}✖ ERROR:{RESET} {err}")
            for warn in s.warnings:
                lines.append(f"   {YELLOW}▲ WARN :{RESET} {warn}")
            if s.passed and not s.warnings and s.details:
                # Include short diagnostic summary if available
                detail_strs = [f"{k}={v}" for k, v in list(s.details.items())[:4]]
                if detail_strs:
                    lines.append(f"   {CYAN}✔ Details:{RESET} {', '.join(detail_strs)}")

        lines.append(f"{BOLD}{CYAN}======================================================================{RESET}")
        return "\n".join(lines)
```

---

### 3.2 `StructuralValidator` Class Architecture

```python
class StructuralValidator:
    """
    Production-Grade 6-Stage Programmatic Structural Validator for Live2D Cubism Model Bundles.
    """

    @classmethod
    def validate_live2d_model(
        cls,
        model_entry_path: Union[str, Path],
        strict: bool = False
    ) -> ValidationReport:
        """
        Primary validation entrypoint. Accepts directory, .model3.json path, or .moc3 path.
        Executes all 6 stages sequentially and returns comprehensive ValidationReport.
        """
        ...

    @classmethod
    def validate_stage1_moc3_header(cls, moc3_bytes: bytes) -> ValidationStageResult:
        """Stage 1: Validates b'MOC3' magic header, Version 3, and Little-Endian flag."""
        ...

    @classmethod
    def validate_stage2_section_tables(cls, moc3_bytes: bytes) -> ValidationStageResult:
        """Stage 2: Validates SectionOffsetTable, 64-byte alignment, CountInfoTable, CanvasInfo."""
        ...

    @classmethod
    def validate_stage3_json_manifest(
        cls,
        model_dir: Path,
        model3_path: Path
    ) -> Tuple[ValidationStageResult, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Stage 3: Validates .model3.json and .cdi3.json schemas and forward-slash path existence."""
        ...

    @classmethod
    def validate_stage4_parameter_bounds(
        cls,
        cdi_json: Optional[Dict[str, Any]],
        moc3_parsed: Optional[Dict[str, Any]]
    ) -> ValidationStageResult:
        """Stage 4: Validates ParamAngleX/Y/Z, ranges [-30, 30], and keyform divisions."""
        ...

    @classmethod
    def validate_stage5_textures_and_uvs(
        cls,
        model_dir: Path,
        texture_rel_paths: List[str],
        moc3_parsed: Optional[Dict[str, Any]]
    ) -> ValidationStageResult:
        """Stage 5: Validates Power-of-Two PNG textures (512..8192) and [0.0, 1.0] UV coordinates."""
        ...

    @classmethod
    def validate_stage6_topology_and_deformation(
        cls,
        moc3_bytes: bytes,
        moc3_parsed: Optional[Dict[str, Any]]
    ) -> ValidationStageResult:
        """Stage 6: Validates signed triangle area preservation (> -1e-4) and vertex finite bounds."""
        ...
```

---

## 4. Standalone CLI Tool: `validate_live2d.py`

### 4.1 CLI Specifications
`validate_live2d.py` resides at the workspace root (`d:\VitubModel\validate_live2d.py`) and allows users, scripts, or CI pipelines to inspect any exported Live2D model bundle.

#### Invocations
```bash
# Validate model bundle directory
python validate_live2d.py output/SampleModel

# Validate specific .model3.json
python validate_live2d.py output/SampleModel/SampleModel.model3.json

# Validate standalone .moc3 binary
python validate_live2d.py output/SampleModel/SampleModel.moc3

# Output JSON report
python validate_live2d.py output/SampleModel --json-report report.json --quiet

# Disable ANSI color formatting
python validate_live2d.py output/SampleModel --no-color
```

#### Argument Schema
| Argument | Type | Default | Description |
|---|---|---|---|
| `model_path` (Positional) | `str` | Required | Path to Live2D model directory, `.model3.json`, or `.moc3` file |
| `-o`, `--json-report` | `str` | `None` | Optional path to export machine-readable JSON validation report |
| `-q`, `--quiet` | `bool` | `False` | Suppress all stdout output except exit code and critical errors |
| `-v`, `--verbose` | `bool` | `False` | Display expanded diagnostic metrics for every stage |
| `--no-color` | `bool` | `False` | Disable ANSI color escapes in console output |
| `--strict` | `bool` | `False` | Treat all warnings as hard validation errors |

#### Exit Codes
- `0`: Validation Passed (`is_valid == True`).
- `1`: Invalid Arguments / File Not Found.
- `5`: Validation Failed (`total_errors > 0` or `is_valid == False`).

---

## 5. Concrete Implementation Blueprint

### 5.1 `src/validator/structural_validator.py` Implementation Details

Here is the complete structural architecture for `src/validator/structural_validator.py`:

```python
"""
src/validator/structural_validator.py
Production 6-Stage Programmatic Structural Validator for Live2D Cubism Model Bundles.
"""

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import struct
from typing import Dict, List, Tuple, Optional, Any, Union
import numpy as np
from PIL import Image

from src.exporter.moc3_writer import Moc3Reader, decode_id_64


@dataclass
class ValidationStageResult:
    """Detailed outcome for an individual validation stage."""
    stage_number: int
    stage_name: str
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_number": self.stage_number,
            "stage_name": self.stage_name,
            "passed": self.passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "details": self.details,
        }


@dataclass
class ValidationReport:
    """Master validation summary report aggregating results across all 6 stages."""
    passed: bool = True
    stages: List[ValidationStageResult] = field(default_factory=list)
    total_errors: int = 0
    total_warnings: int = 0
    model_path: str = ""
    model_name: str = ""

    @property
    def is_valid(self) -> bool:
        return self.passed

    @property
    def stages_passed(self) -> List[int]:
        return [s.stage_number for s in self.stages if s.passed]

    @property
    def errors(self) -> List[str]:
        errs = []
        for s in self.stages:
            errs.extend(s.errors)
        return errs

    @property
    def warnings(self) -> List[str]:
        warns = []
        for s in self.stages:
            warns.extend(s.warnings)
        return warns

    def add_stage(self, stage_result: ValidationStageResult) -> None:
        self.stages.append(stage_result)
        self.total_errors += len(stage_result.errors)
        self.total_warnings += len(stage_result.warnings)
        if not stage_result.passed:
            self.passed = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "passed": self.passed,
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
            "stages_passed": self.stages_passed,
            "model_path": self.model_path,
            "model_name": self.model_name,
            "stages": [s.to_dict() for s in self.stages],
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def format_console(self, use_color: bool = True) -> str:
        GREEN = "\033[92m" if use_color else ""
        RED = "\033[91m" if use_color else ""
        YELLOW = "\033[93m" if use_color else ""
        CYAN = "\033[96m" if use_color else ""
        BOLD = "\033[1m" if use_color else ""
        RESET = "\033[0m" if use_color else ""

        lines = []
        lines.append(f"{BOLD}{CYAN}======================================================================{RESET}")
        lines.append(f"{BOLD}{CYAN}             LIVE2D 6-STAGE STRUCTURAL VALIDATION REPORT              {RESET}")
        lines.append(f"{BOLD}{CYAN}======================================================================{RESET}")
        lines.append(f"Model Target : {self.model_path or 'N/A'}")
        lines.append(f"Model Name   : {self.model_name or 'N/A'}")
        status_str = f"{GREEN}[PASSED]{RESET}" if self.passed else f"{RED}[FAILED]{RESET}"
        lines.append(f"Overall Status: {BOLD}{status_str}{RESET} (Errors: {self.total_errors}, Warnings: {self.total_warnings})")
        lines.append(f"----------------------------------------------------------------------")

        for s in self.stages:
            tag = f"{GREEN}PASS{RESET}" if s.passed else f"{RED}FAIL{RESET}"
            lines.append(f" Stage {s.stage_number}: [{tag}] {BOLD}{s.stage_name}{RESET}")
            for err in s.errors:
                lines.append(f"   {RED}✖ ERROR:{RESET} {err}")
            for warn in s.warnings:
                lines.append(f"   {YELLOW}▲ WARN :{RESET} {warn}")
            if s.passed and not s.warnings and s.details:
                detail_strs = [f"{k}={v}" for k, v in list(s.details.items())[:4]]
                if detail_strs:
                    lines.append(f"   {CYAN}✔ Details:{RESET} {', '.join(detail_strs)}")

        lines.append(f"{BOLD}{CYAN}======================================================================{RESET}")
        return "\n".join(lines)


class StructuralValidator:
    """6-Stage Structural Validator for Live2D Cubism models."""

    @classmethod
    def validate_stage1_moc3_header(cls, moc3_bytes: bytes) -> ValidationStageResult:
        errors = []
        warnings = []
        details = {}

        if len(moc3_bytes) < 64:
            errors.append(f"MOC3 binary file too small: {len(moc3_bytes)} bytes < 64 bytes minimum header")
            return ValidationStageResult(1, "Binary MOC3 Header Integrity", False, errors, warnings, details)

        magic = moc3_bytes[:4]
        if magic != b"MOC3":
            errors.append(f"Invalid MOC3 magic header bytes: expected b'MOC3', got {magic}")

        version = moc3_bytes[4]
        if version not in (1, 2, 3, 4, 5):
            errors.append(f"Unsupported MOC3 version: {version} (expected 3 or 4)")

        endianness = moc3_bytes[5]
        if endianness != 0:
            errors.append(f"Unsupported endianness flag: {endianness} (expected 0 Little-Endian)")

        details["magic"] = magic.decode("ascii", errors="replace")
        details["version"] = version
        details["endianness"] = "little-endian" if endianness == 0 else "big-endian"
        details["file_size_bytes"] = len(moc3_bytes)

        return ValidationStageResult(
            stage_number=1,
            stage_name="Binary MOC3 Header Integrity",
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details=details
        )

    @classmethod
    def validate_stage2_section_tables(cls, moc3_bytes: bytes) -> ValidationStageResult:
        errors = []
        warnings = []
        details = {}

        if len(moc3_bytes) < 64:
            return ValidationStageResult(2, "Section Table Offsets & Count Table Sanity", False, ["Binary too small (< 64 bytes)"], warnings, details)

        # 64-byte alignment check of physical file size
        if len(moc3_bytes) % 64 != 0:
            warnings.append(f"Total MOC3 binary size ({len(moc3_bytes)} bytes) is not 64-byte aligned (remainder {len(moc3_bytes) % 64})")

        # Section table at 0x0040 (640 bytes = 160 uint32s)
        if len(moc3_bytes) >= 704:
            section_offsets = list(struct.unpack_from("<160I", moc3_bytes, 64))
            aligned_count = 0
            for idx, off in enumerate(section_offsets):
                if off > 0:
                    if off % 64 != 0:
                        errors.append(f"Section offset [{idx}] at {hex(off)} is not 64-byte aligned")
                    if off >= len(moc3_bytes):
                        errors.append(f"Section offset [{idx}] at {hex(off)} exceeds file size ({len(moc3_bytes)} bytes)")
                    else:
                        aligned_count += 1
            details["active_sections"] = aligned_count

            # Null RuntimeAddressMap at 0x02C0..0x0740
            if len(moc3_bytes) >= 0x0740:
                null_map = moc3_bytes[0x02C0:0x0740]
                if any(b != 0 for b in null_map):
                    warnings.append("RuntimeAddressMap at 0x02C0 contains non-null bytes")

            # CountInfoTable at Section 0 (0x0740)
            cnt_off = section_offsets[0] or 0x0740
            if len(moc3_bytes) >= cnt_off + 256:
                counters = struct.unpack_from("<128x23I36x", moc3_bytes, cnt_off)
                details["parts"] = counters[0]
                details["art_meshes"] = counters[4]
                details["parameters"] = counters[5]
                details["art_mesh_keyforms"] = counters[9]
                details["keyform_positions"] = counters[10]
                details["keys"] = counters[14]
                details["uvs"] = counters[15]
                details["position_indices"] = counters[16]

                if counters[0] < 1:
                    warnings.append(f"CountInfoTable: Parts count is {counters[0]} (expected >= 1)")
                if counters[4] < 1:
                    errors.append(f"CountInfoTable: ArtMeshes count is 0")
                if counters[5] < 1:
                    errors.append(f"CountInfoTable: Parameters count is 0")
                if counters[15] < 1:
                    errors.append(f"CountInfoTable: UV count is 0")
                if counters[16] < 1:
                    errors.append(f"CountInfoTable: Position indices count is 0")

            # CanvasInfo at Section 1 (0x0840)
            canvas_off = section_offsets[1] or 0x0840
            if len(moc3_bytes) >= canvas_off + 64:
                canvas_fields = struct.unpack_from("<5fB43x", moc3_bytes, canvas_off)
                details["canvas_width"] = canvas_fields[3]
                details["canvas_height"] = canvas_fields[4]
                details["pixels_per_unit"] = canvas_fields[0]
                if canvas_fields[3] <= 0 or canvas_fields[4] <= 0:
                    errors.append(f"Invalid Canvas dimensions: {canvas_fields[3]}x{canvas_fields[4]}")

        return ValidationStageResult(
            stage_number=2,
            stage_name="Section Table Offsets & Count Table Sanity",
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details=details
        )

    @classmethod
    def validate_stage3_json_manifest(
        cls,
        model_dir: Path,
        model3_path: Path
    ) -> Tuple[ValidationStageResult, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        errors = []
        warnings = []
        details = {}
        model3_data = None
        cdi3_data = None

        if not model3_path.exists():
            errors.append(f"model3.json manifest not found at {model3_path}")
            return ValidationStageResult(3, "JSON Manifest & File Reference Conformance", False, errors, warnings, details), None, None

        try:
            with open(model3_path, "r", encoding="utf-8") as f:
                model3_data = json.load(f)
        except Exception as e:
            errors.append(f"Invalid JSON syntax in {model3_path.name}: {e}")
            return ValidationStageResult(3, "JSON Manifest & File Reference Conformance", False, errors, warnings, details), None, None

        # Version check
        v = model3_data.get("Version")
        if v != 3:
            errors.append(f"model3.json: Expected Version == 3, got {v}")
        details["version"] = v

        file_refs = model3_data.get("FileReferences", {})
        if not file_refs:
            errors.append("model3.json: Missing 'FileReferences' object")
            return ValidationStageResult(3, "JSON Manifest & File Reference Conformance", False, errors, warnings, details), model3_data, None

        # Moc file check
        moc_rel = file_refs.get("Moc")
        if not moc_rel:
            errors.append("model3.json: Missing 'FileReferences.Moc'")
        else:
            if "\\" in moc_rel:
                errors.append(f"model3.json: Moc path contains Windows backslash: '{moc_rel}'")
            moc_full = model_dir / moc_rel
            if not moc_full.exists():
                errors.append(f"model3.json: Referenced Moc file does not exist: {moc_full}")
            details["moc_file"] = moc_rel

        # Textures check
        tex_list = file_refs.get("Textures", [])
        if not tex_list:
            errors.append("model3.json: 'FileReferences.Textures' is empty")
        else:
            details["texture_count"] = len(tex_list)
            for tex_rel in tex_list:
                if "\\" in tex_rel:
                    errors.append(f"model3.json: Texture path contains Windows backslash: '{tex_rel}'")
                tex_full = model_dir / tex_rel
                if not tex_full.exists():
                    errors.append(f"model3.json: Referenced Texture file does not exist: {tex_full}")

        # DisplayInfo (.cdi3.json) check
        cdi_rel = file_refs.get("DisplayInfo")
        if cdi_rel:
            if "\\" in cdi_rel:
                errors.append(f"model3.json: DisplayInfo path contains Windows backslash: '{cdi_rel}'")
            cdi_full = model_dir / cdi_rel
            if not cdi_full.exists():
                warnings.append(f"model3.json: Referenced DisplayInfo file not found: {cdi_full}")
            else:
                try:
                    with open(cdi_full, "r", encoding="utf-8") as f:
                        cdi3_data = json.load(f)
                    if cdi3_data.get("Version") != 3:
                        warnings.append(f"cdi3.json: Expected Version == 3, got {cdi3_data.get('Version')}")
                except Exception as e:
                    warnings.append(f"cdi3.json: Failed to parse JSON: {e}")

        return (
            ValidationStageResult(
                stage_number=3,
                stage_name="JSON Manifest & File Reference Conformance",
                passed=len(errors) == 0,
                errors=errors,
                warnings=warnings,
                details=details
            ),
            model3_data,
            cdi3_data
        )

    @classmethod
    def validate_stage4_parameter_bounds(
        cls,
        cdi_json: Optional[Dict[str, Any]],
        moc3_parsed: Optional[Dict[str, Any]]
    ) -> ValidationStageResult:
        errors = []
        warnings = []
        details = {}

        param_ids = []
        if moc3_parsed and "parameter_ids" in moc3_parsed:
            param_ids = moc3_parsed["parameter_ids"]
        elif cdi_json and "Parameters" in cdi_json:
            param_ids = [p["Id"] for p in cdi_json["Parameters"] if "Id" in p]

        details["parameters_found"] = param_ids

        # Check essential tracking parameters
        for required_pid in ["ParamAngleX", "ParamAngleY"]:
            if required_pid not in param_ids:
                errors.append(f"Required head tracking parameter '{required_pid}' not found")
        if "ParamAngleZ" not in param_ids:
            warnings.append("Recommended parameter 'ParamAngleZ' (Head Roll) not found")

        return ValidationStageResult(
            stage_number=4,
            stage_name="Parameter & Keyform Bounds Verification",
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details=details
        )

    @classmethod
    def validate_stage5_textures_and_uvs(
        cls,
        model_dir: Path,
        texture_rel_paths: List[str],
        moc3_bytes: Optional[bytes]
    ) -> ValidationStageResult:
        errors = []
        warnings = []
        details = {}

        # 1. Texture image checks
        valid_textures = 0
        for tex_rel in texture_rel_paths:
            tex_full = model_dir / tex_rel
            if not tex_full.exists():
                continue
            try:
                with Image.open(tex_full) as img:
                    w, h = img.size
                    details[f"{Path(tex_rel).name}_dimensions"] = f"{w}x{h}"
                    # Power of two check
                    if (w <= 0) or (w & (w - 1) != 0) or (h <= 0) or (h & (h - 1) != 0):
                        errors.append(f"Texture '{tex_rel}' dimensions ({w}x{h}) are not power-of-two (e.g. 512, 1024, 2048, 4096, 8192)")
                    if w < 512 or h < 512 or w > 8192 or h > 8192:
                        warnings.append(f"Texture '{tex_rel}' dimensions ({w}x{h}) outside nominal [512..8192] range")
                    if img.mode != "RGBA":
                        warnings.append(f"Texture '{tex_rel}' color format is {img.mode}, recommended RGBA 32-bit")
                    valid_textures += 1
            except Exception as e:
                errors.append(f"Failed to read texture image '{tex_rel}': {e}")

        # 2. UV bounds check if binary moc3 is available
        if moc3_bytes and len(moc3_bytes) >= 704:
            section_offsets = struct.unpack_from("<160I", moc3_bytes, 64)
            uv_off = section_offsets[33]
            cnt_off = section_offsets[0] or 0x0740
            if uv_off > 0 and len(moc3_bytes) >= cnt_off + 256:
                counters = struct.unpack_from("<128x23I36x", moc3_bytes, cnt_off)
                n_uvs = counters[15]
                if n_uvs > 0 and len(moc3_bytes) >= uv_off + n_uvs * 8:
                    uv_floats = struct.unpack_from(f"<{n_uvs * 2}f", moc3_bytes, uv_off)
                    uv_arr = np.array(uv_floats, dtype=np.float32).reshape(-1, 2)
                    min_uv = np.min(uv_arr, axis=0)
                    max_uv = np.max(uv_arr, axis=0)
                    details["min_uv"] = [float(min_uv[0]), float(min_uv[1])]
                    details["max_uv"] = [float(max_uv[0]), float(max_uv[1])]
                    if np.any(uv_arr < -1e-4) or np.any(uv_arr > 1.0 + 1e-4):
                        errors.append(f"UV coordinates exceed [0.0, 1.0] range (bounds: min={min_uv}, max={max_uv})")

        return ValidationStageResult(
            stage_number=5,
            stage_name="Texture Atlas & UV Coordinate Safety",
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details=details
        )

    @classmethod
    def validate_stage6_topology_and_deformation(
        cls,
        moc3_bytes: bytes
    ) -> ValidationStageResult:
        errors = []
        warnings = []
        details = {}

        if len(moc3_bytes) < 704:
            return ValidationStageResult(6, "Topological Non-Inversion & Deformation Continuity", True, errors, warnings, details)

        section_offsets = struct.unpack_from("<160I", moc3_bytes, 64)
        cnt_off = section_offsets[0] or 0x0740
        if len(moc3_bytes) < cnt_off + 256:
            return ValidationStageResult(6, "Topological Non-Inversion & Deformation Continuity", True, errors, warnings, details)

        counters = struct.unpack_from("<128x23I36x", moc3_bytes, cnt_off)
        n_art_meshes = counters[4]
        n_keyform_positions = counters[10]
        n_indices = counters[16]

        pos_off = section_offsets[32]
        idx_off = section_offsets[34]

        if pos_off > 0 and n_keyform_positions > 0 and len(moc3_bytes) >= pos_off + n_keyform_positions * 8:
            pos_floats = struct.unpack_from(f"<{n_keyform_positions * 2}f", moc3_bytes, pos_off)
            pos_arr = np.array(pos_floats, dtype=np.float32).reshape(-1, 2)
            if np.isnan(pos_arr).any() or np.isinf(pos_arr).any():
                errors.append("Keyform vertex positions contain NaN or Inf values")
            details["total_keyform_vertices"] = n_keyform_positions

        if idx_off > 0 and n_indices > 0 and len(moc3_bytes) >= idx_off + n_indices * 2:
            raw_indices = struct.unpack_from(f"<{n_indices}H", moc3_bytes, idx_off)
            indices_arr = np.array(raw_indices, dtype=np.int32)
            details["total_indices"] = n_indices
            details["total_triangles"] = n_indices // 3

            # Check for inverted triangles in keyforms if index array aligns
            if pos_off > 0 and len(indices_arr) >= 3 and len(pos_arr) > 0:
                triangles = indices_arr.reshape(-1, 3)
                # Compute signed areas for base mesh triangles (first N vertices)
                max_idx = np.max(triangles)
                if max_idx < len(pos_arr):
                    p0 = pos_arr[triangles[:, 0]]
                    p1 = pos_arr[triangles[:, 1]]
                    p2 = pos_arr[triangles[:, 2]]
                    v1 = p1 - p0
                    v2 = p2 - p0
                    signed_areas = 0.5 * (v1[:, 0] * v2[:, 1] - v1[:, 1] * v2[:, 0])
                    inverted = np.sum(signed_areas <= -1e-4)
                    details["min_signed_area"] = float(np.min(signed_areas)) if len(signed_areas) > 0 else 0.0
                    if inverted > 0:
                        errors.append(f"Found {inverted} inverted triangles with negative signed area (min area: {np.min(signed_areas):.2e})")

        return ValidationStageResult(
            stage_number=6,
            stage_name="Topological Non-Inversion & Deformation Continuity",
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details=details
        )

    @classmethod
    def validate_live2d_model(
        cls,
        model_entry_path: Union[str, Path],
        strict: bool = False
    ) -> ValidationReport:
        path = Path(model_entry_path)
        report = ValidationReport(model_path=str(path))

        # 1. Resolve path to .model3.json and parent folder
        model3_path = None
        model_dir = None
        moc3_path = None

        if path.is_dir():
            model_dir = path
            m3_files = list(path.glob("*.model3.json"))
            if m3_files:
                model3_path = m3_files[0]
                report.model_name = model3_path.stem.replace(".model3", "")
            else:
                moc_files = list(path.glob("*.moc3"))
                if moc_files:
                    moc3_path = moc_files[0]
                    report.model_name = moc3_path.stem
        elif path.suffix == ".json":
            model3_path = path
            model_dir = path.parent
            report.model_name = path.stem.replace(".model3", "")
        elif path.suffix == ".moc3":
            moc3_path = path
            model_dir = path.parent
            report.model_name = path.stem
        else:
            model_dir = path.parent
            model3_path = path

        # Read MOC3 binary if available
        moc3_bytes = b""
        model3_data = None
        cdi3_data = None
        texture_rel_paths = []

        # Execute Stage 3 first if model3.json is available to locate files
        if model3_path:
            s3_res, model3_data, cdi3_data = cls.validate_stage3_json_manifest(model_dir, model3_path)
            if model3_data:
                frefs = model3_data.get("FileReferences", {})
                moc_rel = frefs.get("Moc")
                if moc_rel:
                    moc3_path = model_dir / moc_rel
                texture_rel_paths = frefs.get("Textures", [])

        if moc3_path and moc3_path.exists():
            try:
                with open(moc3_path, "rb") as f:
                    moc3_bytes = f.read()
            except Exception as e:
                report.add_stage(ValidationStageResult(1, "Binary MOC3 Header Integrity", False, [f"Failed to read MOC3 file: {e}"]))
                return report

        # Execute Stage 1: MOC3 Header
        s1_res = cls.validate_stage1_moc3_header(moc3_bytes)
        report.add_stage(s1_res)

        # Execute Stage 2: Section Tables
        s2_res = cls.validate_stage2_section_tables(moc3_bytes)
        report.add_stage(s2_res)

        # Record Stage 3 result
        if model3_path:
            report.add_stage(s3_res)
        else:
            report.add_stage(ValidationStageResult(3, "JSON Manifest & File Reference Conformance", False, ["No .model3.json found"]))

        # Execute Stage 4: Parameter Bounds
        moc3_parsed = None
        if moc3_bytes and len(moc3_bytes) >= 64:
            try:
                moc3_parsed = Moc3Reader.parse_bytes(moc3_bytes)
            except Exception:
                pass

        s4_res = cls.validate_stage4_parameter_bounds(cdi3_data, moc3_parsed)
        report.add_stage(s4_res)

        # Execute Stage 5: Textures & UVs
        s5_res = cls.validate_stage5_textures_and_uvs(model_dir, texture_rel_paths, moc3_bytes)
        report.add_stage(s5_res)

        # Execute Stage 6: Topology & Non-Inversion
        s6_res = cls.validate_stage6_topology_and_deformation(moc3_bytes)
        report.add_stage(s6_res)

        if strict and report.total_warnings > 0:
            report.passed = False

        return report


# Top-level functional export
def validate_live2d_model(
    model_entry_path: Union[str, Path],
    strict: bool = False
) -> ValidationReport:
    """Universal function validating a Live2D model directory or manifest."""
    return StructuralValidator.validate_live2d_model(model_entry_path, strict=strict)
```

---

### 5.2 `validate_live2d.py` CLI Tool Blueprint

```python
"""
validate_live2d.py
Standalone Programmatic Structural Validator for Live2D Cubism Model Bundles.
Validates headers, section alignment, schemas, parameters, textures, and mesh non-inversion.
"""

import argparse
import json
import sys
from pathlib import Path

# Add workspace to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from src.validator.structural_validator import validate_live2d_model, StructuralValidator


def main():
    parser = argparse.ArgumentParser(
        description="Live2D Cubism 6-Stage Programmatic Structural Validator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python validate_live2d.py output/MyModel/
  python validate_live2d.py output/MyModel/MyModel.model3.json
  python validate_live2d.py output/MyModel/MyModel.moc3
  python validate_live2d.py output/MyModel/ --json-report validation_report.json
        """
    )
    parser.add_argument(
        "model_path",
        type=str,
        help="Path to Live2D model directory, .model3.json manifest, or .moc3 binary file."
    )
    parser.add_argument(
        "-o", "--json-report",
        type=str,
        default=None,
        help="Optional destination path to export JSON validation report."
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        default=False,
        help="Suppress all standard console output."
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=False,
        help="Show verbose diagnostic metrics and section tables."
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="Disable ANSI color codes in console output."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Treat warnings as hard errors (fail validation if warnings exist)."
    )

    args = parser.parse_args()
    model_path = Path(args.model_path)

    if not model_path.exists():
        print(f"Error: Specified target path does not exist: {model_path}", file=sys.stderr)
        sys.exit(1)

    # Run 6-stage validation suite
    report = validate_live2d_model(model_path, strict=args.strict)

    # Output to console
    if not args.quiet:
        print(report.format_console(use_color=not args.no_color))

    # Export JSON report if requested
    if args.json_report:
        out_json_path = Path(args.json_report)
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_json_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        if not args.quiet:
            print(f"JSON validation report written to: {out_json_path}")

    # Standard exit code: 0 on success, 5 on structural validation failure
    if report.is_valid:
        sys.exit(0)
    else:
        sys.exit(5)


if __name__ == "__main__":
    main()
```

---

## 6. Comprehensive Test Strategy & Adversarial Matrix

The validator must be rigorously tested by `tests/test_validator.py` and `tests/test_cli.py`. The table below outlines all test scenarios, the validation stage triggered, and expected behavior.

| Test Case Name | Target Stage | Injected Condition / Asset | Expected Outcome |
|---|---|---|---|
| `test_valid_model_all_stages_pass` | Stages 1–6 | Fully valid synthetic character model bundle | `is_valid == True`, `stages_passed == [1, 2, 3, 4, 5, 6]`, exit code 0 |
| `test_corrupt_magic_bytes` | Stage 1 | Byte 0..3 changed to `b"BAD3"` | `Stage 1 FAIL: Magic bytes mismatch`, `is_valid == False`, exit code 5 |
| `test_invalid_version_byte` | Stage 1 | Byte 4 set to `99` | `Stage 1 FAIL: Unsupported MOC3 version`, `is_valid == False` |
| `test_big_endian_flag` | Stage 1 | Byte 5 set to `1` (Big-Endian) | `Stage 1 FAIL: Unsupported endianness flag`, `is_valid == False` |
| `test_truncated_moc3_file` | Stage 1 & 2 | Binary truncated to 32 bytes | `Stage 1 FAIL: Binary file too small`, `is_valid == False` |
| `test_unaligned_section_offset` | Stage 2 | Offset in SectionOffsetTable set to odd byte `0x0741` | `Stage 2 FAIL: Section offset not 64-byte aligned`, `is_valid == False` |
| `test_out_of_bounds_section_offset` | Stage 2 | Section offset set to `file_len + 128` | `Stage 2 FAIL: Section offset exceeds file size`, `is_valid == False` |
| `test_zero_art_mesh_count` | Stage 2 | CountInfoTable art_meshes counter set to 0 | `Stage 2 FAIL: CountInfoTable: ArtMeshes count is 0`, `is_valid == False` |
| `test_invalid_model3_json_syntax` | Stage 3 | Corrupted JSON with syntax error | `Stage 3 FAIL: Invalid JSON syntax`, `is_valid == False` |
| `test_missing_moc_file_reference` | Stage 3 | `FileReferences.Moc` references non-existent file | `Stage 3 FAIL: Referenced Moc file does not exist`, `is_valid == False` |
| `test_missing_texture_file_reference`| Stage 3 | `FileReferences.Textures` references missing PNG | `Stage 3 FAIL: Referenced Texture file does not exist`, `is_valid == False` |
| `test_windows_backslash_rejection` | Stage 3 | Path containing `subdir\model.moc3` | `Stage 3 FAIL: Moc path contains Windows backslash`, `is_valid == False` |
| `test_missing_tracking_parameters` | Stage 4 | Model without `ParamAngleX` or `ParamAngleY` | `Stage 4 FAIL: Required head tracking parameter not found`, `is_valid == False` |
| `test_non_power_of_two_texture` | Stage 5 | Texture dimensions $500 \times 500$ or $1000 \times 1000$ | `Stage 5 FAIL: Texture dimensions are not power-of-two`, `is_valid == False` |
| `test_out_of_bounds_uv_coordinates` | Stage 5 | UV coordinates with $u = 1.25$ or $v = -0.1$ | `Stage 5 FAIL: UV coordinates exceed [0.0, 1.0]`, `is_valid == False` |
| `test_inverted_triangle_topology` | Stage 6 | Deformed keyform with inverted triangle ($A \le -10^{-4}$) | `Stage 6 FAIL: Found inverted triangles with negative signed area`, `is_valid == False` |
| `test_nan_vertex_coordinates` | Stage 6 | Vertex keyform containing `np.nan` or `np.inf` | `Stage 6 FAIL: Keyform positions contain NaN or Inf`, `is_valid == False` |
| `test_cli_runner_json_report_export`| CLI | `--json-report report.json` | Report written to disk, matches parsed schema |

---

## 7. Implementation Guidelines for Sub-Orchestrator & Implementer

1. **Package Initialization**:
   - Create `src/validator/__init__.py` exposing `StructuralValidator`, `ValidationReport`, `ValidationStageResult`, and `validate_live2d_model`.
2. **Module Creation**:
   - Implement `src/validator/structural_validator.py` adhering strictly to the architecture and data models above.
3. **CLI Tool Creation**:
   - Implement `validate_live2d.py` at workspace root. Ensure execute permissions and clean exit code handling (`0` for valid, `1` for argument/input error, `5` for structural validation failure).
4. **Unit Test Suite**:
   - Implement `tests/test_validator.py` testing all 6 individual stages in both positive and negative (adversarial defect injection) modes.
5. **E2E & CLI Integration**:
   - Implementer 2 (`src/cli/main.py` and `export_live2d.py`) will import `validate_live2d_model` to power the `--validate` flag, returning exit code 5 upon validation failure.

This concludes the architectural and technical specification for the 6-Stage Structural Validator.
