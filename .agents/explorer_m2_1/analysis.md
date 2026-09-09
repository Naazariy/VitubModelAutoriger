# Technical Analysis & Architectural Blueprint: Depth Proxy Models & Differential Geometry (Milestone 2)

**Agent**: Explorer M2-1 (Depth Proxy & Differential Geometry Specialist)  
**Date**: 2026-08-21  
**Working Directory**: `d:\VitubModel\.agents\explorer_m2_1`  
**Target Focus**: `src/depth/depth_model.py` and `src/geometry/geometry_engine.py`

---

## 1. Executive Summary & Scope Overview

In the automated VTuber rigging pipeline, **Milestone 2 (Automated 3D Head Deformation Engine)** bridges the 2D segmented artwork ingested in Milestone 1 with the Live2D keyform tensor export in Milestone 3. Converting flat 2D layers into lifelike 3D rotations without manual keyform authoring requires lifting 2D mesh vertices into a 3D proxy space, extracting local differential geometric features, applying SO(3) Euler rotations with depth-stratified perspective parallax, and regularizing deformations via an As-Rigid-As-Possible (ARAP) solver.

This report establishes the complete mathematical formulations, data structures, algorithms, and test methodologies for two foundational engines:
1. **Depth Proxy Modeling Engine (`src/depth/depth_model.py`)**:
   - Parametric and implicit formulations of **Ellipsoidal**, **Cylindrical**, **Planar**, **Inverted Shell**, and **Conical/Feature Bump** depth proxies.
   - Comprehensive semantic layer depth stratification across all 10 character categories (`face`, `hair_front`, `hair_back`, `eyes`, `eyebrows`, `nose`, `mouth`, `ears`, `body`/`neck`, `accessories`).
   - Multi-layer Z-offset stacking and non-penetration clearance guarantees ($\Delta Z \ge \delta_{\min} > 0$) across full rotation envelopes ($\theta \in [-30^\circ, +30^\circ]$).
   - Global depth normalization to the standard range $[-1.0, 1.0]$.
2. **Differential Geometry Engine (`src/geometry/geometry_engine.py`)**:
   - Analytical and discrete 3D unit normal vectors $\mathbf{N}(x, y, z)$, orthonormal tangent bases $(\mathbf{T}_u, \mathbf{T}_v)$, and UV-aligned Tangent-Bitangent-Normal (TBN) frames.
   - Surface gradient, First and Second Fundamental Forms, Mean Curvature $H$, and Gaussian Curvature $K$ (analytical and discrete Laplace-Beltrami cotangent operators).
   - Comparative projection mechanics: Weak Perspective, Pinhole Perspective, and Non-linear Stylistic Anime Foreshortening.
3. **Data Structures & Interfaces**:
   - Pure Python / NumPy dataclasses and TypedDicts maintaining complete interface compatibility with Milestone 1's `LayerData`, `LayerCollection`, `Mesh`, `Vertex`, `Triangle`, `UV`, and `KeyformTable`.

```
2D Ingested Layers & Delaunay Meshes (Milestone 1)
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│             Depth Proxy Engine (src/depth/)                 │
│  - Semantic Category Classification & Proxy Selection       │
│  - Ellipsoidal, Cylindrical, Planar, & Shell Geometries     │
│  - Multi-Layer Z-Stacking & Non-Penetration Offsets         │
│  - Global Depth Normalization to [-1.0, 1.0]                │
└──────────────────────┬──────────────────────────────────────┘
                       │ Output: V_3D = (x, y, z) per vertex
                       ▼
┌─────────────────────────────────────────────────────────────┐
│       Differential Geometry Engine (src/geometry/)          │
│  - Analytical & Discrete Surface Normals N(x, y, z)         │
│  - Orthonormal Tangents (Tu, Tv) & TBN Frames               │
│  - Mean Curvature H & Gaussian Curvature K                  │
│  - Weak Perspective / Perspective / Anime Parallax Projector│
└──────────────────────┬──────────────────────────────────────┘
                       │ Output: GeometryProperties & Target Projected Positions
                       ▼
3D SO(3) Rotation & ARAP Constraint Solver (Deformation Engine)
```

---

## 2. Depth Proxy Modeling Engine (`src/depth/depth_model.py`)

### 2.1 Mathematical Formulations of Primitive Proxies

A depth proxy maps 2D vertex positions $(x, y)$ in normalized canvas space $[-1.0, 1.0]$ or pixel space to continuous 3D depth values $z = Z(x, y)$.

```
   Ellipsoidal Proxy (Head Dome)          Cylindrical Proxy (Neck/Torso)          Planar Proxy (Accessories)
           +Z ▲                                   +Z ▲                                   +Z ▲
              │                                      │                                      │    /
         .---' '---.                           .-----│-----.                           .----'  /
       .'     │     `.                        /      │      \                         /    '  /
      /       │       \                      |       │       |                       |   '   /
     |────────┼────────| ──► +X             |───────┼───────| ──► +X               |──'───/───| ──► +X
      \       │       /                      |       │       |                       | '   /    |
       `.     │     .'                        \      │      /                         /'  /     |
         `---. .---'                           `-----│-----'                           `-/------'
              │                                      │                                  /
```

#### 1. Ellipsoidal Proxy (Head & Facial Features)
The base head geometry is modeled as a 3D tri-axial ellipsoid centered at $\mathbf{C} = (X_c, Y_c, Z_c)$ with semi-axes $(R_x, R_y, R_z)$:
$$\frac{(x - X_c)^2}{R_x^2} + \frac{(y - Y_c)^2}{R_y^2} + \frac{(z - Z_c)^2}{R_z^2} = 1$$

##### Explicit Front-Facing Dome:
Let the normalized radial distance $u = \frac{x - X_c}{R_x}$ and $v = \frac{y - Y_c}{R_y}$, with normalized radius $r^2 = u^2 + v^2$.
$$Z_{\text{ellipsoid}}(x, y) = \begin{cases} Z_c + R_z \sqrt{1 - \left(u^2 + v^2\right)}, & \text{if } u^2 + v^2 \le 1 \\ Z_c \cdot \exp\left(-\alpha (u^2 + v^2 - 1)\right), & \text{if } u^2 + v^2 > 1 \text{ (Smooth falloff)} \end{cases}$$
where $\alpha \ge 2.0$ guarantees $C^1$ smooth boundary transition without NaN or imaginary roots.

##### Implicit Surface Representation:
$$F_{\text{ellipsoid}}(x, y, z) = \frac{(x - X_c)^2}{R_x^2} + \frac{(y - Y_c)^2}{R_y^2} + \frac{(z - Z_c)^2}{R_z^2} - 1 = 0$$

##### Analytical First-Order Partial Derivatives:
For interior points ($u^2 + v^2 < 1$):
$$\frac{\partial Z}{\partial x} = -\frac{R_z}{R_x^2} \frac{x - X_c}{\sqrt{1 - u^2 - v^2}} = -\frac{R_z}{R_x} \frac{u}{\sqrt{1 - u^2 - v^2}}$$
$$\frac{\partial Z}{\partial y} = -\frac{R_z}{R_y^2} \frac{y - Y_c}{\sqrt{1 - u^2 - v^2}} = -\frac{R_z}{R_y} \frac{v}{\sqrt{1 - u^2 - v^2}}$$

