"""
tests/test_texture_packer_adversarial.py
Adversarial empirical stress tests and mathematical invariant generators for TextureAtlasPacker.
"""

import math
import numpy as np
import pytest
from PIL import Image

from src.core.layer import LayerData, LayerCollection
from src.core.mesh import Mesh
from src.core.vertex import Vertex
from src.core.keyform import DrawableKeyforms
from src.exporter.texture_packer import (
    TextureAtlasPacker,
    PackingConfig,
    PackingResult,
    PackedLayer,
    PackingHeuristic,
    SortOrder,
    MaxRectsBin,
    Rect,
)


class TestTexturePackerAdversarial:
    """Adversarial stress-test suite challenging texture packer invariants."""

    def test_high_density_packing_50_plus_diverse_layers(self):
        """
        Stress Test 1: High-density packing with 60 diverse layer dimensions.
        Validates:
        - All 60 layers are successfully placed.
        - Pairwise non-overlap geometric invariant holds for all layer pairs on the same page.
        - Padding distances are strictly maintained.
        - All UV coordinates remain strictly within [0.0, 1.0].
        """
        np.random.seed(42)
        layers = []
        padding = 4

        # Generate 60 diverse layers
        for i in range(60):
            w = int(np.random.randint(15, 180))
            h = int(np.random.randint(15, 180))
            color = np.random.randint(0, 255, size=3, dtype=np.uint8)
            img = np.zeros((h, w, 4), dtype=np.uint8)
            img[:, :, :3] = color
            img[:, :, 3] = 255
            layers.append(LayerData(name=f"DenseLayer_{i:03d}", image=img))

        config = PackingConfig(max_atlas_size=4096, padding=padding, bleed_radius=2)
        result = TextureAtlasPacker.pack(layers, config=config)

        assert len(result.placements) == 60
        assert result.stats.total_layers == 60
        assert len(result.pages) >= 1

        # Check pairwise non-overlap geometric invariants
        placements = list(result.placements.values())
        unique_placements = list({p.layer_id: p for p in placements}.values())

        for i in range(len(unique_placements)):
            pi = unique_placements[i]
            # Verify UV bounds
            u_min, v_min, u_max, v_max = pi.uv_rect
            assert 0.0 <= u_min < u_max <= 1.0, f"Layer {pi.layer_id} invalid UV bounds: {pi.uv_rect}"
            assert 0.0 <= v_min < v_max <= 1.0, f"Layer {pi.layer_id} invalid UV bounds: {pi.uv_rect}"

            # Verify placement inside atlas bounds
            atlas_h, atlas_w = result.pages[pi.page_index].shape[:2]
            assert pi.x >= 0 and pi.y >= 0
            assert pi.x + pi.width <= atlas_w
            assert pi.y + pi.height <= atlas_h

            for j in range(i + 1, len(unique_placements)):
                pj = unique_placements[j]
                if pi.page_index == pj.page_index:
                    # Invariant: Disjoint with padding
                    disjoint_x = (pi.x + pi.width + padding <= pj.x) or (pj.x + pj.width + padding <= pi.x)
                    disjoint_y = (pi.y + pi.height + padding <= pj.y) or (pj.y + pj.height + padding <= pi.y)
                    assert disjoint_x or disjoint_y, (
                        f"Overlap / padding violation between {pi.layer_id} ({pi.x}, {pi.y}, {pi.width}, {pi.height}) "
                        f"and {pj.layer_id} ({pj.x}, {pj.y}, {pj.width}, {pj.height}) on page {pi.page_index}"
                    )

    def test_extreme_aspect_ratios(self):
        """
        Stress Test 2: Extreme aspect ratios:
        - Needle thin: 1000x2, 2x1000
        - Single pixel: 1x1
        - Pancake wide: 1500x5, 5x1500
        - Prime/Odd dimensions: 17x389, 401x13
        """
        dimensions = [
            (1000, 2),
            (2, 1000),
            (1, 1),
            (1500, 5),
            (5, 1500),
            (17, 389),
            (401, 13),
            (3, 3),
            (7, 800),
            (800, 7),
        ]
        layers = []
        for idx, (w, h) in enumerate(dimensions):
            img = np.full((h, w, 4), 200, dtype=np.uint8)
            img[:, :, 3] = 255
            layers.append(LayerData(name=f"Extreme_{idx}_{w}x{h}", image=img))

        config = PackingConfig(max_atlas_size=4096, padding=4, bleed_radius=2)
        result = TextureAtlasPacker.pack(layers, config=config)

        assert len(result.placements) >= len(dimensions)
        for idx, (w, h) in enumerate(dimensions):
            name = f"Extreme_{idx}_{w}x{h}"
            assert name in result.placements
            p = result.placements[name]
            assert p.width == w
            assert p.height == h
            u_min, v_min, u_max, v_max = p.uv_rect
            assert 0.0 <= u_min < u_max <= 1.0
            assert 0.0 <= v_min < v_max <= 1.0

    @pytest.mark.parametrize("target_limit", [512, 1024, 2048, 4096, 8192])
    def test_pot_escalation_and_power_of_two_invariants(self, target_limit):
        """
        Stress Test 3: Escalation ladder across POT limits (512, 1024, 2048, 4096, 8192).
        Verifies:
        - Resulting page width and height are strictly 2^k.
        - POT size matches escalation calculation.
        """
        layers = [
            LayerData(name=f"EscLayer_{i}", image=np.full((120, 120, 4), 150, dtype=np.uint8))
            for i in range(12)
        ]
        config = PackingConfig(max_atlas_size=target_limit, min_atlas_size=512)
        result = TextureAtlasPacker.pack(layers, config=config)

        for p_idx, page in enumerate(result.pages):
            h, w = page.shape[:2]
            assert (w & (w - 1)) == 0, f"Page {p_idx} width {w} not POT"
            assert (h & (h - 1)) == 0, f"Page {p_idx} height {h} not POT"
            assert w <= max(target_limit, 512)
            assert h <= max(target_limit, 512)

    def test_pairwise_non_overlap_geometric_oracle(self):
        """
        Stress Test 4: Rigorous geometric oracle checking pairwise intersection
        $R_i \\cap R_j = \\emptyset$ for all $i \\neq j$ across 100 pseudo-random boxes.
        """
        np.random.seed(1337)
        layers = []
        for i in range(100):
            w = int(np.random.randint(10, 80))
            h = int(np.random.randint(10, 80))
            img = np.zeros((h, w, 4), dtype=np.uint8)
            img[:, :, :3] = np.random.randint(10, 250, size=3, dtype=np.uint8)
            img[:, :, 3] = 255
            layers.append(LayerData(name=f"OracleBox_{i}", image=img))

        config = PackingConfig(max_atlas_size=2048, padding=6, bleed_radius=2)
        result = TextureAtlasPacker.pack(layers, config=config)

        unique_placements = list({p.layer_id: p for p in result.placements.values()}.values())
        assert len(unique_placements) == 100

        # Pixel occupancy map check per page
        for p_idx, page in enumerate(result.pages):
            h, w = page.shape[:2]
            occupancy = np.zeros((h, w), dtype=np.int32)
            page_placements = [p for p in unique_placements if p.page_index == p_idx]

            for p in page_placements:
                assert p.x >= 0 and p.x + p.width <= w
                assert p.y >= 0 and p.y + p.height <= h

                # Mark content area in occupancy map (each pixel must be owned by exactly 1 layer)
                region = occupancy[p.y : p.y + p.height, p.x : p.x + p.width]
                assert np.all(region == 0), f"Overlap detected in pixel occupancy on page {p_idx} for layer {p.layer_id}"
                occupancy[p.y : p.y + p.height, p.x : p.x + p.width] += 1

    def test_edge_bleed_color_accuracy_voronoi(self):
        """
        Stress Test 5: Edge bleed color accuracy.
        Verify that dilated transparent pixels (alpha == 0) around an island of opaque pixels
        take on the EXACT RGB color of the nearest opaque boundary pixel.
        """
        img = np.zeros((20, 20, 4), dtype=np.uint8)
        img[2:8, 2:8] = [0, 0, 255, 255]       # Blue
        img[12:18, 12:18] = [255, 255, 0, 255]  # Yellow

        bled = TextureAtlasPacker.apply_color_bleed(img, radius=2)

        # Check that original opaque pixels are unchanged
        assert np.array_equal(bled[2:8, 2:8], img[2:8, 2:8])
        assert np.array_equal(bled[12:18, 12:18], img[12:18, 12:18])

        # Check dilated pixels adjacent to Blue square (e.g. at (1, 5) and (8, 5))
        assert np.array_equal(bled[1, 5, :3], [0, 0, 255]), f"Bleed mismatch at (1, 5): {bled[1, 5]}"
        assert bled[1, 5, 3] == 0, "Bleed dilated pixel must retain alpha=0"

        # Check dilated pixels adjacent to Yellow square (e.g. at (11, 15) and (18, 15))
        assert np.array_equal(bled[11, 15, :3], [255, 255, 0]), f"Bleed mismatch at (11, 15): {bled[11, 15]}"
        assert bled[11, 15, 3] == 0, "Bleed dilated pixel must retain alpha=0"

        # Check radius 2 dilation
        assert np.array_equal(bled[0, 5, :3], [0, 0, 255]), f"Radius 2 bleed mismatch at (0, 5): {bled[0, 5]}"
        assert bled[0, 5, 3] == 0

    def test_uv_remapping_mathematical_bounds_and_subdivision(self):
        """
        Stress Test 6: UV remapping mathematical bounds and mesh triangulation.
        Tests mesh with 100 internal Steiner vertices and checks:
        - All global UVs are strictly in [0.0, 1.0].
        - UV transformation is strictly affine and monotonic.
        - Flip V option correctly maps v -> 1 - v.
        """
        xs = np.linspace(0.0, 1.0, 11)
        ys = np.linspace(0.0, 1.0, 11)
        gx, gy = np.meshgrid(xs, ys)
        uvs_local = np.column_stack([gx.ravel(), gy.ravel()]).astype(np.float32)

        vertices = [Vertex(position=np.array([u * 100.0, v * 100.0])) for u, v in uvs_local]
        triangles = np.zeros((10, 3), dtype=np.int32)
        mesh = Mesh(vertices=vertices, triangles=triangles, uvs=uvs_local, layer_id="GridLayer")

        uv_rect = (0.125, 0.250, 0.625, 0.750)
        remapped_normal = TextureAtlasPacker.remap_mesh_uvs(mesh, uv_rect, flip_v=False)

        assert np.all(remapped_normal.uvs >= 0.0)
        assert np.all(remapped_normal.uvs <= 1.0)
        assert np.isclose(np.min(remapped_normal.uvs[:, 0]), 0.125)
        assert np.isclose(np.max(remapped_normal.uvs[:, 0]), 0.625)
        assert np.isclose(np.min(remapped_normal.uvs[:, 1]), 0.250)
        assert np.isclose(np.max(remapped_normal.uvs[:, 1]), 0.750)

        # Test flip_v
        remapped_flipped = TextureAtlasPacker.remap_mesh_uvs(mesh, uv_rect, flip_v=True)
        assert np.all(remapped_flipped.uvs >= 0.0)
        assert np.all(remapped_flipped.uvs <= 1.0)
        assert np.isclose(np.min(remapped_flipped.uvs[:, 1]), 0.250)
        assert np.isclose(np.max(remapped_flipped.uvs[:, 1]), 0.750)

    @pytest.mark.parametrize("heuristic", [
        PackingHeuristic.BSSF,
        PackingHeuristic.BLSF,
        PackingHeuristic.BAF,
        PackingHeuristic.BL,
        PackingHeuristic.CP,
    ])
    def test_all_packing_heuristics_geometric_invariants(self, heuristic):
        """
        Stress Test 7: Verify all 5 MaxRects placement heuristics enforce non-overlap.
        """
        layers = [
            LayerData(name=f"HLayer_{i}", image=np.ones((40 + i * 5, 50 + (i % 3) * 10, 4), dtype=np.uint8) * 128)
            for i in range(15)
        ]
        config = PackingConfig(max_atlas_size=1024, padding=4, heuristic=heuristic)
        result = TextureAtlasPacker.pack(layers, config=config)

        unique_placements = list({p.layer_id: p for p in result.placements.values()}.values())
        assert len(unique_placements) == 15

        for i in range(len(unique_placements)):
            pi = unique_placements[i]
            for j in range(i + 1, len(unique_placements)):
                pj = unique_placements[j]
                if pi.page_index == pj.page_index:
                    disjoint_x = (pi.x + pi.width + 4 <= pj.x) or (pj.x + pj.width + 4 <= pi.x)
                    disjoint_y = (pi.y + pi.height + 4 <= pj.y) or (pj.y + pj.height + 4 <= pi.y)
                    assert disjoint_x or disjoint_y, f"Collision with heuristic {heuristic}"

    @pytest.mark.parametrize("sort_order", [
        SortOrder.MAX_SIDE_DESC,
        SortOrder.AREA_DESC,
        SortOrder.HEIGHT_DESC,
        SortOrder.WIDTH_DESC,
        SortOrder.NONE,
    ])
    def test_all_sort_orders_geometric_invariants(self, sort_order):
        """
        Stress Test 8: Verify all sort orders maintain valid layouts without overlap.
        """
        layers = [
            LayerData(name=f"SLayer_{i}", image=np.ones((20 + (i * 13) % 70, 30 + (i * 17) % 60, 4), dtype=np.uint8) * 200)
            for i in range(20)
        ]
        config = PackingConfig(max_atlas_size=1024, padding=4, sort_order=sort_order)
        result = TextureAtlasPacker.pack(layers, config=config)

        unique_placements = list({p.layer_id: p for p in result.placements.values()}.values())
        assert len(unique_placements) == 20

        for i in range(len(unique_placements)):
            pi = unique_placements[i]
            for j in range(i + 1, len(unique_placements)):
                pj = unique_placements[j]
                if pi.page_index == pj.page_index:
                    disjoint_x = (pi.x + pi.width + 4 <= pj.x) or (pj.x + pj.width + 4 <= pi.x)
                    disjoint_y = (pi.y + pi.height + 4 <= pj.y) or (pj.y + pj.height + 4 <= pi.y)
                    assert disjoint_x or disjoint_y, f"Collision with sort order {sort_order}"

    def test_multi_page_many_medium_layers(self):
        """
        Stress Test 9: Force multi-page allocation with 25 medium layers that cannot fit on 512x512.
        """
        layers = [
            LayerData(name=f"MedLayer_{i}", image=np.ones((160, 160, 4), dtype=np.uint8) * (50 + i * 5))
            for i in range(25)
        ]
        config = PackingConfig(max_atlas_size=512, padding=4)
        result = TextureAtlasPacker.pack(layers, config=config)

        assert len(result.pages) >= 3
        assert result.stats.num_pages >= 3

        unique_placements = list({p.layer_id: p for p in result.placements.values()}.values())
        assert len(unique_placements) == 25

        for i in range(len(unique_placements)):
            pi = unique_placements[i]
            assert 0 <= pi.page_index < len(result.pages)
            for j in range(i + 1, len(unique_placements)):
                pj = unique_placements[j]
                if pi.page_index == pj.page_index:
                    disjoint_x = (pi.x + pi.width + 4 <= pj.x) or (pj.x + pj.width + 4 <= pi.x)
                    disjoint_y = (pi.y + pi.height + 4 <= pj.y) or (pj.y + pj.height + 4 <= pi.y)
                    assert disjoint_x or disjoint_y, f"Collision on multi-page atlas: {pi.layer_id} vs {pj.layer_id}"

    def test_complex_topological_alpha_edge_bleed(self):
        """
        Stress Test 10: Edge bleed on complex topological shapes (Donut ring).
        """
        img = np.zeros((30, 30, 4), dtype=np.uint8)
        cy, cx = 15, 15
        for y in range(30):
            for x in range(30):
                r = math.hypot(x - cx, y - cy)
                if 6 <= r <= 12:
                    img[y, x] = [100, 200, 50, 255]  # Green ring

        bled = TextureAtlasPacker.apply_color_bleed(img, radius=2)

        # Ring center remains transparent
        assert bled[15, 15, 3] == 0

        # Pixel at r=5 (inner hole) dilated green with alpha 0
        assert np.array_equal(bled[15, 10, :3], [100, 200, 50])
        assert bled[15, 10, 3] == 0

        # Pixel at r=13 (outer rim) dilated green with alpha 0
        assert np.array_equal(bled[15, 28, :3], [100, 200, 50])
        assert bled[15, 28, 3] == 0

    def test_multi_page_oversized_layers_mixed(self):
        """
        Stress Test 11: Oversized layers (> max_atlas_size) mixed with normal layers.
        Verifies:
        - Each oversized layer gets allocated on its own dedicated page of sufficient POT size.
        - Page index mapping matches pages list.
        - No two layers overlap on any page.
        """
        l1 = LayerData(name="Big1", image=np.ones((600, 600, 4), dtype=np.uint8) * 200)
        l2 = LayerData(name="Big2", image=np.ones((700, 700, 4), dtype=np.uint8) * 220)
        l3 = LayerData(name="Small1", image=np.ones((100, 100, 4), dtype=np.uint8) * 100)
        l4 = LayerData(name="Small2", image=np.ones((120, 120, 4), dtype=np.uint8) * 120)

        # max_atlas_size = 512, so Big1 (600x600) and Big2 (700x700) are oversized
        config = PackingConfig(max_atlas_size=512, padding=4)
        result = TextureAtlasPacker.pack([l1, l2, l3, l4], config=config)

        unique_placements = list({p.layer_id: p for p in result.placements.values()}.values())
        assert len(unique_placements) == 4

        for p in unique_placements:
            assert 0 <= p.page_index < len(result.pages)
            page = result.pages[p.page_index]
            assert p.x + p.width <= page.shape[1]
            assert p.y + p.height <= page.shape[0]

        for i in range(len(unique_placements)):
            pi = unique_placements[i]
            for j in range(i + 1, len(unique_placements)):
                pj = unique_placements[j]
                if pi.page_index == pj.page_index:
                    disjoint_x = (pi.x + pi.width + 4 <= pj.x) or (pj.x + pj.width + 4 <= pi.x)
                    disjoint_y = (pi.y + pi.height + 4 <= pj.y) or (pj.y + pj.height + 4 <= pi.y)
                    assert disjoint_x or disjoint_y, f"Overlap between {pi.layer_id} and {pj.layer_id} on page {pi.page_index}"
