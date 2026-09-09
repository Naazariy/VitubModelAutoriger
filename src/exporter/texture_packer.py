"""
src/exporter/texture_packer.py
Production-Grade MaxRects Power-of-Two 2D Texture Atlas Packer & UV Remapper for Live2D Cubism.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import List, Tuple, Dict, Optional, Any, Union
import numpy as np
from PIL import Image

try:
    import scipy.ndimage
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from src.core.layer import LayerData, LayerCollection
from src.core.mesh import Mesh
from src.core.keyform import DrawableKeyforms


class PackingHeuristic(Enum):
    """MaxRects placement heuristic selection."""
    BSSF = "BestShortSideFit"
    BLSF = "BestLongSideFit"
    BAF = "BestAreaFit"
    BL = "BottomLeft"
    CP = "ContactPoint"


class SortOrder(Enum):
    """Sorting strategy prior to bin packing."""
    MAX_SIDE_DESC = "max_side_desc"
    AREA_DESC = "area_desc"
    HEIGHT_DESC = "height_desc"
    WIDTH_DESC = "width_desc"
    NONE = "none"


@dataclass
class Rect:
    """Represents a 2D integer rectangle in pixel space."""
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h

    def contains(self, other: 'Rect') -> bool:
        """Returns True if this rectangle fully encloses the other rectangle."""
        return (
            self.x <= other.x and
            self.y <= other.y and
            self.right >= other.right and
            self.bottom >= other.bottom
        )

    def intersects(self, other: 'Rect') -> bool:
        """Returns True if this rectangle overlaps with the other rectangle."""
        return not (
            self.right <= other.x or
            other.right <= self.x or
            self.bottom <= other.y or
            other.bottom <= self.y
        )


@dataclass
class PackedLayer:
    """Metadata representing a single packed layer's placement within the texture atlas."""
    layer_id: str
    page_index: int
    x: int
    y: int
    width: int
    height: int
    uv_rect: Tuple[float, float, float, float]  # (u_min, v_min, u_max, v_max) in [0, 1]
    rotated: bool = False


# Alias for compatibility with analysis specs
LayerPlacement = PackedLayer


@dataclass
class PackingStats:
    """Statistical summary of packing efficiency and atlas layout."""
    total_layers: int
    num_pages: int
    page_dimensions: List[Tuple[int, int]]
    total_layer_area: int
    total_atlas_area: int
    efficiency: float


@dataclass
class PackingConfig:
    """Configuration options for texture atlas packing."""
    max_atlas_size: int = 4096
    min_atlas_size: int = 512
    padding: int = 4
    bleed_radius: int = 2
    heuristic: PackingHeuristic = PackingHeuristic.BSSF
    sort_order: SortOrder = SortOrder.MAX_SIDE_DESC
    allow_rotation: bool = False
    power_of_two: bool = True
    square: bool = True
    flip_v: bool = False
    crop_transparent: bool = False


@dataclass
class PackingResult:
    """Complete bundle returned by TextureAtlasPacker."""
    pages: List[np.ndarray]                                      # RGBA (H, W, 4) uint8 arrays per page
    placements: Dict[str, PackedLayer]                           # Layer ID -> PackedLayer
    uv_rects: Dict[str, Tuple[float, float, float, float]]       # Layer ID -> (u_min, v_min, u_max, v_max)
    remapped_meshes: Dict[str, Mesh] = field(default_factory=dict)
    drawables: List[DrawableKeyforms] = field(default_factory=list)
    stats: Optional[PackingStats] = None

    @property
    def primary_atlas(self) -> np.ndarray:
        """Returns the primary (page 0) texture atlas RGBA array."""
        if self.pages:
            return self.pages[0]
        return np.zeros((512, 512, 4), dtype=np.uint8)

    @property
    def primary_atlas_image(self) -> Image.Image:
        """Returns PIL Image of page 0 atlas."""
        return Image.fromarray(self.primary_atlas)