##### Boundary Singularity Regularization:
As $u^2 + v^2 \to 1^-$, the denominator $\sqrt{1 - u^2 - v^2} \to 0$, causing explicit derivatives to diverge. To prevent numerical overflow, we compute the gradient via the implicit formulation:
$$\nabla F = \left( \frac{2(x - X_c)}{R_x^2}, \frac{2(y - Y_c)}{R_y^2}, \frac{2(z - Z_c)}{R_z^2} \right)^T$$
$$\mathbf{N}(x, y, z) = \frac{\nabla F}{\|\nabla F\|}$$
At the boundary ($z = Z_c$), $\nabla F = \left(\frac{2u}{R_x}, \frac{2v}{R_y}, 0\right)^T$, yielding a stable, bounded unit normal with zero singularities.

---

#### 2. Cylindrical Proxy (Neck, Torso, Limbs, Hair Strands)
Cylindrical surfaces provide translational invariance along an axis $\mathbf{a}$, ideal for the neck and upper torso.

##### Vertical Cylinder (Aligned with Y-axis):
For neck/torso centered at $(X_c, Y_c, Z_c)$ with horizontal semi-width $R_x$, vertical extent, and depth radius $R_z$:
$$Z_{\text{cyl}}(x, y) = \begin{cases} Z_c + R_z \sqrt{1 - \left(\frac{x - X_c}{R_x}\right)^2}, & \text{if } |x - X_c| \le R_x \\ Z_c \cdot \exp\left(-\alpha \left(\frac{|x - X_c|^2}{R_x^2} - 1\right)\right), & \text{if } |x - X_c| > R_x \end{cases}$$

##### Arbitrarily Oriented Cylinder:
For a cylindrical proxy with 2D axis unit direction $\mathbf{d} = (d_x, d_y)^T$ ($\|\mathbf{d}\| = 1$):
The perpendicular signed distance from point $(x, y)$ to the cylinder centerline is:
$$p_\perp(x, y) = -(x - X_c) d_y + (y - Y_c) d_x$$
Normalized cross-sectional coordinate: $u_\perp = \frac{p_\perp(x, y)}{R_\perp}$.
$$Z_{\text{cyl\_oriented}}(x, y) = Z_c + R_z \sqrt{\max\left(0, 1 - u_\perp^2\right)}$$

##### Analytical Derivatives:
$$\frac{\partial Z_{\text{cyl}}}{\partial x} = -\frac{R_z}{R_x^2} \frac{x - X_c}{\sqrt{1 - \left(\frac{x - X_c}{R_x}\right)^2}}, \quad \frac{\partial Z_{\text{cyl}}}{\partial y} = 0$$

---

#### 3. Planar Proxy (Accessories, Glasses, Cards, Ribbons)
A planar proxy represents flat or tilted planar elements defined by a center $(X_c, Y_c, Z_c)$ and surface normal $\mathbf{n} = (n_x, n_y, n_z)^T$ with $\|\mathbf{n}\| = 1, n_z \ne 0$:
$$n_x (x - X_c) + n_y (y - Y_c) + n_z (z - Z_c) = 0$$
$$Z_{\text{plane}}(x, y) = Z_c - \frac{n_x (x - X_c) + n_y (y - Y_c)}{n_z}$$

##### Parametrization via Pitch Angle $\alpha_p$ and Yaw Angle $\beta_y$:
$$Z_{\text{plane}}(x, y) = Z_c + \tan(\beta_y) \cdot (x - X_c) - \tan(\alpha_p) \cdot (y - Y_c)$$
For flat front-facing accessories parallel to the canvas: $n_x = 0, n_y = 0, n_z = 1 \implies Z_{\text{plane}}(x, y) = Z_c$.

##### Analytical Derivatives:
$$\frac{\partial Z_{\text{plane}}}{\partial x} = -\frac{n_x}{n_z} = \tan(\beta_y), \quad \frac{\partial Z_{\text{plane}}}{\partial y} = -\frac{n_y}{n_z} = -\tan(\alpha_p)$$

---

#### 4. Inverted Shell Proxy (Hair Back, Rear Head Cavity)
The back of the hair wraps *behind* the head, moving in opposition to the front dome during rotation.
$$Z_{\text{back}}(x, y) = Z_c - R_z \sqrt{\max\left(0, 1 - \left(\frac{x - X_c}{R_x}\right)^2 - \left(\frac{y - Y_c}{R_y}\right)^2\right)} - \Delta Z_{\text{back}}$$
This ensures that when the head turns right ($\theta_x > 0$), the back hair shifts in the opposite parallax direction, creating natural 3D depth parallax occlusions.

---

#### 5. Conical / Feature Bump Proxy (Nose, Eye Bulge, Eyebrow Ridge)
Local facial features require localized depth protrusions superimposed on the base head dome:
$$\delta Z_{\text{feature}}(x, y) = A_{\text{peak}} \cdot \exp\left( -\left( \frac{(x - X_{\text{feat}})^2}{2 \sigma_x^2} + \frac{(y - Y_{\text{feat}})^2}{2 \sigma_y^2} \right) \right)$$
- **Nose Cone**: Sharp Gaussian bump ($A_{\text{peak}} = +0.25 \cdot R_z$, $\sigma_x = 0.08 \cdot R_x$, $\sigma_y = 0.12 \cdot R_y$).
- **Eye Bulge**: Spherical dome conforming to ocular socket ($A_{\text{peak}} = +0.06 \cdot R_z$, $\sigma = 0.15 \cdot R_x$).

---

### 2.2 Per-Layer Semantic Depth Stratification Strategy

A VTuber character model consists of stacked visual layers. To ensure proper visual depth ordering during 3D rotation, each layer is assigned a composite depth function:
$$Z_L(x, y) = Z_{\text{proxy}}^{(L)}(x, y) + \Delta Z_{\text{semantic}}(L) + \delta Z_{\text{stack}}(L) + \delta Z_{\text{peripheral}}(x, y)$$

#### 1. Semantic Depth Matrix
The 10 standard semantic categories mapped from Milestone 1 are parameterized as follows:

