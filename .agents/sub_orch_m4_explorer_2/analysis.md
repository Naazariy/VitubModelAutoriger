# Architectural Analysis & Design: Headless Zero-Intervention CLI & End-to-End Pipeline Integration

**Author**: Explorer 2 (Milestone 4: CLI & End-to-End Pipeline Integration)  
**Date**: 2026-08-22  
**Target Modules**: `src/cli/main.py`, `src/cli/__init__.py`, `src/cli/__main__.py`, `export_live2d.py`

---

## 1. Executive Summary & Objective

The objective of Milestone 4 is to provide the unified, zero-intervention command-line entrypoint (`export_live2d.py` and `python -m src.cli`) that seamlessly chains together the completed core engine modules:
1. **Asset Ingestion** (`src/importer/`): Multi-layer PSD extraction and single PNG/directory loader with bilingual semantic classification.
2. **Mesh Generation** (`src/generator/`): Pure-Python SciPy Delaunay triangulation with Steiner internal sampling and boundary clipping.
3. **3D Deformation & Physics** (`src/depth/`, `src/deformation/`, `src/constraints/`): 3D SO(3) Euler rotations (Angle X, Y, Z), depth parallax, and ARAP local-global energy minimization.
4. **Texture Packing & UV Remapping** (`src/exporter/texture_packer.py`): Power-of-two MaxRects texture atlas packing and Voronoi color bleed dilation.
5. **Live2D Binary & Metadata Serialization** (`src/exporter/moc3_writer.py`, `src/exporter/model3_writer.py`): Pure-Python `.moc3` binary builder, `.model3.json`, and `.cdi3.json` generators.
6. **Programmatic Quality Gate** (`src/validator/structural_validator.py`): 6-stage structural validation suite.

---

## 2. Command-Line Interface Specification (`src/cli/main.py`)

### 2.1 Argument Parser Flags & Options

The CLI parser is designed with full compatibility for positional and flagged arguments, supporting aliases to accommodate both developer scripts and user workflows.

| Flag / Option | Short | Type | Default | Description |
|---|---|---|---|---|
| `input_path` | `input`, `-i` | `str` | *Required* | Path to input PSD file, PNG image, or layer directory |
| `--output-dir` | `-o`, `--output` | `str` | `"./output"` | Root output directory where model subfolder will be created |
| `--model-name` | `-n`, `--name` | `str` | `None` (auto from stem) | Live2D model name and subfolder/file prefix |
| `--texture-size` | `--resolution`, `--atlas-size` | `int` | `4096` | Maximum texture atlas page dimension (POT: 512, 1024, 2048, 4096, 8192) |
| `--mesh-density` | `--grid-size` | `int` | `25` | Target internal Steiner grid spacing in pixels |
| `--contour-threshold`| `--threshold` | `int` | `10` | Alpha mask silhouette extraction threshold in [0, 255] |
| `--simplify-eps` | `--contour-epsilon` | `float` | `2.0` | Douglas-Peucker contour polygon simplification epsilon |
| `--smoothing-iterations` | `--smoothing` | `int` | `3` | Boundary-pinned constrained Laplacian smoothing passes |
| `--angle-x-range` | | `str` | `"-30.0,30.0"` | Angle X (Yaw) minimum and maximum range in degrees |
| `--angle-y-range` | | `str` | `"-30.0,30.0"` | Angle Y (Pitch) minimum and maximum range in degrees |
| `--angle-z-range` | | `str` | `"-20.0,20.0"` | Angle Z (Roll) minimum and maximum range in degrees |
| `--keyforms-x` | | `int` | `3` | Number of keyform divisions for Angle X (`[-30, 0, 30]`) |
| `--keyforms-y` | | `int` | `3` | Number of keyform divisions for Angle Y (`[-30, 0, 30]`) |
| `--keyforms-z` | | `int` | `3` | Number of keyform divisions for Angle Z (`[-20, 0, 20]`) |
| `--include-angle-z` | `--enable-roll` | `bool` | `True` | Include Angle Z roll parameter in keyform tensor |
| `--head-radii` | | `str` | `"0.6,0.8,0.4"` | 3D head proxy ellipsoid radii `Rx,Ry,Rz` |
| `--parallax-scale` | | `float` | `0.45` | Perspective depth parallax intensity scale |
| `--arap-weight` | | `float` | `2.5` | ARAP mass-spring regularization stiffness weight |
| `--arap-iterations` | | `int` | `4` | Number of local-global ARAP solver iterations |
| `--padding` | `--atlas-padding` | `int` | `4` | Pixel padding margin between packed atlas sprites |
| `--bleed-radius` | `--edge-bleed` | `int` | `2` | Voronoi color bleed dilation radius in pixels |
| `--crop-transparent`| | `bool` | `True` | Crop transparent padding from layer images before packing |
| `--include-hidden` | | `bool` | `False` | Include hidden PSD layers in extraction |
| `--auto-depth` | | `bool` | `True` | Enable automated semantic depth proxy modeling |
| `--auto-stiffness`| | `bool` | `True` | Enable automated feature stiffness estimation |
| `--validate` | | `bool` | `False` | Run 6-stage structural validator after export |
| `--strict` | | `bool` | `False` | Treat structural validation warnings as errors |
| `--gui` | `--launch-gui` | `bool` | `False` | Launch interactive PySide6 GUI visualizer after export |
| `--overwrite` | `-f`, `--force` | `bool` | `False` | Overwrite existing output model directory without warning |
| `--quiet` | `-q` | `bool` | `False` | Suppress non-error console output |
| `--verbose` | `-v` | `bool` | `False` | Enable verbose debug logging and per-layer stats |
| `--json-output` | | `bool` | `False` | Print machine-readable JSON execution summary to stdout |

