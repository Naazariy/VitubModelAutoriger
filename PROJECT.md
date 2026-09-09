# Project: Automated VTuber Key Deformation & Live2D Export Tool

## Architecture Overview
The system provides a fully automated pipeline transforming 2D character artwork (PSD layers, PNG images, or layer directories) into a fully functional, rig-free Live2D Cubism model bundle (.moc3, .model3.json, .cdi3.json, and packed texture atlas) with auto-calculated 3D head rotation deformations (Angle X, Angle Y, Angle Z).

```
2D Input (PSD / PNG / Directory)
           │
           ▼
1. Asset Ingestion & Layer Parser (src/importer/)
   - Layer decomposition, semantic classification, depth assignment
           │
           ▼
2. Robust Triangulation & Mesh Generator (src/generator/)
   - Pure-Python SciPy Delaunay triangulation, Steiner internal sampling, boundary clipping
           │
           ▼
3. 3D Head Deformation & Keyform Engine (src/depth/, src/deformation/, src/constraints/)
   - SO(3) Euler rotation (Angle X yaw, Angle Y pitch, Angle Z roll)
   - Layer-stratified depth parallax & anime silhouette foreshortening
   - ARAP local-global regularization (positive signed triangle area)
   - Multi-dimensional Keyform displacement tensor evaluation
           │
           ▼
4. Live2D Binary Exporter & Texture Packer (src/exporter/)
   - Power-of-two MaxRects Texture Atlas packing & UV remapping
   - Pure-Python .moc3 binary encoder (64-byte alignment, section tables, drawables, keyforms)
   - .model3.json & .cdi3.json metadata generators
           │
           ▼
5. CLI, Validator & Verification (export_live2d.py, validate_live2d.py, WALKTHROUGH.md)
   - Zero-intervention headless CLI
   - 6-stage programmatic structural validation suite
   - Live2D Cubism Viewer & VTube Studio verification guide
```

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F01 | Multi-Layer PSD Ingestion | Extract layers, dimensions, and masks from PSD files with English/Japanese semantic categorization | M1 | R1, Survey |
| F02 | PNG / Directory Ingestion | Fallback loader for single PNGs and layer image folders | M1 | R1, Survey |
| F03 | Robust Mesh Triangulation | Pure-Python SciPy Delaunay triangulation with Steiner grid & contour clipping (zero C-extension dependency) | M1 | R1, Survey |
| F04 | Semantic Depth Stratification | Ellipsoidal & proxy geometry depth assignment across facial layer hierarchy | M2 | R1, Survey |
| F05 | 3D SO(3) Head Rotation Math | Unified Euler rotation matrix for Angle X ($\pm 30^\circ$), Angle Y ($\pm 30^\circ$), and Angle Z ($\pm 30^\circ$) | M2 | R1, Survey |
| F06 | Parallax & Foreshortening | Depth-scaled perspective parallax and anime silhouette foreshortening | M2 | R1, Survey |
| F07 | ARAP Mesh Regularization | As-Rigid-As-Possible solver with sparse LU factorization ensuring positive signed triangle areas | M2 | R1, Survey |
| F08 | Keyform Tensor Generation | Discrete vertex displacement tables for 9-keyform Cartesian grid ($3 \times 3$ Angle X/Y) + Angle Z | M2 | R1, Survey |
| F09 | MaxRects Texture Atlas Packer | Power-of-two texture atlas packing with edge bleed padding and UV coordinate remapping | M3 | R2, Survey |
| F10 | Pure-Python .moc3 Binary Writer | Compliant binary moc3 serialization (magic header, section tables, drawables, parameters, keyform positions) | M3 | R2, Survey |
| F11 | .model3.json & .cdi3.json Generator | Master manifest and display info metadata writer compatible with Cubism & VTube Studio | M3 | R2, Survey |
| F12 | Headless Zero-Touch CLI | CLI tool (`export_live2d.py` / `python -m src.cli`) running full pipeline without user intervention | M4 | AC-1, Survey |
| F13 | 6-Stage Structural Validator | Standalone validation script (`validate_live2d.py`) checking binary headers, section tables, schemas, parameter bounds, UVs, and mesh topology | M4 | AC-2, Survey |
| F14 | User Manual Verification Guide | Detailed step-by-step loading and testing instructions for Live2D Cubism Viewer & VTube Studio | M4 | AC-2, Survey |
| F15 | E2E Testing Infrastructure | 4-Tier test suite covering feature coverage, edge cases, pairwise interactions, and full real-world pipeline scenarios | E2E | Plan |
| F16 | Adversarial Hardening (Tier 5) | White-box stress testing and corner-case verification by Challenger agents | M5 | Plan |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Track | E2E test infra (`TEST_INFRA.md`), Tiers 1-4 test suite, `TEST_READY.md` publication | None | DONE |
| M1 | Asset Ingestion & Mesh Engine | PSD/PNG ingestion, layer decomposition, SciPy Delaunay triangulation (`src/importer/`, `src/generator/`, `src/core/`) | None | DONE |
| M2 | Automated 3D Deformation Engine | Angle X/Y/Z rotation, depth parallax, ARAP regularization, keyform tensor generation (`src/depth/`, `src/geometry/`, `src/deformation/`, `src/constraints/`) | M1 | DONE |
| M3 | Live2D Binary Exporter & Texture Packer | Pure Python `.moc3` writer, `.model3.json` / `.cdi3.json` generators, MaxRects texture packer (`src/exporter/`) | M1, M2 | DONE |
| M4 | CLI Interface & Structural Validator | Zero-intervention CLI (`export_live2d.py`), 6-stage structural validator (`validate_live2d.py`), manual walkthrough (`WALKTHROUGH.md`) | M3 | DONE |
| M5 | Final Milestone: 100% E2E Pass & Tier 5 Hardening | Pass 100% E2E tests (Tiers 1-4) and complete Tier 5 adversarial hardening | E2E, M4 | DONE |

