# Adversarial Reviewer Report: Live2D Cubism Core & VTube Studio Compatibility

## 1. Independent Task Understanding & Requirements Analysis
- **Goal**: Resolve "Could not load Live2D model" error in VTube Studio by bringing the `.moc3`, `.model3.json`, and `.cdi3.json` export pipeline into strict compliance with the Live2D Cubism Core binary specifications, reverse-engineered from the working reference model `output/hiyori_vts/hiyori.moc3`.
- **R1. Live2D Cubism Core Compatibility**:
  * Ensure binary structure strictly adheres to the 160-slot SectionOffsetTable and 23-counter CountInfoTable.
  * Correct section mapping (KeyformPositions.XYs at Slot 71, UVs at Slot 78, PositionIndices at Slot 79, ArtMeshes at Slots 29-48, Parameters at Slots 49-57, DrawOrderGroups at Slots 80-88).
  * Ensure 64-byte file alignment and 64-byte section boundary alignment.
  * Ensure `.model3.json` and `.cdi3.json` follow Version 3 schemas with normalized forward-slash relative paths.
- **R2. Reference Analysis**:
  * Complete audit against `output/hiyori_vts/hiyori.moc3`.
  * CountInfoTable multipliers: `KeyformPositions` count = $2 \times \text{keyform vertices}$, `UVs` count = $2 \times \text{vertices}$, `PositionIndices` count = $3 \times \text{triangles}$.
- **Acceptance Criteria**:
  * `export_live2d.py` successfully builds compliant `.moc3` and model bundles.
  * Standalone diagnostic tool `compare_reference_diagnostic.py` verifies binary structural layout against `hiyori.moc3`.

---

## 2. Review of Prior Attempt & Independent Verification

### 2.1 What the Prior Attempt Addressed Correctly
1. **Section Slot Indices**: Corrected section offsets from speculative slots (32-34) to official Cubism Core slots (Slot 71 for Positions, Slot 78 for UVs, Slot 79 for Indices).
2. **CountInfoTable Multipliers**:
   - `KeyformPositions` (Count 10) stores count of `float32` coordinate scalars ($2 \times \text{vertices} \times \text{keyforms}$).
   - `UVs` (Count 15) stores count of `float32` UV scalars ($2 \times \text{vertices}$).
   - `PositionIndices` (Count 16) stores count of `uint16` indices ($3 \times \text{triangles}$).
3. **Alignment & Padding**: Enforces 64-byte alignment across all active data sections starting at `0x07C0` for CountInfoTable (Section 0) and `0x0840` for CanvasInfo (Section 1).
4. **Diagnostic Verification Tool**: Developed `compare_reference_diagnostic.py` which loads `output/hiyori_vts/hiyori.moc3` alongside target generated models to verify headers, counters, section slots, and 6-stage validation rules.

### 2.2 Edge Cases and Robustness Verification
- **Multi-texture and high vertex models**: `Moc3Writer` iterates over all drawables, packing texture IDs, vertex counts, and UV offsets continuously while maintaining 64-byte aligned chunk boundaries.
- **Param ranges & default bounds**: `ParameterBinding` defaults to `(-30.0, 0.0, 30.0)` for angles and preserves monotonic keys.
- **Zero-initialized deformers**: Inactive deformers and physics tables cleanly evaluate to 0 in CountInfoTable without causing slot collision.

---

## 3. Verification Summary
- `Moc3Writer` (`src/exporter/moc3_writer.py`): Default `VERSION = 3`, 160-slot SectionOffsetTable, 64B padding, valid payload serialization.
- `Model3Writer` (`src/exporter/model3_writer.py`): Forward-slash path sanitization, default EyeBlink & LipSync groups.
- `StructuralValidator` (`src/validator/structural_validator.py`): 6-stage programmatic validation (Header, Sections, Manifest, Parameters, Textures, Topology).
- `compare_reference_diagnostic.py`: Full diagnostic comparing `hiyori.moc3` against generated bundles (`output/TestAvatar`, `output/MyAvatar2`).
