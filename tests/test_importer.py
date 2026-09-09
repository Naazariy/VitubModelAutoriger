import os
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


class TestSemanticClassifier:
    """Unit tests for the bilingual semantic classification engine."""

    def test_bilingual_classification_japanese(self):
        jp_cases = [
            ("前髪", SemanticCategory.HAIR_FRONT, 0.50),
            ("前髪_束_01", SemanticCategory.HAIR_FRONT, 0.50),
            ("右目_瞳", SemanticCategory.EYES, 0.25),
            ("左目_まつ毛", SemanticCategory.EYES, 0.25),
            ("眉毛_左", SemanticCategory.EYEBROWS, 0.35),
            ("輪郭", SemanticCategory.FACE, 0.00),
            ("顔肌", SemanticCategory.FACE, 0.00),
            ("頬_赤み", SemanticCategory.FACE, 0.00),
            ("上唇", SemanticCategory.MOUTH, 0.20),
            ("口_開き", SemanticCategory.MOUTH, 0.20),
            ("後ろ髪ベース", SemanticCategory.HAIR_BACK, -0.60),
            ("ポニーテール", SemanticCategory.HAIR_BACK, -0.60),
            ("首", SemanticCategory.BODY, -0.35),
            ("服_上着", SemanticCategory.BODY, -0.35),
            ("ケモ耳", SemanticCategory.EARS, -0.15),
            ("リボン_頭", SemanticCategory.ACCESSORIES, 0.45),
            ("メガネ", SemanticCategory.ACCESSORIES, 0.45),
            ("鼻筋", SemanticCategory.NOSE, 0.30),
        ]
        for name, expected_cat, expected_depth in jp_cases:
            cat, depth = SemanticClassifier.classify(name)
            assert cat == expected_cat, f"Failed for Japanese name: '{name}', got '{cat}' expected '{expected_cat}'"
            assert abs(depth - expected_depth) < 1e-4

    def test_bilingual_classification_english(self):
        en_cases = [
            ("bangs", SemanticCategory.HAIR_FRONT, 0.50),
            ("hair_front", SemanticCategory.HAIR_FRONT, 0.50),
            ("side_hair", SemanticCategory.HAIR_FRONT, 0.50),
            ("eye_l", SemanticCategory.EYES, 0.25),
            ("pupil_r", SemanticCategory.EYES, 0.25),
            ("eyebrow_r", SemanticCategory.EYEBROWS, 0.35),
            ("nose", SemanticCategory.NOSE, 0.30),
            ("mouth", SemanticCategory.MOUTH, 0.20),
            ("lip_upper", SemanticCategory.MOUTH, 0.20),
            ("face", SemanticCategory.FACE, 0.00),
            ("chin", SemanticCategory.FACE, 0.00),
            ("ear_l", SemanticCategory.EARS, -0.15),
            ("neck", SemanticCategory.BODY, -0.35),
            ("body", SemanticCategory.BODY, -0.35),
            ("hair_back", SemanticCategory.HAIR_BACK, -0.60),
            ("ponytail", SemanticCategory.HAIR_BACK, -0.60),
            ("ribbon", SemanticCategory.ACCESSORIES, 0.45),
        ]
        for name, expected_cat, expected_depth in en_cases:
            cat, depth = SemanticClassifier.classify(name)
            assert cat == expected_cat, f"Failed for English name: '{name}', got '{cat}' expected '{expected_cat}'"
            assert abs(depth - expected_depth) < 1e-4

    def test_mixed_naming_and_case_insensitivity(self):
        cases = [
            ("Hair_Front_01.png", SemanticCategory.HAIR_FRONT),
            ("顔_赤み(乗算).PNG", SemanticCategory.FACE),
            ("R_EYE_pupil_v2", SemanticCategory.EYES),
            ("BACK_HAIR_LAYER", SemanticCategory.HAIR_BACK),
            ("Head/Eyes/Left_Iris", SemanticCategory.EYES),
        ]
        for name, expected_cat in cases:
            cat, _ = SemanticClassifier.classify(name)
            assert cat == expected_cat, f"Failed for mixed name '{name}'"

    def test_nominal_z_depth_stratification(self):
        # Verify strict depth ordering
        _, z_front = SemanticClassifier.classify("bangs")
        _, z_brow = SemanticClassifier.classify("eyebrow")
        _, z_eye = SemanticClassifier.classify("eye")
        _, z_face = SemanticClassifier.classify("face")
        _, z_ear = SemanticClassifier.classify("ear")
        _, z_body = SemanticClassifier.classify("body")
        _, z_back = SemanticClassifier.classify("hair_back")

        assert z_front > z_brow > z_eye > z_face > z_ear > z_body > z_back

    def test_spatial_heuristic_fallbacks(self):
        # Unnamed layer at bottom of canvas -> body
        cat_body, _ = SemanticClassifier.classify(
            name="Layer 1",
            bbox=(100, 400, 400, 500),
            canvas_size=(512, 512)
        )
        assert cat_body == SemanticCategory.BODY

        # Unnamed layer in upper bilateral region -> eyebrows or eyes
        cat_eye, _ = SemanticClassifier.classify(
            name="Bitmap 2",
            bbox=(100, 160, 180, 220),
            canvas_size=(512, 512)
        )
        assert cat_eye in [SemanticCategory.EYES, SemanticCategory.EYEBROWS]

    def test_camel_case_classification(self):
        cases = [
            ("FrontHair", SemanticCategory.HAIR_FRONT),
            ("HairBack", SemanticCategory.HAIR_BACK),
            ("SideHair", SemanticCategory.HAIR_FRONT),
            ("HairFront", SemanticCategory.HAIR_FRONT),
        ]
        for name, expected_cat in cases:
            cat, _ = SemanticClassifier.classify(name)
            assert cat == expected_cat, f"Failed for CamelCase name '{name}': got '{cat}', expected '{expected_cat}'"

    def test_anti_collision_keywords(self):
        # Anti-collision tests: ensure substring collisions do not trigger false positives
        # 'outerwear' contains 'ear', but must not be classified as EARS
        cat_outerwear, _ = SemanticClassifier.classify("outerwear")
        assert cat_outerwear != SemanticCategory.EARS, f"'outerwear' misclassified as EARS"

        # 'floral_dress' contains 'oral' (mouth) and 'dress' (body). Must classify as BODY, not MOUTH.
        cat_floral, _ = SemanticClassifier.classify("floral_dress")
        assert cat_floral == SemanticCategory.BODY, f"'floral_dress' got '{cat_floral}', expected BODY"

        # 'tears' contains 'ear', must not be classified as EARS
        cat_tears, _ = SemanticClassifier.classify("tears")
        assert cat_tears != SemanticCategory.EARS, f"'tears' misclassified as EARS"

        # 'heart_accessory' contains 'ear', must classify as ACCESSORIES, not EARS
        cat_heart, _ = SemanticClassifier.classify("heart_accessory")
        assert cat_heart == SemanticCategory.ACCESSORIES, f"'heart_accessory' got '{cat_heart}', expected ACCESSORIES"

        # 'pearl_necklace' contains 'ear', must not be classified as EARS
        cat_pearl, _ = SemanticClassifier.classify("pearl_necklace")
        assert cat_pearl != SemanticCategory.EARS, f"'pearl_necklace' misclassified as EARS"