class MaxRectsBin:
    """
    Maximal Rectangles (MaxRects) 2D bin packing engine for a single texture page.
    Maintains a list of maximal free rectangles, splits them upon placement,
    and prunes non-maximal sub-rectangles.
    """

    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.free_rectangles: List[Rect] = [Rect(0, 0, width, height)]
        self.used_rectangles: List[Rect] = []

    def score_rect(
        self, width: int, height: int, free_rect: Rect, method: PackingHeuristic
    ) -> Tuple[float, float]:
        """Calculates placement score according to heuristic rule."""
        if free_rect.w < width or free_rect.h < height:
            return (float('inf'), float('inf'))

        rem_w = free_rect.w - width
        rem_h = free_rect.h - height

        if method == PackingHeuristic.BSSF:
            score1 = min(rem_w, rem_h)
            score2 = max(rem_w, rem_h)
        elif method == PackingHeuristic.BLSF:
            score1 = max(rem_w, rem_h)
            score2 = min(rem_w, rem_h)
        elif method == PackingHeuristic.BAF:
            score1 = free_rect.w * free_rect.h - width * height
            score2 = min(rem_w, rem_h)
        elif method == PackingHeuristic.BL:
            score1 = free_rect.y + height
            score2 = free_rect.x
        else:
            score1 = min(rem_w, rem_h)
            score2 = max(rem_w, rem_h)

        return (float(score1), float(score2))

    def find_position_for_new_node(
        self,
        width: int,
        height: int,
        method: PackingHeuristic = PackingHeuristic.BSSF,
        allow_rotation: bool = False
    ) -> Tuple[Optional[Rect], bool]:
        """
        Finds the optimal free rectangle position for an item of size (width, height).
        """
        best_rect: Optional[Rect] = None
        best_score1 = float('inf')
        best_score2 = float('inf')
        best_rotated = False

        for free_rect in self.free_rectangles:
            # Unrotated check
            s1, s2 = self.score_rect(width, height, free_rect, method)
            if s1 < best_score1 or (s1 == best_score1 and s2 < best_score2):
                best_score1 = s1
                best_score2 = s2
                best_rect = Rect(free_rect.x, free_rect.y, width, height)
                best_rotated = False

            # Rotated check
            if allow_rotation and width != height:
                s1_rot, s2_rot = self.score_rect(height, width, free_rect, method)
                if s1_rot < best_score1 or (s1_rot == best_score1 and s2_rot < best_score2):
                    best_score1 = s1_rot
                    best_score2 = s2_rot
                    best_rect = Rect(free_rect.x, free_rect.y, height, width)
                    best_rotated = True

        return best_rect, best_rotated

    def place_rect(self, node: Rect) -> None:
        """
        Places a rectangle, splitting overlapping free rectangles and pruning redundant ones.
        """
        num_free = len(self.free_rectangles)
        i = 0
        while i < num_free:
            if self._split_free_node(self.free_rectangles[i], node):
                self.free_rectangles.pop(i)
                num_free -= 1
            else:
                i += 1

        self._prune_free_list()
        self.used_rectangles.append(node)

    def _split_free_node(self, free_node: Rect, used_node: Rect) -> bool:
        """Splits free_node if used_node intersects it, adding up to 4 sub-rectangles."""
        if not free_node.intersects(used_node):
            return False

        # Top sub-rectangle
        if used_node.y > free_node.y and used_node.y < free_node.bottom:
            self.free_rectangles.append(
                Rect(free_node.x, free_node.y, free_node.w, used_node.y - free_node.y)
            )

        # Bottom sub-rectangle
        if used_node.bottom < free_node.bottom:
            self.free_rectangles.append(
                Rect(free_node.x, used_node.bottom, free_node.w, free_node.bottom - used_node.bottom)
            )

        # Left sub-rectangle
        if used_node.x > free_node.x and used_node.x < free_node.right:
            self.free_rectangles.append(
                Rect(free_node.x, free_node.y, used_node.x - free_node.x, free_node.h)
            )

        # Right sub-rectangle
        if used_node.right < free_node.right:
            self.free_rectangles.append(
                Rect(used_node.right, free_node.y, free_node.right - used_node.right, free_node.h)
            )

        return True

    def _prune_free_list(self) -> None:
        """Removes non-maximal free rectangles that are completely contained within other free rectangles."""
        i = 0
        while i < len(self.free_rectangles):
            j = i + 1
            while j < len(self.free_rectangles):
                if self.free_rectangles[j].contains(self.free_rectangles[i]):
                    self.free_rectangles.pop(i)
                    i -= 1
                    break
                if self.free_rectangles[i].contains(self.free_rectangles[j]):
                    self.free_rectangles.pop(j)
                else:
                    j += 1
            i += 1


