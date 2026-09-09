# Milestone 1 Handoff: Core Data Models & Downstream Compatibility

**Agent**: Explorer 3 (Core Data Models & Downstream Compatibility Specialist)  
**Date**: 2026-08-21  
**Working Directory**: `d:\VitubModel\.agents\explorer_m1_3`  
**Handoff Type**: Hard (Task Complete)  

---

## 1. Observation

### 1.1 Existing Codebase State
1. **Existing Core Modules**:
   - `src/core/vertex.py` (Lines 1–25): Defines `@dataclass class Vertex` containing `position: np.ndarray`, `normal: np.ndarray`, `depth: float`, `stiffness: float`, `weight: float`, `layer_id: str`.
   - `src/core/mesh.py` (Lines 1–88): Defines `class Mesh` holding `vertices: List[Vertex]`, `triangles: np.ndarray` $(M, 3)$, `uvs: np.ndarray` $(N, 2)$, `edges: List[Tuple[int, int]]`, `rest_edge_lengths: np.ndarray`. Implements `get_positions()`, `set_positions()`, `get_normals()`, `get_depths()`, `get_stiffnesses()`, and `compute_triangle_signed_areas()`.
   - `src/core/layer.py`: Currently missing.
   - `src/core/keyform.py`: Currently missing.
   - `src/core/__init__.py` (Lines 1–6): Imports only `Vertex` and `Mesh`.

2. **Downstream Solvers & Consumers**:
   - `src/constraints/constraint_solver.py` (Lines 77–104, 131–158): Directly queries `mesh.edges`, `mesh.triangles`, `mesh.get_stiffnesses()`, and `mesh.get_positions()`.
   - `src/deformation/deformation_solver.py` (Lines 74–93): Iterates over `mesh.vertices` accessing `vtx.position`, `vtx.depth`, and `vtx.layer_id`.
   - `src/depth/depth_model.py` (Lines 53–68): Iterates over `mesh.vertices` mutating `vtx.depth`.
   - `src/geometry/geometry_engine.py` (Lines 20–41, 64–77): Reads `vtx.position`, `vtx.depth`, assigns `vtx.normal`, and iterates over `mesh.edges`.
   - `src/renderer/renderer.py` (Lines 146–189): Reads `mesh.get_stiffnesses()`, `mesh.get_normals()`, `mesh.uvs`, and `mesh.triangles`.

3. **Project Specifications**:
   - `PROJECT.md` § Interface Contracts (Lines 142–168) explicitly specifies:
     - Contract 1: `LayerData` with `name`, `image` $(H, W, 4)$ uint8, `offset_x`, `offset_y`, `z_depth_hint`, `category`.
     - Contract 2: `Mesh` with `vertices` $(N, 2)$ float32, `triangles` $(M, 3)$ int32, `uvs` $(N, 2)$ float32, `depth_z` $(N,)$ float32, `layer_id`, `rest_positions` $(N, 2)$, `edges` $(E, 2)$.
     - Contract 3: `KeyformTable` and `DrawableKeyforms` with `parameter_ids`, `parameter_ranges`, `drawable_id`, `texture_index`, `base_vertices`, `triangles`, `uvs_atlas`, `deformed_positions` Dict[Tuple, $(N, 2)$].
   - `SCOPE.md` (Lines 40–61): Specifies exact layer fields, category strings (`hair_front`, `face`, `eyes`, `nose`, `mouth`, `hair_back`, `body`, `unknown`), and mesh properties.

4. **Environment Check**:
   - Running `python -m pip list` confirmed: `numpy 2.5.1`, `scipy 1.18.0`, `pillow 12.3.0`, `pytest 9.1.1`, `PySide6_Essentials 6.11.1`, `PyOpenGL 3.1.10`.
   - `triangle` C-extension is not installed, reinforcing `PROJECT.md` requirement F03 for pure-Python / SciPy triangulation.

---

## 2. Logic Chain

1. **Dual-Access Core Mesh Requirement**:
   - *Observation 1.2* shows that existing M2 solvers (`DeformationSolver`, `DepthModel`, `GeometryEngine`) iterate over `mesh.vertices: List[Vertex]`.
   - *Observation 1.3* shows that `PROJECT.md` Contract 2 and M3 binary MOC3 serialization require contiguous NumPy arrays (`float32` vertices, `int32` triangles, `float32` UVs, `float32` depths, `int32` edges).
   - *Inference*: `Mesh` in `src/core/mesh.py` must support both vectorized NumPy array backends and synchronized `Vertex` object access to guarantee 100% downstream compatibility with zero solver refactoring needed.

