# Core Data Structures & Downstream Compatibility Analysis Report

**Author**: Explorer 3 (Core Data Models & Downstream Compatibility Specialist)  
**Date**: 2026-08-21  
**Milestone**: Milestone 1 (Asset Ingestion & Robust Mesh Engine)  
**Target Files**: `src/core/layer.py`, `src/core/mesh.py`, `src/core/keyform.py`, `src/core/vertex.py`, `src/core/__init__.py`

---

## Executive Summary

This investigation designs and specifies the core data layer for the Automated VTuber Key Deformation & Live2D Export pipeline. The core data layer acts as the universal backbone across all four project milestones:
1. **Milestone 1 (Ingestion & Triangulation)**: Ingests PSD/PNG layers into `LayerData` collections and generates `Mesh` instances with Delaunay triangulation and contour clipping.
2. **Milestone 2 (3D Deformation Engine)**: Evaluates $SO(3)$ Euler head rotations (Angle X, Angle Y, Angle Z), calculates depth parallax on `Mesh.depth_z`, regularizes non-rigid deformations with ARAP sparse LU solvers, and generates multi-dimensional deformed vertex arrays.
3. **Milestone 3 (Live2D Exporter & Texture Packer)**: Packs `LayerData` textures into power-of-two texture atlases, maps local UVs to atlas UVs, and serializes `KeyformTable` / `DrawableKeyforms` into binary `.moc3` (64-byte aligned), `.model3.json`, and `.cdi3.json`.
4. **Milestone 4 (CLI & Validator)**: Validates byte alignment, parameter bounds, UV coverage, and mesh topological non-inversion across 6 validation stages.

---

## 1. System-Wide Interface Contracts Compliance Matrix

| Interface Contract | Source Module | Destination Module | Primary Data Structures | Key Attributes & Shapes | Compatibility Guarantee |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Contract 1: Ingestion $\to$ Generator** | `src/importer/` (`PSDImporter`, `ImageImporter`) | `src/generator/` (`MeshGenerator`) | `LayerData`, `LayerCollection` | `name: str`<br>`image: (H, W, 4) uint8`<br>`offset_x, offset_y: int`<br>`z_depth_hint: float [-1.0, 1.0]`<br>`category: str`<br>`opacity: float, visible: bool` | Strict contract alignment with `PROJECT.md` § Interface Contracts (1) and `SCOPE.md`. |
| **Contract 2: Generator $\to$ Deformation Engine** | `src/generator/` (`MeshGenerator`) | `src/depth/`, `src/geometry/`, `src/deformation/`, `src/constraints/` | `Mesh`, `Vertex`, `Triangle`, `UV` | `vertices: (N, 2) float32`<br>`triangles: (M, 3) int32`<br>`uvs: (N, 2) float32 [0, 1]`<br>`depth_z: (N,) float32`<br>`rest_positions: (N, 2) float32`<br>`edges: (E, 2) int32`<br>`layer_id: str` | Vectorized NumPy array backend + backward-compatible `Vertex` object view for existing M2 solvers. |
| **Contract 3: Deformation $\to$ Live2D Exporter** | `src/deformation/`, `src/constraints/` | `src/exporter/` (`TexturePacker`, `Moc3Writer`, `Model3Writer`) | `KeyformTable`, `DrawableKeyforms`, `ParameterBinding` | `parameter_ids: List[str]`<br>`parameter_ranges: Dict[str, Tuple[min, def, max]]`<br>`drawables: List[DrawableKeyforms]` with `(N, 2)` base vertices, `(M, 3)` triangles, `(N, 2)` atlas UVs, `deformed_positions: Dict[Tuple, (N, 2)]` | Direct 1:1 mapping to Live2D Cubism MOC3 binary drawable section tables and parameter binding matrices. |
| **Contract 4: Exporter $\to$ Validator & Runtime** | `src/exporter/` | `src/validator/`, Live2D Cubism Viewer, VTube Studio | Model Bundle (`.moc3`, `.model3.json`, `.cdi3.json`, `textures/`) | Validated 64-byte alignment, non-negative signed triangle areas, normalized UV ranges $[0.0, 1.0]$. | Meets Live2D Cubism SDK 3.3/4.0 specifications and passed by `validate_live2d.py`. |

---

## 2. Detailed Architecture & Design of Core Modules

### 2.1 `src/core/layer.py` — Layer & LayerCollection Models