class TextureAtlasPacker:
    """
    Production MaxRects Texture Atlas Packer for Live2D Cubism Models:
    - Dynamic Power-of-Two (POT) atlas dimensions (512..8192).
    - MaxRects-BSSF bin packing with border padding.
    - Edge color bleeding / Voronoi dilation to prevent bilinear interpolation fringe seams.
    - Global atlas UV coordinate remapping [0.0, 1.0].
    """

    @staticmethod
    def next_power_of_two(val: int) -> int:
        """Returns the smallest power of two greater than or equal to val."""
        if val <= 0:
            return 1
        return 1 << (val - 1).bit_length()

    @classmethod
    def apply_color_bleed(cls, rgba: np.ndarray, radius: int = 2) -> np.ndarray:
        """
        Dilates RGB colors of opaque pixels into surrounding transparent pixels (alpha=0),
        preventing dark/black fringe seams during bilinear texture sampling.
        """
        if radius <= 0 or rgba.size == 0:
            return rgba.copy()

        h, w = rgba.shape[:2]
        result = rgba.copy()
        alpha = result[:, :, 3]
        opaque_mask = alpha > 0

        # If completely opaque or completely transparent, nothing to dilate
        if np.all(opaque_mask) or not np.any(opaque_mask):
            return result

        if HAS_SCIPY:
            # Exact Euclidean Voronoi dilation via distance transform
            dist, indices = scipy.ndimage.distance_transform_edt(
                ~opaque_mask, return_distances=True, return_indices=True
            )
            bleed_mask = (~opaque_mask) & (dist <= radius)
            if np.any(bleed_mask):
                nearest_y = indices[0][bleed_mask]
                nearest_x = indices[1][bleed_mask]
                result[bleed_mask, :3] = rgba[nearest_y, nearest_x, :3]
            return result

        # Pure-Python iterative morphological 8-neighbor dilation fallback
        current_rgba = result.copy()
        for _ in range(radius):
            current_opaque = current_rgba[:, :, 3] > 0
            new_rgb = current_rgba[:, :, :3].copy()
            new_marked = np.zeros((h, w), dtype=bool)

            for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
                sy = np.clip(np.arange(h) + dy, 0, h - 1)
                sx = np.clip(np.arange(w) + dx, 0, w - 1)
                neighbor_opaque = current_opaque[np.ix_(sy, sx)]
                candidate_mask = (~current_opaque) & neighbor_opaque & (~new_marked)
                if np.any(candidate_mask):
                    neighbor_rgb = current_rgba[sy, :][:, sx, :3]
                    new_rgb[candidate_mask] = neighbor_rgb[candidate_mask]
                    new_marked[candidate_mask] = True

            current_rgba[:, :, :3] = new_rgb
            current_opaque |= new_marked

        result[:, :, :3] = current_rgba[:, :, :3]
        return result

    @classmethod
    def remap_mesh_uvs(
        cls,
        mesh: Mesh,
        uv_rect: Tuple[float, float, float, float],
        flip_v: bool = False
    ) -> Mesh:
        """
        Transforms a Mesh's local layer UV coordinates into normalized global atlas UV space [0.0, 1.0].
        """
        u_min, v_min, u_max, v_max = uv_rect
        span_u = u_max - u_min
        span_v = v_max - v_min

        remapped = mesh.copy()
        if len(mesh.uvs) > 0:
            local_u = np.clip(mesh.uvs[:, 0], 0.0, 1.0)
            local_v = np.clip(mesh.uvs[:, 1], 0.0, 1.0)

            global_u = u_min + local_u * span_u
            global_v = v_min + local_v * span_v

            if flip_v:
                global_v = 1.0 - global_v

            remapped.uvs = np.column_stack([
                np.clip(global_u, 0.0, 1.0),
                np.clip(global_v, 0.0, 1.0)
            ]).astype(np.float32)

        return remapped

    @classmethod
    def pack(
        cls,
        layers: Union[List[LayerData], LayerCollection],
        meshes: Optional[Dict[str, Mesh]] = None,
        keyforms: Optional[Dict[str, DrawableKeyforms]] = None,
        config: Optional[PackingConfig] = None,
        padding: Optional[int] = None,
        max_atlas_size: Optional[int] = None,
        edge_bleed: Optional[int] = None,
    ) -> PackingResult:
        """
        Packs layer images into power-of-two texture atlas pages, applies edge bleed dilation,
        and remaps mesh UV coordinates to global atlas space.
        """
        cfg = config if config is not None else PackingConfig()
        if padding is not None:
            cfg.padding = padding
        if max_atlas_size is not None:
            cfg.max_atlas_size = max_atlas_size
        if edge_bleed is not None:
            cfg.bleed_radius = edge_bleed

        layer_list: List[LayerData] = list(layers) if isinstance(layers, (list, tuple, LayerCollection)) else []
        pad = max(0, cfg.padding)

        # Filter layers with non-zero dimensions
        valid_layers = [l for l in layer_list if l.image.shape[0] > 0 and l.image.shape[1] > 0]
        if not valid_layers:
            empty_size = max(512, cfg.min_atlas_size)
            empty_atlas = np.zeros((empty_size, empty_size, 4), dtype=np.uint8)
            return PackingResult(
                pages=[empty_atlas],
                placements={},
                uv_rects={},
                remapped_meshes={},
                drawables=[],
                stats=PackingStats(
                    total_layers=0,
                    num_pages=1,
                    page_dimensions=[(empty_size, empty_size)],
                    total_layer_area=0,
                    total_atlas_area=empty_size * empty_size,
                    efficiency=0.0
                )
            )

        # Sort layers
        if cfg.sort_order == SortOrder.MAX_SIDE_DESC:
            sorted_layers = sorted(valid_layers, key=lambda l: max(l.image.shape[0], l.image.shape[1]), reverse=True)
        elif cfg.sort_order == SortOrder.AREA_DESC:
            sorted_layers = sorted(valid_layers, key=lambda l: l.image.shape[0] * l.image.shape[1], reverse=True)
        elif cfg.sort_order == SortOrder.HEIGHT_DESC:
            sorted_layers = sorted(valid_layers, key=lambda l: l.image.shape[0], reverse=True)
        elif cfg.sort_order == SortOrder.WIDTH_DESC:
            sorted_layers = sorted(valid_layers, key=lambda l: l.image.shape[1], reverse=True)
        else:
            sorted_layers = list(valid_layers)

        # Estimate initial POT size
        total_padded_area = sum((l.image.shape[1] + 2 * pad) * (l.image.shape[0] + 2 * pad) for l in sorted_layers)
        max_item_w = max(l.image.shape[1] + 2 * pad for l in sorted_layers)
        max_item_h = max(l.image.shape[0] + 2 * pad for l in sorted_layers)
        max_item_dim = max(max_item_w, max_item_h)

        target_size = max(cfg.min_atlas_size, max_item_dim, int(math.sqrt(total_padded_area / 0.70)))
        pot_size = min(cfg.max_atlas_size, max(cfg.min_atlas_size, cls.next_power_of_two(target_size)))

        # Sizing escalation loop: find smallest POT atlas that fits all layers
        pages_bins: List[MaxRectsBin] = []
        layer_page_placements: Dict[str, Tuple[int, Rect, bool, LayerData]] = {}

        cur_size = pot_size
        while cur_size <= cfg.max_atlas_size:
            bin_candidate = MaxRectsBin(cur_size, cur_size)
            fits = True
            trial_placements: Dict[str, Tuple[int, Rect, bool, LayerData]] = {}
            for l in sorted_layers:
                lw = l.image.shape[1] + 2 * pad
                lh = l.image.shape[0] + 2 * pad
                pos, rot = bin_candidate.find_position_for_new_node(lw, lh, cfg.heuristic, cfg.allow_rotation)
                if pos is None:
                    fits = False
                    break
                bin_candidate.place_rect(pos)
                trial_placements[l.layer_id] = (0, pos, rot, l)

            if fits:
                pages_bins = [bin_candidate]
                layer_page_placements = trial_placements
                break
            cur_size *= 2

        # Multi-page fallback if layers exceed max_atlas_size on single page
        if not pages_bins:
            remaining = list(sorted_layers)
            page_idx = 0
            while remaining:
                bin_page = MaxRectsBin(cfg.max_atlas_size, cfg.max_atlas_size)
                unplaced = []
                for l in remaining:
                    lw = l.image.shape[1] + 2 * pad
                    lh = l.image.shape[0] + 2 * pad
                    pos, rot = bin_page.find_position_for_new_node(lw, lh, cfg.heuristic, cfg.allow_rotation)
                    if pos is not None:
                        bin_page.place_rect(pos)
                        layer_page_placements[l.layer_id] = (page_idx, pos, rot, l)
                    else:
                        unplaced.append(l)

                pages_bins.append(bin_page)

                if len(unplaced) == len(remaining):
                    # Hard single layer exceeds max_atlas_size -> force place in dedicated page
                    l = unplaced.pop(0)
                    needed_w = cls.next_power_of_two(l.image.shape[1] + 2 * pad)
                    needed_h = cls.next_power_of_two(l.image.shape[0] + 2 * pad)
                    forced_size = max(cfg.max_atlas_size, needed_w, needed_h)
                    forced_bin = MaxRectsBin(forced_size, forced_size)
                    pos = Rect(0, 0, l.image.shape[1] + 2 * pad, l.image.shape[0] + 2 * pad)
                    forced_bin.place_rect(pos)
                    layer_page_placements[l.layer_id] = (len(pages_bins), pos, False, l)
                    pages_bins.append(forced_bin)

                remaining = unplaced
                page_idx += 1

        # Render atlas pages & calculate UV rectangles
        pages_imgs: List[np.ndarray] = [
            np.zeros((b.height, b.width, 4), dtype=np.uint8) for b in pages_bins
        ]

        placements: Dict[str, PackedLayer] = {}
        uv_rects: Dict[str, Tuple[float, float, float, float]] = {}

        for layer_id, (p_idx, rect, rot, layer) in layer_page_placements.items():
            atlas_img = pages_imgs[p_idx]
            aw, ah = atlas_img.shape[1], atlas_img.shape[0]

            # Apply color bleed dilation
            bled_img = cls.apply_color_bleed(layer.image, radius=cfg.bleed_radius)
            if rot:
                bled_img = np.rot90(bled_img, -1).copy()

            # Content placement (inset by padding)
            px = rect.x + pad
            py = rect.y + pad
            lw = bled_img.shape[1]
            lh = bled_img.shape[0]

            # Paste into atlas buffer
            end_x = min(px + lw, aw)
            end_y = min(py + lh, ah)
            slice_w = end_x - px
            slice_h = end_y - py

            if slice_w > 0 and slice_h > 0:
                atlas_img[py:end_y, px:end_x] = bled_img[:slice_h, :slice_w]

            u_min = px / float(aw)
            v_min = py / float(ah)
            u_max = (px + slice_w) / float(aw)
            v_max = (py + slice_h) / float(ah)

            uv_rect = (u_min, v_min, u_max, v_max)
            uv_rects[layer.name] = uv_rect
            uv_rects[layer_id] = uv_rect

            packed_meta = PackedLayer(
                layer_id=layer_id,
                page_index=p_idx,
                x=px,
                y=py,
                width=slice_w,
                height=slice_h,
                uv_rect=uv_rect,
                rotated=rot
            )
            placements[layer_id] = packed_meta
            if layer.name != layer_id:
                placements[layer.name] = packed_meta

        # Remap meshes & construct drawables if provided
        remapped_meshes: Dict[str, Mesh] = {}
        drawables_list: List[DrawableKeyforms] = []

        if meshes:
            for name, mesh in meshes.items():
                rect = uv_rects.get(name) or uv_rects.get(mesh.layer_id)
                p_meta = placements.get(name) or placements.get(mesh.layer_id)
                tex_idx = p_meta.page_index if p_meta else 0

                if rect:
                    rm_mesh = cls.remap_mesh_uvs(mesh, rect, flip_v=cfg.flip_v)
                else:
                    rm_mesh = mesh.copy()

                remapped_meshes[name] = rm_mesh

                if keyforms and name in keyforms:
                    dk = keyforms[name]
                    dk.uvs_atlas = rm_mesh.uvs.astype(np.float32)
                    dk.texture_index = tex_idx
                    drawables_list.append(dk)
                else:
                    drawables_list.append(DrawableKeyforms(
                        drawable_id=f"ArtMesh_{name}",
                        texture_index=tex_idx,
                        base_vertices=rm_mesh.get_positions().astype(np.float32),
                        triangles=rm_mesh.triangles.astype(np.int32),
                        uvs_atlas=rm_mesh.uvs.astype(np.float32)
                    ))

        total_layer_area = sum(l.image.shape[0] * l.image.shape[1] for l in valid_layers)
        total_atlas_area = sum(img.shape[0] * img.shape[1] for img in pages_imgs)
        stats = PackingStats(
            total_layers=len(valid_layers),
            num_pages=len(pages_imgs),
            page_dimensions=[(img.shape[1], img.shape[0]) for img in pages_imgs],
            total_layer_area=total_layer_area,
            total_atlas_area=total_atlas_area,
            efficiency=total_layer_area / float(total_atlas_area) if total_atlas_area > 0 else 0.0
        )

        return PackingResult(
            pages=pages_imgs,
            placements=placements,
            uv_rects=uv_rects,
            remapped_meshes=remapped_meshes,
            drawables=drawables_list,
            stats=stats
        )

    @classmethod
    def pack_layers(
        cls,
        layers: Union[List[LayerData], LayerCollection],
        max_atlas_size: int = 4096,
        padding: int = 4,
        bleed_radius: int = 2
    ) -> Tuple[np.ndarray, Dict[str, Tuple[float, float, float, float]]]:
        """
        High-level backwards-compatible API:
        Returns (atlas_img, uv_rects).
        """
        config = PackingConfig(
            max_atlas_size=max_atlas_size,
            padding=padding,
            bleed_radius=bleed_radius
        )
        result = cls.pack(layers=layers, config=config)
        return result.primary_atlas, result.uv_rects
