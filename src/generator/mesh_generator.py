"""
Pure-Python SciPy Delaunay Mesh Generator.
Zero C-extension compilation dependencies.
"""
from typing import List, Tuple, Optional, Set, Dict
import numpy as np
from scipy.spatial import Delaunay

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

from src.core.vertex import Vertex
from src.core.mesh import Mesh
from src.core.layer import LayerData


class MeshGenerator:
    """
    Generates a 2D/2.5D Delaunay mesh from silhouette contours or alpha masks
    using pure-Python SciPy Delaunay triangulation, Steiner internal grid sampling,
    exterior triangle filtering, and constrained boundary-pinned Laplacian smoothing.
    """

    @staticmethod
    def _point_polygon_test_pure_python(polygon: np.ndarray, point: Tuple[float, float]) -> float:
        """
        Pure-Python fallback for cv2.pointPolygonTest when OpenCV is not available.
        Returns:
            Positive distance if inside polygon.
            Negative distance if outside polygon.
            Zero if on the boundary.
        """
        px, py = float(point[0]), float(point[1])
        n = len(polygon)
        if n < 3:
            return -1.0

        inside = False
        min_dist_sq = float('inf')

        for i in range(n):
            x1, y1 = float(polygon[i, 0]), float(polygon[i, 1])
            x2, y2 = float(polygon[(i + 1) % n, 0]), float(polygon[(i + 1) % n, 1])

            # Ray casting test
            if ((y1 > py) != (y2 > py)):
                denom = y2 - y1
                if abs(denom) > 1e-12:
                    intersect_x = (x2 - x1) * (py - y1) / denom + x1
                    if px < intersect_x:
                        inside = not inside

            # Segment distance
            dx, dy = x2 - x1, y2 - y1
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq < 1e-12:
                dist_sq = (px - x1) ** 2 + (py - y1) ** 2
            else:
                t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / seg_len_sq))
                proj_x = x1 + t * dx
                proj_y = y1 + t * dy
                dist_sq = (px - proj_x) ** 2 + (py - proj_y) ** 2
            
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq

        min_dist = float(np.sqrt(min_dist_sq))
        return min_dist if inside else -min_dist

    @staticmethod
    def point_polygon_distance(polygon: np.ndarray, point: Tuple[float, float]) -> float:
        """
        Computes signed Euclidean distance from point to closed polygon.
        Positive: inside polygon. Negative: outside polygon.
        """
        if len(polygon) < 3:
            return -1.0
        if HAS_CV2:
            poly_cv = polygon.astype(np.float32).reshape((-1, 1, 2))
            return float(cv2.pointPolygonTest(poly_cv, (float(point[0]), float(point[1])), True))
        else:
            return MeshGenerator._point_polygon_test_pure_python(polygon, point)

    @staticmethod
    def _laplacian_smoothing(
        vertices: np.ndarray,
        triangles: np.ndarray,
        boundary_indices: Set[int],
        contour_pts: np.ndarray,
        iterations: int = 3,
        lambda_factor: float = 0.5,
        min_boundary_margin: float = 2.0
    ) -> np.ndarray:
        """
        Applies constrained Laplacian smoothing to interior vertices.
        Boundary vertices are strictly pinned to preserve silhouette geometry.
        """
        N = len(vertices)
        if N == 0 or len(triangles) == 0:
            return vertices

        # Build adjacency graph and vertex-to-triangles map
        adj: Dict[int, Set[int]] = {i: set() for i in range(N)}
        v2t: Dict[int, List[int]] = {i: [] for i in range(N)}
        for t_idx, tri in enumerate(triangles):
            i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
            adj[i0].add(i1)
            adj[i0].add(i2)
            adj[i1].add(i0)
            adj[i1].add(i2)
            adj[i2].add(i0)
            adj[i2].add(i1)
            v2t[i0].append(t_idx)
            v2t[i1].append(t_idx)
            v2t[i2].append(t_idx)

        smoothed = vertices.copy()
        for _ in range(iterations):
            new_pos = smoothed.copy()
            for i in range(N):
                if i not in boundary_indices and len(adj[i]) > 0:
                    neighbor_mean = np.mean(smoothed[list(adj[i])], axis=0)
                    candidate = (1.0 - lambda_factor) * smoothed[i] + lambda_factor * neighbor_mean
                    
                    # Verify candidate point remains comfortably inside the polygon
                    dist = MeshGenerator.point_polygon_distance(contour_pts, (candidate[0], candidate[1]))
                    if dist < min_boundary_margin:
                        continue

                    # Verify that EVERY incident triangle in v2t[i] has strictly positive signed area > 1e-6
                    valid_move = True
                    for tri_idx in v2t[i]:
                        tri = triangles[tri_idx]
                        p0 = candidate if tri[0] == i else smoothed[tri[0]]
                        p1 = candidate if tri[1] == i else smoothed[tri[1]]
                        p2 = candidate if tri[2] == i else smoothed[tri[2]]
                        v1 = p1 - p0
                        v2 = p2 - p0
                        area = 0.5 * (v1[0] * v2[1] - v1[1] * v2[0])
                        if area <= 1e-6:
                            valid_move = False
                            break

                    if valid_move:
                        new_pos[i] = candidate
            smoothed = new_pos

        return smoothed

    @classmethod
    def generate_mesh_from_contour(
        cls,
        contour_pts: np.ndarray,
        image_shape: Tuple[int, int],
        target_grid_size: int = 25,
        default_layer: str = "Head",
        smoothing_iterations: int = 3,
        feature_pts: Optional[np.ndarray] = None
    ) -> Mesh:
        """
        Generates a 2D triangular mesh bounded by contour_pts using pure-Python SciPy Delaunay.

        Args:
            contour_pts: (K, 2) array of boundary polygon vertices in pixel coordinates.
            image_shape: (height, width) of image layer.
            target_grid_size: Spacing for internal Steiner grid vertices in pixels.
            default_layer: Semantic layer name for created vertices.
            smoothing_iterations: Number of constrained Laplacian smoothing passes.
            feature_pts: Optional internal facial landmark points to include.

        Returns:
            Mesh: Initialized Mesh object with vertices, positive-oriented triangles, UVs, and edges.
        """
        height, width = image_shape
        contour_pts = np.asarray(contour_pts, dtype=np.float64).reshape(-1, 2)
        N_boundary = len(contour_pts)

        # Fallback to image bounding rectangle if invalid contour
        if N_boundary < 3:
            contour_pts = np.array([
                [0.0, 0.0],
                [float(width), 0.0],
                [float(width), float(height)],
                [0.0, float(height)]
            ], dtype=np.float64)
            N_boundary = 4

        # 1. Sample internal Steiner grid points
        grid_step = max(5, int(target_grid_size))
        x_min = max(0.0, float(np.min(contour_pts[:, 0])))
        x_max = min(float(width), float(np.max(contour_pts[:, 0])))
        y_min = max(0.0, float(np.min(contour_pts[:, 1])))
        y_max = min(float(height), float(np.max(contour_pts[:, 1])))

        # Minimum distance from boundary for Steiner points (prevents sliver triangles)
        min_margin = 0.4 * grid_step

        xs = np.arange(x_min + grid_step * 0.5, x_max, grid_step, dtype=np.float64)
        ys = np.arange(y_min + grid_step * 0.5, y_max, grid_step, dtype=np.float64)

        steiner_pts_list: List[np.ndarray] = []
        for x in xs:
            for y in ys:
                pt = (float(x), float(y))
                dist = cls.point_polygon_distance(contour_pts, pt)
                if dist >= min_margin:
                    steiner_pts_list.append(np.array([x, y], dtype=np.float64))

        # Include optional feature points if strictly inside
        if feature_pts is not None and len(feature_pts) > 0:
            for fp in feature_pts:
                pt = (float(fp[0]), float(fp[1]))
                dist = cls.point_polygon_distance(contour_pts, pt)
                if dist >= 1.0:
                    steiner_pts_list.append(np.array(pt, dtype=np.float64))

        # 2. Combine boundary and interior vertices
        boundary_pts = contour_pts.copy()
        if len(steiner_pts_list) > 0:
            steiner_pts = np.array(steiner_pts_list, dtype=np.float64)
            all_pts = np.vstack([boundary_pts, steiner_pts])
        else:
            all_pts = boundary_pts.copy()

        # Deduplicate points within small tolerance
        unique_pts: List[np.ndarray] = []
        for pt in all_pts:
            if not any(np.linalg.norm(pt - u) < 1e-4 for u in unique_pts):
                unique_pts.append(pt)
        all_pts = np.array(unique_pts, dtype=np.float64)

        if len(all_pts) < 3:
            return Mesh(layer_id=default_layer)

        # 3. Perform SciPy Delaunay Triangulation
        try:
            dt = Delaunay(all_pts)
            raw_simplices = dt.simplices
        except Exception:
            return Mesh(layer_id=default_layer)

        # 4. Strict exterior triangle filtering
        filtered_triangles: List[List[int]] = []
        for tri in raw_simplices:
            i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
            p0, p1, p2 = all_pts[i0], all_pts[i1], all_pts[i2]

            # Compute triangle centroid
            centroid = (p0 + p1 + p2) / 3.0
            dist_centroid = cls.point_polygon_distance(contour_pts, (centroid[0], centroid[1]))

            # Discard if centroid is outside polygon
            if dist_centroid < -1e-4:
                continue

            # Additional check: edge midpoints for triangles connecting boundary points
            if i0 < N_boundary and i1 < N_boundary and i2 < N_boundary:
                m01 = (p0 + p1) * 0.5
                m12 = (p1 + p2) * 0.5
                m20 = (p2 + p0) * 0.5
                if (cls.point_polygon_distance(contour_pts, (m01[0], m01[1])) < -1.0 or
                    cls.point_polygon_distance(contour_pts, (m12[0], m12[1])) < -1.0 or
                    cls.point_polygon_distance(contour_pts, (m20[0], m20[1])) < -1.0):
                    continue

            # Check signed area
            v1 = p1 - p0
            v2 = p2 - p0
            signed_area = 0.5 * (v1[0] * v2[1] - v1[1] * v2[0])

            # Discard degenerate zero-area triangles
            if abs(signed_area) < 1e-7:
                continue

            # Ensure positive signed area (counter-clockwise orientation)
            if signed_area < 0:
                filtered_triangles.append([i0, i2, i1])
            else:
                filtered_triangles.append([i0, i1, i2])

        if len(filtered_triangles) == 0:
            return Mesh(layer_id=default_layer)

        triangles_arr = np.array(filtered_triangles, dtype=np.int32)

        # 5. Constrained Laplacian smoothing (boundary vertices strictly pinned)
        boundary_indices = set(range(min(N_boundary, len(all_pts))))
        if smoothing_iterations > 0:
            smoothed_pts = cls._laplacian_smoothing(
                all_pts,
                triangles_arr,
                boundary_indices,
                contour_pts,
                iterations=smoothing_iterations,
                lambda_factor=0.5,
                min_boundary_margin=min_margin * 0.5
            )
        else:
            smoothed_pts = all_pts.copy()

        # Final winding and non-inversion check: recompute signed area for each triangle;
        # if any triangle is inverted (Area < 0), swap indices to make it CCW (Area > 0);
        # prune any degenerate triangle with |Area| <= 1e-7.
        valid_triangles: List[List[int]] = []
        for tri in triangles_arr:
            i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
            p0, p1, p2 = smoothed_pts[i0], smoothed_pts[i1], smoothed_pts[i2]
            v1 = p1 - p0
            v2 = p2 - p0
            signed_area = 0.5 * (v1[0] * v2[1] - v1[1] * v2[0])
            if abs(signed_area) <= 1e-7:
                continue
            if signed_area < 0:
                valid_triangles.append([i0, i2, i1])
            else:
                valid_triangles.append([i0, i1, i2])

        if len(valid_triangles) == 0:
            return Mesh(layer_id=default_layer)

        triangles_arr = np.array(valid_triangles, dtype=np.int32)

        # 6. Prune unreferenced vertices & reindex
        used_indices = sorted(list(set(triangles_arr.flatten())))
        index_map = {old_idx: new_idx for new_idx, old_idx in enumerate(used_indices)}
        
        reindexed_triangles = np.zeros_like(triangles_arr)
        for r in range(len(triangles_arr)):
            for c in range(3):
                reindexed_triangles[r, c] = index_map[triangles_arr[r, c]]

        final_pts = smoothed_pts[used_indices]

        # 7. Construct Vertex objects and UVs
        half_w = width / 2.0
        half_h = height / 2.0
        vertices: List[Vertex] = []
        uvs_list: List[np.ndarray] = []

        for i, pt in enumerate(final_pts):
            px, py = pt[0], pt[1]

            # Canvas normalized coordinates [-1.0, 1.0]
            nx = (px - half_w) / half_w if half_w > 0 else 0.0
            ny = (py - half_h) / half_h if half_h > 0 else 0.0

            # Normalized UV coordinates [0.0, 1.0]
            u = np.clip(px / float(width), 0.0, 1.0) if width > 0 else 0.0
            v = np.clip(py / float(height), 0.0, 1.0) if height > 0 else 0.0

            vtx = Vertex(
                position=np.array([nx, ny], dtype=np.float64),
                normal=np.array([0.0, 0.0, 1.0], dtype=np.float64),
                depth=0.0,
                stiffness=0.5,
                weight=1.0,
                layer_id=default_layer,
                index=i
            )
            vertices.append(vtx)
            uvs_list.append(np.array([u, v], dtype=np.float32))

        uvs = np.array(uvs_list, dtype=np.float32)
        if len(vertices) > 65535:
            raise ValueError(f"Generated mesh vertex count ({len(vertices)}) exceeds Live2D uint16 limit (65535). Increase grid_size.")
        mesh = Mesh(vertices=vertices, triangles=reindexed_triangles, uvs=uvs, layer_id=default_layer)
        return mesh

    @classmethod
    def generate_mesh_from_alpha_mask(
        cls,
        alpha_mask: np.ndarray,
        target_grid_size: int = 25,
        threshold: int = 10,
        simplify_eps: float = 2.0,
        default_layer: str = "Head"
    ) -> Mesh:
        """
        End-to-end generation from an alpha mask: extracts boundary contour and constructs mesh.
        """
        from src.importer.image_importer import ImageImporter
        contour = ImageImporter.extract_contour(alpha_mask, threshold=threshold, simplify_eps=simplify_eps)
        return cls.generate_mesh_from_contour(
            contour_pts=contour,
            image_shape=alpha_mask.shape[:2],
            target_grid_size=target_grid_size,
            default_layer=default_layer
        )

    @classmethod
    def generate_mesh_from_layer(
        cls,
        layer: LayerData,
        target_grid_size: int = 25,
        threshold: int = 10,
        simplify_eps: float = 2.0
    ) -> Mesh:
        """
        Constructs a Mesh directly from a LayerData instance.
        """
        return cls.generate_mesh_from_alpha_mask(
            alpha_mask=layer.alpha_mask,
            target_grid_size=target_grid_size,
            threshold=threshold,
            simplify_eps=simplify_eps,
            default_layer=layer.name
        )

    @staticmethod
    def generate_warp_grid(
        grid_rows: int = 4,
        grid_cols: int = 4,
        bounds: Tuple[float, float, float, float] = (-1.0, -1.0, 1.0, 1.0)
    ) -> np.ndarray:
        """
        Generates a 2D regular grid of vertices for a Live2D Warp Deformer.
        Returns:
            ( (grid_rows + 1) * (grid_cols + 1), 2 ) ndarray in row-major order.
        """
        min_x, min_y, max_x, max_y = bounds
        xs = np.linspace(min_x, max_x, grid_cols + 1, dtype=np.float32)
        ys = np.linspace(min_y, max_y, grid_rows + 1, dtype=np.float32)
        grid_pts = []
        for y in ys:
            for x in xs:
                grid_pts.append([x, y])
        return np.array(grid_pts, dtype=np.float32)