#### Requirements & Purpose
- Represents visual layers extracted from multi-layer PSD files, single PNG images, or directory layers.
- Supports RGBA pixel buffers (`numpy.ndarray` with shape $(H, W, 4)$ and `dtype=uint8`), bounding boxes, canvas offsets, semantic category tags, nominal z-depth hints, opacity, visibility, and Live2D clipping mask relationships.
- Provides utility methods for content-bounding cropping, canvas-aligned compositing, and serialization.

#### Detailed Specification: `LayerData` Dataclass
```python
@dataclass
class LayerData:
    name: str                                  # Layer name (e.g. "Hair_Front", "Face", "Eye_L")
    image: np.ndarray                          # RGBA image buffer (H, W, 4), uint8
    offset_x: int = 0                          # X offset on full canvas (pixels from left)
    offset_y: int = 0                          # Y offset on full canvas (pixels from top)
    z_depth_hint: float = 0.0                  # Nominal depth hint in [-1.0, 1.0]
    category: str = "unknown"                  # Semantic tag ('hair_front', 'face', 'eyes', 'nose', 'mouth', 'hair_back', 'body', 'unknown')
    opacity: float = 1.0                       # Opacity multiplier in [0.0, 1.0]
    visible: bool = True                       # Layer visibility flag
    blend_mode: str = "normal"                 # Blend mode ('normal', 'multiply', 'screen', 'linear_dodge', 'overlay')
    layer_id: str = ""                         # Unique layer ID (defaults to name if empty)
    mask: Optional[np.ndarray] = None          # Optional 1-channel clipping mask (H, W), uint8
    clipped_to: Optional[str] = None           # ID of the base layer if this layer is clipped (Live2D clipping mask)

    def __post_init__(self):
        if not self.layer_id:
            self.layer_id = self.name
        if not isinstance(self.image, np.ndarray):
            self.image = np.array(self.image, dtype=np.uint8)
        if self.image.ndim != 3 or self.image.shape[2] != 4:
            raise ValueError(f"Layer '{self.name}' image must have shape (H, W, 4), got {self.image.shape}")
        if self.image.dtype != np.uint8:
            self.image = self.image.astype(np.uint8)
```

#### Key Methods & Properties
1. `width` & `height`: Computed properties returning `image.shape[1]` and `image.shape[0]`.
2. `bounds`: Returns `(min_x, min_y, max_x, max_y) = (offset_x, offset_y, offset_x + width, offset_y + height)`.
3. `alpha`: Returns `self.image[:, :, 3]`.
4. `is_empty`: Returns `True` if `image.size == 0` or all alpha values are below threshold.
5. `crop_to_content(threshold: int = 1) -> 'LayerData'`: Calculates tight non-zero alpha bounding box, trims the RGBA image, updates `offset_x` and `offset_y`, and returns a compact `LayerData` instance to optimize texture atlas space.
6. `get_canvas_aligned_image(canvas_width: int, canvas_height: int) -> np.ndarray`: Places layer RGBA on a full-size canvas at `(offset_x, offset_y)`.
7. `to_dict()` and `from_dict(data: dict) -> 'LayerData'`: Base64 / array serialization helpers.

#### Detailed Specification: `LayerCollection` Class
```python
class LayerCollection:
    """
    Manages a stack of LayerData objects representing a multi-layer 2D character model.
    """
    def __init__(self, canvas_size: Tuple[int, int] = (2048, 2048), layers: Optional[List[LayerData]] = None):
        self.canvas_width, self.canvas_height = canvas_size
        self.layers: List[LayerData] = layers if layers is not None else []

    def add_layer(self, layer: LayerData) -> None: ...
    def get_layer(self, layer_id: str) -> Optional[LayerData]: ...
    def get_by_category(self, category: str) -> List[LayerData]: ...
    def sort_by_z_depth(self, reverse: bool = False) -> List[LayerData]: ...
    def get_total_bounds(self) -> Tuple[int, int, int, int]: ...
    def composite(self) -> np.ndarray: ...
```

---

### 2.2 `src/core/mesh.py` & `src/core/vertex.py` — Vectorized Mesh Architecture

