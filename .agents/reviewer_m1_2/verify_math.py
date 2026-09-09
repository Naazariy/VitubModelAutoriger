import sys
sys.path.insert(0, 'd:/VitubModel')
import numpy as np
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator
from src.core.mesh import Mesh
from src.core.layer import LayerData, LayerCollection
from src.importer.semantic_classifier import SemanticClassifier

print('=== Testing 14 Synthetic Layers ===')
layers = ImageImporter.create_synthetic_layered_head(512, 512)
assert len(layers) == 14

for l in layers:
    mesh = MeshGenerator.generate_mesh_from_layer(l, target_grid_size=20)
    assert len(mesh.vertices) >= 3, f'Layer {l.name} has fewer than 3 vertices ({len(mesh.vertices)})'
    assert len(mesh.triangles) >= 1, f'Layer {l.name} has 0 triangles'
    
    # 1. Check positive signed area
    areas = mesh.compute_triangle_signed_areas()
    assert np.all(areas > 1e-6), f'Layer {l.name} has non-positive areas! Min area: {np.min(areas)}'
    
    # 2. Check UV range [0, 1]
    assert np.all(mesh.uvs >= 0.0) and np.all(mesh.uvs <= 1.0), f'Layer {l.name} UVs out of [0, 1]'
    
    # 3. Check normalized vertex coordinates [-1, 1]
    pos = mesh.get_positions()
    assert np.all(pos >= -1.0) and np.all(pos <= 1.0), f'Layer {l.name} pos out of [-1, 1]'
    
    # 4. Check topology validation
    valid, errors = mesh.validate_topology()
    assert valid, f'Layer {l.name} topology invalid: {errors}'
    
    print(f'Layer {l.name:15s}: {len(mesh.vertices):4d} verts, {len(mesh.triangles):4d} tris, min area: {np.min(areas):.6f} -> OK')

print('All 14 layers passed mathematical verification!')
