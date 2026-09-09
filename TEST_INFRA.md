# E2E Test Infrastructure Specification

## 1. Test Philosophy & Architecture
The E2E testing framework for the Automated VTuber Key Deformation & Live2D Export project adheres to an **opaque-box, requirement-driven, interface-contract** paradigm:
- **Opaque-Box Testing**: Tests validate functionality through public APIs, headless CLI execution, data structures, and exported binary/JSON file artifacts without coupling to volatile private implementation details.
- **Requirement-Driven & Mathematical Invariant Verification**: Expected outputs are derived directly from the mathematical properties of $SO(3)$ rotations, Delaunay triangulation, ARAP energy formulation, and official Live2D Cubism 3.0+ file specifications (`.moc3`, `.model3.json`, `.cdi3.json`).
- **Progressive Testability & Zero C-Extension Dependency**: All test fixtures, mocks, and spatial operations are executed with pure Python, NumPy, SciPy, OpenCV, and Pillow, ensuring deterministic execution on Windows platforms without C++ build tool dependencies.

---

## 2. Feature Inventory Mapping (F01 – F16)

| # | Feature Code | Feature Description | Primary Tier | Secondary Tiers | Test Module | Target Coverage Threshold |
|---|---|---|---|---|---|---|
| F01 | `FEAT_PSD_INGEST` | Multi-Layer PSD Ingestion, layer extraction, alpha mask decomposition, semantic categorization | Tier 1 | Tier 3 | `test_tier1_features.py`, `test_tier3_combinations.py` | $\ge 5$ atomic tests |
| F02 | `FEAT_PNG_INGEST` | Single PNG / Directory Ingestion, contour extraction, synthetic head generation | Tier 1 | Tier 2 | `test_tier1_features.py`, `test_tier2_boundaries.py` | $\ge 5$ atomic tests |
| F03 | `FEAT_MESH_GEN` | Delaunay Triangulation, Steiner grid generation, contour clipping, positive rest triangle area | Tier 1 | Tier 2, Tier 3 | `test_tier1_features.py`, `test_tier2_boundaries.py` | $\ge 5$ atomic tests |
| F04 | `FEAT_DEPTH_STRAT` | Semantic Depth Stratification, ellipsoidal & proxy depth map calculations, peripheral falloff | Tier 1 | Tier 3, Tier 4 | `test_tier1_features.py`, `test_tier3_combinations.py` | $\ge 5$ atomic tests |
| F05 | `FEAT_SO3_ROT` | 3D $SO(3)$ Head Rotation Math ($R_x, R_y, R_z$ for AngleX, AngleY, AngleZ) | Tier 1 | Tier 2, Tier 4 | `test_tier1_features.py`, `test_tier2_boundaries.py` | $\ge 5$ atomic tests |
| F06 | `FEAT_PARALLAX` | Layer-stratified depth parallax and anime silhouette foreshortening | Tier 1 | Tier 3 | `test_tier1_features.py`, `test_tier3_combinations.py` | $\ge 5$ atomic tests |
| F07 | `FEAT_ARAP_SOLVER` | ARAP local-global regularization, spring stiffness, positive signed triangle area | Tier 1 | Tier 2, Tier 4 | `test_tier1_features.py`, `test_tier2_boundaries.py` | $\ge 5$ atomic tests |
| F08 | `FEAT_KEYFORM_TENSOR`| Discrete vertex displacement keyform grid ($3 \times 3$ Angle X/Y + Angle Z) | Tier 1 | Tier 3, Tier 4 | `test_tier1_features.py`, `test_tier4_scenarios.py` | $\ge 5$ atomic tests |
| F09 | `FEAT_ATLAS_PACKER` | MaxRects Texture Atlas Packer, power-of-two bounds, UV remapping to $[0, 1]$ | Tier 1 | Tier 2, Tier 3 | `test_tier1_features.py`, `test_tier2_boundaries.py` | $\ge 5$ atomic tests |
| F10 | `FEAT_MOC3_WRITER` | Pure-Python `.moc3` Binary Writer (magic bytes `MOC3`, 64-byte alignment, section tables) | Tier 1 | Tier 4 | `test_tier1_features.py`, `test_tier4_scenarios.py` | $\ge 5$ atomic tests |
| F11 | `FEAT_JSON_META` | `.model3.json` and `.cdi3.json` metadata generators (Cubism Version 3, relative paths) | Tier 1 | Tier 4 | `test_tier1_features.py`, `test_tier4_scenarios.py` | $\ge 5$ atomic tests |
| F12 | `FEAT_CLI_ENGINE` | Headless Zero-Touch CLI (`export_live2d.py`, argument schema, exit code specifications) | Tier 1 | Tier 2, Tier 3 | `test_tier1_features.py`, `test_tier3_combinations.py` | $\ge 5$ atomic tests |
| F13 | `FEAT_VALIDATOR` | 6-Stage Structural Validator (`validate_live2d.py`, binary, schema, UVs, topology) | Tier 1 | Tier 4 | `test_tier1_features.py`, `test_tier4_scenarios.py` | $\ge 5$ atomic tests |
| F14 | `FEAT_MANUAL_GUIDE` | Verification Guide format, parameter binding specifications (Live2D Viewer & VTS) | Tier 4 | — | `test_tier4_scenarios.py` | Full verification coverage |
| F15 | `FEAT_E2E_INFRA` | 4-Tier Test Runner, pytest fixtures, deterministic execution harness | All | All | `tests/conftest.py`, `tests/e2e/` | 100% pass across all tiers |
| F16 | `FEAT_ADVERSARIAL` | Defect injection & rejection suite (corrupt headers, out-of-bounds UVs, flipped triangles) | Tier 4 | Tier 2 | `test_tier4_scenarios.py`, `test_tier2_boundaries.py` | $\ge 5$ defect scenarios |