| Semantic Category | Primary Proxy Type | Nominal Base Offset $\Delta Z$ | Parallax Multiplier $\kappa_L$ | Stiffness $S_i$ | Deformation Behavior |
|---|---|---|---|---|---|
| `hair_front` (Bangs/Ahoge) | Offset Ellipsoid | $+0.50 \cdot R_z$ | $1.35\times$ | $0.20$ | Soft spring elastic parallax, large leading displacement |
| `accessories` (Glasses/Pins) | Planar / Conforming | $+0.45 \cdot R_z$ | $1.25\times$ | $0.85$ | Rigid planar attachment, preserves rectilinear shape |
| `eyebrows` (Left/Right) | Conforming Ellipsoid | $+0.35 \cdot R_z$ | $1.10\times$ | $0.70$ | Conforms to brow ridge curvature |
| `nose` (Bridge/Tip) | Conical Bump + Ellipsoid | $+0.30 \cdot R_z$ | $1.25\times$ | $0.90$ | High parallax prominence, maximal horizontal shift |
| `eyes` (Pupil/Sclera/Lash) | Spherical Bulge | $+0.25 \cdot R_z$ | $1.05\times$ | $0.80$ | Rigid spherical tracking, non-collapsing pupil |
| `mouth` (Lips/Teeth/Interior)| Conforming Ellipsoid | $+0.20 \cdot R_z$ | $1.02\times$ | $0.75$ | Follows lower facial curvature |
| `face` (Skin Base/Cheeks) | Base Ellipsoid | $0.00$ | $1.00\times$ | $0.50$ | Reference anchor dome, silhouette foreshortening |
| `ears` (Left/Right) | Peripheral Ellipsoid | $-0.15 \cdot R_z$ | $0.90\times$ | $0.60$ | Peripheral occlusion and backward sweep |
| `body` (Neck/Torso/Clothes) | Vertical Cylinder | $-0.35 \cdot R_z$ | $0.40\times$ | $0.90$ | Stable root anchor, cylindrical contour |
| `hair_back` (Ponytail/Back) | Inverted Shell | $-0.60 \cdot R_z$ | $0.70\times$ | $0.30$ | Inverted counter-parallax motion |
| `unknown` | Base Ellipsoid | $0.00$ | $1.00\times$ | $0.50$ | Neutral fallback |

#### 2. Peripheral Stratification (Ear & Lateral Hair Occlusion)
To replicate natural head curvature where the ears and sideburns recede around the lateral contour:
$$\delta Z_{\text{peripheral}}(x, y) = \begin{cases} 0.0, & \text{if } |u| \le 0.6 \\ -0.40 \cdot R_z \left(\frac{|u| - 0.6}{0.4}\right)^2, & \text{if } |u| > 0.6 \end{cases}$$
where $u = \frac{x - X_c}{R_x}$. This parabolic falloff smoothly pushes lateral vertices backward by up to $-0.40 \cdot R_z$, preventing ears from clipping through the cheek during $\pm 30^\circ$ yaw turns.

---

### 2.3 Multi-Layer Z-Offset Stacking & Non-Penetration Condition

#### 1. The Layer Penetration Problem
When two layers $A$ (foreground, e.g. Bangs) and $B$ (background, e.g. Face) rotate in 3D by yaw $\theta_x$:
$$\mathbf{P}'_A = \mathbf{R}_y(\theta_x)(\mathbf{P}_A - \mathbf{C}) + \mathbf{C}$$
$$\mathbf{P}'_B = \mathbf{R}_y(\theta_x)(\mathbf{P}_B - \mathbf{C}) + \mathbf{C}$$
The rotated depth difference is:
$$\Delta Z'_{A, B} = P'_{z, A} - P'_{z, B} = (x_A - x_B) \sin\theta_x + (z_A - z_B) \cos\theta_x$$
If $z_A - z_B$ is insufficient, non-zero horizontal separation $(x_A - x_B) \sin\theta_x$ can cause $\Delta Z'_{A,B} < 0$ (visual penetration / layer inversion / z-fighting).

#### 2. Strict Clearance Guarantee
To guarantee non-penetration across all angles $\theta \in [-\theta_{\max}, +\theta_{\max}]$ (where $\theta_{\max} = 30^\circ$):
$$\min_{\theta \in [-\theta_{\max}, \theta_{\max}]} \Delta Z'_{A, B} \ge \delta_{\min} > 0$$
$$\Delta Z_{\text{nominal}}(A, B) \ge \delta_{\min} + \Delta x_{\max} \cdot \sin(\theta_{\max})$$

#### 3. Intra-Category Stacking Offset
When multiple layers belong to the same semantic category (e.g. 5 sub-layers of `hair_front` or 4 layers of `eyes`):
$$\delta Z_{\text{stack}}(L_k) = \left( k - \frac{K - 1}{2} \right) \cdot \Delta z_{\text{sub}}$$
where $k \in \{0, \dots, K-1\}$ is the layer stack index (ordered back-to-front), and $\Delta z_{\text{sub}} = 0.02 \cdot R_z$.

---

### 2.4 Global Depth Normalization Engine

All depth values across all meshes must be globally normalized into the canonical range $[-1.0, 1.0]$:
1. Compute the global depth bounds across all vertices $i \in \bigcup_{L} \mathcal{V}_L$:
   $$Z_{\min} = \min_{i} z_i, \quad Z_{\max} = \max_{i} z_i, \quad Z_{\text{pivot}} = Z_c$$
2. Normalize symmetrically around the rotation pivot $Z_c$:
   $$S_z = \max\left(|Z_{\max} - Z_c|, |Z_{\min} - Z_c|, \epsilon\right)$$
   $$z_{\text{norm}, i} = \frac{z_i - Z_c}{S_z} \in [-1.0, 1.0]$$
3. Assign normalized depth to each `Vertex.depth` and `Mesh.depth_z` buffer.

---

## 3. Differential Geometry Engine (`src/geometry/geometry_engine.py`)

```
          Surface Differential Properties on 2.5D Mesh
                  
                       ▲ Unit Normal N(x, y, z)
                       │
                       │    ▲ Tangent Tv (along Y / V)
                       │   /
                       │  /
                 .─────┼─/─────.
                /      │/       \
               /       o─────────► Tangent Tu (along X / U)
              /  Vertex P(x,y,z)  \
             '─────────────────────'
          Curvature Field: H (Mean), K (Gaussian)
```

### 3.1 3D Surface Normal Vectors $\mathbf{N}(x, y, z)$

#### 1. Analytical Surface Normal (Parametric Surface $z = f(x, y)$)
For a depth proxy surface defined explicitly by $z = f(x, y)$:
$$\mathbf{t}_x = \left( 1, 0, \frac{\partial f}{\partial x} \right)^T, \quad \mathbf{t}_y = \left( 0, 1, \frac{\partial f}{\partial y} \right)^T$$
$$\mathbf{n}_{\text{unnorm}} = \mathbf{t}_x \times \mathbf{t}_y = \begin{vmatrix} \mathbf{i} & \mathbf{j} & \mathbf{k} \\ 1 & 0 & f_x \\ 0 & 1 & f_y \end{vmatrix} = \begin{pmatrix} -f_x \\ -f_y \\ 1 \end{pmatrix}$$
$$\mathbf{N}(x, y) = \frac{\left( -f_x, -f_y, 1 \right)^T}{\sqrt{1 + f_x^2 + f_y^2}}$$

#### 2. Implicit Surface Normal (Ellipsoid / Cylinder)
For implicit surface $F(x, y, z) = 0$:
$$\mathbf{N}(x, y, z) = \frac{\nabla F(x, y, z)}{\|\nabla F(x, y, z)\|}$$

