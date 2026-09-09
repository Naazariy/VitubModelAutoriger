# Synthesis: Milestone 2 Architectural & Mathematical Specification

## 1. Depth Proxy Modeling (`src/depth/depth_model.py`)
- **Proxies Supported**:
  - `ELLIPSOIDAL`: $Z(x, y) = Z_0 \cdot \sqrt{\max(0, 1 - (x-x_0)^2/R_x^2 - (y-y_0)^2/R_y^2)}$ for Face/Head.
  - `CYLINDRICAL`: $Z(x, y) = Z_0 \cdot \sqrt{\max(0, 1 - (x-x_0)^2/R_x^2)}$ for Neck/Torso.
  - `PLANAR`: $Z(x, y) = Z_0 + a(x-x_0) + b(y-y_0)$ for Accessories/Ears/Body.
  - `INVERTED_SHELL`: Hollow concave shell for HairBack.
  - `CONICAL_BUMP`: Localized depth accentuation for Nose/Mouth.
- **Layer Stacking & Normalization**:
  - Semantic layer category hierarchy mapping:
    `HAIR_BACK` (-0.8 to -0.4), `TORSO`/`NECK` (-0.4 to -0.1), `FACE`/`HEAD` (0.0 to 0.4), `MOUTH`/`NOSE`/`EYES` (0.4 to 0.7), `HAIR_FRONT`/`ACCESSORY` (0.7 to 1.0).
  - Clearance guarantee $\Delta Z \ge \delta_{\min} + \Delta x_{\max}\sin(30^\circ)$ to prevent depth layer penetration during 3D yaw rotations.
  - Full depth coordinate normalization into $[-1.0, 1.0]$.

## 2. Differential Geometry Engine (`src/geometry/geometry_engine.py`)
- **Analytical Normals**:
  - $\mathbf{N} = \frac{\nabla F}{\|\nabla F\|}$ computed analytically for proxy surfaces, fallback to mesh face-weighted vertex normals.
- **Tangent Space & Curvature**:
  - Orthonormal tangent frames $(\mathbf{T}_u, \mathbf{T}_v)$ aligned with parametric coordinates.
  - First and Second Fundamental Forms ($I, II$), Mean Curvature $H = \frac{eG - 2fF + gE}{2(EG - F^2)}$, Gaussian Curvature $K = \frac{eg - f^2}{EG - F^2}$.
- **Projective Geometry**:
  - Weak perspective and full pinhole camera projection.

## 3. 3D Deformation Engine & Keyform Tensors (`src/deformation/deformation_solver.py`)
- **SO(3) Lie Group Rotations**:
  - Compound Euler rotation $\mathbf{R}(\theta_x, \theta_y, \theta_z) = \mathbf{R}_z(\theta_z) \mathbf{R}_y(\theta_x) \mathbf{R}_x(\theta_y)$.
  - Analytical proof of orthonormality ($\mathbf{R}^T \mathbf{R} = \mathbf{I}$, $\det(\mathbf{R}) = 1$).
- **Normalized Relative Parallax (Zero-Identity Invariant)**:
  - Perspective scaling ratio $S(P) = \frac{1 + \kappa (P'_z - Z_c)/R_z}{1 + \kappa (P_z - Z_c)/R_z}$, guaranteeing $\Delta \mathbf{V}^{(0,0,0)} \equiv \mathbf{0}$.
- **Anime Foreshortening**:
  - Non-linear 2D modulation field $\boldsymbol{\Phi}(\mathbf{u}, \boldsymbol{\theta})$ for cheek compression, chin curvature, and eye aspect ratio preservation.
- **Live2D Keyform Tensor Generation**:
  - 3x3 grid (Angle X $\in \{-30^\circ, 0^\circ, 30^\circ\} \times$ Angle Y $\in \{-30^\circ, 0^\circ, 30^\circ\}$) = 9 keyforms.
  - Angle Z $\in \{-30^\circ, 0^\circ, 30^\circ\}$ = 3 keyforms.
  - Compute discrete vertex displacement buffers $\Delta \mathbf{V} = \mathbf{V}_{\text{deformed}} - \mathbf{V}_{\text{base}}$ into `KeyformTable` and `DrawableKeyforms`.

## 4. ARAP Constraint Solver & Area Preservation (`src/constraints/constraint_solver.py`)
- **Closed-Form Polar Decomposition**:
  - Fast SO(2) rotation extraction $\theta_i = \text{atan2}(S_{01} - S_{10}, S_{00} + S_{11})$, achieving machine-precision SVD equivalence with 10x performance gain.
- **Sparse LU Pre-factorization**:
  - Cached `scipy.sparse.linalg.splu(L)` enabling $<0.1\text{ ms}$ solve per iteration.
- **Positive Signed Area Barrier**:
  - Continuous Backtracking Line Search guaranteeing $\text{Area}(T) \ge \epsilon > 0$ for all triangles.
  - Laplacian spring regularization energy minimizing shear distortion.
