"""
tests/test_texture_packer.py
Unit and Integration Test Suite for TextureAtlasPacker (MaxRects POT Packing & UV Remapping).
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


@pytest.fixture
def sample_character_layers():
    """Generates synthetic character layers for testing."""
    layers = []
    # 1. Hair Back
    img_hb = np.zeros((300, 300, 4), dtype=np.uint8)
    img_hb[20:280, 20:280] = [50, 40, 60, 255]
    layers.append(LayerData(name="Hair_Back", image=img_hb, offset_x=100, offset_y=100, z_depth_hint=-0.2, category="hair_back"))

    # 2. Face Skin
    img_f = np.zeros((260, 260, 4), dtype=np.uint8)
    img_f[10:250, 10:250] = [255, 220, 195, 255]
    layers.append(LayerData(name="Face", image=img_f, offset_x=120, offset_y=120, z_depth_hint=0.0, category="face"))

    # 3. Eyes
    img_e = np.zeros((80, 160, 4), dtype=np.uint8)
    img_e[10:70, 10:70] = [50, 120, 240, 255]
    img_e[10:70, 90:150] = [50, 120, 240, 255]
    layers.append(LayerData(name="Eyes", image=img_e, offset_x=170, offset_y=180, z_depth_hint=0.05, category="eyes"))

    # 4. Mouth
    img_m = np.zeros((40, 60, 4), dtype=np.uint8)
    img_m[10:30, 10:50] = [220, 70, 70, 255]
    layers.append(LayerData(name="Mouth", image=img_m, offset_x=220, offset_y=270, z_depth_hint=0.02, category="mouth"))

    # 5. Hair Front
    img_hf = np.zeros((200, 280, 4), dtype=np.uint8)
    img_hf[10:190, 10:270] = [65, 50, 80, 255]
    layers.append(LayerData(name="Hair_Front", image=img_hf, offset_x=110, offset_y=90, z_depth_hint=0.15, category="hair_front"))

    return layers


class TestTextureAtlasPackerUnit:
    """Unit tests for TextureAtlasPacker and MaxRectsBin."""

    def test_rect_geometry_methods(self):
        """Verify Rect contains and intersects logic."""
        r1 = Rect(0, 0, 100, 100)
        r2 = Rect(10, 10, 50, 50)
        r3 = Rect(80, 80, 50, 50)
        r4 = Rect(200, 200, 50, 50)

        assert r1.contains(r2)
        assert not r2.contains(r1)
        assert r1.intersects(r3)
        assert not r1.intersects(r4)

    def test_empty_layer_list_handling(self):
        """Verify packing an empty layer list produces a valid blank power-of-two atlas."""
        atlas_img, uv_rects = TextureAtlasPacker.pack_layers([])
        assert atlas_img.shape[0] >= 512 and atlas_img.shape[1] >= 512
        assert (atlas_img.shape[0] & (atlas_img.shape[0] - 1)) == 0
        assert (atlas_img.shape[1] & (atlas_img.shape[1] - 1)) == 0
        assert len(uv_rects) == 0

        res = TextureAtlasPacker.pack([])
        assert len(res.pages) == 1
        assert len(res.placements) == 0
        assert res.stats.total_layers == 0

    def test_transparent_zero_pixel_layers(self):
        """Verify 100% transparent layers are handled gracefully."""
        trans_layer = LayerData(name="Ghost", image=np.zeros((64, 64, 4), dtype=np.uint8))
        res = TextureAtlasPacker.pack([trans_layer])
        assert res.primary_atlas.shape[0] >= 512

    def test_single_layer_packing_and_uvs(self):
        """Verify single layer packing produces valid normalized UVs."""
        img = np.ones((128, 128, 4), dtype=np.uint8) * 200
        layer = LayerData(name="Box", image=img)
        atlas_img, uv_rects = TextureAtlasPacker.pack_layers([layer], max_atlas_size=1024, padding=4)

        assert "Box" in uv_rects
        u_min, v_min, u_max, v_max = uv_rects["Box"]
        assert 0.0 <= u_min < u_max <= 1.0
        assert 0.0 <= v_min < v_max <= 1.0

        h, w = atlas_img.shape[:2]
        assert (w & (w - 1)) == 0
        assert (h & (h - 1)) == 0

    def test_multi_layer_maxrects_packing(self, sample_character_layers):
        """Verify multi-layer MaxRects packing places all layers without errors."""
        res = TextureAtlasPacker.pack(sample_character_layers, config=PackingConfig(max_atlas_size=2048, padding=4))
        assert len(res.pages) >= 1
        assert len(res.placements) >= len(sample_character_layers)

        for l in sample_character_layers:
            assert l.name in res.uv_rects
            u_min, v_min, u_max, v_max = res.uv_rects[l.name]
            assert 0.0 <= u_min < u_max <= 1.0
            assert 0.0 <= v_min < v_max <= 1.0

    @pytest.mark.parametrize("atlas_size", [512, 1024, 2048, 4096, 8192])
    def test_power_of_two_dimension_invariant(self, sample_character_layers, atlas_size):
        """Verify atlas dimensions are strictly power-of-two across all size limits."""
        res = TextureAtlasPacker.pack(sample_character_layers, config=PackingConfig(max_atlas_size=atlas_size))
        for page in res.pages:
            h, w = page.shape[:2]
            assert (w & (w - 1)) == 0, f"Atlas width {w} is not a power of two"
            assert (h & (h - 1)) == 0, f"Atlas height {h} is not a power of two"
            assert w <= atlas_size and h <= atlas_size

    def test_border_padding_enforcement(self):
        """Verify pixel distance between any two placed layer bounding boxes is >= padding."""
        padding = 8
        l1 = LayerData(name="L1", image=np.ones((60, 60, 4), dtype=np.uint8) * 255)
        l2 = LayerData(name="L2", image=np.ones((60, 60, 4), dtype=np.uint8) * 255)
        l3 = LayerData(name="L3", image=np.ones((60, 60, 4), dtype=np.uint8) * 255)

        res = TextureAtlasPacker.pack([l1, l2, l3], config=PackingConfig(padding=padding, min_atlas_size=512))
        p1 = res.placements["L1"]
        p2 = res.placements["L2"]
        p3 = res.placements["L3"]

        placements = [p1, p2, p3]
        for i in range(len(placements)):
            for j in range(i + 1, len(placements)):
                pi, pj = placements[i], placements[j]
                if pi.page_index == pj.page_index:
                    # Check padding distance
                    disjoint_x = (pi.x + pi.width + padding <= pj.x) or (pj.x + pj.width + padding <= pi.x)
                    disjoint_y = (pi.y + pi.height + padding <= pj.y) or (pj.y + pj.height + padding <= pi.y)
                    assert disjoint_x or disjoint_y, f"Padding constraint violated between {pi.layer_id} and {pj.layer_id}"

    def test_edge_bleed_dilation(self):
        """Verify color bleed dilates opaque RGB into transparent borders while keeping alpha=0."""
        img = np.zeros((10, 10, 4), dtype=np.uint8)
        # 4x4 red square in center with alpha 255
        img[3:7, 3:7] = [255, 0, 0, 255]

        bled = TextureAtlasPacker.apply_color_bleed(img, radius=2)
        assert bled.shape == img.shape

        # Original opaque pixels preserved
        assert np.all(bled[3:7, 3:7, 0] == 255)
        assert np.all(bled[3:7, 3:7, 3] == 255)

        # Border pixels adjacent to square should have red RGB but 0 alpha
        assert bled[2, 4, 0] == 255  # Red color dilated
        assert bled[2, 4, 3] == 0    # Alpha still 0

    def test_uv_coordinate_remapping_precision(self):
        """Verify remap_mesh_uvs linearly transforms [0, 1] into atlas [u_min, u_max]."""
        v1 = Vertex(position=np.array([0.0, 0.0]))
        v2 = Vertex(position=np.array([1.0, 0.0]))
        v3 = Vertex(position=np.array([0.0, 1.0]))
        mesh = Mesh(
            vertices=[v1, v2, v3],
            triangles=np.array([[0, 1, 2]], dtype=np.int32),
            uvs=np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            layer_id="Face"
        )

        uv_rect = (0.25, 0.50, 0.75, 1.00)
        remapped = TextureAtlasPacker.remap_mesh_uvs(mesh, uv_rect)

        assert np.allclose(remapped.uvs[0], [0.25, 0.50], atol=1e-6)
        assert np.allclose(remapped.uvs[1], [0.75, 0.50], atol=1e-6)
        assert np.allclose(remapped.uvs[2], [0.25, 1.00], atol=1e-6)

    def test_pairwise_disjointness_overlap_check(self, sample_character_layers):
        """Verify no two packed layer bounding boxes intersect."""
        res = TextureAtlasPacker.pack(sample_character_layers)
        placements = list(res.placements.values())

        for i in range(len(placements)):
            for j in range(i + 1, len(placements)):
                pi, pj = placements[i], placements[j]
                if pi.page_index == pj.page_index:
                    u1_min, v1_min, u1_max, v1_max = pi.uv_rect
                    u2_min, v2_min, u2_max, v2_max = pj.uv_rect
                    is_disjoint = (u1_max <= u2_min) or (u2_max <= u1_min) or (v1_max <= v2_min) or (v2_max <= v1_min)
                    assert is_disjoint, f"Overlap detected between {pi.layer_id} and {pj.layer_id}"

    def test_pixel_data_fidelity_transfer(self):
        """Verify pixel colors are accurately transferred into atlas canvas."""
        img = np.zeros((30, 30, 4), dtype=np.uint8)
        img[:, :] = [123, 234, 45, 255]
        layer = LayerData(name="ColorTest", image=img)

        res = TextureAtlasPacker.pack([layer], config=PackingConfig(padding=0, bleed_radius=0))
        p = res.placements["ColorTest"]
        atlas = res.primary_atlas

        sample = atlas[p.y + 5, p.x + 5]
        assert sample[0] == 123
        assert sample[1] == 234
        assert sample[2] == 45
        assert sample[3] == 255

    def test_multi_page_atlas_overflow(self):
        """Verify large layers overflowing single atlas allocate multi-page atlas."""
        large_layers = [
            LayerData(name=f"BigLayer_{i}", image=np.ones((600, 600, 4), dtype=np.uint8) * 100)
            for i in range(4)
        ]
        # max_atlas_size = 512, each layer is 600x600 -> must allocate multiple pages
        res = TextureAtlasPacker.pack(large_layers, config=PackingConfig(max_atlas_size=512))
        assert len(res.pages) >= 2
        assert res.stats.num_pages >= 2
