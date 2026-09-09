# Scope: Milestone 3 — Live2D Binary Exporter & Texture Packer Pipeline

## Architecture & Responsibilities
- `src/exporter/texture_packer.py`: MaxRects bin packing algorithm for 2D texture atlas generation.
  - Power-of-two texture atlas dimensions (512, 1024, 2048, 4096, 8192).
  - Configurable border padding and edge bleeding to prevent texture filtering artifacts (bilinear bleed/seams).
  - UV coordinate recalculation mapping layer local pixel space to global atlas UV space [0.0, 1.0].
  - Returns packed texture PIL Image / RGBA numpy array and UV mapping metadata per ArtMesh layer.
- `src/exporter/moc3_writer.py`: Pure-Python Live2D .moc3 binary builder.
  - 64-byte Header (magic `MOC3`, version 3, little-endian byte ordering).
  - SectionOffsetTable starting at offset `0x0040` (64-byte aligned offsets for CanvasInfo, Parts, Deformers, WarpDeformers, RotationDeformers, ArtMeshes, Parameters, Keyforms, etc.).
  - RuntimeAddressMap starting at offset `0x02C0` (1152 bytes null padding).
  - CanvasInfo section (pixelsPerUnit, originX, originY, canvasWidth, canvasHeight, flags).
  - CountInfoTable (Counts for Parts, Deformers, WarpDeformers, RotationDeformers, ArtMeshes, Parameters, Keyforms, KeyformPositions, UVs, Indices).
  - Parts table (IDs, names, parent parts).
  - ArtMeshes / Drawables table (IDs, parent deformers, texture indices, blend modes, culling flags, vertex counts, UV offsets, index offsets).
  - Parameters table (`ParamAngleX`, `ParamAngleY`, `ParamAngleZ`, `ParamEyeLOpen`, etc.) with min, max, default values and key values.
  - Keyforms / KeyformPositions tables mapping parameters and 9-keyform Cartesian grid (ParamAngleX x ParamAngleY) + ParamAngleZ deformation vertices.
- `src/exporter/model3_writer.py`: Live2D Cubism 3+ metadata generator.
  - `.model3.json` containing references to `.moc3` binary, texture atlas PNGs, physics, cdi3, and group definitions compatible with Cubism Viewer and VTube Studio.
  - `.cdi3.json` (Combined Display Info) providing friendly names and parameter group hierarchies for Live2D editors and tracking apps.
- `tests/test_texture_packer.py`, `tests/test_moc3_writer.py`, `tests/test_model3_writer.py`:
  - Comprehensive unit test suite with 32 tests.

## Milestones / Subtasks
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M3.1 | Exploration & Spec Mining | Analyze format, prior milestones, Live2D moc3 binary structures | none | DONE |
| M3.2 | Worker Implementation | Implement texture_packer.py, moc3_writer.py, model3_writer.py, unit tests | M3.1 | DONE |
| M3.3 | Review, Challenge & Audit | 2 Reviewers, 2 Challengers, 1 Forensic Auditor | M3.2 | DONE |
| M3.4 | Gate & Handoff | Gate verification, passing all tests, final handoff to parent | M3.3 | DONE |
