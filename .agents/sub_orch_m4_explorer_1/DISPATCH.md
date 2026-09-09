## 2026-08-22T07:05:00Z
You are Explorer 1 for Milestone 4 (CLI & 6-Stage Structural Validator).
Working directory: d:\VitubModel\.agents\sub_orch_m4_explorer_1

You MUST read:
1. d:\VitubModel\.agents\ORIGINAL_REQUEST.md
2. d:\VitubModel\PROJECT.md
3. d:\VitubModel\.agents\sub_orch_m4\SCOPE.md
4. d:\VitubModel\.agents\explorer_survey_3\analysis.md
5. Existing code in src/exporter/ (moc3_writer.py, model3_exporter.py, texture_packer.py), src/core/ (mesh.py, parameters.py, keyforms.py), src/geometry/ (delaunay.py, signed_area.py), src/deformation/ (engine.py, as_rigid_as_possible.py).

Your Task:
Investigate and design the 6-Stage Structural Validator (`src/validator/structural_validator.py` and `validate_live2d.py`).
Analyze the exact requirements for each stage:
1. Stage 1: Binary MOC3 Header verification (magic bytes `b"MOC3"`, version 3, little-endian flag = 1).
2. Stage 2: Section Table offsets, 64-byte alignment, monotonicity, count table sanity.
3. Stage 3: `.model3.json` and `.cdi3.json` JSON schema conformance, relative path existence, texture file references.
4. Stage 4: Parameter IDs (ParamAngleX, ParamAngleY, ParamAngleZ), keyform counts, ranges [-30, 30].
5. Stage 5: Texture Atlas PNG dimensions (power-of-two 512..8192), valid RGBA8 channels, UV coordinates in [0.0, 1.0].
6. Stage 6: Topological non-inversion & deformation continuity (signed triangle area preservation > -1e-4 across all keyforms).

Produce a detailed analysis report in `d:\VitubModel\.agents\sub_orch_m4_explorer_1\analysis.md` and send completion message back. Include concrete data structures, class designs, function signatures, validation result models, error formatting, and code snippets.
