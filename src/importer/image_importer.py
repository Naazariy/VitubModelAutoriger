import os
import math
from pathlib import Path
from typing import Tuple, List, Optional
import numpy as np
from PIL import Image, ImageDraw

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import scipy.spatial
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from src.core.layer import LayerData
from src.importer.semantic_classifier import SemanticClassifier, SemanticCategory, CATEGORY_NOMINAL_DEPTHS


class ImageImporter:
    """
    Handles single image loading, directory ingestion, silhouette contour extraction
    (with OpenCV acceleration and pure-Python fallback), and multi-layer synthetic head generation.
    """

    @staticmethod
    def load_image(filepath: str) -> Tuple[np.ndarray, np.ndarray]:
        """
        Loads an image from filepath.
        Returns:
            rgba_image: np.ndarray of shape (H, W, 4) in uint8 [0, 255]
            alpha_mask: np.ndarray of shape (H, W) in uint8 [0, 255]
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {filepath}")

        pil_img = Image.open(filepath).convert("RGBA")
        rgba = np.array(pil_img, dtype=np.uint8)
        alpha = rgba[:, :, 3]
        return rgba, alpha

    @classmethod
    def load_directory(cls, dirpath: str, canvas_size: Optional[Tuple[int, int]] = None) -> List[LayerData]:
        """
        Scans a directory of PNG/JPG images and loads each as a LayerData object.
        Applies bilingual semantic classification and nominal depth assignment based on filenames.

        Args:
            dirpath: Path to folder containing image files.
            canvas_size: Optional (width, height) specifying expected canvas dimensions.

        Returns:
            List[LayerData]: Sorted list of layer objects.
        """
        folder = Path(dirpath)
        if not folder.exists() or not folder.is_dir():
            raise FileNotFoundError(f"Directory not found: {dirpath}")

        valid_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in valid_extensions]

        # Sort naturally (e.g. 01_hair_back, 02_body, ...)
        files.sort(key=lambda p: p.stem.lower())
        total_layers = len(files)

        layers: List[LayerData] = []
        for idx, file_path in enumerate(files):
            rgba, _ = cls.load_image(str(file_path))
            h, w = rgba.shape[:2]
            name = file_path.stem

            cw = canvas_size[0] if canvas_size else w
            ch = canvas_size[1] if canvas_size else h

            cat, depth = SemanticClassifier.classify(
                name=name,
                canvas_size=(cw, ch),
                stack_index=idx,
                total_layers=total_layers
            )

            layer = LayerData(
                name=name,
                image=rgba,
                offset_x=0,
                offset_y=0,
                z_depth_hint=depth,
                category=cat,
                layer_id=f"{name}_{idx}"
            )
            layers.append(layer)

        return layers

    @staticmethod
    def _extract_contour_pure_python(alpha_mask: np.ndarray, threshold: int = 10, simplify_eps: float = 2.0) -> np.ndarray:
        """
        Pure-Python fallback contour extraction when OpenCV is unavailable.
        Uses boundary pixel scanning and convex hull / polygon approximation.
        """
        h, w = alpha_mask.shape
        binary = alpha_mask >= threshold
        ys, xs = np.where(binary)

        if len(xs) < 3:
            return np.array([[0.0, 0.0], [float(w), 0.0], [float(w), float(h)], [0.0, float(h)]], dtype=np.float64)

        points = np.column_stack([xs, ys]).astype(np.float64)

        if HAS_SCIPY:
            try:
                hull = scipy.spatial.ConvexHull(points)
                hull_pts = points[hull.vertices]
                return hull_pts
            except Exception:
                pass

        # Simple bounding box fallback
        min_x, max_x = float(np.min(xs)), float(np.max(xs))
        min_y, max_y = float(np.min(ys)), float(np.max(ys))
        return np.array([
            [min_x, min_y],
            [max_x, min_y],
            [max_x, max_y],
            [min_x, max_y]
        ], dtype=np.float64)

    @classmethod
    def extract_contour(cls, alpha_mask: np.ndarray, threshold: int = 10, simplify_eps: float = 2.0) -> np.ndarray:
        """
        Extracts boundary contour of character silhouette from alpha mask.
        Returns:
            contour: np.ndarray of shape (K, 2) containing boundary polygon (x, y) coordinates.
        """
        h, w = alpha_mask.shape
        if not np.any(alpha_mask >= threshold):
            return np.array([[0.0, 0.0], [float(w), 0.0], [float(w), float(h)], [0.0, float(h)]], dtype=np.float64)

        if not HAS_CV2:
            return cls._extract_contour_pure_python(alpha_mask, threshold, simplify_eps)

        _, binary = cv2.threshold(alpha_mask, threshold, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return np.array([[0.0, 0.0], [float(w), 0.0], [float(w), float(h)], [0.0, float(h)]], dtype=np.float64)

        largest_contour = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest_contour) < 4:
            return np.array([[0.0, 0.0], [float(w), 0.0], [float(w), float(h)], [0.0, float(h)]], dtype=np.float64)

        if simplify_eps > 0:
            approx = cv2.approxPolyDP(largest_contour, simplify_eps, True)
            contour_pts = approx.reshape(-1, 2).astype(np.float64)
        else:
            contour_pts = largest_contour.reshape(-1, 2).astype(np.float64)

        if len(contour_pts) < 3:
            return np.array([[0.0, 0.0], [float(w), 0.0], [float(w), float(h)], [0.0, float(h)]], dtype=np.float64)

        return contour_pts

    @staticmethod
    def create_synthetic_head_image(width: int = 512, height: int = 512) -> Tuple[np.ndarray, np.ndarray]:
        """
        Generates a single flat synthetic character head image (ellipse head with eyes, mouth, ear)
        for testing and default visualization without external assets.
        """
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        center_x, center_y = width // 2, height // 2
        head_rx, head_ry = width // 3, int(height // 2.5)

        # 1. Ears
        ear_w, ear_h = 25, 45
        draw.ellipse([center_x - head_rx - ear_w, center_y - ear_h, center_x - head_rx + ear_w, center_y + ear_h], fill=(240, 200, 170, 255))
        draw.ellipse([center_x + head_rx - ear_w, center_y - ear_h, center_x + head_rx + ear_w, center_y + ear_h], fill=(240, 200, 170, 255))

        # 2. Head background (skin tone)
        draw.ellipse([center_x - head_rx, center_y - head_ry, center_x + head_rx, center_y + head_ry], fill=(255, 220, 190, 255), outline=(180, 140, 110, 255), width=3)

        # 3. Eyes
        eye_y = int(center_y - head_ry * 0.15)
        eye_offset = int(head_rx * 0.4)
        
        # Left eye
        draw.ellipse([center_x - eye_offset - 20, eye_y - 28, center_x - eye_offset + 20, eye_y + 28], fill=(255, 255, 255, 255))
        draw.ellipse([center_x - eye_offset - 10, eye_y - 10, center_x - eye_offset + 10, eye_y + 10], fill=(50, 100, 200, 255))
        
        # Right eye
        draw.ellipse([center_x + eye_offset - 20, eye_y - 28, center_x + eye_offset + 20, eye_y + 28], fill=(255, 255, 255, 255))
        draw.ellipse([center_x + eye_offset - 10, eye_y - 10, center_x + eye_offset + 10, eye_y + 10], fill=(50, 100, 200, 255))

        # 4. Nose & Mouth
        draw.ellipse([center_x - 4, center_y + 15 - 4, center_x + 4, center_y + 15 + 4], fill=(200, 120, 100, 255))
        draw.arc([center_x - 30, center_y + 45, center_x + 30, center_y + 65], start=0, end=180, fill=(200, 60, 60, 255), width=4)

        rgba = np.array(img, dtype=np.uint8)
        alpha = rgba[:, :, 3]
        return rgba, alpha

    @classmethod
    def create_synthetic_layered_head(cls, width: int = 512, height: int = 512) -> List[LayerData]:
        """
        Generates a 14-layer synthetic character decomposition for 100% self-contained
        end-to-end multi-layer VTuber deformation and Live2D export testing.
        """
        cx, cy = width // 2, height // 2
        head_rx, head_ry = width // 3, int(height // 2.5)

        layers: List[LayerData] = []

        def _make_layer(name: str, cat: str, z_hint: float, draw_fn) -> LayerData:
            img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw_fn(draw)
            rgba = np.array(img, dtype=np.uint8)
            layer = LayerData(
                name=name,
                image=rgba,
                offset_x=0,
                offset_y=0,
                z_depth_hint=z_hint,
                category=cat,
                layer_id=name
            )
            return layer.crop_to_content()

        # 1. Hair_Back (z = -0.60)
        def draw_hair_back(draw: ImageDraw.ImageDraw):
            draw.ellipse([cx - head_rx - 30, cy - head_ry - 20, cx + head_rx + 30, cy + head_ry + 60], fill=(45, 35, 55, 255))
        layers.append(_make_layer("Hair_Back", SemanticCategory.HAIR_BACK, -0.60, draw_hair_back))

        # 2. Neck_Body (z = -0.35)
        def draw_neck_body(draw: ImageDraw.ImageDraw):
            draw.rectangle([cx - 35, cy + int(head_ry * 0.6), cx + 35, height], fill=(235, 200, 175, 255))
            draw.polygon([(cx - 140, height), (cx + 140, height), (cx + 80, cy + int(head_ry * 0.9)), (cx - 80, cy + int(head_ry * 0.9))], fill=(60, 80, 120, 255))
        layers.append(_make_layer("Neck_Body", SemanticCategory.BODY, -0.35, draw_neck_body))

        # 3. Ear_L (z = -0.15)
        def draw_ear_l(draw: ImageDraw.ImageDraw):
            draw.ellipse([cx - head_rx - 25, cy - 45, cx - head_rx + 25, cy + 45], fill=(240, 200, 170, 255), outline=(190, 150, 120, 255), width=2)
        layers.append(_make_layer("Ear_L", SemanticCategory.EARS, -0.15, draw_ear_l))

        # 4. Ear_R (z = -0.15)
        def draw_ear_r(draw: ImageDraw.ImageDraw):
            draw.ellipse([cx + head_rx - 25, cy - 45, cx + head_rx + 25, cy + 45], fill=(240, 200, 170, 255), outline=(190, 150, 120, 255), width=2)
        layers.append(_make_layer("Ear_R", SemanticCategory.EARS, -0.15, draw_ear_r))

        # 5. Face (z = 0.00)
        def draw_face(draw: ImageDraw.ImageDraw):
            draw.ellipse([cx - head_rx, cy - head_ry, cx + head_rx, cy + head_ry], fill=(255, 225, 195, 255), outline=(180, 140, 110, 255), width=2)
        layers.append(_make_layer("Face", SemanticCategory.FACE, 0.00, draw_face))

        # 6. Blush_L (z = +0.05)
        def draw_blush_l(draw: ImageDraw.ImageDraw):
            draw.ellipse([cx - int(head_rx * 0.65), cy + 15, cx - int(head_rx * 0.25), cy + 45], fill=(255, 150, 160, 160))
        layers.append(_make_layer("Blush_L", SemanticCategory.FACE, 0.05, draw_blush_l))

        # 7. Blush_R (z = +0.05)
        def draw_blush_r(draw: ImageDraw.ImageDraw):
            draw.ellipse([cx + int(head_rx * 0.25), cy + 15, cx + int(head_rx * 0.65), cy + 45], fill=(255, 150, 160, 160))
        layers.append(_make_layer("Blush_R", SemanticCategory.FACE, 0.05, draw_blush_r))

        # 8. Mouth (z = +0.20)
        def draw_mouth(draw: ImageDraw.ImageDraw):
            draw.arc([cx - 28, cy + 45, cx + 28, cy + 65], start=0, end=180, fill=(200, 50, 50, 255), width=3)
        layers.append(_make_layer("Mouth", SemanticCategory.MOUTH, 0.20, draw_mouth))

        # 9. Eye_L (z = +0.25)
        def draw_eye_l(draw: ImageDraw.ImageDraw):
            ey = int(cy - head_ry * 0.15)
            ex = int(cx - head_rx * 0.45)
            draw.ellipse([ex - 22, ey - 30, ex + 22, ey + 30], fill=(255, 255, 255, 255))
            draw.ellipse([ex - 14, ey - 18, ex + 14, ey + 18], fill=(60, 110, 220, 255))
            draw.ellipse([ex - 6, ey - 8, ex + 6, ey + 8], fill=(20, 30, 80, 255))
            draw.ellipse([ex + 2, ey - 12, ex + 8, ey - 6], fill=(255, 255, 255, 255))
            draw.arc([ex - 24, ey - 34, ex + 24, ey - 10], start=180, end=360, fill=(30, 30, 40, 255), width=4)
        layers.append(_make_layer("Eye_L", SemanticCategory.EYES, 0.25, draw_eye_l))

        # 10. Eye_R (z = +0.25)
        def draw_eye_r(draw: ImageDraw.ImageDraw):
            ey = int(cy - head_ry * 0.15)
            ex = int(cx + head_rx * 0.45)
            draw.ellipse([ex - 22, ey - 30, ex + 22, ey + 30], fill=(255, 255, 255, 255))
            draw.ellipse([ex - 14, ey - 18, ex + 14, ey + 18], fill=(60, 110, 220, 255))
            draw.ellipse([ex - 6, ey - 8, ex + 6, ey + 8], fill=(20, 30, 80, 255))
            draw.ellipse([ex + 2, ey - 12, ex + 8, ey - 6], fill=(255, 255, 255, 255))
            draw.arc([ex - 24, ey - 34, ex + 24, ey - 10], start=180, end=360, fill=(30, 30, 40, 255), width=4)
        layers.append(_make_layer("Eye_R", SemanticCategory.EYES, 0.25, draw_eye_r))

        # 11. Nose (z = +0.30)
        def draw_nose(draw: ImageDraw.ImageDraw):
            draw.ellipse([cx - 3, cy + 12, cx + 3, cy + 18], fill=(190, 110, 90, 255))
        layers.append(_make_layer("Nose", SemanticCategory.NOSE, 0.30, draw_nose))

        # 12. Eyebrow_L (z = +0.35)
        def draw_eyebrow_l(draw: ImageDraw.ImageDraw):
            ex = int(cx - head_rx * 0.45)
            ey = int(cy - head_ry * 0.15) - 45
            draw.arc([ex - 26, ey - 10, ex + 26, ey + 20], start=200, end=340, fill=(50, 40, 60, 255), width=4)
        layers.append(_make_layer("Eyebrow_L", SemanticCategory.EYEBROWS, 0.35, draw_eyebrow_l))

        # 13. Eyebrow_R (z = +0.35)
        def draw_eyebrow_r(draw: ImageDraw.ImageDraw):
            ex = int(cx + head_rx * 0.45)
            ey = int(cy - head_ry * 0.15) - 45
            draw.arc([ex - 26, ey - 10, ex + 26, ey + 20], start=200, end=340, fill=(50, 40, 60, 255), width=4)
        layers.append(_make_layer("Eyebrow_R", SemanticCategory.EYEBROWS, 0.35, draw_eyebrow_r))

        # 14. Hair_Front (z = +0.50)
        def draw_hair_front(draw: ImageDraw.ImageDraw):
            # Forehead bangs fringe
            draw.polygon([
                (cx - head_rx - 10, cy - head_ry - 10),
                (cx + head_rx + 10, cy - head_ry - 10),
                (cx + head_rx + 5, cy),
                (cx + int(head_rx * 0.5), cy - 20),
                (cx + int(head_rx * 0.2), cy + 10),
                (cx, cy - 30),
                (cx - int(head_rx * 0.2), cy + 10),
                (cx - int(head_rx * 0.5), cy - 20),
                (cx - head_rx - 5, cy)
            ], fill=(60, 45, 75, 255))
            # Ahoge strand
            draw.arc([cx - 20, cy - head_ry - 50, cx + 40, cy - head_ry + 10], start=220, end=350, fill=(60, 45, 75, 255), width=5)
        layers.append(_make_layer("Hair_Front", SemanticCategory.HAIR_FRONT, 0.50, draw_hair_front))

        return layers

