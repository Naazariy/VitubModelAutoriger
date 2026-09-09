import re
from typing import Optional, Tuple, Dict, List, Any


class SemanticCategory:
    """Standardized VTuber layer semantic categories."""
    HAIR_FRONT = "hair_front"
    EYEBROWS = "eyebrows"
    NOSE = "nose"
    EYES = "eyes"
    MOUTH = "mouth"
    FACE = "face"
    EARS = "ears"
    BODY = "body"
    HAIR_BACK = "hair_back"
    ACCESSORIES = "accessories"
    UNKNOWN = "unknown"


# Nominal Z-depth mapping according to 2.5D head stratification
CATEGORY_NOMINAL_DEPTHS: Dict[str, float] = {
    SemanticCategory.HAIR_FRONT: 0.50,
    SemanticCategory.ACCESSORIES: 0.45,
    SemanticCategory.EYEBROWS: 0.35,
    SemanticCategory.NOSE: 0.30,
    SemanticCategory.EYES: 0.25,
    SemanticCategory.MOUTH: 0.20,
    SemanticCategory.FACE: 0.00,
    SemanticCategory.EARS: -0.15,
    SemanticCategory.BODY: -0.35,
    SemanticCategory.HAIR_BACK: -0.60,
    SemanticCategory.UNKNOWN: 0.00,
}