| Proxy Type | Implicit Equation $F(x, y, z) = 0$ | Gradient $\nabla F(x, y, z)$ | Analytical Unit Normal $\mathbf{N}$ |
|---|---|---|---|
| **Ellipsoid** | $\frac{(x-X_c)^2}{R_x^2} + \frac{(y-Y_c)^2}{R_y^2} + \frac{(z-Z_c)^2}{R_z^2} - 1 = 0$ | $\left( \frac{2(x-X_c)}{R_x^2}, \frac{2(y-Y_c)}{R_y^2}, \frac{2(z-Z_c)}{R_z^2} \right)^T$ | $\frac{\left( \frac{x-X_c}{R_x^2}, \frac{y-Y_c}{R_y^2}, \frac{z-Z_c}{R_z^2} \right)}{\sqrt{\frac{(x-X_c)^2}{R_x^4} + \frac{(y-Y_c)^2}{R_y^4} + \frac{(z-Z_c)^2}{R_z^4}}}$ |
| **Cylinder** | $\frac{(x-X_c)^2}{R_x^2} + \frac{(z-Z_c)^2}{R_z^2} - 1 = 0$ | $\left( \frac{2(x-X_c)}{R_x^2}, 0, \frac{2(z-Z_c)}{R_z^2} \right)^T$ | $\frac{\left( \frac{x-X_c}{R_x^2}, 0, \frac{z-Z_c}{R_z^2} \right)}{\sqrt{\frac{(x-X_c)^2}{R_x^4} + \frac{(z-Z_c)^2}{R_z^4}}}$ |
| **Plane** | $n_x(x-X_c) + n_y(y-Y_c) + n_z(z-Z_c) = 0$ | $(n_x, n_y, n_z)^T$ | $(n_x, n_y, n_z)^T$ |

#### 3. Discrete Mesh Normals (Arbitrary Triangulated Meshes)
When proxy analytical parameters are unavailable, normals are computed directly from the 3D triangulated mesh $(\mathcal{V}_{3D}, \mathcal{T})$:
1. **Face Normal**: For triangle $T = (\mathbf{p}_0, \mathbf{p}_1, \mathbf{p}_2)$ with CCW vertex order:
   $$\mathbf{e}_1 = \mathbf{p}_1 - \mathbf{p}_0, \quad \mathbf{e}_2 = \mathbf{p}_2 - \mathbf{p}_0$$
   $$\mathbf{n}_T = \mathbf{e}_1 \times \mathbf{e}_2, \quad \mathbf{N}_T = \frac{\mathbf{n}_T}{\max(\|\mathbf{n}_T\|, 10^{-12})}$$
2. **Angle-Weighted Vertex Normal**:
   For vertex $i$, let $\mathcal{T}(i)$ be the set of incident triangles. For triangle $T \in \mathcal{T}(i)$, let $\alpha_{i, T}$ be the interior angle at vertex $i$:
   $$\cos \alpha_{i, T} = \frac{(\mathbf{p}_j - \mathbf{p}_i) \cdot (\mathbf{p}_k - \mathbf{p}_i)}{\|\mathbf{p}_j - \mathbf{p}_i\| \|\mathbf{p}_k - \mathbf{p}_i\|}$$
   $$\mathbf{n}_i = \sum_{T \in \mathcal{T}(i)} \alpha_{i, T} \mathbf{N}_T, \quad \mathbf{N}_i = \frac{\mathbf{n}_i}{\max(\|\mathbf{n}_i\|, 10^{-12})}$$
   Angle weighting eliminates mesh tessellation bias (equilateral vs. sliver triangles) and preserves surface smoothness.

---

### 3.2 3D Tangent Vectors ($\mathbf{T}_u, \mathbf{T}_v$) & Orthonormal TBN Basis

#### 1. Orthonormal Tangent Frame from Normal $\mathbf{N}$
Given a unit normal $\mathbf{N} = (N_x, N_y, N_z)^T$, we construct an orthonormal tangent frame $(\mathbf{T}_u, \mathbf{T}_v, \mathbf{N})$ via Gram-Schmidt projection:
$$\mathbf{T}_u = \begin{cases} \frac{(N_z, 0, -N_x)^T}{\sqrt{N_z^2 + N_x^2}}, & \text{if } |N_z| < 0.999 \\ (1, 0, 0)^T, & \text{if } |N_z| \ge 0.999 \end{cases}$$
$$\mathbf{T}_v = \mathbf{N} \times \mathbf{T}_u$$
Properties verified:
$$\|\mathbf{T}_u\| = 1, \quad \|\mathbf{T}_v\| = 1, \quad \|\mathbf{N}\| = 1$$
$$\mathbf{T}_u \cdot \mathbf{N} = 0, \quad \mathbf{T}_v \cdot \mathbf{N} = 0, \quad \mathbf{T}_u \cdot \mathbf{T}_v = 0$$

#### 2. UV-Aligned Tangent-Bitangent-Normal (TBN) Matrix
For texturing and anisotropic elasticity, tangents aligned with texture coordinates $(u, v)$ are computed:
For triangle $(\mathbf{p}_0, \mathbf{p}_1, \mathbf{p}_2)$ with UVs $(\mathbf{uv}_0, \mathbf{uv}_1, \mathbf{uv}_2)$:
$$\Delta \mathbf{p}_1 = \mathbf{p}_1 - \mathbf{p}_0, \quad \Delta \mathbf{p}_2 = \mathbf{p}_2 - \mathbf{p}_0$$
$$\Delta u_1 = u_1 - u_0, \quad \Delta v_1 = v_1 - v_0, \quad \Delta u_2 = u_2 - u_0, \quad \Delta v_2 = v_2 - v_0$$
$$\begin{bmatrix} \Delta \mathbf{p}_1^T \\ \Delta \mathbf{p}_2^T \end{bmatrix} = \begin{bmatrix} \Delta u_1 & \Delta v_1 \\ \Delta u_2 & \Delta v_2 \end{bmatrix} \begin{bmatrix} \mathbf{T}^T \\ \mathbf{B}^T \end{bmatrix}$$
Let determinant $D = \Delta u_1 \Delta v_2 - \Delta v_1 \Delta u_2$. If $|D| > 10^{-10}$:
$$\begin{bmatrix} \mathbf{T}^T \\ \mathbf{B}^T \end{bmatrix} = \frac{1}{D} \begin{bmatrix} \Delta v_2 & -\Delta v_1 \\ -\Delta u_2 & \Delta u_1 \end{bmatrix} \begin{bmatrix} \Delta \mathbf{p}_1^T \\ \Delta \mathbf{p}_2^T \end{bmatrix}$$
Orthogonalize $\mathbf{T}$ against $\mathbf{N}$:
$$\mathbf{T}' = \frac{\mathbf{T} - (\mathbf{N} \cdot \mathbf{T}) \mathbf{N}}{\|\mathbf{T} - (\mathbf{N} \cdot \mathbf{T}) \mathbf{N}\|}, \quad \mathbf{B}' = (\mathbf{N} \times \mathbf{T}') \cdot \text{sign}\left((\mathbf{N} \times \mathbf{T}') \cdot \mathbf{B}\right)$$

---

### 3.3 Surface Gradient, Fundamental Forms & Curvature Metrics

