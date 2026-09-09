# Implementation Plan: Geometry-Driven Live2D / VTuber Model Deformation Prototype

## Scope & Goals

> [!IMPORTANT]
> **Prototype Purpose & Scope Boundaries**:
> - **Current Goal**: **Validation of the Mathematical Engine** (Depth Model → Geometry Engine → Deformation Solver → Mass-Spring Constraint Solver). This prototype is a proof-of-concept to verify that 2.5D head rotation ($\pm 30^\circ$ AngleX / AngleY) can be generated mathematically without manual keyform rigging.
> - **Future Goal (Next Stage, Out of Scope for MVP)**: The engine will eventually export generated vertex offsets/keyforms compatible with Live2D Cubism (`.moc3` / parameter keyforms), replacing manual vertex tweaking in standard Live2D pipelines.
> - **NOT in Scope for MVP**: Building a custom production rendering engine, motion tracking, replacing Cubism Editor, saving/loading full project files, or complex export pipelines.
> - **Definition of Done for MVP**: The mathematical engine passes all correctness unit tests (identity deformation, triangle non-inversion, unit normals, energy convergence, z-buffer depth occlusion) across 2-3 test character meshes. The GUI is minimal, serving only for visual inspection (AngleX/AngleY sliders and view mode toggle).

---

## Architecture & Module Structure

```
Importer ──► Mesh Generator ──► Depth Model ──► Geometry Engine ──► Deformation Solver ──► Mass-Spring Constraint Solver ──► Renderer
                                                                                                                          ▲
                                                                                                                       GUI Editor
```

```
VitubModel/
├── main.py                          # Application entry point (minimal GUI viewer)
├── requirements.txt                 # Project dependencies
├── README.md                        # Setup guide, architecture, Definition of Done
├── tests/                           # Unit tests for mathematical engine
│   ├── test_mesh_generator.py       # Triangulation & boundary tests
│   ├── test_geometry_engine.py      # Normals & depth projection tests
│   ├── test_deformation_solver.py   # Identity & 3D rotation parallax tests
│   ├── test_constraint_solver.py    # Energy monotonicity & non-inversion tests
│   └── test_renderer_occlusion.py   # Z-buffer occlusion correctness tests
└── src/
    ├── __init__.py
    ├── core/                        # Core data structures
    │   ├── vertex.py                # Vertex (position, normal, depth, stiffness, weight, layer_id)
    │   └── mesh.py                  # Mesh data structure (vertices, edges, triangles, region assignments)
    ├── importer/                    # Importer module
    │   └── image_importer.py        # PNG image loading, alpha channel processing, contour extraction
    ├── generator/                   # Mesh Generator module
    │   └── mesh_generator.py        # Constrained Delaunay 2D mesh generation
    ├── depth/                       # Depth Model module
    │   └── depth_model.py           # Ellipsoid heightmap projection & depth map brush tools
    ├── geometry/                    # Geometry Engine module
    │   └── geometry_engine.py       # Surface normals, tangents, local principal curvature calculation
    ├── deformation/                 # Deformation Solver module
    │   └── deformation_solver.py    # Keyframe-free 2.5D deformation solver (AngleX, AngleY)
    ├── constraints/                 # Constraint Solver module
    │   └── constraint_solver.py     # Mass-Spring Constraint Solver with cached sparse matrix factorization
    ├── ai/                          # AI Assistant module
    │   └── ai_assistant.py          # Auto depth map, normal extraction, auto segmentation & stiffness
    ├── renderer/                    # Renderer module
    │   └── renderer.py              # Hardware-accelerated textured mesh renderer with explicit Z-buffer depth test
    └── gui/                         # Minimal GUI Editor module
        ├── main_window.py           # PySide6 viewer window with AngleX/AngleY sliders
        ├── viewport.py              # Interactive 2D viewport canvas
        └── widgets/                 # Parameter sliders & view mode toggle
```

---

## Proposed Changes & Components