---

## Code Layout
```
d:\VitubModel\
├── export_live2d.py           # Primary CLI entry script
├── validate_live2d.py         # Programmatic structural validator script
├── launch.py                  # Optional GUI launcher
├── WALKTHROUGH.md             # User manual verification guide
├── requirements.txt           # Python dependencies
├── PROJECT.md                 # Global project index & architecture
├── TEST_INFRA.md              # E2E test infrastructure specification
├── TEST_READY.md              # E2E test suite ready signal
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── layer.py           # Layer and ArtMesh data structures
│   │   ├── mesh.py            # Vertex, Triangle, UV data models
│   │   └── keyform.py         # Parameter keyform mapping data models
│   ├── importer/
│   │   ├── __init__.py
│   │   ├── psd_importer.py    # PSD layer extraction & semantic categorization
│   │   └── image_importer.py  # PNG image loader & contour extractor
│   ├── generator/
│   │   ├── __init__.py
│   │   └── mesh_generator.py  # Pure-Python SciPy Delaunay mesh triangulation
│   ├── depth/
│   │   ├── __init__.py
│   │   └── depth_model.py     # Ellipsoidal & proxy depth map calculations
│   ├── geometry/
│   │   ├── __init__.py
│   │   └── geometry_engine.py # Surface normals & geometric transformations
│   ├── deformation/
│   │   ├── __init__.py
│   │   └── deformation_solver.py # 3D SO(3) Angle X, Y, Z & parallax solver
│   ├── constraints/
│   │   ├── __init__.py
│   │   └── constraint_solver.py  # ARAP local-global regularizer
│   ├── exporter/
│   │   ├── __init__.py
│   │   ├── moc3_writer.py     # Pure-Python Live2D .moc3 binary builder
│   │   ├── model3_writer.py   # .model3.json and .cdi3.json serializers
│   │   └── texture_packer.py  # MaxRects texture atlas packer & UV mapper
│   ├── validator/
│   │   ├── __init__.py
│   │   └── structural_validator.py # 6-stage MOC3 / JSON validator
│   └── cli/
│       ├── __init__.py
│       └── main.py            # CLI argument parser and execution pipeline
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_importer.py
    ├── test_mesh_generator.py
    ├── test_deformation.py
    ├── test_moc3_writer.py
    ├── test_texture_packer.py
    ├── test_validator.py
    ├── test_cli.py
    └── e2e/
        ├── test_tier1_features.py
        ├── test_tier2_boundaries.py
        ├── test_tier3_combinations.py
        └── test_tier4_scenarios.py
```

---

## Interface Contracts

### 1. Ingestion (`src/importer/`) $\to$ Mesh Generator (`src/generator/`)
- `LayerData`:
  - `name: str` (e.g., `"Hair_Front"`, `"Face"`, `"Eye_L"`, `"Mouth"`)
  - `image: np.ndarray` (RGBA, shape $(H, W, 4)$, uint8)
  - `offset_x: int, offset_y: int` (Position on full canvas)
  - `z_depth_hint: float` (Default nominal depth $[-1.0, 1.0]$)
  - `category: str` (`"hair_front"`, `"face"`, `"eyes"`, `"nose"`, `"mouth"`, `"hair_back"`, `"body"`)

### 2. Mesh Generator (`src/generator/`) $\to$ Deformation Engine (`src/deformation/`)
- `Mesh`:
  - `vertices: np.ndarray` (shape $(N, 2)$, float32, normalized/canvas coordinates)
  - `triangles: np.ndarray` (shape $(M, 3)$, int32 vertex indices)
  - `uvs: np.ndarray` (shape $(N, 2)$, float32 $[0.0, 1.0]$ local layer coords)
  - `depth_z: np.ndarray` (shape $(N,)$, float32)

### 3. Deformation Engine $\to$ Live2D Exporter (`src/exporter/`)
- `KeyformTable`:
  - `parameter_ids: List[str]` (`["ParamAngleX", "ParamAngleY", "ParamAngleZ"]`)
  - `parameter_ranges: Dict[str, Tuple[float, float, float]]` (`{"ParamAngleX": (-30.0, 0.0, 30.0), ...}`)
  - `drawables: List[DrawableKeyforms]`:
    - `drawable_id: str`
    - `texture_index: int`
    - `base_vertices: np.ndarray` (shape $(N, 2)$)
    - `triangles: np.ndarray` (shape $(M, 3)$)
    - `uvs_atlas: np.ndarray` (shape $(N, 2)$ in global atlas coordinates $[0, 1]$)
    - `deformed_positions: Dict[Tuple[float, ...], np.ndarray]` (mapping parameter key tuple to $(N, 2)$ vertex positions)

### 4. Live2D Exporter $\to$ Output Directory & Structural Validator
- Output Folder Structure:
  - `<model_name>.model3.json`
  - `<model_name>.moc3`
  - `<model_name>.cdi3.json`
  - `textures/texture_00.png`
- Return status: Exit code 0 on success, non-zero on error.