---

## 3. Standardized Exit Code System & Exception Hierarchy

### 3.1 Exit Codes Specification

The CLI and pipeline runners conform strictly to standardized numeric exit codes:

| Code | Constant | Category | Description |
|---|---|---|---|
| `0` | `EXIT_SUCCESS` | **Success** | Pipeline completed successfully, bundle written and verified. |
| `1` | `EXIT_ERR_INPUT` | **Input / Argument Error** | File not found, unreadable image/PSD, invalid CLI arguments, missing input. |
| `2` | `EXIT_ERR_MESH` | **Mesh Generation Error** | Delaunay triangulation failed, degenerate geometry, boundary clipping error. |
| `3` | `EXIT_ERR_DEFORMATION` | **Deformation / Physics Error** | 3D deformation solve failed, ARAP solver divergence, unrecoverable triangle inversion. |
| `4` | `EXIT_ERR_EXPORT` | **Export / Serialization Error** | Texture atlas packing overflow, MOC3 binary alignment error, file I/O write failure. |
| `5` | `EXIT_ERR_VALIDATION` | **Structural Validation Error** | Exported model failed one or more of the 6 structural validation stages. |

### 3.2 Exception Hierarchy Design

```python
class PipelineException(Exception):
    """Base exception for all Live2D export pipeline failures."""
    exit_code: int = 1
    
    def __init__(self, message: str, stage: str = "Pipeline", details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.details = details or {}

class InputError(PipelineException):
    """Raised when input asset is missing, corrupted, or unsupported."""
    exit_code = 1

class MeshGenerationError(PipelineException):
    """Raised when contour extraction or Delaunay triangulation fails."""
    exit_code = 2

class DeformationError(PipelineException):
    """Raised when 3D math, depth modeling, or ARAP regularization fails."""
    exit_code = 3

class ExportError(PipelineException):
    """Raised when texture packing, binary moc3 serialization, or file I/O fails."""
    exit_code = 4

class ValidationError(PipelineException):
    """Raised when exported model bundle fails 6-stage structural validation."""
    exit_code = 5
```

---

## 4. End-to-End Pipeline Architecture & Stage Execution Flow