### 1. Core Data Structures (`src/core/`)

#### [NEW] [vertex.py](file:///d:/VitubModel/src/core/vertex.py)
Defines the `Vertex` dataclass:
```python
@dataclass
class Vertex:
    position: np.ndarray  # [x, y] in 2D space
    normal: np.ndarray    # [nx, ny, nz] 3D unit surface normal
    depth: float          # depth z in [0, 1] relative to head center
    stiffness: float      # resistance to deformation [0, 1]
    weight: float         # influence weight [0, 1]
    layer_id: str         # semantic region ID ('Head', 'Face', 'Hair', 'Eyes', 'Accessories')
```

#### [NEW] [mesh.py](file:///d:/VitubModel/src/core/mesh.py)
Manages mesh data (array of `Vertex`, triangle indices matrix $T \in \mathbb{Z}^{M \times 3}$, edge connectivity matrix, region metadata).

---

### 2. Importer & Mesh Generator (`src/importer/`, `src/generator/`)

#### [NEW] [image_importer.py](file:///d:/VitubModel/src/importer/image_importer.py)
Imports PNG images, extracts RGBA alpha masks, locates character silhouette boundary contours using OpenCV, and computes bounding boxes.

#### [NEW] [mesh_generator.py](file:///d:/VitubModel/src/generator/mesh_generator.py)
Generates 2D triangular mesh inside character contour using Delaunay triangulation with boundary preservation and resolution controls.

---

### 3. Depth Model & Geometry Engine (`src/depth/`, `src/geometry/`)

#### [NEW] [depth_model.py](file:///d:/VitubModel/src/depth/depth_model.py)
Provides ellipsoidal 3D depth field projection:
$$z(x, y) = Z_c + R_z \sqrt{\max\left(0, 1 - \left(\frac{x - X_c}{R_x}\right)^2 - \left(\frac{y - Y_c}{R_y}\right)^2\right)}$$
Supports heightmap brush edits for depth adjustment.

#### [NEW] [geometry_engine.py](file:///d:/VitubModel/src/geometry/geometry_engine.py)
Calculates local geometric properties for every vertex:
- 3D Position $\mathbf{P} = (x, y, z)$
- 3D Surface Unit Normal $\mathbf{N} = \text{normalize}\left(\frac{\partial z}{\partial x}, \frac{\partial z}{\partial y}, -1\right)$
- Tangent Vectors $\mathbf{T}_x, \mathbf{T}_y$
- Local Curvature fields (Gaussian & Mean curvature estimation via SciPy/NumPy finite differences)

---

### 4. Deformation & Mass-Spring Constraint Solvers (`src/deformation/`, `src/constraints/`)

#### [NEW] [deformation_solver.py](file:///d:/VitubModel/src/deformation/deformation_solver.py)
Calculates keyframe-free 2.5D vertex displacements given `AngleX` ($\theta_x$) and `AngleY` ($\theta_y$):
1. Applies 3D rotation matrix $\mathbf{R}_{yx}(\theta_x, \theta_y)$ around head center $\mathbf{C}$.
2. Computes rotated 3D position $\mathbf{P}' = \mathbf{R} \cdot (\mathbf{P} - \mathbf{C}) + \mathbf{C}$.
3. Projects $\mathbf{P}'$ to 2D view space with depth parallax:
   $$\mathbf{x}_{\text{proj}} = \mathbf{C}_{\text{2D}} + (\mathbf{P}'_{xy} - \mathbf{C}_{\text{2D}}) \cdot \left(1 + \kappa_{\text{parallax}} \cdot \frac{P'_z - Z_c}{R_z}\right)$$
4. Calculates local scaling, shear, and stretch matrices.

