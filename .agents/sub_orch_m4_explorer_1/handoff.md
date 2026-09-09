# Milestone 4 Handoff Report: 6-Stage Structural Validator & CLI Architecture

## 1. Observation
1. **Codebase Inspection**:
   - `src/exporter/moc3_writer.py` (lines 58-62, 78-82, 144-174, 505-546): Implements `Moc3Writer`, `Moc3Reader`, and `validate_moc3_bytes`. Uses `MAGIC = b"MOC3"`, `VERSION = 3`, `BIG_ENDIAN = 0`, 160 uint32 section offsets, 64-byte alignment, 256-byte CountInfoTable at `0x0740`, and 64-byte CanvasInfo at `0x0840`.
   - `src/exporter/model3_writer.py` (lines 25-43, 71-86, 109-121, 175-181, 191-256): Implements `Model3Writer` creating `.model3.json` (`Version: 3`, `FileReferences.Moc`, `FileReferences.Textures`, `Groups`, `Layout`) and `.cdi3.json` (`Version: 3`, `Parameters`, `ParameterGroups`, `Parts`). Path normalization converts all backslashes to `/`.
   - `src/exporter/texture_packer.py` (lines 294-299, 411-458, 545-565): Implements `TextureAtlasPacker` enforcing Power-of-Two (POT) atlas dimensions ($512 \dots 8192$) and normalized atlas UV bounds $[0.0, 1.0]$.
   - `src/core/mesh.py` (lines 120-139, 156-218): Implements `compute_triangle_signed_areas(positions)` with $A_{\text{signed}} = 0.5 \cdot ((x_1-x_0)(y_2-y_0) - (x_2-x_0)(y_1-y_0))$ and `validate_topology()`.
   - `tests/conftest.py` (lines 173-180, 405-535): Provides reference stub `StructuralValidator.validate_live2d_model` returning `ValidationResult(is_valid, stages_passed, errors, warnings)`.
   - `tests/e2e/test_tier1_features.py` (lines 537-586) & `tests/e2e/test_tier4_scenarios.py` (lines 230-331): Tests expect `StructuralValidator.validate_live2d_model` to return an object with `.is_valid`, `.stages_passed`, `.errors`, and `.warnings`, and to reject corrupted magic headers (`b"BAD3"`), missing texture files, non-POT textures, and inverted triangles ($A_{\text{signed}} \le -10^{-4}$).

## 2. Logic Chain
1. **From M1-M3 output to M4 validator**:
   - `Moc3Writer` exports raw binary bytes with a 64-byte header, 160 section offsets at `0x0040`, 1152-byte null map at `0x02C0`, CountInfoTable at `0x0740`, and CanvasInfo at `0x0840`.
   - The Stage 1 & Stage 2 validators must check these exact byte-level structures: magic bytes `b"MOC3"`, version `3`, little-endian `0`, 64-byte alignment of total file size and all non-zero offsets, and positive counters for meshes, parameters, UVs, and indices.
2. **From manifest specifications to Stage 3 validator**:
   - `model3.json` and `cdi3.json` are master manifests consumed by Live2D Cubism Viewer and VTube Studio.
   - Any Windows backslash `\` in relative paths causes native runtime loading failures on mobile/macOS platforms.
   - Therefore, Stage 3 must verify `Version: 3`, strictly require forward slashes `/`, and verify that all referenced `.moc3`, texture `.png`, and `.cdi3.json` files physically exist on disk relative to the model directory.
3. **From tracking rig requirements to Stage 4 validator**:
   - Standard Live2D tracking requires `ParamAngleX` and `ParamAngleY` (and optionally `ParamAngleZ`).
   - Stage 4 must verify these parameter IDs, valid bounds ($\text{min} < \text{default} < \text{max}$, nominal $[-30, 0, 30]$), and monotonic key values.
4. **From texture packing to Stage 5 validator**:
   - Live2D OpenGL texture samplers require power-of-two texture pages ($512 \dots 8192$) with 4-channel RGBA format.
   - Stage 5 must verify image loadability, POT dimensions, and ensure all mesh UV coordinates lie strictly in $[0.0, 1.0]$.
5. **From ARAP deformation physics to Stage 6 validator**:
   - Meshes during extreme rotation must not collapse or flip inside-out.
   - Stage 6 computes signed triangle areas $A_{\text{signed}} = 0.5 \cdot ((x_1-x_0)(y_2-y_0) - (x_2-x_0)(y_1-y_0))$ across base pose and all keyforms, asserting $A_{\text{signed}} > -10^{-4}$, and checks for zero NaNs/Infs and bounded displacements.
6. **From test compatibility to data model design**:
   - Existing E2E tests check `result.is_valid`, `result.stages_passed`, `result.errors`, `result.warnings`.
   - New requirements in `SCOPE.md` specify `ValidationStageResult(stage_number, stage_name, passed, errors, warnings, details)` and `ValidationReport(passed, stages, total_errors, total_warnings)`.
   - Designing `ValidationReport` with backward-compatible properties (`is_valid`, `stages_passed`, `errors`, `warnings`) satisfies 100% of both old and new contracts.

## 3. Caveats
- Stage 6 topological validation can operate either directly on the binary `.moc3` section 32 (KeyformPositions) and section 34 (PositionIndices) or on a provided `KeyformTable`. The design supports both paths gracefully.
- No caveats.

## 4. Conclusion
The 6-stage structural validator architecture is completely analyzed and fully specified in `d:\VitubModel\.agents\sub_orch_m4_explorer_1\analysis.md`. The design covers:
1. `src/validator/structural_validator.py` with `ValidationStageResult`, `ValidationReport`, `StructuralValidator`, and `validate_live2d_model`.
2. `validate_live2d.py` standalone CLI tool supporting `--json-report`, `--quiet`, `--verbose`, `--no-color`, and standardized exit codes (0 for pass, 1 for argument error, 5 for validation failure).
3. Ready for immediate implementation by Milestone 4 implementers.

## 5. Verification Method
1. **Independent File Inspection**:
   - Read `d:\VitubModel\.agents\sub_orch_m4_explorer_1\analysis.md` to verify all 6 stages, data structures, signatures, and blueprints.
2. **Post-Implementation Test Execution**:
   ```bash
   pytest tests/test_validator.py -v
   pytest tests/test_cli.py -v
   pytest tests/e2e/ -v
   ```
3. **Invalidation Conditions**:
   - Any stage failing to catch injected defects (corrupt magic, missing textures, out-of-bounds UVs, negative triangle areas).
   - Incompatibility between `ValidationReport` and `ValidationResult` in `tests/conftest.py`.
