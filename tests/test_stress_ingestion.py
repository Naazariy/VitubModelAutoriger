import os
import sys
import shutil
import tempfile
from pathlib import Path
import pytest
import numpy as np
from PIL import Image

from src.core.layer import LayerData, LayerCollection
from src.importer.semantic_classifier import SemanticClassifier, SemanticCategory, CATEGORY_NOMINAL_DEPTHS
from src.importer.image_importer import ImageImporter
from src.importer.psd_importer import PSDImporter


class TestAdversarialDimensionsAndGeometry:
    def test_1x1_single_pixel_image(self):
        img = np.array([[[255, 0, 0, 255]]], dtype=np.uint8)
        layer = LayerData(name='Pixel', image=img, offset_x=10, offset_y=20)
        assert layer.width == 1
        assert layer.height == 1
        assert not layer.is_empty
        assert layer.bbox == (10, 20, 11, 21)

        cropped = layer.crop_to_content()
        assert cropped.width == 1
        assert cropped.height == 1
        assert cropped.offset_x == 10
        assert cropped.offset_y == 20

    def test_1x1_transparent_pixel_image(self):
        img = np.array([[[0, 0, 0, 0]]], dtype=np.uint8)
        layer = LayerData(name='EmptyPixel', image=img, offset_x=5, offset_y=5)
        assert layer.is_empty
        cropped = layer.crop_to_content()
        assert cropped.width == 1
        assert cropped.height == 1

    def test_extreme_aspect_ratio_tall(self):
        img = np.zeros((4096, 1, 4), dtype=np.uint8)
        img[100:200, 0] = [255, 255, 255, 255]
        layer = LayerData(name='TallStripe', image=img, offset_x=0, offset_y=0)
        assert layer.height == 4096
        assert layer.width == 1
        assert not layer.is_empty

        cropped = layer.crop_to_content()
        assert cropped.width == 1
        assert cropped.height == 100
        assert cropped.offset_y == 100

    def test_extreme_aspect_ratio_wide(self):
        img = np.zeros((1, 4096, 4), dtype=np.uint8)
        img[0, 500:600] = [100, 150, 200, 255]
        layer = LayerData(name='WideStripe', image=img, offset_x=10, offset_y=20)
        assert layer.width == 4096
        assert layer.height == 1
        assert not layer.is_empty

        cropped = layer.crop_to_content()
        assert cropped.width == 100
        assert cropped.height == 1
        assert cropped.offset_x == 510

    def test_negative_and_huge_canvas_offsets(self):
        img = np.full((100, 100, 4), 255, dtype=np.uint8)
        layer_neg = LayerData(name='OffCanvasNeg', image=img, offset_x=-5000, offset_y=-5000)
        canvas_neg = layer_neg.get_canvas_aligned_image(512, 512)
        assert canvas_neg.shape == (512, 512, 4)
        assert np.all(canvas_neg == 0)

        layer_pos = LayerData(name='OffCanvasPos', image=img, offset_x=5000, offset_y=5000)
        canvas_pos = layer_pos.get_canvas_aligned_image(512, 512)
        assert canvas_pos.shape == (512, 512, 4)
        assert np.all(canvas_pos == 0)

        layer_overlap = LayerData(name='PartialNeg', image=img, offset_x=-50, offset_y=-30)
        canvas_overlap = layer_overlap.get_canvas_aligned_image(512, 512)
        assert canvas_overlap.shape == (512, 512, 4)
        assert np.all(canvas_overlap[0:70, 0:50] == 255)
        assert np.all(canvas_overlap[70:, :] == 0)
        assert np.all(canvas_overlap[:, 50:] == 0)


class TestTransparencyAndCompositing:
    def test_fully_transparent_layer_composite(self):
        col = LayerCollection(canvas_size=(100, 100))
        img = np.zeros((100, 100, 4), dtype=np.uint8)
        layer = LayerData(name='Ghost', image=img)
        col.add_layer(layer)

        comp = col.composite()
        assert comp.shape == (100, 100, 4)
        assert np.all(comp == 0)

    def test_zero_opacity_layer(self):
        col = LayerCollection(canvas_size=(100, 100))
        img = np.full((100, 100, 4), 255, dtype=np.uint8)
        layer = LayerData(name='Invisible', image=img, opacity=0.0)
        col.add_layer(layer)

        comp = col.composite()
        assert np.all(comp == 0)

    def test_multi_layer_alpha_over_blending(self):
        col = LayerCollection(canvas_size=(10, 10))
        img_red = np.zeros((10, 10, 4), dtype=np.uint8)
        img_red[:, :] = [255, 0, 0, 255]
        l_red = LayerData(name='Red', image=img_red, z_depth_hint=-0.5)

        img_blue = np.zeros((10, 10, 4), dtype=np.uint8)
        img_blue[:, :] = [0, 0, 255, 128]
        l_blue = LayerData(name='Blue', image=img_blue, z_depth_hint=0.5)

        col.add_layer(l_blue)
        col.add_layer(l_red)

        comp = col.composite()
        assert comp.shape == (10, 10, 4)
        assert comp[0, 0, 3] == 255
        assert comp[0, 0, 0] > 50
        assert comp[0, 0, 2] > 50