2. **Topological Validation Requirement**:
   - *Observation 1.1 & 1.3* note that Live2D MOC3 binary runtime crashes if any triangle has inverted or zero signed area, or if UVs exceed $[0.0, 1.0]$.
   - *Inference*: `Mesh` must implement `compute_triangle_signed_areas()`, `rebuild_edges()`, `build_adjacency_list()`, `build_vertex_to_triangle_map()`, and `validate_topology()`.

3. **Layer Abstraction Requirement**:
   - *Observation 1.1* shows `src/core/layer.py` is absent, while `PROJECT.md` Contract 1 requires `LayerData` to bridge `src/importer/` and `src/generator/`.
   - *Inference*: `src/core/layer.py` must define `LayerData` and `LayerCollection` supporting RGBA numpy arrays, bounding box calculation, canvas offsets, semantic categories, nominal z-depth hints, opacity, visibility, and Live2D clipping mask relationships (`clipped_to`, `mask`).

4. **Keyform Data Architecture Requirement**:
   - *Observation 1.1 & 1.3* show `src/core/keyform.py` is absent, while `PROJECT.md` Contract 3 requires `KeyformTable` and `DrawableKeyforms` to bridge M2 (Deformation Engine) and M3 (Live2D Exporter).
   - *Inference*: `src/core/keyform.py` must define `ParameterBinding`, `DrawableKeyforms`, and `KeyformTable` with support for multi-parameter Cartesian grids (e.g. $3 \times 3$ for Angle X / Angle Y), discrete keyform displacement dictionaries, atlas UV mappings, and serialization methods.

---

## 3. Caveats

1. **Coordinate Frame Conventions**:
   - Canvas coordinate space has $(0, 0)$ at the top-left pixel.
   - Normalized coordinate space uses $[-1.0, 1.0]$ with $(0, 0)$ at center.
   - Live2D MOC3 standard units are centered at canvas origin. Coordinate conversion helper methods must be consistently applied during export.
2. **Read-Only Investigation Scope**:
   - In accordance with the explorer role, no code files in `src/` or `tests/` were directly modified. Complete proposed file designs are provided in `analysis.md` for implementation by the Builder agent.

---

## 4. Conclusion

1. The specifications for `src/core/layer.py`, `src/core/mesh.py`, `src/core/keyform.py`, `src/core/vertex.py`, and `src/core/__init__.py` have been designed in full detail.
2. All data structures strictly satisfy `PROJECT.md` § Interface Contracts 1, 2, 3, and 4.
3. The proposed dual-access architecture for `Mesh` ensures zero breakage for Milestone 2 solvers while providing high-performance vectorized buffers for Milestone 3 MOC3 binary serialization and texture packing.

---

## 5. Verification Method

To independently verify the core data model designs once implemented:

1. **Unit Test Verification**:
   Execute the test suite using Python:
   ```powershell
   python -m pytest tests/test_mesh_generator.py tests/test_deformation_solver.py tests/test_constraint_solver.py -v
   ```
2. **Topology & Inversion Check**:
   Instantiate `Mesh` from synthetic head contour and verify:
   ```python
   mesh = MeshGenerator.generate_mesh_from_contour(...)
   is_valid, errors = mesh.validate_topology()
   assert is_valid, f"Topology errors: {errors}"
   areas = mesh.compute_triangle_signed_areas()
   assert np.all(areas > 0.0), "All rest triangles must have positive signed area"
   ```
3. **Keyform Table Validation**:
   Instantiate `KeyformTable`, populate 9 keyforms for `ParamAngleX` $\times$ `ParamAngleY`, and verify:
   ```python
   is_valid, errors = keyform_table.validate()
   assert is_valid, f"KeyformTable validation failed: {errors}"
   ```
4. **Invalidation Conditions**:
   - Any negative signed triangle area in neutral/rest pose.
   - Mismatch between `DrawableKeyforms` vertex count and base vertex count.
   - Failure of `tests/test_deformation_solver.py` or `tests/test_constraint_solver.py`.