---

## 3. 4-Tier Test Architecture & Coverage Thresholds

```
┌────────────────────────────────────────────────────────────────────────┐
│               TIER 1: Feature Coverage (Atomic Functions)               │
│   Threshold: >= 5 distinct tests per feature group (>= 40 tests total) │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│           TIER 2: Boundary & Corner Cases (Extreme Limits)             │
│   Threshold: >= 8 boundary condition test suites (>= 15 tests total)   │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│          TIER 3: Cross-Feature Combinations (Pairwise Matrix)          │
│   Threshold: >= 5 combinatorial integration tests (>= 10 tests total)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             TIER 4: Real-World Scenarios & Adversarial Sweeps          │
│   Threshold: Lifecycle E2E, 100-point parameter sweep, defect rejection│
└────────────────────────────────────────────────────────────────────────┘
```

### Tier Breakdown & Rules:
1. **Tier 1 — Feature Coverage (`tests/e2e/test_tier1_features.py`)**:
   - Focus: Unit and component integration coverage for every functional building block.
   - Requirements: At least 5 explicit test cases for each feature domain (Ingestion, Mesh Triangulation, 3D Rotation Math & Parallax, ARAP Regularization, Texture Atlas Packing, MOC3 Binary Serialization, JSON Metadata Generation, CLI & Validator).
   - Target: $\ge 40$ passing tests.

2. **Tier 2 — Boundary & Corner Cases (`tests/e2e/test_tier2_boundaries.py`)**:
   - Focus: Edge cases, scale limits, extreme geometries, zero divisions, and non-standard inputs.
   - Requirements:
     - Minimal dimensions ($1\times 1$, $16\times 16$, $64\times 64$ micro-images).
     - Odd and non-square dimensions ($513\times 729$, $301\times 301$).
     - Empty and $100\%$ transparent layers (graceful bypass).
     - Disconnected multi-island contours (no bridge triangles across ribbons).
     - Single-layer vs. multi-layer edge conditions.
     - Extreme rotation angles ($\text{AngleX}=\pm 60^\circ, \text{AngleY}=\pm 45^\circ, \text{AngleZ}=\pm 45^\circ$).
     - High vertex density mesh ($\text{grid\_size}=10$, $>1000$ vertices).
     - Power-of-two texture dimensions ($512, 1024, 2048, 4096, 8192$) and atlas boundary enforcement.

3. **Tier 3 — Cross-Feature Combinations (`tests/e2e/test_tier3_combinations.py`)**:
   - Focus: Pairwise and multi-dimensional interactions between independently configured features.
   - Requirements:
     - Multi-layer PSD + Simultaneous 3-axis compound deformation ($\text{AngleX}=25^\circ, \text{AngleY}=-20^\circ, \text{AngleZ}=15^\circ$).
     - High-density mesh + Custom $8192\times 8192$ texture atlas packing.
     - AI Auto-Depth & Stiffness + Full deformation solving & keyform tensor generation.
     - Batch folder export (processing multiple character models in a single CLI run).
     - CLI execution with `--validate` flag active (in-flight self-check).

4. **Tier 4 — Real-World Application Scenarios (`tests/e2e/test_tier4_scenarios.py`)**:
   - Focus: End-to-end character model lifecycle, parameter space continuity sweeps, and adversarial hardening.
   - Requirements:
     - Full synthetic VTuber lifecycle (Ingest $\to$ Mesh Gen $\to$ Depth & Stiffness $\to$ Keyform Tensor $\to$ Atlas Packing $\to$ MOC3 & JSON Export $\to$ 6-Stage Programmatic Validation).
     - 100-point parameter space sweep across $[-30, 30] \times [-30, 30] \times [-20, 20]$ verifying smooth displacement and positive signed triangle area ($A_{\text{signed}} > -10^{-4}$).
     - Adversarial defect injection and rejection suite (corrupted MOC3 magic header, missing texture file, out-of-bounds UV coordinates $u=1.25$, inverted triangle with negative signed area, NaN vertex coordinates in keyform).

---

## 4. Test Runner & Verification Instructions

### 4.1 Running the Full E2E Test Suite
Execute the pytest runner in the project virtual environment:

```powershell
.\venv\Scripts\python.exe -m pytest tests/e2e -v
```

### 4.2 Running Specific Test Tiers
```powershell
# Tier 1: Feature Coverage
.\venv\Scripts\python.exe -m pytest tests/e2e/test_tier1_features.py -v

# Tier 2: Boundary & Corner Cases
.\venv\Scripts\python.exe -m pytest tests/e2e/test_tier2_boundaries.py -v

# Tier 3: Combinations
.\venv\Scripts\python.exe -m pytest tests/e2e/test_tier3_combinations.py -v

# Tier 4: Scenarios & Sweeps
.\venv\Scripts\python.exe -m pytest tests/e2e/test_tier4_scenarios.py -v
```

### 4.3 Success Verification Criteria
1. **Pass Rate**: $100\%$ of collected tests must exit with code `0`.
2. **Deterministic Output**: Tests must run without flaky network or external binary requirements.
3. **Artifact Integrity**: Generated test models in temporary test directories must produce valid `.moc3`, `.model3.json`, `.cdi3.json`, and packed texture atlases satisfying the 6-stage structural validator.
