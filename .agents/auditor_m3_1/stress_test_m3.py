"""
Stress testing boundary and edge conditions for Milestone 3.
"""
import sys
import os
sys.path.insert(0, os.path.abspath("."))
import struct
import numpy as np
import pytest

from src.core.layer import LayerData, LayerCollection
from src.core.mesh import Mesh
from src.core.vertex import Vertex
from src.core.keyform import KeyformTable, ParameterBinding, DrawableKeyforms
from src.exporter.texture_packer import (
    TextureAtlasPacker,
    PackingConfig,
    PackingHeuristic,
    SortOrder,
    MaxRectsBin,
    Rect,
)
from src.exporter.moc3_writer import (
    Moc3Writer,
    Moc3Reader,
    validate_moc3_bytes,
    align_to_64,
    pad_buffer_to_64,
    encode_id_64,
    decode_id_64,
)
from src.exporter.model3_writer import Model3Writer


def test_extreme_texture_sizes():
    print("Testing extreme texture sizes...")
    # 1. 1x1 pixel image
    img1x1 = np.ones((1, 1, 4), dtype=np.uint8) * 255
    l1 = LayerData(name="Pixel1", image=img1x1)
    res1 = TextureAtlasPacker.pack([l1], config=PackingConfig(min_atlas_size=512, padding=1))
    assert res1.primary_atlas.shape == (512, 512, 4)
    assert "Pixel1" in res1.placements
    assert res1.placements["Pixel1"].width == 1
    assert res1.placements["Pixel1"].height == 1

    # 2. 4096 x 4096 single image
    img4096 = np.zeros((4096, 4096, 4), dtype=np.uint8)
    img4096[100:200, 100:200] = 255
    l_huge = LayerData(name="Huge", image=img4096)
    res_huge = TextureAtlasPacker.pack([l_huge], config=PackingConfig(max_atlas_size=4096, padding=0, bleed_radius=0))
    assert res_huge.primary_atlas.shape == (4096, 4096, 4)
    assert res_huge.placements["Huge"].width == 4096

    # 3. Multiple huge layers forcing multi-page atlas creation
    l_huge2 = LayerData(name="Huge2", image=img4096.copy())
    res_multi = TextureAtlasPacker.pack([l_huge, l_huge2], config=PackingConfig(max_atlas_size=4096, padding=0, bleed_radius=0))
    assert len(res_multi.pages) == 2
    assert res_multi.stats.num_pages == 2
    assert res_multi.placements["Huge"].page_index == 0
    assert res_multi.placements["Huge2"].page_index == 1
    print("Extreme texture sizes: PASS")


def test_dense_mesh_moc3_serialization():
    print("Testing dense mesh moc3 serialization...")
    table = KeyformTable(canvas_width=4096, canvas_height=4096, model_name="DenseModel")
    
    # 5 parameters
    for p_i in range(5):
        table.add_parameter(ParameterBinding(
            param_id=f"Param_{p_i}",
            min_val=-1.0,
            default_val=0.0,
            max_val=1.0,
            key_values=[-1.0, 0.0, 1.0]
        ))
        
    # Dense mesh with 500 vertices and ~950 triangles
    n_v = 500
    np.random.seed(42)
    grid_x, grid_y = np.meshgrid(np.linspace(-1, 1, 25), np.linspace(-1, 1, 20))
    base_v = np.column_stack([grid_x.ravel(), grid_y.ravel()]).astype(np.float32)
    
    from scipy.spatial import Delaunay
    tri = Delaunay(base_v)
    triangles = tri.simplices.astype(np.int32)
    uvs = (base_v + 1.0) * 0.5
    
    d = DrawableKeyforms(
        drawable_id="ArtMesh_DenseBody",
        texture_index=0,
        base_vertices=base_v,
        triangles=triangles,
        uvs_atlas=uvs,
        draw_order=500
    )
    
    # 27 keyforms (3x3x3 grid for first 3 params)
    for p0 in [-1.0, 0.0, 1.0]:
        for p1 in [-1.0, 0.0, 1.0]:
            for p2 in [-1.0, 0.0, 1.0]:
                def_v = base_v * (1.0 + p0 * 0.05 + p1 * 0.02 + p2 * 0.01)
                d.add_keyform((p0, p1, p2), def_v.astype(np.float32))
                
    table.add_drawable(d)
    
    raw_data = Moc3Writer.build_bytes(table)
    assert len(raw_data) % 64 == 0
    val_res = validate_moc3_bytes(raw_data)
    assert val_res["is_valid"] is True
    assert len(val_res["errors"]) == 0
    
    parsed = Moc3Reader.parse_bytes(raw_data)
    assert parsed["counts"]["art_meshes"] == 1
    assert parsed["counts"]["parameters"] == 5
    assert parsed["counts"]["art_mesh_keyforms"] == 27
    assert parsed["counts"]["keyform_positions"] == 500 * 27
    assert parsed["counts"]["uvs"] == 500
    assert parsed["counts"]["position_indices"] == len(triangles) * 3
    print("Dense mesh moc3 serialization: PASS")


def test_special_characters_metadata():
    print("Testing special characters in model3 / cdi3...")
    custom_names = {
        "ParamAngleX": "顔の回転 X (Yaw)",
        "ParamAngleY": "顔の回転 Y (Pitch)",
        "ParamAngleZ": "顔の傾き Z (Roll)",
        "ParamSpecial": "Special @#$%^&*()_+ {}:\"<>?~`",
    }
    cdi_dict = Model3Writer.generate_cdi3_json(
        parameter_ids=["ParamAngleX", "ParamAngleY", "ParamAngleZ", "ParamSpecial"],
        part_ids=["Part_Head", "Part_髪の毛_Front"],
        custom_param_names=custom_names
    )
    assert cdi_dict["Version"] == 3
    param_map = {p["Id"]: p["Name"] for p in cdi_dict["Parameters"]}
    assert param_map["ParamAngleX"] == "顔の回転 X (Yaw)"
    assert param_map["ParamSpecial"] == "Special @#$%^&*()_+ {}:\"<>?~`"
    part_names = [p["Name"] for p in cdi_dict["Parts"]]
    assert "Head" in part_names
    assert "髪の毛_Front" in part_names
    print("Special characters metadata: PASS")


if __name__ == "__main__":
    test_extreme_texture_sizes()
    test_dense_mesh_moc3_serialization()
    test_special_characters_metadata()
    print("\nALL STRESS & CORNER CASE TESTS PASSED CLEANLY!")