class TestImageImporter:
    """Unit tests for ImageImporter and synthetic head generation."""

    def test_load_single_flat_png(self, tmp_path):
        test_file = tmp_path / "test_sample.png"
        img = Image.new("RGBA", (100, 80), (255, 0, 0, 200))
        img.save(test_file)

        rgba, alpha = ImageImporter.load_image(str(test_file))
        assert rgba.shape == (80, 100, 4)
        assert alpha.shape == (80, 100)
        assert rgba.dtype == np.uint8
        assert np.all(rgba[:, :, 0] == 255)
        assert np.all(alpha == 200)

    def test_load_directory_png_layers(self, tmp_path):
        sub_dir = tmp_path / "character_layers"
        sub_dir.mkdir()

        # Create 3 layer files
        Image.new("RGBA", (200, 200), (40, 40, 50, 255)).save(sub_dir / "01_hair_back.png")
        Image.new("RGBA", (200, 200), (250, 220, 190, 255)).save(sub_dir / "02_face.png")
        Image.new("RGBA", (200, 200), (60, 50, 70, 255)).save(sub_dir / "03_hair_front.png")

        layers = ImageImporter.load_directory(str(sub_dir), canvas_size=(200, 200))
        assert len(layers) == 3
        assert layers[0].name == "01_hair_back"
        assert layers[0].category == SemanticCategory.HAIR_BACK
        assert layers[1].name == "02_face"
        assert layers[1].category == SemanticCategory.FACE
        assert layers[2].name == "03_hair_front"
        assert layers[2].category == SemanticCategory.HAIR_FRONT

    def test_synthetic_layered_head_generator(self):
        layers = ImageImporter.create_synthetic_layered_head(512, 512)
        assert len(layers) == 14

        layer_names = [l.name for l in layers]
        assert "Hair_Back" in layer_names
        assert "Face" in layer_names
        assert "Eye_L" in layer_names
        assert "Eye_R" in layer_names
        assert "Mouth" in layer_names
        assert "Nose" in layer_names
        assert "Hair_Front" in layer_names

        # Check all layers have non-empty cropped images
        for l in layers:
            assert l.width > 0
            assert l.height > 0
            assert l.image.ndim == 3
            assert l.image.shape[2] == 4
            assert l.image.dtype == np.uint8
            assert np.any(l.alpha_mask > 0)

    def test_contour_extraction_robustness(self):
        # Circle mask
        alpha = np.zeros((100, 100), dtype=np.uint8)
        y, x = np.ogrid[:100, :100]
        mask = (x - 50)**2 + (y - 50)**2 <= 30**2
        alpha[mask] = 255

        contour = ImageImporter.extract_contour(alpha, threshold=10, simplify_eps=2.0)
        assert len(contour) >= 3
        assert contour.shape[1] == 2

        # Empty mask fallback to bounding box
        empty_alpha = np.zeros((64, 64), dtype=np.uint8)
        empty_contour = ImageImporter.extract_contour(empty_alpha, threshold=10)
        assert len(empty_contour) >= 3

    def test_pure_python_contour_fallback(self):
        alpha = np.zeros((50, 50), dtype=np.uint8)
        alpha[10:40, 10:40] = 255
        contour = ImageImporter._extract_contour_pure_python(alpha, threshold=10)
        assert len(contour) >= 3
        assert contour.shape[1] == 2


