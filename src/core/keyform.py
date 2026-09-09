"""
src/core/keyform.py
Core data structures for Live2D Cubism Keyform Tensors, Deformers, and Parameter Bindings.
Supports official Live2D Cubism deformer hierarchy:
RootPart -> RotationDeformer (Angle Z) -> WarpDeformer (Angle X/Y) -> ArtMeshes.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import numpy as np


@dataclass
class ParameterBinding:
    """
    Represents a Live2D parameter binding with range and keyform divisions.
    """
    param_id: str                              # e.g. "ParamAngleX", "ParamAngleY", "ParamAngleZ"
    min_val: float = -30.0                     # Minimum parameter value
    default_val: float = 0.0                   # Default / neutral parameter value
    max_val: float = 30.0                      # Maximum parameter value
    key_values: List[float] = field(default_factory=lambda: [-30.0, 0.0, 30.0])
    name: str = ""                             # Human-readable display name (e.g. "Angle X", "角度 X")

    @property
    def key_count(self) -> int:
        return len(self.key_values)


@dataclass
class WarpDeformer:
    """
    Live2D Warp Deformer (曲面デフォーマ).
    Controls 2D keyform grid deformations (e.g. ParamAngleX x ParamAngleY) applied to child deformers or ArtMeshes.
    """
    deformer_id: str = "Warp_Head"
    parent_part_id: str = "PartRoot"
    parent_deformer_id: Optional[str] = "Rotation_Head"
    parameter_ids: List[str] = field(default_factory=lambda: ["ParamAngleX", "ParamAngleY"])
    grid_rows: int = 4
    grid_cols: int = 4
    base_vertices: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), dtype=np.float32)) # shape: ((rows+1)*(cols+1), 2)
    keyform_keys: List[Tuple[float, ...]] = field(default_factory=list)
    deformed_positions: Dict[Tuple[float, ...], np.ndarray] = field(default_factory=dict)
    opacity: float = 1.0

    @property
    def total_grid_vertices(self) -> int:
        if len(self.base_vertices) > 0:
            return len(self.base_vertices)
        return (self.grid_rows + 1) * (self.grid_cols + 1)

    def add_keyform(self, key_tuple: Tuple[float, ...], positions: np.ndarray) -> None:
        pos_arr = np.asarray(positions, dtype=np.float32)
        if len(self.base_vertices) > 0 and pos_arr.shape != self.base_vertices.shape:
            raise ValueError(f"WarpDeformer positions shape {pos_arr.shape} != base grid shape {self.base_vertices.shape}")
        self.deformed_positions[key_tuple] = pos_arr
        if key_tuple not in self.keyform_keys:
            self.keyform_keys.append(key_tuple)

    def get_keyform_position(self, key_tuple: Tuple[float, ...]) -> np.ndarray:
        return self.deformed_positions.get(key_tuple, self.base_vertices)


@dataclass
class RotationDeformer:
    """
    Live2D Rotation Deformer (回転デフォーマ).
    Controls 2D rigid rotation/origin/scale keyforms (e.g. ParamAngleZ) applied to child deformers or ArtMeshes.
    """
    deformer_id: str = "Rotation_Head"
    parent_part_id: str = "PartRoot"
    parent_deformer_id: Optional[str] = None
    parameter_ids: List[str] = field(default_factory=lambda: ["ParamAngleZ"])
    base_angle: float = 0.0
    origin_x: float = 0.0
    origin_y: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    keyform_keys: List[Tuple[float, ...]] = field(default_factory=list)
    angles: Dict[Tuple[float, ...], float] = field(default_factory=dict)     # Angle in degrees for each keyform
    origins: Dict[Tuple[float, ...], Tuple[float, float]] = field(default_factory=dict) # (origin_x, origin_y)
    scales: Dict[Tuple[float, ...], Tuple[float, float]] = field(default_factory=dict)   # (scale_x, scale_y)
    opacities: Dict[Tuple[float, ...], float] = field(default_factory=dict)  # Opacity for each keyform

    def add_keyform(
        self,
        key_tuple: Tuple[float, ...],
        angle: float = 0.0,
        origin: Optional[Tuple[float, float]] = None,
        scale: Optional[Tuple[float, float]] = None,
        opacity: float = 1.0
    ) -> None:
        if key_tuple not in self.keyform_keys:
            self.keyform_keys.append(key_tuple)
        self.angles[key_tuple] = float(angle)
        self.origins[key_tuple] = origin if origin is not None else (self.origin_x, self.origin_y)
        self.scales[key_tuple] = scale if scale is not None else (self.scale_x, self.scale_y)
        self.opacities[key_tuple] = float(opacity)


WarpDeformerData = WarpDeformer
RotationDeformerData = RotationDeformer


@dataclass
class DrawableKeyforms:


    """
    Keyform deformation data for a single drawable Live2D mesh (ArtMesh).
    """
    drawable_id: str                                         # e.g. "ArtMesh_Face", "ArtMesh_HairFront"
    texture_index: int = 0                                   # Texture atlas page index (default 0)
    base_vertices: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), dtype=np.float32))
    triangles: np.ndarray = field(default_factory=lambda: np.zeros((0, 3), dtype=np.int32))
    uvs_atlas: np.ndarray = field(default_factory=lambda: np.zeros((0, 2), dtype=np.float32))
    uvs_local: Optional[np.ndarray] = None                   # Layer-local UVs
    parameter_ids: List[str] = field(default_factory=list)   # Parameter bindings (empty when parented to deformer)
    keyform_keys: List[Tuple[float, ...]] = field(default_factory=list)
    deformed_positions: Dict[Tuple[float, ...], np.ndarray] = field(default_factory=dict)
    opacity: float = 1.0                                     # Base opacity
    draw_order: int = 500                                    # Live2D draw order (0-1000)
    culling: bool = False                                    # Double-sided vs backface culled
    blend_mode: int = 0                                      # 0: Normal, 1: Additive, 2: Multiply
    mask_drawable_ids: List[str] = field(default_factory=list) # Clipping mask references
    parent_deformer_id: Optional[str] = "Warp_Head"          # Parent deformer in Live2D hierarchy
    parent_part_id: str = "PartRoot"                         # Parent part in Live2D hierarchy

    def add_keyform(self, key_tuple: Tuple[float, ...], positions: np.ndarray) -> None:
        """Register deformed positions (N, 2) for a given parameter key tuple."""
        pos_arr = np.asarray(positions, dtype=np.float32)
        if len(self.base_vertices) > 0 and pos_arr.shape != self.base_vertices.shape:
            raise ValueError(f"Keyform positions shape {pos_arr.shape} != base vertices shape {self.base_vertices.shape}")
        self.deformed_positions[key_tuple] = pos_arr
        if key_tuple not in self.keyform_keys:
            self.keyform_keys.append(key_tuple)

    def get_keyform_position(self, key_tuple: Tuple[float, ...]) -> np.ndarray:
        """Retrieve keyform position with fallback to base_vertices."""
        return self.deformed_positions.get(key_tuple, self.base_vertices)

    def interpolate_position(self, param_values: Dict[str, float]) -> np.ndarray:
        """
        Multidimensional piecewise bilinear/linear interpolation across keyforms.
        """
        if len(self.deformed_positions) == 0:
            return self.base_vertices.copy()
        
        # If single parameter
        if len(self.parameter_ids) == 1:
            pid = self.parameter_ids[0]
            val = param_values.get(pid, 0.0)
            sorted_keys = sorted(self.deformed_positions.keys(), key=lambda k: k[0])
            if not sorted_keys:
                return self.base_vertices.copy()
            if val <= sorted_keys[0][0]:
                return self.deformed_positions[sorted_keys[0]].copy()
            if val >= sorted_keys[-1][0]:
                return self.deformed_positions[sorted_keys[-1]].copy()
            for i in range(len(sorted_keys) - 1):
                k0, k1 = sorted_keys[i][0], sorted_keys[i+1][0]
                if k0 <= val <= k1:
                    t = (val - k0) / (k1 - k0 + 1e-12)
                    p0 = self.deformed_positions[sorted_keys[i]]
                    p1 = self.deformed_positions[sorted_keys[i+1]]
                    return (1.0 - t) * p0 + t * p1

        # Multi-parameter interpolation (e.g. 2D AngleX, AngleY)
        if len(self.parameter_ids) == 2:
            px_id, py_id = self.parameter_ids[0], self.parameter_ids[1]
            vx = param_values.get(px_id, 0.0)
            vy = param_values.get(py_id, 0.0)
            
            # Find nearest or exact match
            exact_key = (float(vx), float(vy))
            if exact_key in self.deformed_positions:
                return self.deformed_positions[exact_key].copy()

            # Distance-weighted inverse distance weighting fallback
            weights = []
            positions = []
            for k, pos in self.deformed_positions.items():
                kx, ky = k[0], k[1]
                dist = np.hypot(vx - kx, vy - ky)
                if dist < 1e-5:
                    return pos.copy()
                w = 1.0 / (dist ** 2)
                weights.append(w)
                positions.append(pos)

            total_w = sum(weights)
            res = np.zeros_like(self.base_vertices, dtype=np.float32)
            for w, pos in zip(weights, positions):
                res += (w / total_w) * pos
            return res

        # Default fallback
        return self.base_vertices.copy()


@dataclass
class KeyformTable:
    """
    Master keyform table across all parameters, deformers, and drawables for Live2D model export.
    """
    parameters: List[ParameterBinding] = field(default_factory=list)
    drawables: List[DrawableKeyforms] = field(default_factory=list)
    parts: List[str] = field(default_factory=lambda: ["PartRoot"])
    warp_deformers: List[WarpDeformer] = field(default_factory=list)
    rotation_deformers: List[RotationDeformer] = field(default_factory=list)
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

    def get_warp_deformer(self, deformer_id: str) -> Optional[WarpDeformer]:
        for w in self.warp_deformers:
            if w.deformer_id == deformer_id:
                return w
        return None

    def get_rotation_deformer(self, deformer_id: str) -> Optional[RotationDeformer]:
        for r in self.rotation_deformers:
            if r.deformer_id == deformer_id:
                return r
        return None

    def add_drawable(self, drawable: DrawableKeyforms) -> None:
        self.drawables.append(drawable)

    def add_parameter(self, param: ParameterBinding) -> None:
        self.parameters.append(param)

    def add_warp_deformer(self, warp: WarpDeformer) -> None:
        self.warp_deformers.append(warp)

    def add_rotation_deformer(self, rot: RotationDeformer) -> None:
        self.rotation_deformers.append(rot)

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Structural verification for Live2D MOC3 export compatibility.
        """
        errors = []
        if len(self.parameters) == 0:
            errors.append("KeyformTable has no parameters defined.")
        if len(self.drawables) == 0:
            errors.append("KeyformTable has no drawables defined.")
        
        # Validate Drawables
        for d in self.drawables:
            if len(d.base_vertices) == 0:
                errors.append(f"Drawable '{d.drawable_id}' has 0 base vertices.")
            elif len(d.base_vertices) > 65535:
                errors.append(f"Drawable '{d.drawable_id}' vertex count ({len(d.base_vertices)}) exceeds Live2D uint16 limit (65535).")
            if len(d.triangles) == 0:
                errors.append(f"Drawable '{d.drawable_id}' has 0 triangles.")
            else:
                if np.any(d.triangles < 0) or np.any(d.triangles >= len(d.base_vertices)):
                    errors.append(f"Drawable '{d.drawable_id}' contains out-of-range triangle indices for {len(d.base_vertices)} vertices.")
                elif np.any(d.triangles > 65535):
                    errors.append(f"Drawable '{d.drawable_id}' contains triangle index exceeding uint16 limit (65535).")
            if len(d.uvs_atlas) != len(d.base_vertices):
                errors.append(f"Drawable '{d.drawable_id}' atlas UV count ({len(d.uvs_atlas)}) != vertex count ({len(d.base_vertices)}).")
            if np.any(np.isnan(d.uvs_atlas)) or np.any(np.isinf(d.uvs_atlas)):
                errors.append(f"Drawable '{d.drawable_id}' atlas UVs contain NaN/Inf.")
            elif np.any(d.uvs_atlas < -1e-4) or np.any(d.uvs_atlas > 1.0 + 1e-4):
                errors.append(f"Drawable '{d.drawable_id}' atlas UVs exceed [0.0, 1.0].")
            for key, pos in d.deformed_positions.items():
                if pos.shape != d.base_vertices.shape:
                    errors.append(f"Drawable '{d.drawable_id}' keyform {key} shape {pos.shape} != base {d.base_vertices.shape}.")
                if np.isnan(pos).any() or np.isinf(pos).any():
                    errors.append(f"Drawable '{d.drawable_id}' keyform {key} contains NaN/Inf.")

        # Validate Warp Deformers
        for w in self.warp_deformers:
            if w.grid_rows < 1 or w.grid_cols < 1:
                errors.append(f"WarpDeformer '{w.deformer_id}' has invalid grid dimensions ({w.grid_rows}x{w.grid_cols}).")
            for key, pos in w.deformed_positions.items():
                if len(w.base_vertices) > 0 and pos.shape != w.base_vertices.shape:
                    errors.append(f"WarpDeformer '{w.deformer_id}' keyform {key} shape {pos.shape} != base grid {w.base_vertices.shape}.")
                if np.isnan(pos).any() or np.isinf(pos).any():
                    errors.append(f"WarpDeformer '{w.deformer_id}' keyform {key} contains NaN/Inf.")

        # Validate Rotation Deformers
        for r in self.rotation_deformers:
            for key, ang in r.angles.items():
                if np.isnan(ang) or np.isinf(ang):
                    errors.append(f"RotationDeformer '{r.deformer_id}' keyform {key} angle contains NaN/Inf.")

        return len(errors) == 0, errors
