# Scope: Milestone 1 — Asset Ingestion & Robust Mesh Triangulation Engine

## Architecture & Responsibilities
Milestone 1 establishes the asset loading, layer extraction, semantic tagging, and 2D mesh generation pipeline for the Automated VTuber Rigging system.

```
Input Asset (PSD file, PNG file, or directory of layer PNGs)
          │
          ▼
┌────────────────────────────────────────────────────────┐
│                   Asset Ingestion                      │
│ - PSDImporter (src/importer/psd_importer.py)           │
│ - ImageImporter (src/importer/image_importer.py)       │
│ - LayerData / ArtMesh models (src/core/layer.py,       │
│   src/core/mesh.py, src/core/keyform.py)               │
└──────────────────────────┬─────────────────────────────┘
                           │ List[LayerData]
                           ▼
┌────────────────────────────────────────────────────────┐
│                Robust Mesh Generator                   │
│ - MeshGenerator (src/generator/mesh_generator.py)      │
│ - Pure-Python SciPy Delaunay triangulation             │
│ - Steiner internal grid points                         │
│ - Boundary contour extraction & polygon containment    │
│ - Laplacian smoothing & area validation                │
└──────────────────────────┬─────────────────────────────┘
                           │ Dict[str, Mesh]
                           ▼
                 Ready for Milestone 2
```

## Feature Inventory
| # | Feature | Description | Milestone | Status |
|---|---------|-------------|-----------|--------|
| F01 | Multi-Layer PSD Ingestion | Multi-layer extraction, bounds, alpha masks, English/Japanese semantic classification (`psd_importer.py`) | M1 | PLANNED |
| F02 | PNG / Directory Ingestion | Single PNG and directory loading with contour extraction and synthetic head generation (`image_importer.py`) | M1 | PLANNED |
| F03 | Robust Mesh Triangulation | Pure-Python SciPy Delaunay triangulation + Steiner grid + `cv2.pointPolygonTest` clipping (`mesh_generator.py`) | M1 | PLANNED |
| F04 | Core Data Structures | `LayerData`, `Mesh`, `Vertex`, `Triangle`, `UV`, `Keyform` data models (`src/core/`) | M1 | PLANNED |

## Interface Contracts

### 1. Ingestion (`src/importer/`) -> Mesh Generator (`src/generator/`)
- `LayerData`:
  - `name: str` (e.g. `"Hair_Front"`, `"Face"`, `"Eye_L"`, `"Mouth"`)
  - `image: np.ndarray` (RGBA, uint8, shape $(H, W, 4)$)
  - `offset_x: int, offset_y: int` (position on full canvas)
  - `z_depth_hint: float` (nominal depth $[-1.0, 1.0]$)
  - `category: str` (`"hair_front"`, `"face"`, `"eyes"`, `"nose"`, `"mouth"`, `"hair_back"`, `"body"`, `"unknown"`)
  - `visible: bool = True`
  - `opacity: float = 1.0`

### 2. Mesh Generator (`src/generator/`) -> Downstream Engine (`src/deformation/`)
- `Mesh`:
  - `vertices: np.ndarray` (shape $(N, 2)$, float32, canvas/normalized coordinates)
  - `triangles: np.ndarray` (shape $(M, 3)$, int32 vertex indices)
  - `uvs: np.ndarray` (shape $(N, 2)$, float32 $[0.0, 1.0]$ layer-local coordinates)
  - `depth_z: np.ndarray` (shape $(N,)$, float32 nominal depths)
  - `layer_id: str`
  - `rest_positions: np.ndarray` (shape $(N, 2)$, float32)
  - `edges: np.ndarray` (shape $(E, 2)$, int32)

## Quality & Acceptance Criteria
1. `tests/test_importer.py` passes 100% with high coverage for PSD, PNG, directory, and synthetic head generation.
2. `tests/test_mesh_generator.py` passes 100% verifying non-degenerate triangles, positive signed areas, zero C-extension `triangle` dependency, and robust contour clipping.
3. Code layout strictly complies with `PROJECT.md`.
4. Independent verification by 2 Reviewers, 2 Challengers, and 1 Forensic Auditor.