class SemanticClassifier:
    """
    Bilingual (English & Japanese) semantic classifier for VTuber character layers
    with spatial Bayesian bounding-box heuristic fallbacks.
    """

    # Keyword rules ordered by specificity (higher specificity checked first)
    RULES: List[Tuple[str, List[str]]] = [
        (
            SemanticCategory.HAIR_FRONT,
            [
                "hair_front", "front_hair", "hair_f", "side_f", "bangs", "forelock",
                "ahoge", "side_hair", "sidelocks", "frontlock",
                "前髪", "前がみ", "まえがみ", "アホ毛", "あほ毛", "横髪", "よこがみ",
                "サイドヘア", "サイド", "横束", "触角", "鬢", "もみあげ", "前髪_束",
                "前髪ベース", "前髪ハイライト"
            ]
        ),
        (
            SemanticCategory.EYEBROWS,
            [
                "eyebrow", "eyebrows", "brow", "brow_l", "brow_r", "left_eyebrow",
                "right_eyebrow", "eye_brow", "眉", "眉毛", "まゆ", "まゆげ",
                "右眉", "左眉", "眉_左", "眉_右", "眉_上", "眉_下", "眉毛_左", "眉毛_右"
            ]
        ),
        (
            SemanticCategory.HAIR_BACK,
            [
                "hair_back", "back_hair", "hair_behind", "ponytail", "twintail",
                "pigtail", "braid", "backhair", "rear_hair", "behind_hair",
                "後ろ髪", "うしろ髪", "後髪", "うしろがみ", "後ろ髪ベース", "つむじ",
                "ポニーテール", "ツインテール", "おさげ", "三つ編み", "バックヘア",
                "襟足", "えりあし"
            ]
        ),
        (
            SemanticCategory.EYES,
            [
                "eye", "eyes", "eye_l", "eye_r", "pupil", "iris", "sclera",
                "eyelash", "eyeliner", "highlight_eye", "eye_highlight", "lash",
                "目", "め", "右目", "左目", "目_左", "目_右", "瞳", "瞳孔", "黒目",
                "白目", "まつ毛", "まつげ", "上まつげ", "下まつげ", "アイライン",
                "二重", "目頭", "目尻", "ハイライト", "目の光"
            ]
        ),
        (
            SemanticCategory.NOSE,
            [
                "nose", "nostril", "nose_shadow", "nose_tip", "nose_bridge", "nose_line",
                "鼻", "はな", "鼻筋", "鼻頭", "鼻_影", "鼻先", "小鼻"
            ]
        ),
        (
            SemanticCategory.MOUTH,
            [
                "mouth", "lip", "lips", "upper_lip", "lower_lip", "teeth", "tooth",
                "tongue", "mouth_interior", "mouth_cavity", "oral",
                "口", "くち", "上唇", "下唇", "口唇", "唇", "うわくちびる", "したくちびる",
                "歯", "舌", "口内", "口の中", "口_上", "口_下", "口ライン", "口_閉じ", "口_開き"
            ]
        ),
        (
            SemanticCategory.FACE,
            [
                "face", "face_skin", "skin", "face_outline", "head", "head_base",
                "cheek", "blush", "face_base", "contour", "chin", "jaw",
                "顔", "かお", "輪郭", "りんかく", "肌", "はだ", "顔肌", "顔_輪郭",
                "顔ベース", "頬", "ほほ", "ほっぺ", "チーク", "照れ", "赤み", "フェイス"
            ]
        ),
        (
            SemanticCategory.EARS,
            [
                "ear", "ears", "ear_l", "ear_r", "left_ear", "right_ear",
                "cat_ear", "animal_ear", "elf_ear",
                "耳", "みみ", "右耳", "左耳", "耳_左", "耳_右", "ケモ耳", "獣耳",
                "猫耳", "うさ耳", "エルフ耳"
            ]
        ),
        (
            SemanticCategory.BODY,
            [
                "neck", "body", "torso", "chest", "collar", "shoulder", "arm",
                "clothes", "clothing", "shirt", "dress", "jacket", "suit",
                "首", "くび", "体", "からだ", "胴体", "胴", "身体", "服", "衣装",
                "胸", "肩", "腕", "手", "襟", "えり", "ネクタイ", "リボン_胸",
                "上着", "シャツ", "ボディ"
            ]
        ),
        (
            SemanticCategory.ACCESSORIES,
            [
                "accessory", "accessories", "ribbon", "glasses", "hat", "headband",
                "hairpin", "earring", "tiara", "horn", "crown", "pin",
                "アクセサリー", "装飾", "リボン", "メガネ", "眼鏡", "帽子",
                "カチューシャ", "ヘアピン", "ピアス", "イヤリング", "ティアラ", "角", "つの"
            ]
        ),
    ]

    @classmethod
    def _normalize_string(cls, text: str) -> str:
        """Cleans input string: splits CamelCase, lowercases, strips extension, replaces separators."""
        # Strip file extension if present
        text = re.sub(r'\.(png|jpg|jpeg|psd|webp|bmp)$', '', text, flags=re.IGNORECASE)
        # Split CamelCase: e.g. "FrontHair" -> "Front_Hair"
        text = re.sub(r'([a-z])([A-Z])', r'\1_\2', text)
        # Remove numbers and common noise / replace separators
        cleaned = text.lower().replace('-', '_').replace(' ', '_').replace('/', '_')
        return cleaned

    @classmethod
    def _match_keywords(cls, query: str) -> Optional[str]:
        """Matches a string against the ordered bilingual keyword rules."""
        norm = cls._normalize_string(query)
        norm_spaced = norm.replace('_', ' ')
        
        for category, keywords in cls.RULES:
            for kw in keywords:
                if kw.isascii():
                    kw_norm = kw.lower().replace('_', ' ')
                    # Token/word-boundary match for Latin-alphabet keywords
                    pattern = r'\b' + re.escape(kw_norm) + r'\b'
                    if re.search(pattern, norm_spaced):
                        return category
                else:
                    # Substring match for Japanese / CJK characters
                    if kw in query or kw.lower() in norm:
                        return category
        return None

    @classmethod
    def classify_spatial(
        cls,
        bbox: Tuple[int, int, int, int],
        canvas_size: Tuple[int, int],
        stack_index: Optional[int] = None,
        total_layers: Optional[int] = None
    ) -> str:
        """
        Infers semantic category from bounding box geometry and stack position
        when layer name is non-descriptive (e.g. 'Layer 1', 'Bitmap 2').
        """
        x_min, y_min, x_max, y_max = bbox
        cw, ch = canvas_size
        if cw <= 0 or ch <= 0:
            return SemanticCategory.UNKNOWN

        # Normalized coordinates
        cx = (x_min + x_max) / (2.0 * cw)
        cy = (y_min + y_max) / (2.0 * ch)
        w_norm = (x_max - x_min) / float(cw)
        h_norm = (y_max - y_min) / float(ch)
        area_norm = w_norm * h_norm
        aspect_ratio = (x_max - x_min) / float(max(1, y_max - y_min))

        # Bottom region -> Body / Neck
        if cy > 0.65 or (y_max / float(ch)) > 0.85:
            return SemanticCategory.BODY

        # Stacking position heuristic
        if stack_index is not None and total_layers is not None and total_layers >= 5:
            # Bottom 20% of stack with large area -> hair_back
            if stack_index < 0.2 * total_layers and area_norm > 0.15:
                return SemanticCategory.HAIR_BACK
            # Top 25% of stack near upper head -> hair_front
            if stack_index > 0.75 * total_layers and cy < 0.45:
                return SemanticCategory.HAIR_FRONT

        # Eyebrows: thin, horizontal, upper bilateral
        if 0.22 <= cy <= 0.38 and 0.15 <= cx <= 0.85 and area_norm < 0.04 and aspect_ratio > 1.3:
            return SemanticCategory.EYEBROWS

        # Eyes: bilateral, mid-upper facial region
        if 0.28 <= cy <= 0.48 and (0.18 <= cx <= 0.45 or 0.55 <= cx <= 0.82) and area_norm < 0.08:
            return SemanticCategory.EYES

        # Nose: central, small
        if 0.40 <= cy <= 0.58 and 0.42 <= cx <= 0.58 and area_norm < 0.03:
            return SemanticCategory.NOSE

        # Mouth: central lower facial region, horizontal
        if 0.50 <= cy <= 0.70 and 0.35 <= cx <= 0.65 and area_norm < 0.06 and aspect_ratio >= 1.0:
            return SemanticCategory.MOUTH

        # Ears: outer lateral edges
        if 0.30 <= cy <= 0.60 and (cx < 0.28 or cx > 0.72) and area_norm < 0.10:
            return SemanticCategory.EARS

        # Face: large central skin area
        if 0.25 <= cy <= 0.65 and 0.35 <= cx <= 0.65 and area_norm >= 0.10:
            return SemanticCategory.FACE

        # Upper region default
        if cy < 0.40:
            return SemanticCategory.HAIR_FRONT

        return SemanticCategory.UNKNOWN

    @classmethod
    def classify(
        cls,
        name: str,
        parent_group: Optional[str] = None,
        bbox: Optional[Tuple[int, int, int, int]] = None,
        canvas_size: Optional[Tuple[int, int]] = None,
        stack_index: Optional[int] = None,
        total_layers: Optional[int] = None
    ) -> Tuple[str, float]:
        """
        Classifies a layer into a semantic category and returns (category, nominal_z_depth).

        Args:
            name: Layer display name (e.g. "Hair_Front", "前髪", "Layer 1")
            parent_group: Optional parent group hierarchy path (e.g. "Head/Eyes")
            bbox: Optional (x_min, y_min, x_max, y_max) bounding box
            canvas_size: Optional (width, height) of full canvas
            stack_index: Optional 0-based index in layer stack
            total_layers: Optional total count of layers in asset

        Returns:
            Tuple of (category_string, nominal_z_depth_float)
        """
        # Step 1: Direct layer name matching
        cat = cls._match_keywords(name)

        # Step 2: Parent group context inheritance if unmatched
        if cat is None and parent_group:
            cat = cls._match_keywords(parent_group)

        # Step 3: Spatial Bayesian heuristic fallback if still unknown
        if (cat is None or cat == SemanticCategory.UNKNOWN) and bbox is not None and canvas_size is not None:
            cat = cls.classify_spatial(bbox, canvas_size, stack_index, total_layers)

        if cat is None:
            cat = SemanticCategory.UNKNOWN

        depth = CATEGORY_NOMINAL_DEPTHS.get(cat, 0.0)
        return cat, depth
