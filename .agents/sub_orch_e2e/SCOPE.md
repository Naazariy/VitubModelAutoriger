# Scope: E2E Testing Track

## Architecture
The E2E Testing Track provides an opaque-box, requirement-driven 4-Tier test suite covering features F01 through F16, validating the VTuber 3D Key Deformation and Live2D export system at all integration boundaries.

```
E2E Testing Infrastructure (tests/e2e/)
├── Tier 1: Feature Coverage (test_tier1_features.py)
│   ├── Asset ingestion (PNG, PSD, Directory)
│   ├── SciPy Delaunay triangulation & mesh metrics
│   ├── 3D SO(3) Angle X, Angle Y, Angle Z math & parallax
│   ├── ARAP constraint solver convergence & positive area
│   ├── MaxRects texture packing & UV bounds
│   ├── .moc3 binary header & section serialization
│   ├── .model3.json / .cdi3.json schema & relative paths
│   └── Zero-touch CLI execution & argument parsing
├── Tier 2: Boundary & Corner Cases (test_tier2_boundaries.py)
│   ├── 1x1 minimal image & micro assets
│   ├── Odd & non-square canvas dimensions
│   ├── Blank / transparent layers
│   ├── Single layer vs multi-layer edge cases
│   ├── Extreme rotation angles (±60° yaw, ±45° pitch/roll)
│   ├── High vertex density mesh
│   └── Power-of-two texture dimensions & atlas overflow safety
├── Tier 3: Cross-Feature Combinations (test_tier3_combinations.py)
│   ├── Multi-layer PSD with simultaneous Angle X+Y+Z deformation
│   ├── Custom texture atlas resolution with fine mesh grid
│   ├── Full pipeline CLI invocation with in-flight validation (--validate)
│   └── Multi-character batch directory export
└── Tier 4: Real-World Scenarios (test_tier4_scenarios.py)
    ├── Full synthetic VTuber lifecycle (ingest -> mesh -> solve -> export -> validate)
    ├── 100-point parameter space sweep with continuous non-inversion check
    └── Adversarial defect injection & 6-stage structural rejection
```

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F01 | Multi-Layer PSD Ingestion | Extract layers, dimensions, masks with semantic tags | Tier 1, Tier 3 | R1, Survey |
| F02 | PNG / Directory Ingestion | Single PNG and folder ingestion | Tier 1, Tier 2 | R1, Survey |
| F03 | Robust Mesh Triangulation | SciPy Delaunay triangulation with Steiner grid & contour clipping | Tier 1, Tier 2 | R1, Survey |
| F04 | Semantic Depth Stratification | Ellipsoidal & proxy depth map calculations | Tier 1, Tier 3 | R1, Survey |
| F05 | 3D SO(3) Head Rotation Math | Angle X (±30°), Angle Y (±30°), Angle Z (±20°) | Tier 1, Tier 2 | R1, Survey |
| F06 | Parallax & Foreshortening | Perspective parallax and foreshortening | Tier 1, Tier 3 | R1, Survey |
| F07 | ARAP Mesh Regularization | Energy minimization and positive signed area | Tier 1, Tier 2 | R1, Survey |
| F08 | Keyform Tensor Generation | 9-keyform Cartesian grid + Angle Z displacement | Tier 1, Tier 4 | R1, Survey |
| F09 | MaxRects Texture Atlas Packer | Power-of-two packing with UV remapping | Tier 1, Tier 2 | R2, Survey |
| F10 | Pure-Python .moc3 Binary Writer | Magic header, section tables, drawables, keyforms | Tier 1, Tier 4 | R2, Survey |
| F11 | .model3.json & .cdi3.json Generator | Manifest and display metadata | Tier 1, Tier 4 | R2, Survey |
| F12 | Headless Zero-Touch CLI | CLI execution without intervention | Tier 1, Tier 3 | AC-1, Survey |
| F13 | 6-Stage Structural Validator | Standalone validation of moc3, json, UVs, topology | Tier 1, Tier 4 | AC-2, Survey |
| F14 | User Manual Verification Guide | Walkthrough instructions for Live2D Viewer & VTS | Tier 4 | AC-2, Survey |
| F15 | E2E Testing Infrastructure | 4-Tier test suite definition and runner | All Tiers | Plan |
| F16 | Adversarial Hardening (Tier 5) | Challenger stress testing & defect injection tests | Tier 4, Tier 5 | Plan |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E-M1 | TEST_INFRA Formulation | Write TEST_INFRA.md specification | None | DONE |
| E2E-M2 | Tier 1 Feature Coverage Tests | tests/e2e/test_tier1_features.py (41 tests) | E2E-M1 | DONE |
| E2E-M3 | Tier 2 Boundary & Corner Tests | tests/e2e/test_tier2_boundaries.py (17 tests) | E2E-M1 | DONE |
| E2E-M4 | Tier 3 Cross-Feature Tests | tests/e2e/test_tier3_combinations.py (6 tests) | E2E-M1 | DONE |
| E2E-M5 | Tier 4 Real-World Scenario Tests | tests/e2e/test_tier4_scenarios.py (8 tests) | E2E-M1 | DONE |
| E2E-M6 | Test Execution, TEST_READY.md & Gate Review | Run test suite, publish TEST_READY.md, Gate check | E2E-M2, M3, M4, M5 | DONE |

## Interface Contracts
### E2E Test Suite ↔ Test Runner
- Invocation: `.\venv\Scripts\python.exe -m pytest tests/e2e -v`
- Pass Condition: All 72 collected test cases pass with exit code 0.
- Fallback & Mocking: Pure-Python SciPy Delaunay fallback in `tests/conftest.py` ensures 100% deterministic execution on Windows.
