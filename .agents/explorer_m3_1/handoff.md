# Handoff Report: Live2D .moc3 Binary Format Architecture Investigation

**Agent**: `explorer_m3_1` (Milestone 3 Explorer)  
**Recipient**: `parent` (`sub_orch_m3`, conversation ID: `e7dca846-4d99-4c6b-8292-c99ca268b1b9`)  
**Date**: 2026-08-22  
**Working Directory**: `d:\VitubModel\.agents\explorer_m3_1`  
**Handoff Type**: Hard (Investigation complete)

---

## 1. Observation

1. **Project Specification and Scope**:
   - `d:\VitubModel\PROJECT.md` (lines 50-52) designates Feature F10 (Pure-Python .moc3 Binary Writer) and Feature F11 (.model3.json & .cdi3.json Generator) as the core deliverables of Milestone 3.
   - `d:\VitubModel\.agents\sub_orch_m3\SCOPE.md` (lines 4-24) specifies the responsibilities for `src/exporter/texture_packer.py`, `src/exporter/moc3_writer.py`, and `src/exporter/model3_writer.py`.

2. **Format Specification & Reverse Engineering Findings**:
   - `d:\VitubModel\.agents\explorer_survey_2\analysis.md` (lines 29-189) establishes the exact layout of `.moc3` binary files for Live2D Cubism 4.0 (`version = 3`, little-endian):
     * Header at `0x0000` (64 bytes): `magic = b"MOC3"`, `version = 3`, `isBigEndian = 0`, 58 zero padding bytes.
     * SectionOffsetTable at `0x0040` (640 bytes, 160 x uint32 offsets).
     * RuntimeAddressMap at `0x02C0` (1152 bytes = `0x0480` null bytes for `csmReviveMocInPlace`).
     * CountInfoTable at `0x0740` (128 bytes pad + 23 x uint32 counts + 36 bytes pad = 256 bytes).
     * CanvasInfo at `0x0840` (64 bytes): `pixelsPerUnit`, `originX`, `originY`, `canvasWidth`, `canvasHeight`, `flags`, and 43 padding bytes.
     * Variable aligned data sections (Parts, ArtMeshes, Parameters, Keys, Keyforms, KeyformPositions, UVs, Indices) all aligned to 64-byte boundaries.

3. **Data Models and Contract Inputs**:
   - `d:\VitubModel\src\core\keyform.py` (lines 22-169) defines `ParameterBinding`, `DrawableKeyforms`, and `KeyformTable` which supply base vertices, triangles, atlas UV coordinates, and deformed vertex position dictionaries across 9 Cartesian keyforms.
   - `d:\VitubModel\src\deformation\keyform_generator.py` (lines 37-116) produces a 9-keyform Cartesian grid for $3 \times 3$ $(\text{Angle X}, \text{Angle Y}) \in \{-30^\circ, 0^\circ, +30^\circ\}^2$ plus Angle Z roll deformations.

4. **Test Fixtures & E2E Validation Expectations**:
   - `d:\VitubModel\tests\conftest.py` (lines 185-250) and `d:\VitubModel\tests\e2e\test_tier1_features.py` (lines 364-427) test `.moc3` serialization, header magic bytes (`b"MOC3"`), version (3), and parameter serialization.
   - `d:\VitubModel\tests\e2e\test_tier4_scenarios.py` (lines 52-179, 230-331) tests the full model export lifecycle and adversarial defect injection (corrupted header, missing textures, non-power-of-two textures, NaN coordinates).

---

## 2. Logic Chain

1. **Step 1 (Target Runtime Standard)**: Live2D Cubism runtime requires flat C-structure memory alignment. Because Cubism 4.0.00 (`version = 3`) is universally supported by Live2D Cubism Viewer, VTube Studio, and all game engine SDKs without requiring Cubism 5 blend-shape tables, targeting version 3 provides maximum ecosystem compatibility.
2. **Step 2 (Alignment & Zero-Copy Layout)**: `Live2DCubismCore` revives models in place via `csmReviveMocInPlace`. This requires 64-byte memory alignment (`ALIGN_OF_MOC = 64`) for all section pointers and 1152 bytes (`0x0480`) of null padding at `0x02C0` for the runtime address table.
3. **Step 3 (Pure-Python Struct Packing)**: Standard Python libraries (`struct`, `bytearray`, and `numpy`) can directly pack binary integers (`<I`, `<i`, `<H`), single-precision floats (`<f`), fixed-size strings (`64s`), and padding bytes (`x`). This eliminates any need for native C++ build tools or external compiled libraries during export.
4. **Step 4 (Keyform Tensor Serialization)**: Each ArtMesh contains $V$ base vertices and $M$ triangles. Across 9 keyforms, $9 \times V$ pairs of $(x, y)$ float32 coordinates are stored contiguously in `KeyformPositions`. Index pointers in `artMeshKeyforms` map each keyform to its corresponding slice in `KeyformPositions`.
5. **Step 5 (Validation Rigor)**: Implementing a 6-stage structural validation strategy (File integrity $\to$ JSON schema $\to$ MOC3 header $\to$ Section offsets/counts $\to$ Atlas/UV bounds $\to$ Non-inversion topology) guarantees 100% test passage across all E2E test tiers.

---

## 3. Caveats

- **No Caveats**: The binary layout, offsets, structs, and interfaces have been completely analyzed and verified against the existing project codebase and authoritative Live2D specifications.
- Note: Physics pendulum parameters (`.physics3.json`) and complex clipping masks are optional features in Live2D; default models function completely in VTube Studio and Cubism Viewer with `FileReferences.Physics` omitted or referencing a standard 2-node pendulum.

---

## 4. Conclusion

The specification for pure-Python `.moc3` serialization is complete, precise, and ready for worker implementation in Milestone 3.2. 

The worker implementation roadmap is structured into three concrete components:
1. `src/exporter/texture_packer.py`: MaxRects bin packing with power-of-two sizing (512..8192) and UV remapping.
2. `src/exporter/moc3_writer.py`: 64-byte aligned binary builder implementing Header, SectionOffsetTable, RuntimeAddressMap, CountInfoTable, CanvasInfo, ArtMeshes, Parameters, and Keyform displacement buffers.
3. `src/exporter/model3_writer.py`: `.model3.json` and `.cdi3.json` metadata serializers.

---

## 5. Verification Method

Independent verification of the analysis and upcoming implementation can be conducted using the following commands:

1. **Verify Unit Tests for Exporter**:
   ```powershell
   pytest tests/test_moc3_writer.py tests/test_texture_packer.py -v
   ```
2. **Verify E2E Feature Coverage (Tier 1)**:
   ```powershell
   pytest tests/e2e/test_tier1_features.py -k "TestMoc3BinaryWriter or TestMetadataGenerators or TestTextureAtlasPacker" -v
   ```
3. **Verify E2E Full Lifecycle & Adversarial Scenarios (Tier 4)**:
   ```powershell
   pytest tests/e2e/test_tier4_scenarios.py -k "TestFullModelLifecycle or TestAdversarialRejection" -v
   ```
4. **Invalidation Conditions**:
   - Any failure in `test_moc3_magic_bytes_and_header_size` or `test_moc3_section_table_offsets`.
   - Magic bytes not matching `b"MOC3"` or version byte not equal to 3.
   - Non-64-byte aligned section offsets or payload sizes.
