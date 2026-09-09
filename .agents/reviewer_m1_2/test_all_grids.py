import sys
sys.path.insert(0, 'd:/VitubModel')
import numpy as np
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator

layers = ImageImporter.create_synthetic_layered_head(512, 512)

for grid_size in [10, 15, 20, 25, 30]:
    failures = []
    for l in layers:
        m = MeshGenerator.generate_mesh_from_layer(l, target_grid_size=grid_size)
        valid, errors = m.validate_topology()
        if not valid:
            failures.append((l.name, errors))
    print(f'Grid size {grid_size}: {len(failures)}/{len(layers)} layers failed topology validation.')
    for name, err in failures:
        print(f'   - {name}: {err}')