class TestUnicodeAndAdversarialPaths:
    def test_unicode_and_japanese_file_and_folder_paths(self, tmp_path):
        jp_dir = tmp_path / 'test_model_jp'
        jp_dir.mkdir()

        filenames = [
            '01_hair_back_twin.png',
            '02_face_skin.png',
            '03_left_eye_lash.png',
            '04_front_hair_bangs.png'
        ]

        for fname in filenames:
            fpath = jp_dir / fname
            img = Image.new('RGBA', (64, 64), (120, 100, 80, 255))
            img.save(fpath)

        layers = ImageImporter.load_directory(str(jp_dir), canvas_size=(64, 64))
        assert len(layers) == 4
        assert layers[0].category == SemanticCategory.HAIR_BACK
        assert layers[1].category == SemanticCategory.FACE
        assert layers[2].category == SemanticCategory.EYES
        assert layers[3].category == SemanticCategory.HAIR_FRONT

    def test_directory_with_non_image_files_and_subdirectories(self, tmp_path):
        mix_dir = tmp_path / 'mixed_directory'
        mix_dir.mkdir()

        Image.new('RGBA', (32, 32), (255, 255, 255, 255)).save(mix_dir / 'face.png')
        Image.new('RGB', (32, 32), (200, 200, 200)).save(mix_dir / 'hair_front.jpg')

        (mix_dir / 'notes.txt').write_text('VTuber model notes', encoding='utf-8')
        (mix_dir / 'config.json').write_text('{}', encoding='utf-8')
        (mix_dir / '.DS_Store').write_bytes(b'\x00\x01\x02\x03')

        (mix_dir / 'backup_folder').mkdir()
        (mix_dir / 'backup_folder' / 'unused.png').write_bytes(b'dummy')

        layers = ImageImporter.load_directory(str(mix_dir))
        assert len(layers) == 2
        layer_names = [l.name for l in layers]
        assert 'face' in layer_names
        assert 'hair_front' in layer_names

    def test_corrupted_image_handling(self, tmp_path):
        corrupt_dir = tmp_path / 'corrupt_test'
        corrupt_dir.mkdir()
        (corrupt_dir / '01_bad_image.png').write_bytes(b'NOT_A_PNG_FILE_HEADER_CORRUPTED')

        with pytest.raises(Exception):
            ImageImporter.load_directory(str(corrupt_dir))


class TestContourExtractionStress:
    def test_collinear_horizontal_line_mask(self):
        alpha = np.zeros((100, 100), dtype=np.uint8)
        alpha[50, 20:80] = 255

        contour = ImageImporter.extract_contour(alpha, threshold=10)
        assert isinstance(contour, np.ndarray)
        assert contour.ndim == 2
        assert contour.shape[1] == 2
        assert len(contour) >= 3

    def test_collinear_vertical_line_mask(self):
        alpha = np.zeros((100, 100), dtype=np.uint8)
        alpha[10:90, 50] = 255

        contour = ImageImporter.extract_contour(alpha, threshold=10)
        assert isinstance(contour, np.ndarray)
        assert len(contour) >= 3

    def test_single_isolated_pixel(self):
        alpha = np.zeros((64, 64), dtype=np.uint8)
        alpha[32, 32] = 255

        contour = ImageImporter.extract_contour(alpha, threshold=10)
        assert isinstance(contour, np.ndarray)
        assert len(contour) >= 3

    def test_disjoint_multi_island_mask(self):
        alpha = np.zeros((200, 200), dtype=np.uint8)
        y, x = np.ogrid[:200, :200]
        alpha[(x - 50)**2 + (y - 50)**2 <= 20**2] = 255
        alpha[(x - 150)**2 + (y - 150)**2 <= 20**2] = 255

        contour = ImageImporter.extract_contour(alpha, threshold=10)
        assert len(contour) >= 3