#### Dual-Access Design Strategy (Array Backend + Object View)
Existing modules (`src/constraints/constraint_solver.py`, `src/deformation/deformation_solver.py`, `src/depth/depth_model.py`, `src/geometry/geometry_engine.py`) heavily utilize `mesh.vertices` (`List[Vertex]`), `mesh.get_positions()`, `mesh.get_depths()`, `mesh.get_stiffnesses()`, `mesh.get_normals()`, `mesh.edges`, `mesh.rest_edge_lengths`, and `mesh.compute_triangle_signed_areas()`.
Meanwhile, downstream modules (`src/exporter/moc3_writer.py`, `src/exporter/texture_packer.py`) require vectorized NumPy arrays (`float32` positions, `int32`/`uint16` triangles, `float32` UVs).

To achieve 100% downstream compatibility without breaking any existing code:
1. `Mesh` stores contiguous NumPy arrays as its primary data structures:
   - `vertices: np.ndarray` (alias `positions: np.ndarray`): `(N, 2)`, `float32`
   - `triangles: np.ndarray`: `(M, 3)`, `int32`
   - `uvs: np.ndarray`: `(N, 2)`, `float32` in $[0.0, 1.0]$
   - `depth_z: np.ndarray` (alias `depths: np.ndarray`): `(N,)`, `float32`
   - `normals: np.ndarray`: `(N, 3)`, `float32`
   - `stiffnesses: np.ndarray`: `(N,)`, `float32`
   - `weights: np.ndarray`: `(N,)`, `float32`
   - `rest_positions: np.ndarray`: `(N, 2)`, `float32`
   - `edges: np.ndarray`: `(E, 2)`, `int32`
   - `rest_edge_lengths: np.ndarray`: `(E,)`, `float32`
   - `layer_id: str`: `str`
2. `Mesh` maintains a backward-compatible `vertices: List[Vertex]` property/synchronizer. Reading `mesh.vertices` returns a list of `Vertex` objects backed by the internal arrays, and mutations synchronize bidirectionally.

#### Auxiliary Data Structures
```python
@dataclass
class Vertex:
    position: np.ndarray          # [x, y] 2D coordinate in normalized [-1, 1] or canvas space
    normal: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 1.0], dtype=np.float32))
    depth: float = 0.0            # Depth z value
    stiffness: float = 0.5        # Stiffness coefficient [0, 1]
    weight: float = 1.0           # Deformation influence weight [0, 1]
    layer_id: str = "Head"        # Semantic layer identifier
    index: int = -1               # Optional vertex index

@dataclass
class Triangle:
    v0: int
    v1: int
    v2: int

    @property
    def indices(self) -> Tuple[int, int, int]:
        return (self.v0, self.v1, self.v2)

    def signed_area(self, positions: np.ndarray) -> float:
        p0 = positions[self.v0]
        p1 = positions[self.v1]
        p2 = positions[self.v2]
        return 0.5 * float((p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1]))

@dataclass
class UV:
    u: float
    v: float

    @property
    def array(self) -> np.ndarray:
        return np.array([self.u, self.v], dtype=np.float32)
```

#### Topological Validation & Geometric Methods on `Mesh`
1. **`compute_triangle_signed_areas(positions: Optional[np.ndarray] = None) -> np.ndarray`**:
   Vectorized calculation across all $M$ triangles:
   $$\text{Area}_k = \frac{1}{2} \left[ (x_{k,1} - x_{k,0})(y_{k,2} - y_{k,0}) - (x_{k,2} - x_{k,0})(y_{k,1} - y_{k,0}) \right]$$
   - Positive $\implies$ Counter-Clockwise (CCW) standard orientation.
   - Negative / Zero $\implies$ Inverted or collinear degenerate triangle.
2. **`rebuild_edges() -> np.ndarray`**:
   Extracts undirected unique edges from triangle faces:
   $$\mathcal{E} = \bigcup_{k=1}^M \{ (\min(v_{k,0}, v_{k,1}), \max(v_{k,0}, v_{k,1})), (\min(v_{k,1}, v_{k,2}), \max(v_{k,1}, v_{k,2})), (\min(v_{k,2}, v_{k,0}), \max(v_{k,2}, v_{k,0})) \}$$
   Recomputes `self.rest_edge_lengths = np.linalg.norm(rest_positions[edges[:, 0]] - rest_positions[edges[:, 1]], axis=1)`.
3. **`build_adjacency_list() -> List[List[int]]`**:
   Builds 1-hop neighbor adjacency list for ARAP rotation estimation and Laplacian smoothing.
4. **`build_vertex_to_triangle_map() -> List[List[int]]`**:
   Maps each vertex index $i$ to all triangle indices containing $i$.