```
                  ┌────────────────────────────────────────────────────────┐
                  │                 CLI Entrypoint / Args                  │
                  │             (export_live2d.py / main.py)               │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │ Stage 0: Argument Parsing & Workspace Validation       │
                  │ - Validate input file exists                           │
                  │ - Resolve model name and output directories            │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │ Stage 1: Asset Ingestion & Layer Parsing               │
                  │ - PSD: PSDImporter.load_psd_as_collection()            │
                  │ - Single PNG / Directory: ImageImporter                │
                  │ - Bilingual Semantic Category & Depth Hint Assignment  │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │ Stage 2: Robust Delaunay Mesh Generation               │
                  │ - ImageImporter.extract_contour()                      │
                  │ - MeshGenerator.generate_mesh_from_contour()           │
                  │ - Steiner grid sampling, boundary clipping, smoothing  │
                  │ - Topology validation (positive signed area check)     │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │ Stage 3: Depth Modeling, 3D Deformation & Keyforms     │
                  │ - DepthModel.apply_to_layer_collection() (clearance)   │
                  │ - DeformationSolver: SO(3) Euler yaw/pitch/roll +      │
                  │   normalized depth parallax + anime foreshortening     │
                  │ - ARAPConstraintSolver: local-global energy minimize   │
                  │ - KeyformGenerator: 3x3 (AngleX x AngleY) + AngleZ     │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │ Stage 4: MaxRects Texture Atlas Packing & UV Remap     │
                  │ - TextureAtlasPacker.pack()                            │
                  │ - Power-of-two bin sizing (512..8192)                  │
                  │ - Voronoi color bleed dilation (2px)                   │
                  │ - UV coordinate remapping into [0.0, 1.0] global atlas │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │ Stage 5: Live2D Binary & Metadata Serialization        │
                  │ - Moc3Writer.write_moc3() (64-byte aligned tables)     │
                  │ - Model3Writer.generate_model3_json()                  │
                  │ - Model3Writer.generate_cdi3_json()                    │
                  │ - Save texture PNGs to disk                            │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │ Stage 6: Post-Export Programmatic Validation           │
                  │ - StructuralValidator.validate_live2d_model()          │
                  │ - 6 Stages: Header, Sections, JSON, Params, Textures,  │
                  │   Topology & Signed Area Non-Inversion                 │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                  ┌────────────────────────────────────────────────────────┐
                  │ Exit Code 0 (Success) & Summary Metrics Report         │
                  └────────────────────────────────────────────────────────┘
```

### 4.1 Stage Breakdown Details

#### Stage 1: Asset Ingestion
- Supports 3 input modalities:
  1. `.psd` / `.psb` files: Uses `PSDImporter.load_psd_as_collection()`. Rasterizes layers, filters hidden/empty layers, extracts layer bounding boxes and relative offsets.
  2. Directory of images: Uses `ImageImporter.load_directory()`. Scans PNG/JPG/WEBP files, applies filename semantic classification.
  3. Single image file (`.png`, `.jpg`, etc.): Uses `ImageImporter.load_image()`. Automatically generates single mesh layer or synthetic decomposition if requested.
- Error Check: If file does not exist or has zero drawable layers $\to$ raise `InputError` (exit code 1).

#### Stage 2: Mesh Triangulation
- Iterates over all `LayerData` objects in `LayerCollection`:
  * Extracts silhouette polygon contour from layer alpha mask (`cv2` or pure-Python fallback).
  * Computes bounding box and samples internal Steiner points spaced by `--grid-size`.
  * Computes SciPy Delaunay triangulation.
  * Discards exterior simplices whose centroids lie outside the boundary contour.
  * Ensures counter-clockwise orientation ($A_{\text{signed}} > 0$).
  * Applies boundary-pinned constrained Laplacian smoothing (3 iterations).
  * Validates mesh topology: verifies index bounds, no NaNs, no unreferenced vertices.
- Error Check: If triangulation fails for any layer $\to$ raise `MeshGenerationError` (exit code 2).

#### Stage 3: 3D Depth Modeling & Keyform Generation
- Depth Stratification:
  * Computes parametric proxy depth fields (Ellipsoid, Cylindrical, Inverted Shell, Conical Bump) for each layer based on semantic category.
  * Applies layer clearance enforcement: guarantees $z_{\text{front}} - z_{\text{back}} \ge \delta_{\text{min}} + \Delta x_{\text{max}} \sin(30^\circ)$ to prevent depth inter-penetration during rotations.
  * Globally normalizes depth fields to $[-1.0, 1.0]$.
- Keyform Tensor Computation:
  * Configures parameters: `ParamAngleX` ($[-30, 0, 30]$), `ParamAngleY` ($[-30, 0, 30]$), `ParamAngleZ` ($[-20, 0, 20]$).
  * For each parameter grid point, computes 3D SO(3) Euler rotation matrix:
    $$\mathbf{R}(\theta_x, \theta_y, \theta_z) = \mathbf{R}_z(\theta_z) \mathbf{R}_y(\theta_x) \mathbf{R}_x(\theta_y)$$
  * Evaluates depth-scaled perspective parallax and anime foreshortening fields $(\Phi_x, \Phi_y)$.
  * Solves ARAP local-global energy minimization with pre-factorized sparse LU decomposition.
  * Applies backtracking line search to ensure all deformed triangles maintain positive signed area ($A_t > 10^{-5}$).
