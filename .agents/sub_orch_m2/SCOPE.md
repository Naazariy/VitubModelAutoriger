# Scope: Milestone 2 — Automated 3D Head Deformation Engine

## Architecture
Milestone 2 bridges Milestone 1's segmented 2D PSD layers / Delaunay meshes with Live2D physics-ready 3D deformation tensors. It computes 3D depth proxies per layer, calculates differential geometric properties, computes SO(3) Euler rotational deformation with depth-stratified perspective parallax and anime foreshortening, and solves As-Rigid-As-Possible (ARAP) + Laplacian constraint systems with positive signed area barriers to generate distortion-free multi-dimensional keyform tensors.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Depth Proxy Assignment | Ellipsoidal, cylindrical, planar models per layer category | M2 | ORIGINAL_REQUEST.md §2.1 |
| 2 | Multi-layer Depth Field | Depth z in [-1.0, 1.0], layer depth separation | M2 | ORIGINAL_REQUEST.md §2.1 |
| 3 | Differential Geometry | Surface normals, tangent vectors, mean curvature, projective geometry | M2 | ORIGINAL_REQUEST.md §2.2 |
| 4 | SO(3) Euler Rotations | Yaw (Angle X ±30°), Pitch (Angle Y ±30°), Roll (Angle Z ±30°) Rodrigues/Euler transforms | M2 | ORIGINAL_REQUEST.md §2.3 |
| 5 | Anime Foreshortening & Parallax | Depth-stratified perspective parallax & non-linear anime silhouette scaling | M2 | ORIGINAL_REQUEST.md §2.3 |
| 6 | ARAP Constraint Solver | Local-global iterations, sparse LU (splu) factorization cache, Laplacian spring energy | M2 | ORIGINAL_REQUEST.md §2.4 |
| 7 | Signed Area Preservation | Positive signed triangle area barrier to prevent mesh foldovers/inversions | M2 | ORIGINAL_REQUEST.md §2.4 |
| 8 | Keyform Tensor Generation | Discrete vertex displacement buffers (ΔV) for 3x3 grid (Angle X × Angle Y) and Angle Z | M2 | ORIGINAL_REQUEST.md §2.5 |
| 9 | Rigorous Deformation Tests | Test suite in `tests/test_deformation.py` verifying SO(3) algebra, non-inversion, parallax, and ARAP | M2 | ORIGINAL_REQUEST.md §2.6 |

## Milestones & Interfaces
- Inputs from M1: `LayerMesh` / `PSDStructure` with vertices (V_2D, 2), triangles (F, 3), layer categories (Face, HairFront, HairBack, Eye, Nose, Mouth, Torso, etc.).
- Outputs of M2:
  - `DepthMap` / Depth assignments per vertex (V_3D, 3).
  - `GeometryProperties` (normals, tangents, curvature).
  - `DeformationResult` (deformed vertices for given yaw, pitch, roll).
  - `KeyformTable` / `DrawableKeyforms` containing displacement tensors ΔV for all standard Live2D parameter keyforms (ParamAngleX [-30, 0, 30], ParamAngleY [-30, 0, 30], ParamAngleZ [-30, 0, 30]).
