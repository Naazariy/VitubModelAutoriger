import struct
import math
import numpy as np

from src.core.keyform import KeyformTable, ParameterBinding, DrawableKeyforms, WarpDeformer, RotationDeformer
from src.exporter.moc3_writer import Moc3Writer, Moc3Reader
from src.validator.structural_validator import StructuralValidator


def test_full_roundtrip():
    table = KeyformTable(canvas_width=2048, canvas_height=2048, model_name="sample_avatar")

    # 1. Parameters
    table.add_parameter(ParameterBinding("ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]))
    table.add_parameter(ParameterBinding("ParamAngleY", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]))
    table.add_parameter(ParameterBinding("ParamAngleZ", min_val=-30.0, default_val=0.0, max_val=30.0, key_values=[-30.0, 0.0, 30.0]))

    # 2. RotationDeformer (Angle Z)
    rot = RotationDeformer(
        deformer_id="Rotation_Head",
        parent_part_id="PartRoot",
        parent_deformer_id=None,
        parameter_ids=["ParamAngleZ"],
        origin_x=1024.0,
        origin_y=1024.0
    )
    for az in [-30.0, 0.0, 30.0]:
        rot.add_keyform((float(az),), angle=math.radians(az), origin=(1024.0, 1024.0), scale=(1.0, 1.0), opacity=1.0)
    table.add_rotation_deformer(rot)

    # 3. WarpDeformer (Angle X, Angle Y)
    warp = WarpDeformer(
        deformer_id="Warp_Head",
        parent_part_id="PartRoot",
        parent_deformer_id="Rotation_Head",
        parameter_ids=["ParamAngleX", "ParamAngleY"],
        grid_rows=4,
        grid_cols=4
    )
    # Generate 5x5 grid = 25 control points
    gx = np.linspace(500, 1500, 5, dtype=np.float32)
    gy = np.linspace(500, 1500, 5, dtype=np.float32)
    grid_x, grid_y = np.meshgrid(gx, gy)
    base_grid = np.column_stack([grid_x.ravel(), grid_y.ravel()])
    warp.base_vertices = base_grid

    for ay in [-30.0, 0.0, 30.0]:
        for ax in [-30.0, 0.0, 30.0]:
            displaced = base_grid.copy()
            displaced[:, 0] += ax * 2.0
            displaced[:, 1] += ay * 2.0
            warp.add_keyform((float(ax), float(ay)), displaced)
    table.add_warp_deformer(warp)

    # 4. ArtMeshes (children of WarpDeformer)
    d1 = DrawableKeyforms(
        drawable_id="ArtMesh_Face",
        texture_index=0,
        base_vertices=np.array([[800, 800], [1200, 800], [1000, 1200]], dtype=np.float32),
        triangles=np.array([[0, 1, 2]], dtype=np.int32),
        uvs_atlas=np.array([[0.1, 0.1], [0.9, 0.1], [0.5, 0.9]], dtype=np.float32),
        parameter_ids=[],
        parent_deformer_id="Warp_Head",
        draw_order=500
    )
    table.add_drawable(d1)

    # Serialize
    moc3_bytes = Moc3Writer.build_bytes(table)
    assert len(moc3_bytes) >= 2176
    assert len(moc3_bytes) % 64 == 0

    # Validate Stage 1 & Stage 2
    s1 = StructuralValidator.validate_stage1_moc3_header(moc3_bytes)
    assert s1.passed is True, f"Stage 1 failed: {s1.errors}"

    s2 = StructuralValidator.validate_stage2_section_offsets_and_counts(moc3_bytes)
    assert s2.passed is True, f"Stage 2 failed: {s2.errors}"
    assert s2.details["deformers"] == 2
    assert s2.details["rotation_deformers"] == 1
    assert s2.details["warp_deformers"] == 1

    # Read back with Moc3Reader
    parsed = Moc3Reader.parse_bytes(moc3_bytes)
    assert parsed.get("counts", {}).get("deformers") == 2
    assert parsed.get("counts", {}).get("warp_deformers") == 1
    assert parsed.get("counts", {}).get("rotation_deformers") == 1
    assert "Rotation_Head" in parsed.get("deformer_ids", [])
    assert "Warp_Head" in parsed.get("deformer_ids", [])


if __name__ == "__main__":
    test_full_roundtrip()
    print("test_full_roundtrip passed successfully!")
