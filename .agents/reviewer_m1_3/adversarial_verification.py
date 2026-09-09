import sys
import os
import io

# Set UTF-8 output encoding for console compatibility
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, 'd:/VitubModel')
import numpy as np
import pytest
from src.importer.image_importer import ImageImporter
from src.importer.semantic_classifier import SemanticClassifier, SemanticCategory
from src.importer.psd_importer import PSDImporter
from src.generator.mesh_generator import MeshGenerator
from src.core.layer import LayerData, LayerCollection
from src.core.mesh import Mesh

print("================================================================")
print("  REVIEWER 2 / CRITIC ADVERSARIAL STRESS TEST & INTEGRITY SUITE  ")
print("================================================================")

# 1. Comprehensive 14 Layers x 5 Grid Sizes Matrix Verification
print("\n--- 1. Multi-Grid Layer Matrix (14 Layers x 5 Grids = 70 Meshes) ---")
layers = ImageImporter.create_synthetic_layered_head(512, 512)
grid_sizes = [10, 15, 20, 25, 30]

total_configs = 0
passed_configs = 0

for g in grid_sizes:
    print(f"\nEvaluating grid size: {g}")
    for l in layers:
        total_configs += 1
        mesh = MeshGenerator.generate_mesh_from_layer(l, target_grid_size=g)
        
        # Check basic counts
        assert len(mesh.vertices) >= 3, f"[{l.name} @ g={g}] Verts < 3: {len(mesh.vertices)}"
        assert len(mesh.triangles) >= 1, f"[{l.name} @ g={g}] Tris < 1: {len(mesh.triangles)}"
        
        # Check signed areas
        areas = mesh.compute_triangle_signed_areas()
        min_area = np.min(areas)
        assert min_area > 1e-6, f"[{l.name} @ g={g}] Non-positive min area: {min_area}"
        
        # Check topology
        is_valid, errors = mesh.validate_topology()
        assert is_valid, f"[{l.name} @ g={g}] Topology error: {errors}"
        
        # Check UVs
        assert np.all(mesh.uvs >= 0.0) and np.all(mesh.uvs <= 1.0), f"[{l.name} @ g={g}] UV bounds exceeded"
        
        # Check positions
        pos = mesh.get_positions()
        assert np.all(pos >= -1.0) and np.all(pos <= 1.0), f"[{l.name} @ g={g}] Position bounds exceeded"
        
        # Check edges
        assert len(mesh.edges) > 0, f"[{l.name} @ g={g}] 0 edges"
        assert len(mesh.rest_edge_lengths) == len(mesh.edges), f"[{l.name} @ g={g}] Edge length mismatch"
        assert np.all(mesh.rest_edge_lengths > 0.0), f"[{l.name} @ g={g}] Non-positive rest edge length"
        
        passed_configs += 1
        print(f"  [{l.name:15s} @ g={g:2d}] {len(mesh.vertices):4d}v, {len(mesh.triangles):4d}t, min_area: {min_area:.6f} -> PASS")

print(f"\nMatrix Result: {passed_configs}/{total_configs} configurations PASSED 100%.")

# 2. Adversarial Mesh Smoothing Stress Testing
print("\n--- 2. Adversarial Smoothing Stress Testing ---")
star_contour = np.array([
    [100.0, 10.0], [120.0, 70.0], [180.0, 70.0], [130.0, 110.0],
    [150.0, 170.0], [100.0, 130.0], [50.0, 170.0], [70.0, 110.0],
    [20.0, 70.0], [80.0, 70.0]
], dtype=np.float64)

for iters in [0, 5, 15, 30, 50]:
    mesh_star = MeshGenerator.generate_mesh_from_contour(
        star_contour, (200, 200), target_grid_size=12, smoothing_iterations=iters
    )
    areas_star = mesh_star.compute_triangle_signed_areas()
    valid_star, err_star = mesh_star.validate_topology()
    assert valid_star, f"Star mesh invalid at iters={iters}: {err_star}"
    assert np.all(areas_star > 1e-6), f"Star mesh inverted triangle at iters={iters}: min={np.min(areas_star)}"
    print(f"  Star polygon (iters={iters:2d}): {len(mesh_star.vertices):3d}v, {len(mesh_star.triangles):3d}t, min_area={np.min(areas_star):.6f} -> PASS")

# 3. Pathological Edge-Case Meshes
print("\n--- 3. Pathological Edge-Case Meshes ---")
needle_contour = np.array([[10.0, 10.0], [10.5, 10.0], [10.25, 200.0]], dtype=np.float64)
mesh_needle = MeshGenerator.generate_mesh_from_contour(needle_contour, (250, 50), target_grid_size=10)
valid_needle, _ = mesh_needle.validate_topology()
print(f"  Needle contour: {len(mesh_needle.vertices)}v, {len(mesh_needle.triangles)}t, topology_valid={valid_needle}")