- Error Check: If solver diverges or encounters NaNs $\to$ raise `DeformationError` (exit code 3).

#### Stage 4: Texture Atlas Packing & UV Remapping
- Configures `PackingConfig` with power-of-two bounds, padding (4px), and Voronoi color bleed (2px).
- Places all layer rasters into minimal power-of-two texture pages using MaxRects-BSSF (Best Short Side Fit).
- Applies color bleed dilation into transparent regions ($\alpha = 0$) to eliminate black edge fringing during bilinear filtering.
- Remaps each mesh's vertex UV coordinates from layer-local coordinates $[0, 1]$ into global atlas coordinates $[u_{\text{min}}, u_{\text{max}}] \times [v_{\text{min}}, v_{\text{max}}]$.
- Error Check: If packing fails $\to$ raise `ExportError` (exit code 4).

#### Stage 5: Live2D Binary & Metadata Export
- Exports model bundle to directory `<output_dir>/<model_name>/`:
  * `<model_name>.moc3`: Pure-Python 64-byte aligned binary format with section offset table (160 uint32 entries), parts, drawables, parameters, keyform positions, UVs, and triangle index buffers.
  * `<model_name>.model3.json`: Runtime manifest specifying relative paths (with forward slashes), LipSync, and EyeBlink parameter groups.
  * `<model_name>.cdi3.json`: Display info manifest mapping parameter IDs and group names.
  * `<model_name>.<size>/texture_00.png`: Power-of-two RGBA PNG texture atlas.
- Error Check: If file writing fails $\to$ raise `ExportError` (exit code 4).

#### Stage 6: Post-Export Programmatic Validation
- Runs `StructuralValidator.validate_live2d_model()`:
  * Stage 1: Binary MOC3 Header verification (`b"MOC3"`, version 3, Little-Endian).
  * Stage 2: Section Table offsets, 64-byte alignment, monotonicity, count table sanity.
  * Stage 3: `.model3.json` and `.cdi3.json` schema conformance and relative path existence.
  * Stage 4: Parameter IDs, keyform counts, and range bounds $[-30, 30]$.
  * Stage 5: Texture atlas PNG dimensions (power-of-two), RGBA8 channels, UV coordinates in $[0.0, 1.0]$.
  * Stage 6: Topological non-inversion & deformation continuity ($A_{\text{signed}} > -10^{-4}$ across all keyforms).
- Error Check: If validation fails $\to$ raise `ValidationError` (exit code 5).

---

## 5. Root Wrapper Script Design (`export_live2d.py`)

The root script `d:\VitubModel\export_live2d.py` serves as the clean, frictionless entry point:

```python
#!/usr/bin/env python3
"""
export_live2d.py - Root CLI Wrapper for Automated VTuber Key Deformation & Live2D Export.
Delegates directly to src.cli.main.
"""
import sys
import os
from pathlib import Path

# Ensure project root is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
```

---

## 6. Comprehensive Class & Function Signatures

### 6.1 `src/cli/main.py` Architecture

