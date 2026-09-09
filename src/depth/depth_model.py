"""
src/depth/depth_model.py
Automated 3D Depth Proxy Modeling, Semantic Stratification, and Global Normalization.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Tuple, Dict, List, Optional, Any, Union
import numpy as np

from src.core.mesh import Mesh
from src.core.layer import LayerData, LayerCollection


class ProxyType(Enum):
    """Supported 3D geometric depth proxy primitives."""
    ELLIPSOIDAL = "ellipsoidal"
    ELLIPSOID = "ellipsoid"
    CYLINDRICAL = "cylindrical"
    CYLINDER = "cylinder"
    PLANAR = "planar"
    PLANE = "plane"
    INVERTED_SHELL = "inverted_shell"
    CONICAL_BUMP = "conical_bump"
    CONE_BUMP = "cone_bump"
    CONFORMING = "conforming"


@dataclass
class DepthProxyConfig:
    """Configuration parameters for generating depth fields from geometric proxies."""
    proxy_type: ProxyType = ProxyType.ELLIPSOIDAL
    center: Tuple[float, float, float] = (0.0, 0.0, 0.0)        # (Xc, Yc, Zc)
    radii: Tuple[float, float, float] = (0.6, 0.8, 0.4)          # (Rx, Ry, Rz)
    axis: Tuple[float, float] = (0.0, 1.0)                       # 2D axis direction for cylinder (dx, dy)
    plane_normal: Tuple[float, float, float] = (0.0, 0.0, 1.0)   # (nx, ny, nz) for planar proxy
    layer_z_offset: float = 0.0                                  # Semantic base Z-offset relative to Rz
    falloff_power: float = 2.0                                   # Smooth outer falloff exponent
    peripheral_taper: float = 0.40                               # Lateral ear compression strength
    stack_order_offset: float = 0.0                              # Fine intra-category stacking delta
    feature_bump_amplitude: float = 0.0                          # Local feature bump height
    feature_bump_sigma: Tuple[float, float] = (0.1, 0.1)         # (sigma_x, sigma_y) for bump
    feature_bump_center: Optional[Tuple[float, float]] = None    # Center (bx, by) for feature bump


class DepthModel:
    """
    Automated 3D Depth Proxy Engine.
    Computes depth fields z(x,y) for 2D meshes using geometric proxies,
    applies semantic layer stratification, ensures non-penetration clearance,
    and performs global depth normalization into [-1.0, 1.0].
    """

    # Semantic layer depth configuration matrix
    SEMANTIC_CATEGORY_PRESETS: Dict[str, Dict[str, Any]] = {
        "hair_front": {
            "proxy_type": ProxyType.ELLIPSOIDAL,
            "layer_z_offset": 0.65,
            "parallax_factor": 1.35,
            "stiffness": 0.20,
            "peripheral_taper": 0.20,
        },
        "accessories": {
            "proxy_type": ProxyType.PLANAR,
            "layer_z_offset": 0.50,
            "parallax_factor": 1.25,
            "stiffness": 0.85,
            "peripheral_taper": 0.0,
        },
        "eyebrows": {
            "proxy_type": ProxyType.ELLIPSOIDAL,
            "layer_z_offset": 0.38,
            "parallax_factor": 1.10,
            "stiffness": 0.70,
            "peripheral_taper": 0.30,
        },
        "nose": {
            "proxy_type": ProxyType.CONICAL_BUMP,
            "layer_z_offset": 0.32,
            "parallax_factor": 1.25,
            "stiffness": 0.95,
            "peripheral_taper": 0.0,
            "feature_bump_amplitude": 0.18,
            "feature_bump_sigma": (0.08, 0.12),
        },
        "eyes": {
            "proxy_type": ProxyType.ELLIPSOIDAL,
            "layer_z_offset": 0.25,
            "parallax_factor": 1.05,
            "stiffness": 0.80,
            "peripheral_taper": 0.35,
            "feature_bump_amplitude": 0.06,
            "feature_bump_sigma": (0.15, 0.15),
        },
        "mouth": {
            "proxy_type": ProxyType.ELLIPSOIDAL,
            "layer_z_offset": 0.20,
            "parallax_factor": 1.02,
            "stiffness": 0.75,
            "peripheral_taper": 0.35,
        },
        "face": {
            "proxy_type": ProxyType.ELLIPSOIDAL,
            "layer_z_offset": 0.00,
            "parallax_factor": 1.00,
            "stiffness": 0.50,
            "peripheral_taper": 0.40,
        },
        "hair_side": {
            "proxy_type": ProxyType.ELLIPSOIDAL,
            "layer_z_offset": -0.05,
            "parallax_factor": 0.95,
            "stiffness": 0.30,
            "peripheral_taper": 0.45,
        },
        "ears": {
            "proxy_type": ProxyType.ELLIPSOIDAL,
            "layer_z_offset": -0.15,
            "parallax_factor": 0.90,
            "stiffness": 0.60,
            "peripheral_taper": 0.50,
        },
        "body": {
            "proxy_type": ProxyType.CYLINDRICAL,
            "layer_z_offset": -0.35,
            "parallax_factor": 0.40,
            "stiffness": 0.90,
            "peripheral_taper": 0.0,
            "axis": (0.0, 1.0),
        },
        "neck": {
            "proxy_type": ProxyType.CYLINDRICAL,
            "layer_z_offset": -0.35,
            "parallax_factor": 0.40,
            "stiffness": 0.90,
            "peripheral_taper": 0.0,
            "axis": (0.0, 1.0),
        },
        "hair_back": {
            "proxy_type": ProxyType.INVERTED_SHELL,
            "layer_z_offset": -0.60,
            "parallax_factor": 0.70,
            "stiffness": 0.30,
            "peripheral_taper": 0.0,
        },
        "head": {
            "proxy_type": ProxyType.ELLIPSOIDAL,
            "layer_z_offset": 0.00,
            "parallax_factor": 1.00,
            "stiffness": 0.50,
            "peripheral_taper": 0.40,
        },
        "unknown": {
            "proxy_type": ProxyType.ELLIPSOIDAL,
            "layer_z_offset": 0.00,
            "parallax_factor": 1.00,
            "stiffness": 0.50,
            "peripheral_taper": 0.40,
        },
    }

    def __init__(
        self,
        center: Tuple[float, float] = (0.0, 0.0),
        radii: Tuple[float, float, float] = (0.6, 0.8, 0.4),
        z_center: float = 0.0
    ):
        self.center_x, self.center_y = float(center[0]), float(center[1])
        self.radius_x, self.radius_y, self.radius_z = float(radii[0]), float(radii[1]), float(radii[2])
        self.z_center = float(z_center)

    @property
    def head_center(self) -> Tuple[float, float, float]:
        return (self.center_x, self.center_y, self.z_center)

    @property
    def head_radii(self) -> Tuple[float, float, float]:
        return (self.radius_x, self.radius_y, self.radius_z)

    def get_proxy_config_for_category(
        self,
        category: str,
        stack_index: int = 0,
        total_in_stack: int = 1
    ) -> DepthProxyConfig:
        """
        Creates an automated DepthProxyConfig tailored to semantic layer category.
        """
        cat_key = category.lower().strip()
        preset = self.SEMANTIC_CATEGORY_PRESETS.get(cat_key, self.SEMANTIC_CATEGORY_PRESETS["unknown"])

        ptype = preset.get("proxy_type", ProxyType.ELLIPSOIDAL)
        if isinstance(ptype, str):
            ptype = ProxyType(ptype)

        # Intra-category stacking offset
        stack_offset = 0.0
        if total_in_stack > 1:
            stack_offset = (stack_index - (total_in_stack - 1) / 2.0) * (0.02 * self.radius_z)

        bump_amp = preset.get("feature_bump_amplitude", 0.0) * self.radius_z
        bump_sigma_factors = preset.get("feature_bump_sigma", (0.1, 0.1))
        bump_sigma = (bump_sigma_factors[0] * self.radius_x, bump_sigma_factors[1] * self.radius_y)

        return DepthProxyConfig(
            proxy_type=ptype,
            center=(self.center_x, self.center_y, self.z_center),
            radii=(self.radius_x, self.radius_y, self.radius_z),
            axis=preset.get("axis", (0.0, 1.0)),
            plane_normal=(0.0, 0.0, 1.0),
            layer_z_offset=float(preset.get("layer_z_offset", 0.0)),
            falloff_power=2.0,
            peripheral_taper=float(preset.get("peripheral_taper", 0.40)),
            stack_order_offset=stack_offset,
            feature_bump_amplitude=bump_amp,
            feature_bump_sigma=bump_sigma,
            feature_bump_center=preset.get("feature_bump_center", None)
        )

    def compute_proxy_depth_vectorized(
        self,
        positions: np.ndarray,
        config: DepthProxyConfig
    ) -> np.ndarray:
        """
        Computes 3D depth field z(x, y) for an array of 2D vertex positions (N, 2).
        """
        N = len(positions)
        if N == 0:
            return np.zeros(0, dtype=np.float64)

        pos_arr = np.asarray(positions, dtype=np.float64)
        x = pos_arr[:, 0]
        y = pos_arr[:, 1]
        xc, yc, zc = config.center
        rx = max(1e-5, config.radii[0])
        ry = max(1e-5, config.radii[1])
        rz = max(1e-5, config.radii[2])

        ptype = config.proxy_type
        if isinstance(ptype, str):
            ptype = ProxyType(ptype)

        depths = np.zeros(N, dtype=np.float64)

        if ptype in (ProxyType.ELLIPSOIDAL, ProxyType.ELLIPSOID, ProxyType.CONICAL_BUMP, ProxyType.CONE_BUMP, ProxyType.CONFORMING):
            u = (x - xc) / rx
            v = (y - yc) / ry
            sq_dist = u * u + v * v

            inside = sq_dist <= 1.0
            depths[inside] = zc + rz * np.sqrt(np.maximum(0.0, 1.0 - sq_dist[inside]))
            depths[~inside] = zc * np.exp(-config.falloff_power * (sq_dist[~inside] - 1.0))

            # Peripheral lateral taper (ear occlusion falloff)
            if config.peripheral_taper > 0.0:
                u_abs = np.abs(u)
                taper_mask = inside & (u_abs > 0.6)
                if np.any(taper_mask):
                    t = (u_abs[taper_mask] - 0.6) / 0.4
                    depths[taper_mask] -= config.peripheral_taper * rz * (t ** 2)
                    depths[taper_mask] = np.maximum(zc, depths[taper_mask])

        elif ptype in (ProxyType.CYLINDRICAL, ProxyType.CYLINDER):
            axis_len = np.hypot(config.axis[0], config.axis[1])
            dx = config.axis[0] / axis_len if axis_len > 1e-6 else 0.0
            dy = config.axis[1] / axis_len if axis_len > 1e-6 else 1.0

            # Perpendicular distance to cylinder axis
            p_perp = -(x - xc) * dy + (y - yc) * dx
            u = p_perp / rx
            sq_dist = u * u

            inside = sq_dist <= 1.0
            depths[inside] = zc + rz * np.sqrt(np.maximum(0.0, 1.0 - sq_dist[inside]))
            depths[~inside] = zc * np.exp(-config.falloff_power * (sq_dist[~inside] - 1.0))

        elif ptype == ProxyType.INVERTED_SHELL:
            u = (x - xc) / rx
            v = (y - yc) / ry
            sq_dist = u * u + v * v

            inside = sq_dist <= 1.0
            depths[inside] = zc - rz * np.sqrt(np.maximum(0.0, 1.0 - sq_dist[inside]))
            depths[~inside] = zc - rz

        elif ptype in (ProxyType.PLANAR, ProxyType.PLANE):
            nx, ny, nz = config.plane_normal
            nz_safe = nz if abs(nz) > 1e-6 else 1.0
            depths = zc - (nx * (x - xc) + ny * (y - yc)) / nz_safe

        else:
            depths = np.full(N, zc, dtype=np.float64)

        # Apply semantic base Z-offset and stack order offset
        depths += config.layer_z_offset * rz + config.stack_order_offset

        # Localized feature bump (e.g. nose tip, eye bulge)
        if config.feature_bump_amplitude != 0.0:
            bx_center, by_center = config.feature_bump_center if config.feature_bump_center is not None else (xc, yc)
            sigma_x = max(1e-5, config.feature_bump_sigma[0])
            sigma_y = max(1e-5, config.feature_bump_sigma[1])
            dist_sq = ((x - bx_center) ** 2) / (2.0 * sigma_x ** 2) + ((y - by_center) ** 2) / (2.0 * sigma_y ** 2)
            depths += config.feature_bump_amplitude * np.exp(-dist_sq)

        return depths

    def compute_ellipsoid_depth(self, x: float, y: float) -> float:
        """
        Calculates front-facing ellipsoid depth z at normalized position (x, y).
        Returns z in range [0, Rz].
        """
        pos = np.array([[x, y]], dtype=np.float64)
        config = DepthProxyConfig(
            proxy_type=ProxyType.ELLIPSOIDAL,
            center=(self.center_x, self.center_y, self.z_center),
            radii=(self.radius_x, self.radius_y, self.radius_z),
            peripheral_taper=0.0,
            layer_z_offset=0.0
        )
        return float(self.compute_proxy_depth_vectorized(pos, config)[0])

    def apply_ellipsoid_to_mesh(self, mesh: Mesh, category: Optional[str] = None):
        """
        Updates depth field for all vertices using the ellipsoid proxy,
        applying regional Z-offsets and peripheral stratification for occlusion.
        """
        cat = category if category is not None else getattr(mesh, "layer_id", "Face")
        config = self.get_proxy_config_for_category(cat)
        positions = mesh.get_positions()
        if len(positions) == 0:
            return
        depths = self.compute_proxy_depth_vectorized(positions, config)
        mesh.set_depths(depths)

    def apply_to_mesh(
        self,
        mesh: Mesh,
        category: str = "face",
        stack_index: int = 0,
        total_in_stack: int = 1
    ):
        """
        Applies automated depth proxy computation to a single mesh in-place.
        """
        config = self.get_proxy_config_for_category(category, stack_index, total_in_stack)
        positions = mesh.get_positions()
        if len(positions) == 0:
            return
        depths = self.compute_proxy_depth_vectorized(positions, config)
        mesh.set_depths(depths)

    def apply_to_layer_collection(
        self,
        layer_collection: LayerCollection,
        mesh_map: Dict[str, Mesh],
        enforce_clearance: bool = True,
        delta_min: float = 0.02,
        normalize_global: bool = True
    ):
        """
        Processes an entire LayerCollection and dictionary of Mesh instances:
        1. Categorizes layers and evaluates proxy depth fields.
        2. Applies layer clearance stratification to guarantee non-penetration.
        3. Globally normalizes all depth fields into [-1.0, 1.0].
        """
        # Group layers by semantic category for intra-stack indexing
        cat_layers: Dict[str, List[LayerData]] = {}
        for layer in layer_collection.layers:
            cat = layer.category.lower().strip()
            if cat not in cat_layers:
                cat_layers[cat] = []
            cat_layers[cat].append(layer)

        # 1. Evaluate depth for each mesh
        for cat, layers in cat_layers.items():
            total = len(layers)
            for idx, layer in enumerate(layers):
                mesh = mesh_map.get(layer.layer_id) or mesh_map.get(layer.name)
                if mesh is not None:
                    self.apply_to_mesh(mesh, category=cat, stack_index=idx, total_in_stack=total)

        # 2. Enforce layer clearance stratification under 30° rotation
        if enforce_clearance:
            # Sorted back-to-front by nominal semantic offset
            sorted_layers = sorted(
                layer_collection.layers,
                key=lambda l: self.SEMANTIC_CATEGORY_PRESETS.get(l.category.lower(), {}).get("layer_z_offset", 0.0)
            )
            for i in range(len(sorted_layers) - 1):
                l_back = sorted_layers[i]
                l_front = sorted_layers[i + 1]
                m_back = mesh_map.get(l_back.layer_id) or mesh_map.get(l_back.name)
                m_front = mesh_map.get(l_front.layer_id) or mesh_map.get(l_front.name)
                if m_back is not None and m_front is not None:
                    d_back = m_back.get_depths()
                    d_front = m_front.get_depths()
                    if len(d_back) > 0 and len(d_front) > 0:
                        # Required clearance: delta_min + delta_x_max * sin(30°)
                        # In normalized space delta_x_max <= 1.0, sin(30°) = 0.5
                        req_gap = delta_min + 0.5 * 0.05
                        mean_back = float(np.mean(d_back))
                        mean_front = float(np.mean(d_front))
                        if mean_front - mean_back < req_gap:
                            shift = (mean_back + req_gap) - mean_front
                            m_front.set_depths(d_front + shift)

        # 3. Global normalization to [-1.0, 1.0]
        if normalize_global:
            all_meshes = [m for m in mesh_map.values() if len(m.vertices) > 0]
            self.normalize_depths(all_meshes)

    def normalize_depths(self, meshes: List[Mesh]):
        """
        Globally normalizes depth fields across all meshes into [-1.0, 1.0]
        symmetrically centered around the rotation pivot Z_c.
        """
        all_depths = []
        for m in meshes:
            d = m.get_depths()
            if len(d) > 0:
                all_depths.append(d)

        if not all_depths:
            return

        concat = np.concatenate(all_depths)
        z_min = float(np.min(concat))
        z_max = float(np.max(concat))
        zc = self.z_center

        scale_z = max(abs(z_max - zc), abs(z_min - zc), 1e-4)

        for m in meshes:
            d = m.get_depths()
            if len(d) > 0:
                norm_d = (d - zc) / scale_z
                norm_d = np.clip(norm_d, -1.0, 1.0)
                m.set_depths(norm_d)

    def apply_depth_brush(
        self,
        mesh: Mesh,
        brush_pos: Tuple[float, float],
        radius: float = 0.2,
        intensity: float = 0.05,
        additive: bool = True
    ):
        """
        Applies a localized gaussian depth brush edit to mesh vertices near brush_pos.
        """
        bx, by = brush_pos
        for vtx in mesh.vertices:
            dist = np.hypot(vtx.position[0] - bx, vtx.position[1] - by)
            if dist < radius:
                factor = np.exp(- (dist / (0.5 * radius)) ** 2)
                delta = intensity * factor
                if additive:
                    vtx.depth += delta
                else:
                    vtx.depth = max(0.0, vtx.depth - delta)