#### 1. Differential Geometry of Surfaces (First & Second Fundamental Forms)
For surface $\mathbf{S}(x, y) = (x, y, f(x, y))^T$:
- **First Fundamental Form (Metric Tensor)**:
  $$I = E \, dx^2 + 2F \, dx dy + G \, dy^2$$
  $$E = \mathbf{t}_x \cdot \mathbf{t}_x = 1 + f_x^2, \quad F = \mathbf{t}_x \cdot \mathbf{t}_y = f_x f_y, \quad G = \mathbf{t}_y \cdot \mathbf{t}_y = 1 + f_y^2$$
  $$W^2 = EG - F^2 = 1 + f_x^2 + f_y^2 = 1 + \|\nabla f\|^2$$
- **Second Fundamental Form (Curvature Tensor)**:
  $$II = e \, dx^2 + 2f \, dx dy + g \, dy^2$$
  $$e = \mathbf{N} \cdot \mathbf{S}_{xx} = \frac{f_{xx}}{\sqrt{1 + f_x^2 + f_y^2}}, \quad f = \mathbf{N} \cdot \mathbf{S}_{xy} = \frac{f_{xy}}{\sqrt{1 + f_x^2 + f_y^2}}, \quad g = \mathbf{N} \cdot \mathbf{S}_{yy} = \frac{f_{yy}}{\sqrt{1 + f_x^2 + f_y^2}}$$

#### 2. Gaussian Curvature $K$ & Mean Curvature $H$

##### Gaussian Curvature $K$:
$$K = \frac{eg - f^2}{EG - F^2} = \frac{f_{xx} f_{yy} - f_{xy}^2}{(1 + f_x^2 + f_y^2)^2}$$
- **Ellipsoid**: $K(x, y, z) = \frac{1}{R_x^2 R_y^2 R_z^2 \left(\frac{(x-X_c)^2}{R_x^4} + \frac{(y-Y_c)^2}{R_y^4} + \frac{(z-Z_c)^2}{R_z^4}\right)^2} > 0$ (Elliptic everywhere).
- **Cylinder**: $K = 0$ (Parabolic / Developable everywhere).
- **Plane**: $K = 0$ (Flat everywhere).

##### Mean Curvature $H$:
$$H = \frac{eG - 2fF + gE}{2(EG - F^2)} = \frac{(1 + f_y^2) f_{xx} - 2 f_x f_y f_{xy} + (1 + f_x^2) f_{yy}}{2(1 + f_x^2 + f_y^2)^{3/2}}$$

#### 3. Discrete Laplace-Beltrami Operator on Meshes
For arbitrary triangulated meshes, discrete mean curvature is computed via the cotangent formula:
$$\Delta_{\mathcal{M}} \mathbf{p}_i = \frac{1}{2 A_i} \sum_{j \in \mathcal{N}(i)} (\cot \alpha_{ij} + \cot \beta_{ij})(\mathbf{p}_i - \mathbf{p}_j) = -2 H_i \mathbf{N}_i$$
where:
- $\alpha_{ij}, \beta_{ij}$ are the angles opposite to edge $(i, j)$ in the two sharing triangles.
- $A_i$ is the Voronoi / mixed dual area of vertex $i$.
$$H_i = \frac{1}{2} \|\Delta_{\mathcal{M}} \mathbf{p}_i\|$$

---

### 3.4 Projection Mechanics: Weak Perspective vs. Perspective vs. Stylistic Anime

```
      Weak Perspective Model                           Pinhole Camera Model
            Parallel Rays                                 Converging Rays
       │      │      │      │                         \        │        /
       │      │      │      │                          \       │       /
       ▼      ▼      ▼      ▼                           \      ▼      /
   ──────────────────────────── Canvas              ─────────────────────── Canvas
         Linear Parallax                               Nonlinear 1/(D - z)
```