```python
@dataclass
class PipelineConfig:
    """Strongly-typed pipeline configuration container."""
    input_path: str
    output_dir: str = "./output"
    model_name: Optional[str] = None
    atlas_size: int = 4096
    grid_size: int = 25
    contour_threshold: int = 10
    simplify_eps: float = 2.0
    smoothing_iterations: int = 3
    angle_x_range: Tuple[float, float] = (-30.0, 30.0)
    angle_y_range: Tuple[float, float] = (-30.0, 30.0)
    angle_z_range: Tuple[float, float] = (-20.0, 20.0)
    keyforms_x: int = 3
    keyforms_y: int = 3
    keyforms_z: int = 3
    include_angle_z: bool = True
    head_radii: Tuple[float, float, float] = (0.6, 0.8, 0.4)
    parallax_scale: float = 0.45
    arap_weight: float = 2.5
    arap_iterations: int = 4
    padding: int = 4
    bleed_radius: int = 2
    crop_transparent: bool = True
    include_hidden: bool = False
    auto_depth: bool = True
    auto_stiffness: bool = True
    validate: bool = False
    strict: bool = False
    gui: bool = False
    overwrite: bool = False
    quiet: bool = False
    verbose: bool = False
    json_output: bool = False

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> 'PipelineConfig': ...


class PipelineRunner:
    """Executes the 6-stage end-to-end Live2D export pipeline."""
    
    def __init__(self, config: PipelineConfig, logger: Optional[logging.Logger] = None):
        self.config = config
        self.logger = logger or logging.getLogger("Live2DExporter")
        self.metrics: Dict[str, Any] = {}

    def run(self) -> int:
        """Runs the complete pipeline and returns standard exit code."""
        ...

    def stage_ingest(self) -> LayerCollection: ...
    def stage_mesh_generation(self, layers: LayerCollection) -> Dict[str, Mesh]: ...
    def stage_deformation_keyforms(self, layers: LayerCollection, meshes: Dict[str, Mesh]) -> KeyformTable: ...
    def stage_texture_packing(self, layers: LayerCollection, meshes: Dict[str, Mesh], keyform_table: KeyformTable) -> PackingResult: ...
    def stage_export_bundle(self, keyform_table: KeyformTable, packing_result: PackingResult) -> Dict[str, str]: ...
    def stage_validate(self, model3_path: str) -> bool: ...


def build_parser() -> argparse.ArgumentParser: ...
def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace: ...
def run_pipeline(args_or_namespace: Union[List[str], argparse.Namespace]) -> int: ...
def main(argv: Optional[List[str]] = None) -> int: ...
```

---

## 7. Concrete Implementation Code Snippets

### 7.1 Argument Parser Construction

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="export_live2d",
        description="Automated Zero-Intervention 3D Key Deformation & Live2D Model Exporter",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Input / Output
    parser.add_argument("input_path", nargs="?", default=None, help="Path to input PSD file, PNG image, or layer folder")
    parser.add_argument("-i", "--input", dest="input_flag", type=str, default=None, help="Input asset path (alias for positional)")
    parser.add_argument("-o", "--output-dir", "--output", dest="output_dir", type=str, default="./output", help="Output directory")
    parser.add_argument("-n", "--model-name", "--name", dest="model_name", type=str, default=None, help="Model name identifier")
    parser.add_argument("-f", "--force", "--overwrite", dest="overwrite", action="store_true", default=False, help="Overwrite existing output folder")

    # Mesh Generation
    parser.add_argument("--mesh-density", "--grid-size", dest="grid_size", type=int, default=25, help="Mesh Steiner grid resolution in px")
    parser.add_argument("--contour-threshold", "--threshold", dest="contour_threshold", type=int, default=10, help="Alpha silhouette threshold [0-255]")
    parser.add_argument("--simplify-eps", "--contour-epsilon", dest="simplify_eps", type=float, default=2.0, help="Contour simplification epsilon")
    parser.add_argument("--smoothing-iterations", "--smoothing", dest="smoothing_iterations", type=int, default=3, help="Laplacian smoothing iterations")

    # 3D Deformation & Angles
    parser.add_argument("--angle-x-range", type=str, default="-30.0,30.0", help="Angle X (Yaw) range min,max in degrees")
    parser.add_argument("--angle-y-range", type=str, default="-30.0,30.0", help="Angle Y (Pitch) range min,max in degrees")
    parser.add_argument("--angle-z-range", type=str, default="-20.0,20.0", help="Angle Z (Roll) range min,max in degrees")
    parser.add_argument("--keyforms-x", type=int, default=3, help="Keyform count for Angle X")
    parser.add_argument("--keyforms-y", type=int, default=3, help="Keyform count for Angle Y")
    parser.add_argument("--keyforms-z", type=int, default=3, help="Keyform count for Angle Z")
    parser.add_argument("--include-angle-z", "--enable-roll", dest="include_angle_z", action="store_true", default=True, help="Include Angle Z roll keyforms")
    parser.add_argument("--no-angle-z", dest="include_angle_z", action="store_false", help="Disable Angle Z roll keyforms")
    parser.add_argument("--head-radii", type=str, default="0.6,0.8,0.4", help="Head ellipsoid radii Rx,Ry,Rz")
    parser.add_argument("--parallax-scale", type=float, default=0.45, help="Perspective depth parallax factor")
    parser.add_argument("--arap-weight", type=float, default=2.5, help="ARAP regularization stiffness weight")
    parser.add_argument("--arap-iterations", type=int, default=4, help="ARAP solver iterations per keyform")
    parser.add_argument("--auto-depth", action="store_true", default=True, help="Auto-estimate 3D depth field")
    parser.add_argument("--auto-stiffness", action="store_true", default=True, help="Auto-estimate feature stiffness")

    # Texture Atlas Packing
    parser.add_argument("--texture-size", "--resolution", "--atlas-size", dest="atlas_size", type=int, default=4096, help="Texture atlas dimension (POT)")
    parser.add_argument("--padding", "--atlas-padding", dest="padding", type=int, default=4, help="Sprite border padding in pixels")
    parser.add_argument("--bleed-radius", "--edge-bleed", dest="bleed_radius", type=int, default=2, help="Voronoi color bleed dilation radius")
    parser.add_argument("--crop-transparent", dest="crop_transparent", action="store_true", default=True, help="Crop transparent margins")
    parser.add_argument("--include-hidden", dest="include_hidden", action="store_true", default=False, help="Include hidden PSD layers")

    # Validation & Execution
    parser.add_argument("--validate", action="store_true", default=False, help="Run 6-stage structural validator post-export")
    parser.add_argument("--strict", action="store_true", default=False, help="Treat validation warnings as errors")
    parser.add_argument("--gui", "--launch-gui", dest="gui", action="store_true", default=False, help="Launch interactive visualizer after export")
    parser.add_argument("-q", "--quiet", action="store_true", default=False, help="Suppress non-error console output")
    parser.add_argument("-v", "--verbose", action="store_true", default=False, help="Enable verbose diagnostic logging")
    parser.add_argument("--json-output", action="store_true", default=False, help="Print JSON summary metrics to stdout")

    return parser
