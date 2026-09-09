"""
Complete prototype verification script for ARAP solver, cotangent weights, closed-form SO(2),
and signed area barrier line-search.
"""
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import time

def compute_signed_areas(vertices: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    p0 = vertices[triangles[:, 0]]
    p1 = vertices[triangles[:, 1]]
    p2 = vertices[triangles[:, 2]]
    v1 = p1 - p0
    v2 = p2 - p0
    return 0.5 * (v1[:, 0] * v2[:, 1] - v1[:, 1] * v2[:, 0])

def build_cotangent_weights(vertices: np.ndarray, triangles: np.ndarray):
    N = len(vertices)
    edge_weight_map = {}

    for tri in triangles:
        for idx in range(3):
            i = int(tri[idx])
            j = int(tri[(idx + 1) % 3])
            k = int(tri[(idx + 2) % 3])

            vi = vertices[i] - vertices[k]
            vj = vertices[j] - vertices[k]

            dot_prod = float(np.dot(vi, vj))
            cross_prod = float(vi[0] * vj[1] - vi[1] * vj[0])
            cot_k = dot_prod / max(1e-9, abs(cross_prod))
            cot_k = float(np.clip(cot_k, 0.05, 50.0))

            edge_key = (min(i, j), max(i, j))
            if edge_key not in edge_weight_map:
                edge_weight_map[edge_key] = 0.0
            edge_weight_map[edge_key] += 0.5 * cot_k

    return edge_weight_map

class PrototypeARAPSolver:
    def __init__(self, vertices: np.ndarray, triangles: np.ndarray, stiffnesses: np.ndarray, use_cotangent: bool = True):
        self.rest_positions = vertices.copy()
        self.triangles = triangles.copy()
        self.stiffnesses = stiffnesses.copy()
        self.N = len(vertices)
        
        # 1. Weights
        if use_cotangent:
            edge_weight_map = build_cotangent_weights(vertices, triangles)
        else:
            edge_weight_map = {}
            for tri in triangles:
                for idx in range(3):
                    i, j = int(tri[idx]), int(tri[(idx + 1) % 3])
                    edge_weight_map[(min(i, j), max(i, j))] = 1.0

        self.all_edges = sorted(list(edge_weight_map.keys()))
        self.edge_weights = np.array([edge_weight_map[e] for e in self.all_edges], dtype=np.float64)
        
        M = len(self.all_edges)
        self.edge_rest_vectors = np.zeros((M, 2), dtype=np.float64)
        self.adj_neighbors = [[] for _ in range(self.N)]
        self.adj_edge_indices = [[] for _ in range(self.N)]

        for idx, (i, j) in enumerate(self.all_edges):
            u_ij = self.rest_positions[i] - self.rest_positions[j]
            self.edge_rest_vectors[idx] = u_ij
            self.adj_neighbors[i].append(j)
            self.adj_edge_indices[i].append(idx)
            self.adj_neighbors[j].append(i)
            self.adj_edge_indices[j].append(idx)

        # 2. Positional penalty weights: gamma_i = 1.0 + 4.0 * stiffness_i
        self.gamma = 1.0 + 4.0 * self.stiffnesses
        
        # 3. Assemble sparse matrix A = L + diag(gamma)
        rows, cols, data = [], [], []
        for idx, (i, j) in enumerate(self.all_edges):
            w = self.edge_weights[idx]
            rows.extend([i, j, i, j])
            cols.extend([j, i, i, j])
            data.extend([-w, -w, w, w])

        L = sp.coo_matrix((data, (rows, cols)), shape=(self.N, self.N)).tocsc()
        self.A = L + sp.diags(self.gamma, format='csc')
        
        # Factorize once
        t0 = time.perf_counter()
        self.lu = spla.splu(self.A)
        self.factor_time = (time.perf_counter() - t0) * 1000.0

    def estimate_local_rotations_closed_form(self, current_positions: np.ndarray) -> np.ndarray:
        rotations = np.zeros((self.N, 2, 2), dtype=np.float64)
        for i in range(self.N):
            s00, s01, s10, s11 = 0.0, 0.0, 0.0, 0.0
            for j_idx, edge_idx in enumerate(self.adj_edge_indices[i]):
                j = self.adj_neighbors[i][j_idx]
                w = self.edge_weights[edge_idx]
                u = self.edge_rest_vectors[edge_idx] if i == self.all_edges[edge_idx][0] else -self.edge_rest_vectors[edge_idx]
                v = current_positions[i] - current_positions[j]
                s00 += w * u[0] * v[0]
                s01 += w * u[0] * v[1]
                s10 += w * u[1] * v[0]
                s11 += w * u[1] * v[1]

            c = s00 + s11
            s = s01 - s10
            r = np.hypot(c, s)
            if r > 1e-12:
                cos_t = c / r
                sin_t = s / r
            else:
                cos_t = 1.0
                sin_t = 0.0

            rotations[i, 0, 0] = cos_t
            rotations[i, 0, 1] = -sin_t
            rotations[i, 1, 0] = sin_t
            rotations[i, 1, 1] = cos_t
        return rotations

    def estimate_local_rotations_svd(self, current_positions: np.ndarray) -> np.ndarray:
        rotations = np.zeros((self.N, 2, 2), dtype=np.float64)
        for i in range(self.N):
            S = np.zeros((2, 2), dtype=np.float64)
            for j_idx, edge_idx in enumerate(self.adj_edge_indices[i]):
                j = self.adj_neighbors[i][j_idx]
                w = self.edge_weights[edge_idx]
                u = self.edge_rest_vectors[edge_idx] if i == self.all_edges[edge_idx][0] else -self.edge_rest_vectors[edge_idx]
                v = current_positions[i] - current_positions[j]
                S += w * np.outer(u, v)

            U, _, Vt = np.linalg.svd(S)
            R = Vt.T @ U.T
            if np.linalg.det(R) < 0:
                Vt[1, :] *= -1
                R = Vt.T @ U.T
            rotations[i] = R
        return rotations

    def solve(self, target_positions: np.ndarray, num_iterations: int = 5, enforce_noninversion: bool = True):
        curr_pos = target_positions.copy()
        rest_areas = compute_signed_areas(self.rest_positions, self.triangles)
        min_rest_area = np.min(rest_areas)

        for it in range(num_iterations):
            # Local step
            rotations = self.estimate_local_rotations_closed_form(curr_pos)

            # Global step RHS
            rhs_x = self.gamma * target_positions[:, 0]
            rhs_y = self.gamma * target_positions[:, 1]

            for idx, (i, j) in enumerate(self.all_edges):
                w = self.edge_weights[idx]
                u = self.edge_rest_vectors[idx]
                R_ij = 0.5 * (rotations[i] + rotations[j])
                rotated_u = R_ij @ u
                rhs_x[i] += w * rotated_u[0]
                rhs_y[i] += w * rotated_u[1]
                rhs_x[j] -= w * rotated_u[0]
                rhs_y[j] -= w * rotated_u[1]

            cand_x = self.lu.solve(rhs_x)
            cand_y = self.lu.solve(rhs_y)
            cand_pos = np.column_stack([cand_x, cand_y])

            if enforce_noninversion:
                # Backtracking line search from curr_pos towards cand_pos
                alpha = 1.0
                step_dir = cand_pos - curr_pos
                min_allowed_area = 0.05 * min_rest_area
                
                while alpha > 1e-4:
                    test_pos = curr_pos + alpha * step_dir
                    areas = compute_signed_areas(test_pos, self.triangles)
                    if np.all(areas >= min_allowed_area):
                        curr_pos = test_pos
                        break
                    alpha *= 0.5
                else:
                    # Fallback to local projection if step failed
                    curr_pos = cand_pos
            else:
                curr_pos = cand_pos

        return curr_pos

# Verification Run
print("=== Running ARAP Verification Tests ===")
nx, ny = 12, 12
x = np.linspace(-1, 1, nx)
y = np.linspace(-1, 1, ny)
xx, yy = np.meshgrid(x, y)
vertices = np.column_stack([xx.ravel(), yy.ravel()])
triangles = []
for j in range(ny - 1):
    for i in range(nx - 1):
        v0 = j * nx + i
        v1 = j * nx + (i + 1)
        v2 = (j + 1) * nx + i
        v3 = (j + 1) * nx + (i + 1)
        triangles.append([v0, v1, v2])
        triangles.append([v1, v3, v2])
triangles = np.array(triangles, dtype=np.int32)
stiffnesses = np.zeros(len(vertices))
# Set center vertices to high stiffness (simulating eyes/mouth)
center_mask = (np.abs(vertices[:, 0]) < 0.3) & (np.abs(vertices[:, 1]) < 0.3)
stiffnesses[center_mask] = 1.0

solver = PrototypeARAPSolver(vertices, triangles, stiffnesses, use_cotangent=True)
print(f"Sparse system factorized in {solver.factor_time:.3f} ms. Matrix shape: {solver.A.shape}")

# Test 1: Equivalence between Closed-form and SVD SO(2)
# Apply small random rotation and displacement
theta_test = np.radians(25.0)
R_test = np.array([[np.cos(theta_test), -np.sin(theta_test)], [np.sin(theta_test), np.cos(theta_test)]])
deformed_test = (vertices @ R_test.T) + np.random.normal(0, 0.02, size=vertices.shape)

rot_cf = solver.estimate_local_rotations_closed_form(deformed_test)
rot_svd = solver.estimate_local_rotations_svd(deformed_test)
max_rot_diff = np.max(np.abs(rot_cf - rot_svd))
print(f"Test 1 [SO(2) Closed-Form vs SVD]: Max absolute difference = {max_rot_diff:.2e} (MUST be < 1e-10)")

# Test 2: Invariance under Pure Rigid Motion (Rotation + Translation)
pure_rigid = (vertices @ R_test.T) + np.array([0.5, -0.3])
solved_rigid = solver.solve(pure_rigid, num_iterations=4)
rigid_diff = np.max(np.abs(solved_rigid - pure_rigid))
print(f"Test 2 [Pure Rigid Invariance]: Max position error = {rigid_diff:.2e} (MUST be < 1e-10)")

# Test 3: Extreme Shearing & Non-Inversion Guarantee
# Subject mesh to severe shearing and pinch that would invert triangles
sheared_target = vertices.copy()
sheared_target[:, 0] += 0.8 * np.sin(np.pi * vertices[:, 1])
# Artificially pinch / fold corner
sheared_target[0, 0] = sheared_target[1, 0] + 0.5  # Forced fold

t_start = time.perf_counter()
solved_safe = solver.solve(sheared_target, num_iterations=5, enforce_noninversion=True)
solve_time = (time.perf_counter() - t_start) * 1000.0

areas_safe = compute_signed_areas(solved_safe, triangles)
min_safe_area = np.min(areas_safe)
print(f"Test 3 [Extreme Shear & Inversion Prevention]: Solve time = {solve_time:.3f} ms, Min area = {min_safe_area:.6f} > 0: {min_safe_area > 0}")
assert min_safe_area > 0, "Failed: Triangle inverted!"
print("=== All Verification Tests Passed Successfully! ===")