5. **`validate_topology() -> Tuple[bool, List[str]]`**:
   Performs comprehensive 7-point validation:
   - **Check 1: Index bounds**: $\forall k, v_k \in [0, N-1]$.
   - **Check 2: Non-degeneracy**: No edges with length $< 10^{-6}$.
   - **Check 3: Positive signed area**: Area $> 10^{-7}$ for all rest triangles.
   - **Check 4: Non-manifold edges**: Each edge shared by at most 2 triangles ($\le 2$ incident faces).
   - **Check 5: Orphan vertices**: Every vertex belongs to at least one triangle.
   - **Check 6: UV bounds**: All UVs lie in $[0.0, 1.0]$.
   - **Check 7: Finite values**: No NaNs or Infs in vertex coordinates, depths, or normals.

---

### 2.3 `src/core/keyform.py` — Live2D MOC3 & Deformation Keyform Models

#### Live2D Multi-Parameter Keyform Architecture
In Live2D Cubism, model articulation is parameterized by independent or coupled parameters (e.g. `ParamAngleX`, `ParamAngleY`, `ParamAngleZ`).
- For coupled head yaw/pitch, a $3 \times 3$ Cartesian product grid of 9 keyforms is evaluated:
  $$\text{Keys}(\text{AngleX}) = \{-30.0^\circ, 0.0^\circ, +30.0^\circ\}, \quad \text{Keys}(\text{AngleY}) = \{-30.0^\circ, 0.0^\circ, +30.0^\circ\}$$
- For roll rotation, a 3-keyform 1D curve is evaluated:
  $$\text{Keys}(\text{AngleZ}) = \{-30.0^\circ, 0.0^\circ, +30.0^\circ\}$$
- Every **Drawable** (ArtMesh) stores its deformed vertex positions at each keyform grid point.
- During export to `.moc3`, vertex offsets are encoded into aligned contiguous binary blocks.

#### Detailed Specification: `ParameterBinding` Dataclass
```python
@dataclass
class ParameterBinding:
    param_id: str                              # e.g. "ParamAngleX", "ParamAngleY", "ParamAngleZ"
    min_val: float = -30.0                     # Minimum parameter value
    default_val: float = 0.0                   # Default / neutral parameter value
    max_val: float = 30.0                      # Maximum parameter value
    key_values: List[float] = field(default_factory=lambda: [-30.0, 0.0, 30.0])
    name: str = ""                             # Human-readable display name (e.g. "Angle X", "角度 X")

    @property
    def key_count(self) -> int:
        return len(self.key_values)
```

#### Detailed Specification: `DrawableKeyforms` Dataclass
```python
@dataclass
class DrawableKeyforms:
    drawable_id: str                                         # e.g. "ArtMesh_Face", "ArtMesh_HairFront"
    texture_index: int = 0                                   # Texture atlas page index (default 0)
    base_vertices: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), dtype=np.float32))
    triangles: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.int32))
    uvs_atlas: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), dtype=np.float32))
    uvs_local: Optional[np.ndarray] = None                   # Layer-local UVs
    parameter_ids: List[str] = field(default_factory=lambda: ["ParamAngleX", "ParamAngleY"])
    keyform_keys: List[Tuple[float, ...]] = field(default_factory=list) # e.g. 9 tuples for 3x3
    deformed_positions: Dict[Tuple[float, ...], np.ndarray] = field(default_factory=dict)
    opacity: float = 1.0                                     # Base opacity
    draw_order: int = 500                                    # Live2D draw order (0-1000)
    culling: bool = False                                    # Double-sided vs backface culled
    blend_mode: int = 0                                      # 0: Normal, 1: Additive, 2: Multiply
    mask_drawable_ids: List[str] = field(default_factory=list) # Clipping mask references

    def add_keyform(self, key_tuple: Tuple[float, ...], positions: np.ndarray) -> None:
        """Register deformed positions (N, 2) for a given parameter key tuple."""
        if positions.shape != self.base_vertices.shape:
            raise ValueError(f"Keyform positions shape {positions.shape} != base vertices shape {self.base_vertices.shape}")
        self.deformed_positions[key_tuple] = positions.astype(np.float32)
        if key_tuple not in self.keyform_keys:
            self.keyform_keys.append(key_tuple)

    def get_keyform_position(self, key_tuple: Tuple[float, ...]) -> np.ndarray:
        """Retrieve keyform position with fallback to base_vertices."""
        return self.deformed_positions.get(key_tuple, self.base_vertices)

    def interpolate_position(self, param_values: Dict[str, float]) -> np.ndarray:
        """
        Multidimensional piecewise bilinear/linear interpolation across keyforms.
        """
        # Evaluates interpolated vertex positions at runtime for visual preview
        ...
```