```

### 7.2 Core Pipeline Execution Orchestrator

```python
class PipelineRunner:
    def __init__(self, config: PipelineConfig):
        self.config = config

    def run(self) -> int:
        start_time = time.time()
        
        # 1. Validate Input Existence
        input_p = Path(self.config.input_path) if self.config.input_path else None
        if not input_p or not input_p.exists():
            print(f"[ERROR] Input file not found: {self.config.input_path}", file=sys.stderr)
            return EXIT_ERR_INPUT

        try:
            # Stage 1: Asset Ingestion
            layer_collection = self.stage_ingest()
            if len(layer_collection) == 0:
                raise InputError("No drawable layers found in input asset.")

            # Stage 2: Mesh Triangulation
            mesh_map = self.stage_mesh_generation(layer_collection)

            # Stage 3: Depth & 3D Keyforms
            keyform_table = self.stage_deformation_keyforms(layer_collection, mesh_map)

            # Stage 4: Texture Packing & UV Remapping
            packing_result = self.stage_texture_packing(layer_collection, mesh_map, keyform_table)

            # Stage 5: Binary & Metadata Serialization
            bundle_paths = self.stage_export_bundle(keyform_table, packing_result)

            # Stage 6: Validation
            if self.config.validate:
                is_valid = self.stage_validate(bundle_paths["model3_json"])
                if not is_valid:
                    return EXIT_ERR_VALIDATION

            # GUI Launch if requested
            if self.config.gui:
                self.launch_gui(bundle_paths["model3_json"])

            return EXIT_SUCCESS

        except InputError as e:
            print(f"[INPUT ERROR] {e}", file=sys.stderr)
            return EXIT_ERR_INPUT
        except MeshGenerationError as e:
            print(f"[MESH ERROR] {e}", file=sys.stderr)
            return EXIT_ERR_MESH
        except DeformationError as e:
            print(f"[DEFORMATION ERROR] {e}", file=sys.stderr)
            return EXIT_ERR_DEFORMATION
        except ExportError as e:
            print(f"[EXPORT ERROR] {e}", file=sys.stderr)
            return EXIT_ERR_EXPORT
        except ValidationError as e:
            print(f"[VALIDATION ERROR] {e}", file=sys.stderr)
            return EXIT_ERR_VALIDATION
        except Exception as e:
            print(f"[UNEXPECTED PIPELINE FAILURE] {e}", file=sys.stderr)
            return EXIT_ERR_EXPORT
```

---

## 8. UX, Logging & Visual Formatting

### 8.1 Console Output Formatting
When running in interactive mode without `--quiet`, the CLI prints a clean, informative status sequence:

```
======================================================================
  Live2D Automated Key Deformation Exporter (v1.0.0)