#### [NEW] [constraint_solver.py](file:///d:/VitubModel/src/constraints/constraint_solver.py)
**Mass-Spring Constraint Solver**:
- Formulated strictly as a spring-based energy system without local per-triangle rotation matrices or SVD steps:
  $$E(\mathbf{V}) = \sum_i S_i \|\mathbf{v}_i - \mathbf{x}_{i,\text{proj}}\|^2 + \lambda \sum_{(i,j) \in E} (1 - S_{ij}) \left(\|\mathbf{v}_i - \mathbf{v}_j\| - L_{ij}\right)^2$$
  where $L_{ij} = \|\mathbf{v}_i^{(0)} - \mathbf{v}_j^{(0)}\|$ is the initial rest edge length between connected vertices $i$ and $j$.
- **Cached Sparse Matrix Factorization**:
  Since mesh topology (vertices and edges) remains fixed between frames, the system matrix is factorized **once** (e.g. via `scipy.sparse.linalg.splu` or sparse Cholesky). During slider dragging, only the right-hand side (RHS) vector is updated and solved per frame, yielding real-time performance.
- Limits maximum stretch/compression and prevents triangle flipping / mesh inversion.

---

### 5. Renderer with Depth-Based Z-Buffer Occlusion (`src/renderer/`)

#### [NEW] [renderer.py](file:///d:/VitubModel/src/renderer/renderer.py)
**Depth-Based Occlusion via Z-Buffer**:
- Receives rotated 3D coordinates $(P'_x, P'_y, P'_z)$ computed by `Deformation Solver`.
- Passes $P'_z$ directly into the GPU rendering pipeline as an explicit depth component (`GL_DEPTH_TEST` enabled with depth buffer writing during triangle rasterization).
- Occlusion of overlapping features (e.g., far ear disappearing behind cheek contour during a $30^\circ$ turn) is handled automatically via per-pixel z-buffer depth testing, eliminating manual layer-id visibility rules.
- Supports rendering modes: Textured Model, Wireframe Mesh, Depth Map, Normals Visualization.

---

### 6. AI Helpers & Minimal GUI (`src/ai/`, `src/gui/`)

#### [NEW] [ai_assistant.py](file:///d:/VitubModel/src/ai/ai_assistant.py)
Helper AI module for auto depth map estimation, normal map derivation, edge-density stiffness mapping, and region segment heuristics.

#### [NEW] [main_window.py](file:///d:/VitubModel/src/gui/main_window.py) & [viewport.py](file:///d:/VitubModel/src/gui/viewport.py)
Minimal PySide6 GUI Viewer for MVP validation:
- Real-time `AngleX` slider ($-30^\circ \dots +30^\circ$)
- Real-time `AngleY` slider ($-30^\circ \dots +30^\circ$)
- View mode switcher ([Textured | Wireframe | Depth Map | Normals])
- Project save/export buttons marked as stubs (not required for MVP validation).

---

## Verification Plan

### Automated Tests (`tests/`)
1. **`test_mesh_generator.py`**: Verifies boundary contour mesh generation & non-overlapping valid triangles.
2. **`test_geometry_engine.py`**: Verifies surface normal vectors are unit length and ellipsoid depth matches parametric formulas.
3. **`test_deformation_solver.py`**: Verifies identity deformation at `AngleX=0, AngleY=0` and expected depth parallax shifts at `AngleX=30°`.
4. **`test_constraint_solver.py`**:
   - **Energy Monotonicity**: Verifies that for small $\Delta\theta$, system energy monotonically decreases and converges.
   - **Non-Inversion**: Verifies signed triangle areas remain positive (no flipped/inverted triangles).
5. **`test_renderer_occlusion.py`**:
   - **Z-Buffer Occlusion Correctness**: Tests that the renderer correctly occludes back geometry (e.g. far ear behind cheek silhouette) at `AngleX = 30°` by comparing rendered depth z-order against expected visibility.

### Minimal GUI Verification
- Run `python main.py` with test character meshes.
- Interactively move `AngleX` and `AngleY` sliders from $-30^\circ$ to $+30^\circ$.
- Visually confirm smooth 3D head rotation without keyframes, non-inverting triangles, correct z-buffer occlusion of far features, and real-time response.