class TestLayerDataAndCollection:
    """Unit tests for LayerData and LayerCollection models."""

    def test_layer_data_crop_and_bounds(self):
        # 100x100 image with content in [20:60, 30:80]
        img = np.zeros((100, 100, 4), dtype=np.uint8)
        img[20:60, 30:80, :3] = 200
        img[20:60, 30:80, 3] = 255

        layer = LayerData(name="TestLayer", image=img, offset_x=10, offset_y=20)
        assert layer.width == 100
        assert layer.height == 100
        assert layer.bbox == (10, 20, 110, 120)
        assert not layer.is_empty

        cropped = layer.crop_to_content()
        assert cropped.width == 50   # 80 - 30
        assert cropped.height == 40  # 60 - 20
        assert cropped.offset_x == 10 + 30
        assert cropped.offset_y == 20 + 20

    def test_layer_collection_composite_and_sorting(self):
        col = LayerCollection(canvas_size=(200, 200))
        
        # Layer 1: Face (z=0.0)
        img1 = np.full((100, 100, 4), 100, dtype=np.uint8)
        l1 = LayerData(name="Face", image=img1, offset_x=50, offset_y=50, z_depth_hint=0.0)
        
        # Layer 2: Hair (z=0.5)
        img2 = np.full((100, 100, 4), 200, dtype=np.uint8)
        l2 = LayerData(name="Hair", image=img2, offset_x=50, offset_y=50, z_depth_hint=0.5)

        col.add_layer(l2)
        col.add_layer(l1)

        sorted_layers = col.sort_by_z_depth()
        assert sorted_layers[0].name == "Face"
        assert sorted_layers[1].name == "Hair"

        comp = col.composite()
        assert comp.shape == (200, 200, 4)
        assert comp.dtype == np.uint8


class TestErrorHandlingAndPSD:
    """Error handling and PSD integration test suite."""

    def test_missing_files_error_handling(self):
        with pytest.raises(FileNotFoundError):
            ImageImporter.load_image("non_existent_image_path_123.png")

        with pytest.raises(FileNotFoundError):
            ImageImporter.load_directory("non_existent_directory_456")

        with pytest.raises(FileNotFoundError):
            PSDImporter.load_psd("non_existent_psd_789.psd")

    def test_psd_importer_availability_check(self):
        # Availability query should return a boolean without crashing
        avail = PSDImporter.is_available()
        assert isinstance(avail, bool)
