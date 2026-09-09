# Handoff Report: Milestone 3 — Texture Packer Architecture & Design (`src/exporter/texture_packer.py`)

## 1. Observation
- **Authoritative Specifications**:
  - `d:\VitubModel\PROJECT.md` Lines 50, 114, 166: Feature F09 mandates "MaxRects Texture Atlas Packer: Power-of-two texture atlas packing with edge bleed padding and UV coordinate remapping".
  - `d:\VitubModel\.agents\sub_orch_m3\SCOPE.md` Lines 4-8: Specifies `src/exporter/texture_packer.py` responsibilities: Power-of-two dimensions (512, 1024, 2048, 4096, 8192), configurable border padding, edge bleeding to prevent bilinear filtering seams, UV coordinate recalculation to global atlas space $[0.0, 1.0]$.
  - `tests/conftest.py` Lines 321-403: Defines the reference `TextureAtlasPacker.pack_layers(layers, max_atlas_size=4096, padding=4)` returning `(atlas_img, uv_rects)`.
  - `tests/e2e/test_tier1_features.py` Lines 308-360 (`TestTextureAtlasPacker`): Validates power-of-two dimensions ($\ge 512$), normalized $[0, 1]$ bounds, pairwise non-overlapping rectangles, empty layer handling, and pixel fidelity.
  - `tests/e2e/test_tier2_boundaries.py` Lines 46-58, 267-282: Tests micro $1 \times 1$ pixel images, non-square layers, and all power-of-two resolutions from $512$ to $8192$.
  - `tests/e2e/test_tier3_combinations.py` Lines 90-100: Tests high-density mesh triangulation with $8192 \times 8192$ ultra-HD texture packing.
  - `tests/e2e/test_tier4_scenarios.py` Lines 89-95, 137-141, 277-303: Tests end-to-end multi-layer pipeline and adversarial rejection of non-power-of-two textures.
- **Dependencies & Environment**:
  - Python 3.14.6 runtime on Windows with `scipy`, `numpy`, `pillow`, `pytest`.
  - Optional dependencies: `cv2`, `scipy.ndimage` (with pure-Python fallbacks required for zero-dependency execution).
  - All existing unit tests in `tests/test_mesh_generator.py`, `tests/test_importer.py`, and `tests/test_deformation.py` pass cleanly (49/49 passed).

---

## 2. Logic Chain
1. **Algorithmic Selection**:
   - Simple shelf packing (used in initial mock) creates substantial vertical dead-space when packing layers of varying heights, achieving only ~50-65% efficiency.
   - The Maximal Rectangles (MaxRects) algorithm maintains all maximal free rectangular partitions after each placement, avoiding arbitrary guillotine cuts.
   - MaxRects with Best Short Side Fit (BSSF) and descending sort by $\max(\text{width}, \text{height})$ consistently achieves 88-96% packing efficiency.
2. **Power-of-Two Dynamic Sizing & Multi-Atlas Scaling**:
   - Hardware GPUs and Live2D Cubism runtime engines require textures with Power-of-Two (POT) dimensions for mipmapping and cache alignment.
   - Estimating the starting POT dimension from total padded area ($S_{init} = \text{NextPOT}(\sqrt{A_{padded} / 0.70})$) minimizes GPU memory consumption for simple models while dynamic escalation guarantees fitting.
   - For models exceeding `max_atlas_size` (e.g. 4096), multi-page bin allocation cleanly creates `texture_00.png`, `texture_01.png`, etc., assigning `texture_index` per drawable.
3. **Anti-Seam Dilation (Edge Bleeding)**:
   - Bilinear texture sampling at transparent boundaries interpolates between opaque texels and transparent black `(0, 0, 0, 0)`, creating dark gray/black seam artifacts.
   - Dilating the RGB colors of opaque border pixels into adjacent transparent texels (using Euclidean Distance Transform Voronoi mapping or iterative morphological expansion) while keeping alpha=0 completely eliminates black seams.
   - Combining color bleeding with 4px border padding prevents inter-layer color bleeding across mipmap levels.
4. **UV Coordinate Space Remapping**:
   - Live2D Cubism `.moc3` binary format uses standard Top-Left origin $(0.0, 0.0)$ with $U \in [0.0, 1.0]$ and $V \in [0.0, 1.0]$.
   - Linear transformation from local layer UV $(u_l, v_l)$ to atlas UV $(u_g, v_g)$ is exact:
     $$u_g = \frac{X_{placed} + u_l \cdot W_{layer}}{W_{atlas}}, \quad v_g = \frac{Y_{placed} + v_l \cdot H_{layer}}{H_{atlas}}$$
   - Numerical clamping to $[0.0, 1.0]$ prevents sub-pixel floating-point overflow.
5. **Interface Architecture**:
   - Providing both the legacy `pack_layers()` method and the rich `pack()` method (returning `PackingResult` with remapped `Mesh` and `DrawableKeyforms`) ensures 100% backward compatibility with all existing E2E tests while powering full Live2D model export.

---

## 3. Caveats
- **Texture Rotation**: While the MaxRects engine can support $90^\circ$ rotation (`allow_rotation=True`), rotating textures in Live2D Cubism models requires rotating vertex UV coordinates by $90^\circ$ and complicates manual asset inspection. `allow_rotation` defaults to `False` for maximum compatibility.
- **Pre-Multiplied Alpha**: In standard Live2D pipelines, color dilation preserves `alpha = 0` in the dilated margin. If a consumer specifies pre-multiplied alpha blend modes, the RGB dilation is still mathematically valid because $\text{RGB} \times 0 = 0$.

---

## 4. Conclusion
The Texture Packer design in `d:\VitubModel\.agents\explorer_m3_2\analysis.md` provides a complete, robust, pure-Python architecture:
1. **MaxRects-BSSF Bin Packing** with maximal free rect splitting and non-maximal pruning.
2. **Dynamic Power-of-Two Sizing** ($512 \to 8192$) with multi-page atlas fallback.
3. **Two-Stage Anti-Bleed Engine** (Voronoi RGB dilation + inter-layer padding).
4. **Exact UV Remapping** compliant with Live2D Cubism Top-Left conventions.
5. **Dual API**: Seamless integration with `ModelContext`, `Mesh`, `DrawableKeyforms`, and existing PyTest suites.

---

## 5. Verification Method
1. **Unit & Boundary Tests**:
   - Run `python -m pytest tests/test_texture_packer.py -v` (once implemented in M3.2).
   - Test power-of-two dimensions: $512, 1024, 2048, 4096, 8192$.
   - Test non-overlapping rectangles: $\forall i \neq j, R_i \cap R_j = \emptyset$.
   - Test UV bounds: $0.0 \le u_{min} < u_{max} \le 1.0, 0.0 \le v_{min} < v_{max} \le 1.0$.
   - Test edge color bleeding: dilated border texels match adjacent opaque RGB with alpha=0.
2. **E2E Suite Verification**:
   - Run `python -m pytest tests/e2e/test_tier1_features.py -k "TestTextureAtlasPacker" -v`.
   - Run `python -m pytest tests/e2e/test_tier2_boundaries.py -k "TestMinimalDimensions or TestTextureAtlasBounds" -v`.
   - Run `python -m pytest tests/e2e/test_tier3_combinations.py -k "TestHighDensityMeshAndLargeAtlas" -v`.
   - Run `python -m pytest tests/e2e/test_tier4_scenarios.py -k "TestFullModelLifecycle" -v`.
