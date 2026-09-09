# Scope: Milestone 4 (CLI Interface, 6-Stage Structural Validator & Verification Walkthrough)

## Architecture
Milestone 4 completes the end-to-end user-facing pipeline and quality gate for the 2D-to-Live2D conversion system.

### Modules Delivered:
1. **6-Stage Structural Validator (`src/validator/structural_validator.py` and `validate_live2d.py`)**:
   - `validate_live2d_model(model_dir: Path) -> ValidationReport`:
     * Stage 1: Binary MOC3 Header verification (magic bytes `b"MOC3"`, version 3, little-endian flag = 0, length >= 64 bytes).
     * Stage 2: Section Table offsets, 64-byte alignment, monotonicity, count table sanity.
     * Stage 3: `.model3.json` and `.cdi3.json` JSON schema conformance, relative path existence, texture file references.
     * Stage 4: Parameter IDs (`ParamAngleX`, `ParamAngleY`, `ParamAngleZ`), keyform counts (3 keyforms per parameter), ranges [-30, 30].
     * Stage 5: Texture Atlas PNG dimensions (power-of-two 512..8192), valid RGBA8 channels, UV coordinates in [0.0, 1.0].
     * Stage 6: Topological non-inversion & deformation continuity (signed triangle area preservation > -1e-4 across all keyforms).
   - Rich CLI console output with color-coded stage passes/failures, detailed error messages, and summary metrics.

2. **Headless Zero-Intervention CLI (`src/cli/main.py` and `export_live2d.py`)**:
   - End-to-end execution pipeline connecting:
     * Ingestion (`PSDImporter` or single PNG fallback)
     * Mesh Generation (`DelaunayMeshGenerator`)
     * 3D Deformation (`DeformationEngine`, `AsRigidAsPossible`, Depth / ParamAngleX/Y/Z Keyform generation)
     * Texture Packing (`TextureAtlasPacker`)
     * MOC3 & Model3 Export (`MOC3BinaryWriter`, `Model3ConfigExporter`)
     * In-flight or post-export validation (`validate_live2d_model`)
   - CLI flags: `--input`, `--output-dir`, `--model-name`, `--texture-size`, `--mesh-density`, `--validate`, `--gui`, etc.
   - Standardized exit codes:
     * 0: Success
     * 1: Input / Argument Error
     * 2: Mesh Generation Error
     * 3: Deformation/Physics Error
     * 4: Export/Packaging Error
     * 5: Validation Error (model failed structural checks)

3. **User Verification Walkthrough (`WALKTHROUGH.md`)**:
   - Step-by-step user guide explaining:
     * CLI and Python API usage examples.
     * How to load output folder into Live2D Cubism Viewer (drag & drop `<model_name>.model3.json`).
     * How to import into VTube Studio (placing folder into `VTube Studio/VTube Studio_Data/StreamingAssets/Live2DModels/`).
     * Testing parameter sliders (`ParamAngleX`, `ParamAngleY`, `ParamAngleZ`).
     * Visual inspection and troubleshooting guide (texture bleeding, inverted triangles, missing textures, misalignment).

4. **Comprehensive Unit & Integration Test Suite**:
   - `tests/test_validator.py`: 25 unit/integration tests covering all 6 validation stages.
   - `tests/test_cli.py`: 10 unit/integration tests covering argument parsing, exit codes, mock exports, in-flight validation.

## Milestones & Status
| Component | Scope | Dependencies | Status |
|-----------|-------|-------------|--------|
| Structural Validator | `src/validator/structural_validator.py`, `validate_live2d.py` | M1, M2, M3 | DONE |
| CLI Pipeline Runner | `src/cli/main.py`, `export_live2d.py` | M1, M2, M3, Validator | DONE |
| User Walkthrough | `WALKTHROUGH.md` | Validator, CLI | DONE |
| Unit & Integration Tests | `tests/test_validator.py`, `tests/test_cli.py` | All | DONE |

## Interface Contracts
- `src.validator.structural_validator`:
  - `ValidationStageResult(stage_number: int, stage_name: str, passed: bool, errors: List[str], warnings: List[str], details: Dict[str, Any])`
  - `ValidationReport(passed: bool, stages: List[ValidationStageResult], total_errors: int, total_warnings: int, model_path: str, model_name: str)`
  - `validate_live2d_model(model_path: Union[str, Path], strict: bool = False) -> ValidationReport`
- `src.cli.main`:
  - `run_pipeline(args: argparse.Namespace) -> int` (exit code)
  - `parse_args(args: Optional[List[str]] = None) -> argparse.Namespace`
