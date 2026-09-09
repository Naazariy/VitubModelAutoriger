# Milestone 2 Explorer 3 Handoff Report: ARAP Constraint Solver & Positive Signed Area Barrier

**Agent**: Explorer 3 (ARAP & Constraint Solver Specialist)  
**Parent Conversation ID**: `863374ff-82a7-481b-9e77-519ebc423917`  
**Milestone**: Milestone 2 (Automated 3D Head Deformation Engine)  
**Date**: 2026-08-21T18:45:00Z  
**Status**: **COMPLETED (PASS)**  
**Target Modules**: `src/constraints/constraint_solver.py`, `tests/test_deformation.py`

---

## 1. Observation

1. **Current Codebase & Test Failures**:
   - `tests/test_constraint_solver.py`: `test_extreme_rotation_anglex_minus_30_arap_rigidity` failed at line 67 (`assert np.all(deformed_areas > -1e-4)`) because the existing solver lacks an explicit signed area barrier / line-search mechanism, permitting inverted triangles under extreme $\pm 30^\circ$ yaw deformations.
   - `tests/test_deformation_solver.py`: `test_deformation_solver_identity_and_parallax` failed at line 23 (`assert np.allclose(proj_0, pos_orig, atol=0.1)`) because perspective parallax was multiplying coordinates unconditionally even at rest pose ($\theta_x = 0, \theta_y = 0$).
   - `src/constraints/constraint_solver.py`: Implemented single-iteration unconstrained LU solving with approximate edge blending, but omitted cotangent Laplacian weights, obtuse angle clamping, and barrier line searching.

2. **Numerical Prototyping & Benchmarks (`scratch_verify.py`)**:
   - **Sparse System Factorization**: Assembled $\mathbf{A} = \mathbf{L} + \text{diag}(\boldsymbol{\gamma})$ as `scipy.sparse.csc_matrix` and pre-factorized via `scipy.sparse.linalg.splu(A)`. Factorization time was **0.477 ms** for 144 vertices.
   - **Local $\text{SO}(2)$ Optimal Rotation**: Closed-form $\text{atan2}(s_{01} - s_{10}, s_{00} + s_{11})$ rotation estimation matched 2x2 SVD / Polar Decomposition to **$7.77 \times 10^{-16}$** (machine epsilon) with $10\times$ faster execution.
   - **Pure Rigid Invariance**: Pure rigid rotation and translation produced zero deformation error ($6.66 \times 10^{-16}$).
   - **Extreme Shearing & Inversion Barrier**: Under forced fold / severe shearing deformation, backtracking line search maintained strictly positive signed area ($\min \text{Area} = 0.005127 > 0$) across $100\%$ of triangles.

---

## 2. Logic Chain

1. **Why ARAP is Essential for 2.5D Layered Art**:
   - Direct 3D perspective projection causes non-uniform stretching and shearing of facial features (e.g. eyes and mouth).
   - Minimizing the ARAP energy $E_{\text{ARAP}} = \sum w_{ij} \| (\mathbf{v}_i - \mathbf{v}_j) - \mathbf{R}_i (\mathbf{u}_i - \mathbf{u}_j) \|^2$ preserves local cell rigidity and aspect ratios.

2. **Why Closed-Form $\text{SO}(2)$ Polar Decomposition is Superior**:
   - In 2D, the optimal rotation angle $\phi_i = \text{atan2}(s_{01} - s_{10}, s_{00} + s_{11})$ is algebraically exact, strictly guarantees $\det(\mathbf{R}_i) = +1.0$, and avoids iterative or branching SVD routines.

3. **Why Backtracking Line Search Guarantees Non-Inversion**:
   - Triangle area is a continuous function of vertex positions: $A(T) = \frac{1}{2}((x_2 - x_1)(y_3 - y_1) - (x_3 - x_1)(y_2 - y_1))$.
   - Since the rest pose has strictly positive area ($A_{\text{rest}} > 0$), stepping along $\mathbf{V}(\alpha) = \mathbf{V}^{(k)} + \alpha \Delta \mathbf{V}$ with $\alpha \in (0, 1]$ and halving $\alpha$ whenever $\min A(T) < \epsilon A_{\text{rest}}$ guarantees that the output mesh configuration remains strictly non-inverted and topologically valid.

4. **Sparse LU Pre-Factorization Architecture**:
   - Because the system matrix $\mathbf{A} = \mathbf{L} + \text{diag}(\boldsymbol{\gamma})$ depends purely on rest topology and stiffness weights, it is static across all keyforms.
   - Factoring once via `splu` enables solving all 9 Cartesian keyforms across 20 layers in $< 20\text{ ms}$ total.

---

## 3. Caveats

- **Extreme Aspect Ratio Triangles**: If initial Delaunay triangulation contains razor-thin triangles (aspect ratio $> 100$), cotangent weights can exceed 50.0. Clamping cotangent weights to $[0.05, 50.0]$ is required to prevent numerical stiffness.
- **Disconnected Components**: For layers with multiple disconnected islands (e.g. two separate eyebrows on one layer), the Laplacian $\mathbf{L}$ is block-diagonal. Positional anchor weights $\gamma_i > 0$ for all vertices guarantee that every diagonal block is strictly positive definite and non-singular.

---

## 4. Conclusion

1. **Solver Architecture**: The complete mathematical formulation, algorithms, and data structures for `ARAPConstraintSolver` have been verified and documented in `d:\VitubModel\.agents\explorer_m2_3\analysis.md`.
2. **Keyform Invariant**: At $(\theta_x = 0, \theta_y = 0, \theta_z = 0)$, the solver mathematically guarantees zero displacement ($\Delta \mathbf{V}^{(4)} \equiv \mathbf{0}$).
3. **Verification Matrix**: A 10-test suite for `tests/test_deformation.py` has been defined to validate $\text{SO}(3)$ rotation algebra, ARAP rigidity, barrier bounds, and keyform tensors.

---

## 5. Verification Method

To independently verify the mathematical derivations and benchmarks:

```powershell
# 1. Run the ARAP mathematical verification prototype
.\venv\Scripts\python.exe d:\VitubModel\.agents\explorer_m2_3\scratch_verify.py

# 2. Inspect the complete technical analysis report
Get-Content d:\VitubModel\.agents\explorer_m2_3\analysis.md
```

### Invalidation Conditions:
- If closed-form rotation differs from 2x2 SVD by $> 10^{-10}$.
- If pure rigid translation/rotation produces non-zero elastic energy ($E > 10^{-10}$).
- If any triangle signed area becomes $\le 0$ under $\pm 30^\circ$ head rotation.
- If single-frame ARAP solve time exceeds $5\text{ ms}$.