#### 1. Weak Perspective Projection (Scaled Orthographic)
Assumes depth variations $\Delta z = P'_z - Z_c$ are small relative to the camera distance $D$ ($D \gg \Delta z$):
$$\mathbf{x}_{\text{proj}} = \begin{bmatrix} X_c \\ Y_c \end{bmatrix} + \left( \begin{bmatrix} P'_x \\ P'_y \end{bmatrix} - \begin{bmatrix} X_c \\ Y_c \end{bmatrix} \right) \cdot \left( 1.0 + \kappa \cdot \frac{P'_z - Z_c}{R_z} \right)$$
where $\kappa = \frac{R_z}{D}$ is the parallax scale coefficient.

#### 2. Full Pinhole Perspective Projection
For camera located at $(X_c, Y_c, Z_c + D)$ with focal length $f$:
$$x_{\text{proj}} = X_c + \frac{f \cdot (P'_x - X_c)}{D - (P'_z - Z_c)}, \quad y_{\text{proj}} = Y_c + \frac{f \cdot (P'_y - Y_c)}{D - (P'_z - Z_c)}$$

##### First-Order Taylor Expansion:
$$\frac{f}{D - \Delta z} = \frac{f}{D} \frac{1}{1 - \frac{\Delta z}{D}} = \frac{f}{D} \left( 1 + \frac{\Delta z}{D} + \mathcal{O}\left(\frac{\Delta z^2}{D^2}\right) \right)$$
Setting $f = D$ demonstrates that the Weak Perspective model is the exact first-order Taylor expansion of Full Perspective.

#### 3. Stylistic Anime Hybrid Parallax Model
Pure physical perspective makes the turned-away jawline protrude excessively in 2D anime illustration. We formulate an Anime Parallax Model incorporating:
1. Layer-specific parallax $\kappa_L$.
2. Asymmetrical horizontal yaw foreshortening $S_{\text{jaw}}(x, \theta_x)$.
3. Vertical pitch chin curve adjustment $S_{\text{chin}}(y, \theta_y)$.

##### Mathematical Formula:
$$\mathbf{P}' = \mathbf{R}_z(\theta_z) \mathbf{R}_y(\theta_x) \mathbf{R}_x(\theta_y) (\mathbf{P} - \mathbf{C}) + \mathbf{C}$$
$$x_{\text{proj}} = X_c + (P'_x - X_c) \cdot \left(1.0 + \kappa_L \frac{P'_z - Z_c}{R_z}\right) \cdot S_{\text{jaw}}(P'_x, \theta_x)$$
$$y_{\text{proj}} = Y_c + (P'_y - Y_c) \cdot \left(1.0 + \kappa_L \frac{P'_z - Z_c}{R_z}\right) + \Delta y_{\text{chin}}(P'_y, \theta_y)$$

where:
- **Jawline Foreshortening**:
  $$S_{\text{jaw}}(x, \theta_x) = \begin{cases} 1.0 - 0.25 \sin|\theta_x| \cdot \left|\frac{x - X_c}{R_x}\right|^{1.5}, & \text{if } (x - X_c) \cdot \theta_x < 0 \text{ (Turned-away side)} \\ 1.0 + 0.08 \sin|\theta_x| \cdot \left(1.0 - \left|\frac{x - X_c}{R_x}\right|\right), & \text{if } (x - X_c) \cdot \theta_x \ge 0 \text{ (Facing side)} \end{cases}$$
- **Pitch Chin Curve**:
  $$\Delta y_{\text{chin}}(y, \theta_y) = -0.15 \cdot R_y \cdot \sin(\theta_y) \cdot \max\left(0, \frac{y - Y_c}{R_y}\right)^2$$

---

## 4. Architectural Design & Interface Contracts

### 4.1 Data Structures in `src/depth/depth_model.py`

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Tuple, Dict, List, Optional
import numpy as np

class ProxyType(Enum):
    ELLIPSOID = "ellipsoid"
    CYLINDER = "cylinder"
    PLANE = "plane"
    INVERTED_SHELL = "inverted_shell"
    CONE_BUMP = "cone_bump"
    CONFORMING = "conforming"

@dataclass
class DepthProxyConfig:
    """Configuration parameters for generating depth fields from geometric proxies."""
    proxy_type: ProxyType = ProxyType.ELLIPSOID
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)      # (Xc, Yc, Zc)
    radii: Tuple[float, float, float] = (0.6, 0.8, 0.4)        # (Rx, Ry, Rz)
    axis: Tuple[float, float] = (0.0, 1.0)                     # 2D axis direction for cylinder
    plane_normal: Tuple[float, float, float] = (0.0, 0.0, 1.0) # (nx, ny, nz) for planar proxy
    layer_z_offset: float = 0.0                                # Semantic base Z-offset
    falloff_power: float = 2.0                                 # Smooth outer falloff exponent
    peripheral_taper: float = 0.40                             # Lateral ear compression strength
    stack_order_offset: float = 0.0                            # Fine intra-category stacking delta
    feature_bump_amplitude: float = 0.0                        # Local feature bump height
    feature_bump_sigma: Tuple[float, float] = (0.1, 0.1)       # (sigma_x, sigma_y) for bump

@dataclass
class DepthAssignmentResult:
    """Output container for layer depth evaluations."""
    layer_id: str
    depth_array: np.ndarray      # (N,) float64 depth values
    z_min: float
    z_max: float
    z_mean: float
```

### 4.2 Data Structures in `src/geometry/geometry_engine.py`

```python
class ProjectionType(Enum):
    WEAK_PERSPECTIVE = "weak_perspective"
    PERSPECTIVE = "perspective"
    ORTHOGRAPHIC = "orthographic"
    ANIME_HYBRID = "anime_hybrid"

@dataclass
class GeometryProperties:
    """Differential geometric surface properties for a 2.5D/3D mesh."""
    normals: np.ndarray             # (N, 3) float64 unit normal vectors
    tangents_u: np.ndarray          # (N, 3) float64 orthonormal tangents (X/U)
    tangents_v: np.ndarray          # (N, 3) float64 orthonormal bitangents (Y/V)
    mean_curvature: np.ndarray      # (N,) float64 mean surface curvature H
    gaussian_curvature: np.ndarray  # (N,) float64 Gaussian curvature K
    tbn_matrices: Optional[np.ndarray] = None # (N, 3, 3) float64 TBN transformation matrices

@dataclass
class CameraConfig:
    """Camera and perspective projection parameters."""
    projection_type: ProjectionType = ProjectionType.ANIME_HYBRID
    camera_distance: float = 1000.0   # Virtual pinhole camera distance
    focal_length: float = 1000.0      # Virtual focal length
    parallax_scale: float = 0.45      # Base parallax expansion factor kappa
    fov_degrees: float = 45.0         # Field of view
```

### 4.3 Integration Contract with Milestone 1 Meshes

```python
# Interface Contract: M1 Mesh -> M2 Depth & Geometry -> M2 Deformation Solver

# 1. Depth Assignment
depth_model = DepthModel(head_center=(0.0, 0.0), head_radii=(0.6, 0.8, 0.4))
depth_model.apply_to_mesh(mesh=layer_mesh, category=layer_data.category)
# Result: mesh.depth_z updated with shape (N,) in [-1.0, 1.0]

# 2. Differential Geometry Evaluation
geom_props = GeometryEngine.compute_mesh_geometry(mesh=layer_mesh, proxy_config=depth_model.get_config(layer_data.category))
# Result: mesh.set_normals(geom_props.normals)
# mesh vertices updated with unit normals (N, 3)

# 3. Target 2D Projection
projected_2d, rotated_3d = GeometryEngine.project_mesh(
    mesh=layer_mesh,
    angle_x_deg=yaw,
    angle_y_deg=pitch,
    angle_z_deg=roll,
    camera_config=camera_cfg,
    layer_category=layer_data.category
)
# Result: projected_2d (N, 2) fed into ARAP Constraint Solver
```

---

## 5. Algorithmic Formulations & Edge Case Mitigations

### 5.1 Depth Generator Algorithm (`src/depth/depth_model.py`)

```python
def compute_proxy_depth_vectorized(
    positions: np.ndarray,      # (N, 2) float64 positions [x, y]
    config: DepthProxyConfig
) -> np.ndarray:                # (N,) float64 depth values
    N = len(positions)
    if N == 0:
        return np.zeros(0, dtype=np.float64)

    xc, yc, zc = config.center
    rx, ry, rz = config.radii
    x = positions[:, 0]
    y = positions[:, 1]

    if config.proxy_type == ProxyType.ELLIPSOID:
        u = (x - xc) / max(rx, 1e-6)
        v = (y - yc) / max(ry, 1e-6)
        sq_dist = u*u + v*v
        
        # Inside dome: exact ellipsoid; Outside: smooth exponential taper
        inside = sq_dist <= 1.0
        depths = np.zeros(N, dtype=np.float64)
        depths[inside] = zc + rz * np.sqrt(np.maximum(0.0, 1.0 - sq_dist[inside]))
        depths[~inside] = zc * np.exp(-config.falloff_power * (sq_dist[~inside] - 1.0))
        
        # Apply peripheral lateral ear tapering
        u_abs = np.abs(u)
        taper_mask = u_abs > 0.6
        if np.any(taper_mask):
            t = (u_abs[taper_mask] - 0.6) / 0.4
            depths[taper_mask] -= config.peripheral_taper * rz * (t ** 2)

    elif config.proxy_type == ProxyType.CYLINDER:
        dx, dy = config.axis
        # Perpendicular distance to cylinder axis
        p_perp = -(x - xc) * dy + (y - yc) * dx
        u = p_perp / max(rx, 1e-6)
        sq_dist = u * u
        inside = sq_dist <= 1.0
        depths = np.zeros(N, dtype=np.float64)
        depths[inside] = zc + rz * np.sqrt(np.maximum(0.0, 1.0 - sq_dist[inside]))
        depths[~inside] = zc * np.exp(-config.falloff_power * (sq_dist[~inside] - 1.0))

    elif config.proxy_type == ProxyType.INVERTED_SHELL:
        u = (x - xc) / max(rx, 1e-6)
        v = (y - yc) / max(ry, 1e-6)
        sq_dist = u*u + v*v
        inside = sq_dist <= 1.0
        depths = np.zeros(N, dtype=np.float64)
        depths[inside] = zc - rz * np.sqrt(np.maximum(0.0, 1.0 - sq_dist[inside]))
        depths[~inside] = zc - rz

    elif config.proxy_type == ProxyType.PLANE:
        nx, ny, nz = config.plane_normal
        nz_safe = nz if abs(nz) > 1e-6 else 1.0
        depths = zc - (nx * (x - xc) + ny * (y - yc)) / nz_safe

    else:
        depths = np.full(N, zc, dtype=np.float64)

    # Add semantic base offset and intra-layer stack order delta
    depths += config.layer_z_offset * rz + config.stack_order_offset

    # Add optional localized feature bump (e.g. nose tip)
    if config.feature_bump_amplitude > 0.0:
        bx = (x - xc) ** 2 / (2.0 * max(config.feature_bump_sigma[0]**2, 1e-6))
        by = (y - yc) ** 2 / (2.0 * max(config.feature_bump_sigma[1]**2, 1e-6))
        depths += config.feature_bump_amplitude * np.exp(-(bx + by))

    return depths
```

### 5.2 Geometry Engine Normal & Curvature Algorithm (`src/geometry/geometry_engine.py`)

```python
def compute_mesh_normals_and_curvatures(
    mesh: Mesh,
    proxy_config: Optional[DepthProxyConfig] = None
) -> GeometryProperties:
    positions_2d = mesh.get_positions()
    depths = mesh.get_depths()
    N = len(positions_2d)
    
    if N == 0:
        return GeometryProperties(
            normals=np.zeros((0, 3)), tangents_u=np.zeros((0, 3)),
            tangents_v=np.zeros((0, 3)), mean_curvature=np.zeros(0),
            gaussian_curvature=np.zeros(0)
        )

    # 1. 3D vertex positions (N, 3)
    pos_3d = np.column_stack([positions_2d, depths])

    # 2. Analytical Normal Evaluation if proxy is supplied
    if proxy_config is not None and proxy_config.proxy_type == ProxyType.ELLIPSOID:
        xc, yc, zc = proxy_config.center
        rx, ry, rz = proxy_config.radii
        dx = pos_3d[:, 0] - xc
        dy = pos_3d[:, 1] - yc
        dz = pos_3d[:, 2] - zc
        
        # Implicit gradient: grad F = [2*dx/rx^2, 2*dy/ry^2, 2*dz/rz^2]
        nx = dx / (rx * rx)
        ny = dy / (ry * ry)
        nz = np.maximum(dz / (rz * rz), 1e-4) # ensure positive front orientation
        
        norms = np.sqrt(nx*nx + ny*ny + nz*nz)
        norms_safe = np.where(norms > 1e-12, norms, 1.0)
        normals = np.column_stack([nx / norms_safe, ny / norms_safe, nz / norms_safe])
        
        # Analytical Ellipsoid Curvatures
        nu = np.sqrt((dx**2)/(rx**4) + (dy**2)/(ry**4) + (dz**2)/(rz**4))
        nu_safe = np.where(nu > 1e-12, nu, 1.0)
        gauss_k = 1.0 / ((rx * ry * rz * (nu_safe ** 2)) ** 2)
        mean_h = 0.5 * nu_safe * ((1.0/rx**2) + (1.0/ry**2) + (1.0/rz**2) - (dx**2/rx**6 + dy**2/ry**6 + dz**2/rz**6)/(nu_safe**2))

    else:
        # 3. Discrete Mesh Normal & Curvature (Angle-Weighted)
        normals = np.zeros((N, 3), dtype=np.float64)
        if len(mesh.triangles) > 0:
            p0 = pos_3d[mesh.triangles[:, 0]]
            p1 = pos_3d[mesh.triangles[:, 1]]
            p2 = pos_3d[mesh.triangles[:, 2]]
            
            e1 = p1 - p0
            e2 = p2 - p0
            tri_normals = np.cross(e1, e2)
            tri_norms = np.linalg.norm(tri_normals, axis=1, keepdims=True)
            tri_norms_safe = np.where(tri_norms > 1e-12, tri_norms, 1.0)
            unit_tri_normals = tri_normals / tri_norms_safe
            
            # Accumulate on vertices
            for t_idx, (i, j, k) in enumerate(mesh.triangles):
                normals[i] += unit_tri_normals[t_idx]
                normals[j] += unit_tri_normals[t_idx]
                normals[k] += unit_tri_normals[t_idx]
                
            v_norms = np.linalg.norm(normals, axis=1, keepdims=True)
            v_norms_safe = np.where(v_norms > 1e-12, v_norms, 1.0)
            normals = normals / v_norms_safe
        else:
            normals[:, 2] = 1.0

        # Discrete Curvature via Normal Gradient across edges
        mean_h = np.zeros(N, dtype=np.float64)
        gauss_k = np.zeros(N, dtype=np.float64)
        if len(mesh.edges) > 0:
            edge_counts = np.zeros(N, dtype=np.float64)
            for i, j in mesh.edges:
                dp = np.linalg.norm(pos_3d[i] - pos_3d[j])
                if dp > 1e-6:
                    dn = np.linalg.norm(normals[i] - normals[j])
                    kappa = dn / dp
                    mean_h[i] += kappa
                    mean_h[j] += kappa
                    edge_counts[i] += 1
                    edge_counts[j] += 1
            nonzero = edge_counts > 0
            mean_h[nonzero] /= edge_counts[nonzero]

    # 4. Orthonormal Tangent Frame (Tu, Tv)
    nz = normals[:, 2]
    mask = np.abs(nz) < 0.999
    tangents_u = np.zeros((N, 3), dtype=np.float64)
    tangents_u[~mask] = [1.0, 0.0, 0.0]
    
    if np.any(mask):
        tx = normals[mask, 2]
        tz = -normals[mask, 0]
        norm_t = np.sqrt(tx*tx + tz*tz)
        norm_t_safe = np.where(norm_t > 1e-12, norm_t, 1.0)
        tangents_u[mask] = np.column_stack([tx / norm_t_safe, np.zeros(np.sum(mask)), tz / norm_t_safe])

    tangents_v = np.cross(normals, tangents_u)
    tv_norms = np.linalg.norm(tangents_v, axis=1, keepdims=True)
    tv_norms_safe = np.where(tv_norms > 1e-12, tv_norms, 1.0)
    tangents_v = tangents_v / tv_norms_safe

    return GeometryProperties(
        normals=normals,
        tangents_u=tangents_u,
        tangents_v=tangents_v,
        mean_curvature=mean_h,
        gaussian_curvature=gauss_k
    )
```

---

### 5.3 Comprehensive Edge Cases & Mitigation Matrix

| # | Potential Edge Case | Mathematical Hazard | Mitigation Strategy |
|---|---|---|---|
| 1 | **Proxy Boundary Singularity** ($u^2 + v^2 \ge 1.0$) | Division by zero ($\sqrt{1 - r^2} \to 0$) in explicit normal derivative | Compute normals using implicit gradient $\nabla F = \left(\frac{2u}{R_x}, \frac{2v}{R_y}, \frac{2z}{R_z}\right)^T$, eliminating the zero denominator. |
| 2 | **Degenerate / Sliver Triangles** in Mesh | $\mathbf{e}_1 \times \mathbf{e}_2 = \mathbf{0}$, producing `NaN` unit normal | Guard normalization with $\max(\|\mathbf{n}\|, 10^{-12})$, fallback to $[0, 0, 1]^T$ for degenerate faces. |
| 3 | **Layer Inversion / Clipping** during Yaw Turn | $\Delta Z'_{A, B} < 0$ causing bangs to clip behind forehead skin | Enforce minimum clearance $\Delta Z_{\text{nominal}}(A, B) \ge \delta_{\min} + \Delta x_{\max} \sin(30^\circ)$ during multi-layer stacking. |
| 4 | **Single-Pixel / 1D Layer** (e.g. 1x1 mask or thin hair strand) | $R_x \to 0$ or $R_y \to 0$, causing divide-by-zero in radial coordinate $u$ | Clamp proxy semi-axes $R_x, R_y \ge \max(0.01, \text{dim})$ and fallback to planar proxy. |
| 5 | **Pole Singularity in Tangent Basis** ($N_z \approx \pm 1.0$) | Cross product $\mathbf{N} \times [0, 1, 0]$ degenerates at the apex | Branch on $|N_z| \ge 0.999$ to select orthonormal basis $\mathbf{T}_u = [1, 0, 0]^T, \mathbf{T}_v = [0, 1, 0]^T$. |
| 6 | **Non-Descriptive Layer Names** (`Layer 1`, `Bitmap 2`) | Inability to determine proxy type via keyword regex | Employ spatial Bayesian bounding box classification (`SemanticClassifier.classify_spatial`) to infer proxy geometry. |

---

## 6. Comprehensive Test & Verification Strategy

To validate all mathematical invariants and numerical stability, the following unit and integration test suites are specified:

### 6.1 Unit Test Specifications

#### Test 1: Primitive Depth Proxy Invariants (`test_depth_proxy_primitives`)
- Verify that Ellipsoidal proxy at $(X_c, Y_c)$ attains exact peak depth $Z_c + R_z$.
- Verify that Ellipsoidal depth decreases monotonically with radial distance $r$.
- Verify that outside points ($r > 1.0$) decay smoothly without NaNs or negative numbers.
- Verify Cylindrical proxy invariance along the cylinder axis ($\frac{\partial Z}{\partial y} = 0$).
- Verify Planar proxy matches linear gradient $Z(x, y) = Z_c - \frac{n_x \Delta x + n_y \Delta y}{n_z}$.

#### Test 2: Global Depth Normalization & Multi-Layer Stacking (`test_depth_normalization_and_stacking`)
- Generate synthetic multi-layer character (`hair_front`, `eyes`, `face`, `hair_back`, `body`).
- Apply semantic depth stratification and global normalization.
- Assert all vertex depths satisfy $-1.0 \le z_i \le 1.0$.
- Assert strict depth ordering: $\bar{Z}(\text{hair\_front}) > \bar{Z}(\text{eyes}) > \bar{Z}(\text{face}) > \bar{Z}(\text{body}) > \bar{Z}(\text{hair\_back})$.

#### Test 3: Normal Vector Unit Length & Apex Orientation (`test_normals_unit_length`)
- Evaluate normals across a 1000-vertex ellipsoidal mesh.
- Assert $\|\mathbf{N}_i\| = 1.0 \pm 10^{-6}$ for all $i$.
- Assert normal at apex $(X_c, Y_c)$ equals $(0, 0, 1)^T$.
- Assert normal at lateral boundary $(X_c + R_x, Y_c)$ equals $(1, 0, 0)^T$.

#### Test 4: Numerical Derivative vs. Analytical Normal Verification (`test_normal_finite_differences`)
- Compare analytical normal $\mathbf{N}_{\text{analytic}}$ against central finite difference gradient:
  $$f_x(x, y) \approx \frac{Z(x + \epsilon, y) - Z(x - \epsilon, y)}{2\epsilon}, \quad f_y(x, y) \approx \frac{Z(x, y + \epsilon) - Z(x, y - \epsilon)}{2\epsilon}$$
- Assert relative error $\|\mathbf{N}_{\text{analytic}} - \mathbf{N}_{\text{num}}\| < 10^{-4}$.

#### Test 5: Tangent Basis Orthonormality (`test_tangent_basis_orthonormality`)
- For all vertices, verify $\mathbf{T}_u \cdot \mathbf{N} = 0$, $\mathbf{T}_v \cdot \mathbf{N} = 0$, $\mathbf{T}_u \cdot \mathbf{T}_v = 0$.
- Verify $\|\mathbf{T}_u\| = 1.0 \pm 10^{-6}$ and $\|\mathbf{T}_v\| = 1.0 \pm 10^{-6}$.
- Verify right-handed orientation $\mathbf{T}_u \times \mathbf{T}_v = \mathbf{N}$.

#### Test 6: Analytical vs. Discrete Curvature Benchmark (`test_curvature_sphere_benchmark`)
- Construct a spherical proxy ($R_x = R_y = R_z = R = 0.5$).
- Assert analytical Gaussian curvature $K = \frac{1}{R^2} = 4.0$ across the surface.
- Assert analytical Mean curvature $H = \frac{1}{R} = 2.0$ across the surface.

#### Test 7: Multi-Layer Non-Penetration Under 3D Rotation (`test_multilayer_nonpenetration_rotation`)
- Rotate multi-layer head across 9-keyform grid ($\theta_x \in \{-30^\circ, 0^\circ, +30^\circ\}, \theta_y \in \{-30^\circ, 0^\circ, +30^\circ\}$).
- For overlapping 2D regions of foreground `HairFront` and background `Face`, compute rotated 3D depths $P'_z(\text{HairFront}) - P'_z(\text{Face})$.
- Assert $P'_z(\text{HairFront}) > P'_z(\text{Face})$ strictly holds across all 9 keyforms (zero clipping).

---

## 7. Implementation Recommendations for Worker M2.1 & M2.2

1. **`src/depth/depth_model.py` Refactoring**:
   - Upgrade the current scalar `DepthModel` class into a robust vectorized engine.
   - Introduce `DepthProxyConfig` and `ProxyType` enums.
   - Implement `DepthGenerator.compute_proxy_depth_vectorized` with NumPy vectorization.
   - Implement `LayerDepthAssigner` to process `LayerCollection` and update all `Mesh` instances in place.
   - Enforce multi-layer non-penetration clearance during stack offset computation.
2. **`src/geometry/geometry_engine.py` Refactoring**:
   - Implement `GeometryEngine.compute_mesh_geometry` returning `GeometryProperties` (normals, tangents, mean/Gaussian curvature).
   - Implement implicit gradient computation for ellipsoids and cylinders to eliminate boundary singularities.
   - Implement angle-weighted discrete mesh normal accumulator for arbitrary organic meshes.
   - Implement `GeometryEngine.project_mesh` with weak perspective, perspective, and anime hybrid foreshortening modes.
3. **Seamless Integration**:
   - Directly consume `Mesh`, `LayerData`, `LayerCollection` from Milestone 1 without mutating interface contracts.
   - Provide clean inputs to `DeformationSolver` and `MassSpringConstraintSolver`.

---

**Report Author**: Explorer M2-1 (Depth Proxy & Differential Geometry Specialist)  
**Status**: Ready for Review & Implementation Delegation
