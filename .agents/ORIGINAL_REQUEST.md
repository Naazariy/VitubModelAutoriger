# Original User Request

## Initial Request — 2026-08-23T07:46:46Z

Rewrite the Live2D auto-rigger generator architecture to create proper Warp and Rotation Deformers for head rotation (Angle X/Y/Z), instead of directly deforming ArtMeshes, to perfectly match the official Live2D Cubism structure.

Requirements:
1. R1. Live2D Deformer Hierarchy: Modify the generation pipeline (main.py, mesh_generator.py, moc3_writer.py, etc.) to generate a standard Live2D deformer hierarchy: `RootPart` -> `RotationDeformer` (for AngleZ) -> `WarpDeformer` (for AngleX and AngleY) -> `ArtMesh`.
2. R2. Parameter Binding: Ensure that `ParamAngleX` and `ParamAngleY` are bound to the `WarpDeformer` keyforms, and `ParamAngleZ` is bound to the `RotationDeformer` keyforms. ArtMeshes should no longer have rotation parameters bound directly to their vertices.

Acceptance Criteria:
- The generated `.moc3` file successfully loads in VTube Studio without the "Could not load Live2D model" error.
- Structural validation scripts and `check_hiyori.py` confirm the presence of deformers (Counts > 0) in the exported model.
- All unit and integration test suites pass.

Please run the SWE Light loop (implementer, adversarial review rounds, verifying with test executions) and write your final handoff.md in your working directory when complete.
