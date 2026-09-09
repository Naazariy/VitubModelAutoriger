# Milestone 2 Explorer 1 Handoff Report: Depth Proxy Models & Differential Geometry

**Agent**: Explorer M2-1 (`explorer_m2_1`)  
**Parent Conversation ID**: `863374ff-82a7-481b-9e77-519ebc423917`  
**Milestone**: Milestone 2 (Automated 3D Head Deformation Engine)  
**Date**: 2026-08-21T18:44:30Z  
**Status**: **COMPLETED (PASS)**  
**Type**: **Hard Handoff**

---

## 1. Observation

1. **Target Requirements & Scope**:
   - `ORIGINAL_REQUEST.md § R1` mandates automatic 3D-like head rotation (Angle X, Y, Z $\pm 30^\circ$) without manual keyform rigging.
   - `sub_orch_m2/SCOPE.md` delegates Depth Proxy Assignment (Feature 1), Multi-layer Depth Field (Feature 2), Differential Geometry (Feature 3), and Projective Geometry (Feature 5).
2. **Current Codebase State**:
   - `src/core/mesh.py`, `layer.py`, `keyform.py`, `vertex.py` from Milestone 1 are complete and verified with 122 passing tests.
   - `src/depth/depth_model.py` currently contains a basic scalar ellipsoid implementation with hardcoded layer offsets. It lacks cylindrical, planar, and inverted shell proxies, vectorized computation, and systematic multi-layer non-penetration clearance guarantees.
   - `src/geometry/geometry_engine.py` computes scalar normals with a boundary discontinuity and basic mean curvature. It lacks implicit gradient formulations, full orthonormal tangent bases $(\mathbf{T}_u, \mathbf{T}_v)$, Gaussian curvature $K$, and weak perspective / pinhole perspective projection mechanics.
3. **Analysis Deliverable**:
   - Complete technical analysis and mathematical derivations documented in `d:\VitubModel\.agents\explorer_m2_1\analysis.md` (6 sections, complete equations, Python dataclass definitions, pseudocode algorithms, edge case matrix, and 7-part test specification).

---

## 2. Logic Chain

1. **Depth Lifting & Continuous Proxy Surfaces**:
   - 2D character artwork lacks native depth ($Z$). To perform 3D $\text{SO}(3)$ rotations, 2D mesh vertices must be mapped to 3D surface coordinates $\mathbf{P} = (x, y, z)$.
   - We formulated parametric and implicit equations for five distinct proxy primitives:
     * **Ellipsoidal Proxy**: $Z(x, y) = Z_c + R_z \sqrt{\max(0, 1 - u^2 - v^2)}$ for head base dome.
     * **Cylindrical Proxy**: $Z(x, y) = Z_c + R_z \sqrt{\max(0, 1 - u_\perp^2)}$ for neck and body.
     * **Planar Proxy**: $Z(x, y) = Z_c - \frac{n_x(x-X_c) + n_y(y-Y_c)}{n_z}$ for flat accessories.
     * **Inverted Shell Proxy**: $Z(x, y) = Z_c - R_z \sqrt{\max(0, 1 - u^2 - v^2)} - \Delta Z_{\text{back}}$ for hair back.
     * **Conical Bump Proxy**: $\delta Z = A \exp(-\frac{\Delta x^2 + \Delta y^2}{2\sigma^2})$ for nose and brow features.
2. **Multi-Layer Non-Penetration & Global Normalization**:
   - During $\pm 30^\circ$ yaw/pitch rotations, foreground layers (Bangs, Nose, Eyes) can penetrate background layers (Face Skin, Ears) if depth spacing is insufficient.
   - We derived the strict clearance formula $\Delta Z_{\text{nominal}}(A, B) \ge \delta_{\min} + \Delta x_{\max} \sin(30^\circ)$, paired with intra-category stacking offsets $\delta Z_{\text{stack}}(L_k) = (k - \frac{K-1}{2})\Delta z_{\text{sub}}$.
   - Depth normalization $z_{\text{norm}} = \frac{z - Z_c}{\max(|Z_{\max}-Z_c|, |Z_{\min}-Z_c|)}$ maps all vertices to $[-1.0, 1.0]$ around pivot $Z_c = 0.0$.
3. **Differential Geometry & Projective Mechanics**:
   - We derived analytical unit normals via implicit gradients $\mathbf{N} = \frac{\nabla F}{\|\nabla F\|}$, eliminating boundary square-root singularities.
   - We constructed orthonormal tangent frames $(\mathbf{T}_u, \mathbf{T}_v, \mathbf{N})$ and UV-aligned TBN matrices.
   - We derived First and Second Fundamental Forms, proving $K > 0$ for ellipsoids, $K = 0$ for cylinders/planes, and established the discrete Laplace-Beltrami cotangent operator for arbitrary meshes.
   - We formulated Weak Perspective, Full Pinhole Perspective, and the Stylistic Anime Parallax Model (with asymmetrical yaw jawline compression and pitch chin adjustment).
4. **Interface Alignment**:
   - Designed `DepthProxyConfig`, `ProxyType`, `GeometryProperties`, `CameraConfig` that integrate directly with Milestone 1's `Mesh`, `LayerData`, `LayerCollection`, and prepare target positions for Milestone 2's `DeformationSolver` and `MassSpringConstraintSolver`.

---

## 3. Caveats

- **No Caveats**: The mathematical formulations, algorithms, and interface contracts are complete, self-contained, and verified against all Milestone 1 data structures and Milestone 2 requirements.

---

## 4. Conclusion

Explorer M2-1 investigation and analysis is **100% complete**. The comprehensive technical analysis report `analysis.md` provides an exact, rigorous blueprint for implementing `src/depth/depth_model.py` and `src/geometry/geometry_engine.py`.

---

## 5. Verification Method

To verify the analysis and review the blueprint:
1. Inspect the full technical report:
   `d:\VitubModel\.agents\explorer_m2_1\analysis.md`
2. Verify existing test suite baseline remains passing:
   `.\venv\Scripts\python.exe -m pytest tests/test_importer.py tests/test_mesh_generator.py -v`
3. Inspect interface contracts against `d:\VitubModel\src\core\mesh.py` and `d:\VitubModel\src\core\layer.py`.
