# Geometry-Driven Live2D / VTuber Model Deformation Prototype

A keyframe-free 2.5D head deformation software prototype for Live2D/VTuber models. 
Instead of manually tweaking vertex positions across parameter keyframes (AngleX, AngleY), model deformations are calculated automatically via a mathematical 3D proxy model (ellipsoid/heightmap), local normals, depth parallax, and a **Mass-Spring Constraint Solver**.

---

## 🎯 Scope & Definition of Done

> [!IMPORTANT]
> **MVP Stage Purpose**:
> - **Primary Goal**: Validation of the mathematical engine (Depth Model → Geometry Engine → Deformation Solver → Mass-Spring Constraint Solver).
> - **Future Stage (Out of Scope for MVP)**: Exporting keyforms / vertex offsets compatible with Live2D Cubism (`.moc3` / parameter keyforms).
> - **NOT in Scope**: Custom production renderer, motion tracking, replacing Cubism Editor, saving/loading full project files.
> - **Definition of Done**: The mathematical engine passes all correctness unit tests (identity deformation, non-inversion, unit normals, energy monotonicity, Z-buffer depth occlusion) on 2-3 test character meshes. The GUI is minimal, providing real-time `AngleX`/`AngleY` sliders and view mode switcher for visual inspection.

---

## 🏗️ Architecture

```
Importer ──► Mesh Generator ──► Depth Model ──► Geometry Engine ──► Deformation Solver ──► Mass-Spring Constraint Solver ──► Renderer
                                                                                                                          ▲
                                                                                                                       GUI Editor
```

### Module Responsibilities:
1. **Importer** (`src/importer/`): Imports PNG images, extracts RGBA alpha masks and silhouette boundary contours using OpenCV.
2. **Mesh Generator** (`src/generator/`): Generates 2D triangular meshes inside character contours using Delaunay triangulation.
3. **Depth Model** (`src/depth/`): Projects ellipsoidal 3D depth field $z(x,y)$ and provides heightmap brush painting.
4. **Geometry Engine** (`src/geometry/`): Calculates 3D surface unit normals $\mathbf{N} = (N_x, N_y, N_z)$, local tangents, and curvature fields.
5. **Deformation Solver** (`src/deformation/`): Computes 3D rotation $\mathbf{R}_{yx}(\theta_x, \theta_y)$ and 2.5D parallax projection for `AngleX` and `AngleY` ($\pm 30^\circ$).
6. **Mass-Spring Constraint Solver** (`src/constraints/`): Solves spring-based length constraints $L_{ij}$ with cached sparse matrix LU factorization (`scipy.sparse.linalg.splu`), preserving mesh smoothness and preventing triangle flipping.
7. **Renderer** (`src/renderer/`): Renders 2.5D textured meshes with explicit GPU Z-buffer depth testing (`GL_DEPTH_TEST`) for automatic per-pixel feature occlusion.
8. **AI Assistant** (`src/ai/`): Auto-estimates depth maps, normal fields, and edge-density stiffness maps.
9. **GUI Editor** (`src/gui/`): Desktop viewer (PySide6) with real-time sliders for `AngleX` and `AngleY`.

---

## 🚀 Installation & Running

### Requirements
- Python 3.10+
- Dependencies listed in `requirements.txt` (`numpy`, `scipy`, `opencv-python`, `PySide6`, `PyOpenGL`, `pillow`, `pytest`)

### Setup
```bash
pip install -r requirements.txt
```

### Run GUI Viewer
```bash
python main.py
```

### Run Automated Unit Tests
```bash
python -m pytest tests/
```