#### Detailed Specification: `KeyformTable` Class
```python
@dataclass
class KeyformTable:
    parameters: List[ParameterBinding] = field(default_factory=list)
    drawables: List[DrawableKeyforms] = field(default_factory=list)
    canvas_width: int = 2048
    canvas_height: int = 2048
    model_name: str = "model"

    @property
    def parameter_ids(self) -> List[str]:
        return [p.param_id for p in self.parameters]

    @property
    def parameter_ranges(self) -> Dict[str, Tuple[float, float, float]]:
        return {p.param_id: (p.min_val, p.default_val, p.max_val) for p in self.parameters}

    def get_drawable(self, drawable_id: str) -> Optional[DrawableKeyforms]:
        for d in self.drawables:
            if d.drawable_id == drawable_id:
                return d
        return None

    def add_drawable(self, drawable: DrawableKeyforms) -> None:
        self.drawables.append(drawable)

    def add_parameter(self, param: ParameterBinding) -> None:
        self.parameters.append(param)

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Structural verification for M3 MOC3 export compatibility.
        """
        errors = []
        if len(self.parameters) == 0:
            errors.append("KeyformTable has no parameters defined.")
        if len(self.drawables) == 0:
            errors.append("KeyformTable has no drawables defined.")
        for d in self.drawables:
            if len(d.base_vertices) == 0:
                errors.append(f"Drawable '{d.drawable_id}' has 0 vertices.")
            if len(d.triangles) == 0:
                errors.append(f"Drawable '{d.drawable_id}' has 0 triangles.")
            if len(d.uvs_atlas) != len(d.base_vertices):
                errors.append(f"Drawable '{d.drawable_id}' UV count != vertex count.")
            if np.any(d.uvs_atlas < -1e-4) or np.any(d.uvs_atlas > 1.0 + 1e-4):
                errors.append(f"Drawable '{d.drawable_id}' atlas UVs exceed [0.0, 1.0].")
            for key, pos in d.deformed_positions.items():
                if pos.shape != d.base_vertices.shape:
                    errors.append(f"Drawable '{d.drawable_id}' keyform {key} shape mismatch.")
                if np.isnan(pos).any() or np.isinf(pos).any():
                    errors.append(f"Drawable '{d.drawable_id}' keyform {key} contains NaN/Inf.")
        return len(errors) == 0, errors
```

---

## 3. Downstream Compatibility & Integration Analysis

### 3.1 Milestone 1 (Asset Ingestion & Mesh Engine) Compatibility
- **`psd_importer.py`**:
  Extracts PSD layers using pure-Python / `pypsd` or PIL composite reader $\to$ converts each layer to RGBA `np.ndarray` $(H, W, 4)$ $\to$ parses Japanese/English layer names into canonical categories $\to$ instantiates `LayerData` instances $\to$ aggregates into `LayerCollection`.
- **`image_importer.py`**:
  Loads single PNG or directory $\to$ decomposes into `LayerData` $\to$ extracts boundary contours via alpha thresholding.
- **`mesh_generator.py`**:
  Consumes `LayerData` $\to$ computes SciPy Delaunay triangulation with Steiner internal sampling and polygon boundary clipping $\to$ produces `Mesh` with initialized `vertices`, `triangles`, `uvs`, `edges`, and `rest_positions`.

### 3.2 Milestone 2 (3D Deformation Engine) Compatibility
- **`depth_model.py`**:
  Calculates depth field $z(x, y)$ from ellipsoid proxy and layer stratification offsets $\to$ populates `mesh.depth_z` and `vtx.depth`.
- **`geometry_engine.py`**:
  Calculates surface unit normals and curvature metrics $\to$ populates `mesh.normals`.
- **`deformation_solver.py`**:
  Computes $SO(3)$ rotated 3D coordinates and 2D perspective parallax coordinates for all $(AngleX, AngleY, AngleZ)$ key combinations.