empty_contour = np.zeros((0, 2), dtype=np.float64)
mesh_empty = MeshGenerator.generate_mesh_from_contour(empty_contour, (100, 100))
valid_empty, _ = mesh_empty.validate_topology()
assert valid_empty and len(mesh_empty.triangles) >= 2
print(f"  Empty contour fallback: {len(mesh_empty.vertices)}v, {len(mesh_empty.triangles)}t -> PASS")

two_pts = np.array([[10.0, 10.0], [20.0, 20.0]], dtype=np.float64)
mesh_two = MeshGenerator.generate_mesh_from_contour(two_pts, (100, 100))
valid_two, _ = mesh_two.validate_topology()
assert valid_two and len(mesh_two.triangles) >= 2
print(f"  Two-point contour fallback: {len(mesh_two.vertices)}v, {len(mesh_two.triangles)}t -> PASS")

# 4. Semantic Classifier Adversarial String Tests
print("\n--- 4. Semantic Classifier Adversarial Token Stress Tests ---")
adv_cases = [
    ("bear_ears", SemanticCategory.EARS),
    ("pearl_earring", SemanticCategory.ACCESSORIES),
    ("tear_drop_glasses", SemanticCategory.ACCESSORIES),
    ("side_fringe_bangs", SemanticCategory.HAIR_FRONT),
    ("back_ponytail_ribbon", SemanticCategory.HAIR_BACK),
    ("left_eyebrow_piercing", SemanticCategory.EYEBROWS),
    ("facial_expression_blush", SemanticCategory.FACE),
    ("mouth_upper_lip_gloss", SemanticCategory.MOUTH),
    ("body_jacket_collar", SemanticCategory.BODY),
    ("FrontHair_Layer_01_FINAL", SemanticCategory.HAIR_FRONT),
    ("BackHairShadow_v2", SemanticCategory.HAIR_BACK),
    ("LeftEyeHighlight_A", SemanticCategory.EYES),
    ("RightEyeLash_B", SemanticCategory.EYES),
    ("前髪ハイライト_02", SemanticCategory.HAIR_FRONT),
    ("後ろ髪_ツインテール", SemanticCategory.HAIR_BACK),
    ("右目_瞳孔", SemanticCategory.EYES),
    ("エルフ耳_右", SemanticCategory.EARS),
    ("チョーカー_首輪", SemanticCategory.BODY),
]

for name, expected in adv_cases:
    cat, d = SemanticClassifier.classify(name)
    assert cat == expected, f"Adversarial case '{name}' failed: got '{cat}', expected '{expected}'"
    print(f"  Adversarial name '{name:28s}' -> '{cat:12s}' (depth={d:+.2f}) -> PASS")

# 5. LayerData Mask and Cropping Edge Cases
print("\n--- 5. LayerData & LayerCollection Edge Cases ---")
img_zero = np.zeros((50, 50, 4), dtype=np.uint8)
mask_zero = np.ones((50, 50), dtype=np.uint8) * 128
layer_zero = LayerData(name="ZeroAlpha", image=img_zero, offset_x=5, offset_y=10, mask=mask_zero)
assert layer_zero.is_empty
cropped_zero = layer_zero.crop_to_content()
assert cropped_zero.mask is not None, "Mask was lost during zero-alpha crop!"
assert cropped_zero.width == 1 and cropped_zero.height == 1
assert cropped_zero.mask.shape == (1, 1)
print("  Empty layer with mask crop preservation -> PASS")

img_1px = np.zeros((10, 10, 4), dtype=np.uint8)
img_1px[4, 4] = [255, 128, 0, 255]
layer_1px = LayerData(name="SinglePixel", image=img_1px, offset_x=10, offset_y=20)
cropped_1px = layer_1px.crop_to_content()
assert cropped_1px.width == 1 and cropped_1px.height == 1
assert cropped_1px.offset_x == 14 and cropped_1px.offset_y == 24
print("  Single pixel layer cropping -> PASS")

col = LayerCollection(canvas_size=(100, 100))
col.add_layer(layer_1px)
comp = col.composite()
assert comp.shape == (100, 100, 4)
assert comp[24, 14, 0] == 255
print("  LayerCollection composite single pixel -> PASS")

print("\n================================================================")
print("  ALL ADVERSARIAL STRESS TESTS PASSED WITH ZERO INTEGRITY DEFECTS! ")
print("================================================================")