======================================================================
[INFO] Ingesting asset: character.psd (PSD format)
  ✔ Extracted 14 layers (Canvas: 2048x2048)
[INFO] Generating Delaunay meshes (Steiner grid spacing: 25px)...
  ✔ Triangulated 14/14 layers (Total Vertices: 1,420, Triangles: 2,640)
[INFO] Solving 3D SO(3) Deformation & Keyforms...
  ✔ Depth proxy evaluated & clearance enforced across 14 layers
  ✔ Computed 9 AngleX/Y keyforms + 3 AngleZ keyforms with ARAP regularization
  ✔ Positive signed triangle area preserved (100% CCW non-inverted)
[INFO] Packing Texture Atlas (Max POT: 4096, Bleed: 2px)...
  ✔ Packed 14 sprites into 1 page (4096x4096), Packing Efficiency: 78.4%
  ✔ UV coordinates remapped to global atlas [0.0, 1.0]
[INFO] Serializing Live2D Model Bundle...
  ✔ Wrote .moc3 binary: output/character/character.moc3 (64-byte aligned)
  ✔ Wrote .model3.json: output/character/character.model3.json
  ✔ Wrote .cdi3.json:   output/character/character.cdi3.json
  ✔ Wrote texture atlas: output/character/character.4096/texture_00.png
[INFO] Executing 6-Stage Programmatic Structural Validation...
  [Stage 1] Binary MOC3 Header Check ............. [ PASSED ]
  [Stage 2] Section Table & Alignment ............ [ PASSED ]
  [Stage 3] JSON Manifest & Schema .............. [ PASSED ]
  [Stage 4] Parameter Ranges & Keyforms .......... [ PASSED ]
  [Stage 5] Texture Atlas & UV Coordinates ....... [ PASSED ]
  [Stage 6] Topology Non-Inversion & Continuity .. [ PASSED ]
======================================================================
[SUCCESS] Export complete in 1.42s! Exit Code: 0
  Model directory: d:\VitubModel\output\character
======================================================================
```

### 8.2 JSON Output Mode (`--json-output`)
When `--json-output` is supplied, structured metrics are emitted to stdout for automated tooling / CI:

```json
{
  "status": "success",
  "exit_code": 0,
  "elapsed_seconds": 1.42,
  "model_name": "character",
  "bundle": {
    "model_dir": "d:/VitubModel/output/character",
    "model3_json": "d:/VitubModel/output/character/character.model3.json",
    "moc3": "d:/VitubModel/output/character/character.moc3",
    "cdi3_json": "d:/VitubModel/output/character/character.cdi3.json",
    "textures": ["d:/VitubModel/output/character/character.4096/texture_00.png"]
  },
  "metrics": {
    "layer_count": 14,
    "total_vertices": 1420,
    "total_triangles": 2640,
    "keyform_count": 12,
    "atlas_pages": 1,
    "atlas_dimensions": [[4096, 4096]],
    "packing_efficiency": 0.784,
    "moc3_bytes": 184576
  },
  "validation": {
    "is_valid": true,
    "stages_passed": [1, 2, 3, 4, 5, 6],
    "errors": [],
    "warnings": []
  }
}
```

---

## 9. Comprehensive Unit & Integration Test Plan (`tests/test_cli.py`)

The CLI test suite will cover:
1. **Argument Parsing Unit Tests**:
   - Parsing defaults, custom resolutions, mesh grid sizes, angle ranges, flags.
   - Positional vs `-i` / `--input` argument handling.
   - Mutual exclusivity / alias correctness.
2. **Exit Code & Defect Handling Tests**:
   - Exit code 0 for valid synthetic and real image inputs.
   - Exit code 1 for non-existent input files, corrupt PSD files, missing input arguments.
   - Exit code 2 for un-triangulatable empty alpha masks.
   - Exit code 5 when `--validate` fails on corrupted inputs.
3. **End-to-End Execution Tests**:
   - Single PNG image $\to$ full bundle export with valid `.model3.json`, `.moc3`, `.cdi3.json`, `texture_00.png`.
   - Multi-layer synthetic avatar $\to$ full bundle export and post-validation.
   - Root wrapper `export_live2d.py` delegation via subprocess and module execution.
   - `--json-output` formatting and schema verification.