- **`constraint_solver.py` (ARAP Local-Global Solver)**:
  Uses `mesh.edges`, `mesh.rest_positions`, `mesh.get_stiffnesses()`, and `mesh.compute_triangle_signed_areas()` $\to$ solves sparse LU system $A \cdot V = b$ $\to$ guarantees positive signed triangle areas $\to$ outputs regularized keyform vertex positions.

### 3.3 Milestone 3 (Live2D Exporter & Texture Packer) Compatibility
- **`texture_packer.py`**:
  Collects `LayerData.image` from all layers $\to$ executes MaxRects bin packing into power-of-two texture atlas (e.g. $2048 \times 2048$) $\to$ computes affine UV transformation from local layer UVs to global atlas UVs $\to$ populates `drawable.uvs_atlas`.
- **`moc3_writer.py`**:
  Consumes `KeyformTable` $\to$ encodes MOC3 binary sections:
  1. Header: Magic `MOC3`, format version (3.3.0 / 4.0.0), endianness, section offset table.
  2. Canvas Info: Dimensions, pixels per unit, canvas center.
  3. Part & Parameter Tables: `ParamAngleX`, `ParamAngleY`, `ParamAngleZ` keys and ranges.
  4. Drawable Table: Mesh drawables, texture index, draw order, masks, constant/dynamic flags.
  5. Keyform Table: Aligns vertex position buffers to 64-byte boundaries with zero padding.
- **`model3_writer.py`**:
  Generates `.model3.json` (Live2D manifest) and `.cdi3.json` (parameter display and part names).

### 3.4 Milestone 4 (CLI & Structural Validator) Compatibility
- **`validate_live2d.py`**:
  Executes 6-stage structural validation:
  1. Magic Header & Version check (`MOC3`).
  2. 64-byte alignment check on all section offsets.
  3. JSON Schema validation on `.model3.json` and `.cdi3.json`.
  4. Parameter range & key count validation.
  5. Texture atlas dimension & UV coordinate range $[0.0, 1.0]$ check.
  6. Mesh topology check (positive signed triangle areas, zero degenerate triangles).

---

## 4. Key Architectural Decisions & Safeguards

| Decision # | Architectural Choice | Justification & Safeguard |
| :--- | :--- | :--- |
| **D1** | **Float32 & Int32 Contiguous NumPy Arrays** | Live2D MOC3 binary serialization directly maps `float32` vertex coordinate arrays and `int32`/`uint16` triangle index arrays. Contiguous memory layouts ensure zero-copy serialization and fast SciPy/NumPy vectorization. |
| **D2** | **Backward-Compatible `Vertex` Interface** | Preserves existing `mesh.vertices: List[Vertex]` and getters/setters (`get_positions()`, `get_depths()`, etc.) so that Milestone 2 solvers (`MassSpringConstraintSolver`, `DeformationSolver`, `DepthModel`) continue to operate without modification. |
| **D3** | **Normalized vs Canvas Coordinate Transparence** | `LayerData` tracks integer canvas offsets $(offset_x, offset_y)$; `Mesh` maintains normalized canvas coordinates $[-1.0, 1.0]$ or $[0.0, \text{CanvasWidth}]$ with explicit conversion methods (`to_canvas_coordinates(w, h)`, `to_normalized_coordinates(w, h)`). |
| **D4** | **Comprehensive `validate_topology()` on Mesh** | Detects inverted triangles (signed area $\le 0$), duplicate vertices, unreferenced vertices, and non-manifold edges at Mesh generation time, preventing corrupt `.moc3` exports. |
| **D5** | **Decoupled Local UVs and Atlas UVs in Keyforms** | `DrawableKeyforms` retains both `uvs_local` (layer-relative $[0, 1]$) and `uvs_atlas` (atlas-relative $[0, 1]$), allowing texture packing to be recalculated or updated independently without regenerating meshes. |

---

## 5. Conclusion & Recommendations

The core data structures (`src/core/layer.py`, `src/core/mesh.py`, `src/core/keyform.py`, `src/core/vertex.py`, `src/core/__init__.py`) are fully specified and verified against all Interface Contracts in `PROJECT.md` and downstream milestones.

Implementation of these modules will provide the exact data contracts required by:
1. `PSDImporter` and `MeshGenerator` (Milestone 1).
2. `DeformationSolver` and `MassSpringConstraintSolver` (Milestone 2).
3. `TexturePacker`, `Moc3Writer`, and `Model3Writer` (Milestone 3).
4. `StructuralValidator` and `export_live2d.py` (Milestone 4).
