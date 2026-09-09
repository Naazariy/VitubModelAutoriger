# Handoff Report: Milestone 3 Explorer Investigation (model3_writer.py & Test Architecture)

**Agent ID**: `explorer_m3_3`  
**Working Directory**: `d:\VitubModel\.agents\explorer_m3_3`  
**Parent Conversation ID**: `e7dca846-4d99-4c6b-8292-c99ca268b1b9`  
**Date**: 2026-08-22  
**Handoff Type**: Hard Handoff (Investigation & Architecture Design Complete)

---

## 1. Observation

1. **Existing Codebase State**:
   - `src/core/keyform.py` lines 6-169 defines `ParameterBinding`, `DrawableKeyforms`, and `KeyformTable` with `validate()` method checking parameter counts, base vertices, triangles, and UV bounds $[0.0, 1.0]$.
   - `src/core/layer.py` lines 9-253 defines `LayerData` and `LayerCollection` with bounding boxes, content cropping, alpha channel extraction, and z-depth sorting.
   - `src/core/mesh.py` lines 5-244 manages 2D/2.5D mesh data models with `compute_triangle_signed_areas()` and `validate_topology()`.
   - `src/deformation/keyform_generator.py` lines 16-196 implements 3x3 Cartesian grid generation for Angle X $\times$ Angle Y ($9$ keyforms) with ARAP regularization and identity at $(0, 0)$.
   - `src/exporter/` directory does not yet exist and is scheduled for implementation in Milestone 3.

2. **Existing Test Suite Execution**:
   - Running `python -m pytest tests/test_deformation.py tests/test_importer.py tests/test_mesh_generator.py` executed 49 tests with exit code 0:
     ```
     ============================= 49 passed in 20.22s =============================
     ```
   - Running `python -m pytest` across all test files flagged `ModuleNotFoundError: No module named 'cv2'` in `tests/e2e/test_tier*.py` and `tests/test_renderer_occlusion.py` due to top-level `import cv2` without try-except fallback.

3. **Live2D Binary & Metadata Format Authoritative Specifications**:
   - `.model3.json` must adhere strictly to Cubism Version 3 schema, containing `FileReferences` (`Moc`, `Textures`, `Physics`, `DisplayInfo`), `Groups` (`LipSync`, `EyeBlink`), `HitAreas`, and forward-slash normalized relative paths.
   - `.cdi3.json` must define Version 3 `Parameters`, `ParameterGroups`, and `Parts` with bilingual English/Japanese display mappings.
   - `.moc3` binary format requires 64-byte Header (`0x0000`), SectionOffsetTable (160 uint32 entries at `0x0040`), RuntimeAddressMap (1152 null bytes at `0x02C0`), CountInfoTable (256 bytes at `0x0740`), CanvasInfo (64 bytes at `0x0840`), followed by 64-byte aligned data array sections.

---

## 2. Logic Chain

1. **Manifest Compatibility Requirement**:
   - *From Observation 1 & 3*: Live2D Cubism Viewer, Cubism Editor, and VTube Studio require `.model3.json` (with exact `"Version": 3`) and `.cdi3.json` to load and track a Live2D model bundle.
   - *Reasoning*: If file paths use Windows backslashes `\`, runtime loaders in cross-platform environments (Unity, WebGL, macOS, iOS) fail to resolve referenced textures and `.moc3` files. Thus, `Model3Writer.generate_model3_json()` must explicitly normalize all relative paths with `.replace('\\', '/')`.
   - *Reasoning*: VTube Studio relies on standard Live2D parameter IDs (`ParamAngleX`, `ParamAngleY`, `ParamAngleZ`, `ParamEyeLOpen`, `ParamEyeROpen`, `ParamMouthOpenY`, `ParamMouthForm`) to automatically bind webcam face-tracking inputs without requiring manual user re-mapping.

2. **Display Info Tree Organization**:
   - *From Observation 3*: Live2D Cubism Editor organizes parameter sliders into collapsible tree nodes using `ParameterGroups` defined in `.cdi3.json`.
   - *Reasoning*: Generating `.cdi3.json` with standard groups (`ParamGroupHead` $\to$ `"Head Rotation"`, `ParamGroupEyes` $\to$ `"Eyes"`, `ParamGroupMouth` $\to$ `"Mouth"`, `ParamGroupBody` $\to$ `"Body"`) ensures full UI feature parity and clean visualization in Live2D editors and VTube Studio parameter menus.

3. **Test Architecture Completeness for Milestone 3**:
   - *From Observation 1 & 2*: Milestone 3 introduces `src/exporter/texture_packer.py`, `src/exporter/moc3_writer.py`, and `src/exporter/model3_writer.py`.
   - *Reasoning*: A unit test suite `tests/test_texture_packer.py` must comprehensively test edge cases (empty layers, 1x1 micro layers, transparent layers, power-of-two invariants $512..8192$, edge bleeding, and UV remapping) to guarantee texture atlas stability.
   - *Reasoning*: A unit test suite `tests/test_moc3_writer.py` must verify binary header magic `b"MOC3"`, version 3, 64-byte alignment across all section offsets, correct element counts in `CountInfoTable`, 9-keyform Cartesian grid displacement serialization, and round-trip parsing validation.
   - *Reasoning*: A unit test suite `tests/test_model3_writer.py` must verify `.model3.json` and `.cdi3.json` schema validity, forward-slash normalization, and directory auto-creation.

---

## 3. Caveats

1. **C-Extension vs. Pure Python**: The design is 100% pure Python using `struct`, `numpy`, and `PIL.Image`, requiring zero native C++ DLL compilation or Live2D Native SDK binaries.
2. **`cv2` Dependency in E2E Tests**: In Python 3.14 environments where native `opencv-python` may not be installed, test files must use `PIL` fallback or wrap `import cv2` in `try...except ImportError` (as done in `tests/conftest.py`).
3. **No Other Caveats**: All format specifications, offsets, padding rules, and test architectures are fully documented in `analysis.md`.

---

## 4. Conclusion

1. **`src/exporter/model3_writer.py` Design**:
   - Ready for worker implementation with `Model3Writer.generate_model3_json()` and `Model3Writer.generate_cdi3_json()`.
   - Strictly enforces Version 3 schema, forward-slash relative path formatting, standard `LipSync`/`EyeBlink` groups, interactive `HitAreas`, and bilingual parameter/part display trees.
2. **Milestone 3 Test Suite Design**:
   - Complete 11-test specification for `tests/test_texture_packer.py` (empty layers, single layer, MaxRects multi-layer packing, power-of-two sizing, padding, edge bleeding, UV recalculation, overlap checks).
   - Complete 10-test specification for `tests/test_moc3_writer.py` (magic header, 64-byte alignment, section offset tables, count tables, ArtMesh serialization, 9-keyform Cartesian grid tensors, round-trip validation).
   - Complete 6-test specification for `tests/test_model3_writer.py` (manifest schemas, path normalization, parameter groups, file write).

---

## 5. Verification Method

To independently verify this design and all existing milestone foundations:

1. **Verify Baseline Unit Tests**:
   ```powershell
   python -m pytest tests/test_deformation.py tests/test_importer.py tests/test_mesh_generator.py -v
   ```
   *Expected Result*: 49 tests passing.

2. **Inspect Analysis Artifacts**:
   - View `d:\VitubModel\.agents\explorer_m3_3\analysis.md` for the complete `.model3.json` schema, `.cdi3.json` schema, compatibility matrix, and test case inventory.
   - Invalidation Condition: If any `.model3.json` field deviates from Cubism Version 3 or section offsets violate 64-byte alignment in `.moc3`, this analysis must be revised.
