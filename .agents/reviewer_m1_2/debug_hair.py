import sys
sys.path.insert(0, 'd:/VitubModel')
import numpy as np
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator
from src.core.mesh import Mesh

layers = ImageImporter.create_synthetic_layered_head(512, 512)
hair_front = [l for l in layers if l.name == 'Hair_Front'][0]

print('Testing Hair_Front with different smoothing iterations:')
for iters in [0, 1, 2, 3, 5]:
    mesh = MeshGenerator.generate_mesh_from_alpha_mask(hair_front.alpha_mask, target_grid_size=20, default_layer='Hair_Front')
    # Let's test with direct call to generate_mesh_from_contour with smoothing_iterations=iters
    contour = ImageImporter.extract_contour(hair_front.alpha_mask, threshold=10, simplify_eps=2.0)
    m = MeshGenerator.generate_mesh_from_contour(contour, hair_front.alpha_mask.shape[:2], target_grid_size=20, smoothing_iterations=iters, default_layer='Hair_Front')
    areas = m.compute_triangle_signed_areas()
    min_a = np.min(areas) if len(areas) > 0 else 0.0
    neg_count = np.sum(areas <= 0)
    print(f'iters={iters}: triangles={len(m.triangles)}, min_area={min_a:.8f}, negative_count={neg_count}')