class TestSemanticClassifierEdgeCases:
    def test_empty_and_whitespace_names(self):
        cat, depth = SemanticClassifier.classify('')
        assert cat == SemanticCategory.UNKNOWN
        assert depth == 0.0

        cat_ws, _ = SemanticClassifier.classify('   \t\n  ')
        assert cat_ws == SemanticCategory.UNKNOWN

    def test_long_noise_string_with_hidden_keyword(self):
        noisy_name = 'Character_v3_Final_Render_HD_2026_08_21_Layer_front_hair_backup_copy_02.PNG'
        cat, depth = SemanticClassifier.classify(noisy_name)
        assert cat == SemanticCategory.HAIR_FRONT
        assert depth == 0.50

    def test_parent_group_inheritance(self):
        cat, depth = SemanticClassifier.classify(
            name='Layer 1',
            parent_group='Head/Eyes/Left'
        )
        assert cat == SemanticCategory.EYES
        assert depth == 0.25

    def test_spatial_classifier_degenerate_canvas_dimensions(self):
        cat = SemanticClassifier.classify_spatial(
            bbox=(0, 0, 10, 10),
            canvas_size=(0, 0)
        )
        assert cat == SemanticCategory.UNKNOWN

        cat_neg = SemanticClassifier.classify_spatial(
            bbox=(0, 0, 10, 10),
            canvas_size=(-100, -100)
        )
        assert cat_neg == SemanticCategory.UNKNOWN


class TestDeepHierarchyAndScale:
    """Stress tests on large-scale layer stacks and deep nested group hierarchies."""

    def test_deeply_nested_psd_hierarchy_mock(self):
        class MockPSDLayer:
            def __init__(self, name, bbox, is_group=False, visible=True, opacity=255, blend='normal', parent=None):
                self.name = name
                self.left = bbox[0]
                self.top = bbox[1]
                self.width = bbox[2] - bbox[0]
                self.height = bbox[3] - bbox[1]
                self._is_group = is_group
                self._visible = visible
                self.opacity = opacity
                self.blend_mode = blend
                self.parent = parent
            def is_group(self): return self._is_group
            def is_visible(self): return self._visible
            def composite(self):
                return Image.new('RGBA', (max(1, self.width), max(1, self.height)), (100, 150, 200, 255))

        class MockParent:
            def __init__(self, name, parent=None):
                self.name = name
                self.parent = parent
                self.is_root = False

        # Build 10-level nested hierarchy
        curr_parent = MockParent('Root')
        curr_parent.is_root = True
        for depth_i in range(1, 10):
            curr_parent = MockParent(f'Group_L{depth_i}', parent=curr_parent)

        deep_layer = MockPSDLayer('Eye_Highlight', (10, 10, 50, 50), parent=curr_parent)

        class MockPSDImage:
            width = 1000
            height = 1000
            def descendants(self):
                return [deep_layer]

        import src.importer.psd_importer as psd_mod
        orig_has = psd_mod.HAS_PSD_TOOLS
        orig_cls = psd_mod.PSDImage
        psd_mod.HAS_PSD_TOOLS = True
        psd_mod.PSDImage = type('MockClass', (), {'open': staticmethod(lambda p: MockPSDImage())})

        try:
            with tempfile.NamedTemporaryFile(suffix='.psd', delete=False) as tf:
                tf.write(b'dummy')
                tmp_psd = tf.name

            layers = PSDImporter.load_psd(tmp_psd)
            assert len(layers) == 1
            assert layers[0].name == 'Eye_Highlight'
            assert layers[0].parent_group == '/'.join([f'Group_L{i}' for i in range(1, 10)])
            assert layers[0].category == SemanticCategory.EYES
            assert layers[0].z_depth_hint == 0.25
        finally:
            psd_mod.HAS_PSD_TOOLS = orig_has
            psd_mod.PSDImage = orig_cls
            if os.path.exists(tmp_psd):
                os.remove(tmp_psd)

    def test_large_layer_stack_compositing(self):
        """100-layer compositing stress test."""
        col = LayerCollection(canvas_size=(128, 128))
        for i in range(100):
            img = np.zeros((32, 32, 4), dtype=np.uint8)
            img[:, :] = [i % 256, (i * 2) % 256, (i * 3) % 256, 20]
            l = LayerData(
                name=f'Layer_{i:03d}',
                image=img,
                offset_x=(i * 2) % 96,
                offset_y=(i * 2) % 96,
                z_depth_hint=-1.0 + (i * 0.02),
                opacity=0.8
            )
            col.add_layer(l)

        assert len(col) == 100
        comp = col.composite()
        assert comp.shape == (128, 128, 4)
        assert comp.dtype == np.uint8


class TestMaskCroppingAndSync:
    """Tests mask synchronization with layer cropping."""

    def test_crop_with_mask_synchronization(self):
        img = np.zeros((100, 100, 4), dtype=np.uint8)
        img[20:60, 30:80, :3] = 200
        img[20:60, 30:80, 3] = 255

        mask = np.zeros((100, 100), dtype=np.uint8)
        mask[25:55, 35:75] = 255

        layer = LayerData(name='MaskedLayer', image=img, mask=mask, offset_x=10, offset_y=20)
        cropped = layer.crop_to_content()

        assert cropped.width == 50
        assert cropped.height == 40
        assert cropped.mask is not None
        assert cropped.mask.shape == (40, 50)
        assert np.all(cropped.mask[5:35, 5:45] == 255)

