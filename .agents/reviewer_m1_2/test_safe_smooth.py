import sys
sys.path.insert(0, 'd:/VitubModel')
import numpy as np
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator

def local_signed_area(p0, p1, p2):
    v1 = p1 - p0
    v2 = p2 - p0
    return 0.5 * (v1[0] * v2[1] - v1[1] * v2[0])

def safe_laplacian_smoothing(vertices, triangles, boundary_indices, contour_pts, iterations=3, lambda_factor=0.5, min_boundary_margin=2.0):
    N = len(vertices)
    if N == 0 or len(triangles) == 0:
        return vertices

    adj = {i: set() for i in range(N)}
    for tri in triangles:
        for i in range(3):
            u = int(tri[i])
            v = int(tri[(i + 1) % 3])
            adj[u].add(v)
            adj[v].add(u)

    v2t = {i: [] for i in range(N)}
    for t_idx, tri in enumerate(triangles):
        for v in tri:
            v2t[int(v)].append(t_idx)

    smoothed = vertices.copy()
    for _ in range(iterations):
        new_pos = smoothed.copy()
        for i in range(N):
            if i not in boundary_indices and len(adj[i]) > 0:
                neighbor_mean = np.mean(smoothed[list(adj[i])], axis=0)
                candidate = (1.0 - lambda_factor) * smoothed[i] + lambda_factor * neighbor_mean
                
                dist = MeshGenerator.point_polygon_distance(contour_pts, (candidate[0], candidate[1]))
                if dist < min_boundary_margin:
                    continue

                # Check all incident triangles to ensure none are inverted
                inverted = False
                for t_idx in v2t[i]:
                    tri = triangles[t_idx]
                    pts = [candidate if v == i else smoothed[v] for v in tri]
                    area = local_signed_area(pts[0], pts[1], pts[2])
                    if area <= 1e-6:
                        inverted = True
                        break
                
                if not inverted:
                    new_pos[i] = candidate
        smoothed = new_pos
    return smoothed

layers = ImageImporter.create_synthetic_layered_head(512, 512)

for grid_size in [10, 15, 20, 25, 30]:
    failures = 0
    for l in layers:
        contour = ImageImporter.extract_contour(l.alpha_mask, threshold=10, simplify_eps=2.0)
        # test with custom smoothed function
        # run raw pipeline
        h, w = l.alpha_mask.shape[:2]
        # Test if safe_laplacian_smoothing fixes all
        # Let us temporarily monkeypatch MeshGenerator._laplacian_smoothing
        orig_smooth = MeshGenerator._laplacian_smoothing
        MeshGenerator._laplacian_smoothing = staticmethod(safe_laplacian_smoothing)
        m = MeshGenerator.generate_mesh_from_layer(l, target_grid_size=grid_size)
        valid, errors = m.validate_topology()
        if not valid:
            failures += 1
            print(f'Failed {l.name}: {errors}')
        MeshGenerator._laplacian_smoothing = orig_smooth

    print(f'Safe Laplacian on Grid size {grid_size}: {failures}/{len(layers)} failures.')
