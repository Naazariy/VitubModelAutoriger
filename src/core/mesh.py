import numpy as np
from typing import List, Tuple, Set, Optional, Dict
from src.core.vertex import Vertex, Triangle, UV

class Mesh:
    """
    Manages 2D/2.5D triangular mesh structure with dual-access NumPy arrays
    and synchronized Vertex object views.
    """
    def __init__(
        self,
        vertices: Optional[List[Vertex]] = None,
        triangles: Optional[np.ndarray] = None,
        uvs: Optional[np.ndarray] = None,
        layer_id: str = "Head"
    ):
        self.layer_id: str = layer_id
        self.vertices: List[Vertex] = vertices if vertices is not None else []
        self.triangles: np.ndarray = np.asarray(triangles, dtype=np.int32) if triangles is not None else np.zeros((0, 3), dtype=np.int32)
        self.uvs: np.ndarray = np.asarray(uvs, dtype=np.float32) if uvs is not None else np.zeros((0, 2), dtype=np.float32)
        
        self.edges: List[Tuple[int, int]] = []
        self.rest_edge_lengths: np.ndarray = np.array([], dtype=np.float64)
        self.rest_positions: np.ndarray = np.zeros((0, 2), dtype=np.float64)
        
        if len(self.vertices) > 0 and len(self.triangles) > 0:
            self.rebuild_edges()
        elif len(self.vertices) > 0:
            self.rest_positions = self.get_positions()

    @property
    def depth_z(self) -> np.ndarray:
        """Vectorized float32 depth array."""
        return self.get_depths().astype(np.float32)

    @depth_z.setter
    def depth_z(self, values: np.ndarray) -> None:
        self.set_depths(values)

    def rebuild_edges(self) -> None:
        """Build unique edges set and compute rest edge lengths."""
        edge_set: Set[Tuple[int, int]] = set()
        for tri in self.triangles:
            i, j, k = int(tri[0]), int(tri[1]), int(tri[2])
            for u, v in [(i, j), (j, k), (k, i)]:
                edge_set.add((min(u, v), max(u, v)))
        
        self.edges = sorted(list(edge_set))
        
        # Compute rest edge lengths
        positions = self.get_positions()
        self.rest_positions = positions.copy()
        
        if len(self.edges) > 0 and len(positions) > 0:
            edges_arr = np.array(self.edges, dtype=np.int32)
            p0 = positions[edges_arr[:, 0]]
            p1 = positions[edges_arr[:, 1]]
            self.rest_edge_lengths = np.linalg.norm(p0 - p1, axis=1).astype(np.float64)
        else:
            self.rest_edge_lengths = np.array([], dtype=np.float64)

    def get_positions(self) -> np.ndarray:
        """Returns (N, 2) position matrix in float64."""
        if len(self.vertices) == 0:
            return np.zeros((0, 2), dtype=np.float64)
        return np.array([v.position for v in self.vertices], dtype=np.float64)

    def set_positions(self, positions: np.ndarray) -> None:
        """Updates vertex positions from (N, 2) position matrix."""
        pos_arr = np.asarray(positions, dtype=np.float64)
        for idx, v in enumerate(self.vertices):
            if idx < len(pos_arr):
                v.position = pos_arr[idx].copy()

    def get_normals(self) -> np.ndarray:
        """Returns (N, 3) normal matrix in float64."""
        if len(self.vertices) == 0:
            return np.zeros((0, 3), dtype=np.float64)
        return np.array([v.normal for v in self.vertices], dtype=np.float64)

    def set_normals(self, normals: np.ndarray) -> None:
        """Updates vertex normals from (N, 3) normal matrix."""
        norm_arr = np.asarray(normals, dtype=np.float64)
        for idx, v in enumerate(self.vertices):
            if idx < len(norm_arr):
                v.normal = norm_arr[idx].copy()

    def get_depths(self) -> np.ndarray:
        """Returns (N,) depth array in float64."""
        if len(self.vertices) == 0:
            return np.array([], dtype=np.float64)
        return np.array([v.depth for v in self.vertices], dtype=np.float64)

    def set_depths(self, depths: np.ndarray) -> None:
        """Updates vertex depth values from (N,) array."""
        depth_arr = np.asarray(depths, dtype=np.float64).ravel()
        for idx, v in enumerate(self.vertices):
            if idx < len(depth_arr):
                v.depth = float(depth_arr[idx])

    def get_stiffnesses(self) -> np.ndarray:
        """Returns (N,) stiffness array in float64."""
        if len(self.vertices) == 0:
            return np.array([], dtype=np.float64)
        return np.array([v.stiffness for v in self.vertices], dtype=np.float64)

    def set_stiffnesses(self, stiffnesses: np.ndarray) -> None:
        """Updates vertex stiffness values from (N,) array."""
        stiff_arr = np.asarray(stiffnesses, dtype=np.float64).ravel()
        for idx, v in enumerate(self.vertices):
            if idx < len(stiff_arr):
                v.stiffness = float(stiff_arr[idx])

    def get_weights(self) -> np.ndarray:
        """Returns (N,) weight array in float64."""
        if len(self.vertices) == 0:
            return np.array([], dtype=np.float64)
        return np.array([v.weight for v in self.vertices], dtype=np.float64)

    def compute_triangle_signed_areas(self, positions: Optional[np.ndarray] = None) -> np.ndarray:
        """
        Computes signed area for all triangles.
        Positive indicates Counter-Clockwise (CCW) winding.
        """
        if len(self.triangles) == 0:
            return np.array([], dtype=np.float64)
        pos = positions if positions is not None else self.get_positions()
        if len(pos) == 0:
            return np.array([], dtype=np.float64)
        p0 = pos[self.triangles[:, 0]]
        p1 = pos[self.triangles[:, 1]]
        p2 = pos[self.triangles[:, 2]]
        
        # Signed area = 0.5 * ((x1 - x0)*(y2 - y0) - (x2 - x0)*(y1 - y0))
        v1 = p1 - p0
        v2 = p2 - p0
        signed_areas = 0.5 * (v1[:, 0] * v2[:, 1] - v1[:, 1] * v2[:, 0])
        return signed_areas.astype(np.float64)

    def build_adjacency_list(self) -> Dict[int, Set[int]]:
        """Builds 1-ring vertex neighbor adjacency list."""
        adj: Dict[int, Set[int]] = {i: set() for i in range(len(self.vertices))}
        for u, v in self.edges:
            adj[u].add(v)
            adj[v].add(u)
        return adj

    def build_vertex_to_triangle_map(self) -> Dict[int, List[int]]:
        """Maps each vertex index to triangle indices containing it."""
        v2t: Dict[int, List[int]] = {i: [] for i in range(len(self.vertices))}
        for t_idx, tri in enumerate(self.triangles):
            for v in tri:
                v2t[int(v)].append(t_idx)
        return v2t

    def validate_topology(self) -> Tuple[bool, List[str]]:
        """
        Validates topological integrity of the mesh.
        Checks:
        1. Valid index bounds
        2. Non-zero area & positive signed area in rest pose
        3. No degenerate edges
        4. UV coordinate validity in [0.0, 1.0]
        5. No NaNs or Infs
        6. No unreferenced vertices
        """
        errors: List[str] = []
        n_verts = len(self.vertices)
        n_tris = len(self.triangles)

        if n_verts == 0 and n_tris == 0:
            return True, []

        if n_tris > 0 and n_verts < 3:
            errors.append(f"Mesh has {n_tris} triangles but only {n_verts} vertices.")

        # Check 1: Index bounds
        if n_tris > 0:
            min_idx = np.min(self.triangles)
            max_idx = np.max(self.triangles)
            if min_idx < 0 or max_idx >= n_verts:
                errors.append(f"Triangle indices [{min_idx}, {max_idx}] exceed vertex range [0, {n_verts-1}].")

        # Check 2: Signed areas
        if n_tris > 0:
            areas = self.compute_triangle_signed_areas()
            if np.any(np.isnan(areas)):
                errors.append("Signed triangle areas contain NaNs.")
            elif np.any(areas <= 1e-7):
                n_inverted = int(np.sum(areas <= 1e-7))
                errors.append(f"Found {n_inverted}/{n_tris} non-positive or degenerate triangles (min area: {np.min(areas):.2e}).")

        # Check 3: Degenerate edge lengths
        if len(self.rest_edge_lengths) > 0:
            if np.any(self.rest_edge_lengths < 1e-6):
                n_zero_edges = int(np.sum(self.rest_edge_lengths < 1e-6))
                errors.append(f"Found {n_zero_edges} degenerate edges with rest length < 1e-6.")

        # Check 4: UV bounds
        if len(self.uvs) > 0:
            if len(self.uvs) != n_verts:
                errors.append(f"UV count ({len(self.uvs)}) != vertex count ({n_verts}).")
            if np.any(self.uvs < -1e-4) or np.any(self.uvs > 1.0 + 1e-4):
                errors.append("UV coordinates outside [0.0, 1.0] range.")

        # Check 5: NaN / Inf checks
        pos = self.get_positions()
        if np.any(np.isnan(pos)) or np.any(np.isinf(pos)):
            errors.append("Vertex positions contain NaN or Inf values.")

        # Check 6: Unreferenced vertices
        if n_tris > 0:
            referenced = set(self.triangles.flatten())
            if len(referenced) < n_verts:
                orphans = n_verts - len(referenced)
                errors.append(f"Found {orphans} orphaned / unreferenced vertices.")

        return len(errors) == 0, errors

    def to_canvas_coordinates(self, canvas_width: int, canvas_height: int) -> np.ndarray:
        """Converts normalized [-1.0, 1.0] positions to canvas pixel coordinates."""
        pos = self.get_positions()
        px = (pos[:, 0] + 1.0) * 0.5 * canvas_width
        py = (pos[:, 1] + 1.0) * 0.5 * canvas_height
        return np.column_stack([px, py])

    def to_normalized_coordinates(self, canvas_width: int, canvas_height: int) -> np.ndarray:
        """Converts canvas pixel coordinates to normalized [-1.0, 1.0] space."""
        pos = self.get_positions()
        nx = (pos[:, 0] / (canvas_width * 0.5)) - 1.0
        ny = (pos[:, 1] / (canvas_height * 0.5)) - 1.0
        return np.column_stack([nx, ny])

    def copy(self) -> 'Mesh':
        new_vertices = [v.copy() for v in self.vertices]
        new_triangles = self.triangles.copy()
        new_uvs = self.uvs.copy()
        new_mesh = Mesh(new_vertices, new_triangles, new_uvs, layer_id=self.layer_id)
        new_mesh.edges = list(self.edges)
        new_mesh.rest_edge_lengths = self.rest_edge_lengths.copy()
        new_mesh.rest_positions = self.rest_positions.copy()
        return new_mesh

