import sys
sys.path.insert(0, 'd:/VitubModel')
import numpy as np
from src.importer.image_importer import ImageImporter
from src.generator.mesh_generator import MeshGenerator

layers = ImageImporter.create_synthetic_layered_head(512, 512)
hair_front = [l for l in layers if l.name == 'Hair_Front'][0]
m = MeshGenerator.generate_mesh_from_layer(hair_front, target_grid_size=20)
valid, errors = m.validate_topology()
print('Topology Valid:', valid)
print('Errors:', errors)
