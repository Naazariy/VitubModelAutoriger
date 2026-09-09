## 2026-08-22T07:04:55Z
You are Explorer 3 for Milestone 4 (Test Architecture & Walkthrough Documentation).
Working directory: d:\VitubModel\.agents\sub_orch_m4_explorer_3

You MUST read:
1. d:\VitubModel\.agents\ORIGINAL_REQUEST.md
2. d:\VitubModel\PROJECT.md
3. d:\VitubModel\.agents\sub_orch_m4\SCOPE.md
4. Existing tests in tests/test_importer.py, tests/test_geometry.py, tests/test_deformation.py, tests/test_exporter.py.

Your Task:
Investigate and design:
1. Unit & Integration test suite for Milestone 4:
   - `tests/test_validator.py`: Exhaustive tests for all 6 validation stages, both passing cases and corrupted/failing fixtures for each stage (corrupt magic bytes, misaligned sections, invalid json schema, out-of-range params, non-power-of-two texture, inverted triangle keyforms).
   - `tests/test_cli.py`: CLI invocation tests, flag parsing, end-to-end export from mock PSD / PNG, exit code verification, --validate flag triggering, error trapping.
2. `WALKTHROUGH.md` documentation design:
   - Clear step-by-step user guide for Live2D Cubism Viewer (loading model, checking physics/parameters) and VTube Studio (folder structure, importing, tracking).
   - Parameter slider verification guide for ParamAngleX, ParamAngleY, ParamAngleZ.
   - Troubleshooting common visual artifacts (texture bleeding, inverted polygons, clipping).

Produce a detailed analysis report in `d:\VitubModel\.agents\sub_orch_m4_explorer_3\analysis.md` and send completion message back. Include test fixtures design, test matrices, and complete outline for WALKTHROUGH.md.
