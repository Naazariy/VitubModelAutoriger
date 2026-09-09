"""
tests/test_model3_writer.py
Unit Test Suite for Model3Writer (.model3.json and .cdi3.json metadata generators).
"""

import json
from pathlib import Path
import numpy as np
import pytest

from src.core.keyform import KeyformTable, ParameterBinding, DrawableKeyforms
from src.exporter.model3_writer import Model3Writer


class TestModel3WriterUnit:
    """Unit tests for Model3Writer metadata generator."""

    def test_model3_json_version_and_references(self, tmp_path):
        """Verify .model3.json complies with Cubism 3 schema."""
        out_file = tmp_path / "model.model3.json"
        data = Model3Writer.generate_model3_json(
            model_name="MyAvatar",
            moc_rel_path="MyAvatar.moc3",
            texture_rel_paths=["MyAvatar.4096/texture_00.png"],
            output_path=str(out_file)
        )

        assert data["Version"] == 3
        assert data["FileReferences"]["Moc"] == "MyAvatar.moc3"
        assert len(data["FileReferences"]["Textures"]) == 1
        assert data["FileReferences"]["Textures"][0] == "MyAvatar.4096/texture_00.png"
        assert out_file.exists()

        # Read back from file
        with open(out_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        assert disk_data == data

    def test_strict_forward_slash_path_normalization(self):
        """Verify Windows backslashes are replaced with forward slashes in all file references."""
        data = Model3Writer.generate_model3_json(
            model_name="WinAvatar",
            moc_rel_path="subdir\\WinAvatar.moc3",
            texture_rel_paths=["textures\\4096\\texture_00.png", "textures\\4096\\texture_01.png"],
            physics_rel_path="physics\\WinAvatar.physics3.json",
            cdi_rel_path="cdi\\WinAvatar.cdi3.json"
        )

        assert "\\" not in data["FileReferences"]["Moc"]
        assert data["FileReferences"]["Moc"] == "subdir/WinAvatar.moc3"
        assert all("\\" not in t for t in data["FileReferences"]["Textures"])
        assert "\\" not in data["FileReferences"]["Physics"]
        assert "\\" not in data["FileReferences"]["DisplayInfo"]

    def test_standard_lipsync_and_eyeblink_groups(self):
        """Verify default LipSync and EyeBlink tracking groups are present."""
        data = Model3Writer.generate_model3_json(
            model_name="TrackingAvatar",
            moc_rel_path="TrackingAvatar.moc3",
            texture_rel_paths=["tex.png"]
        )

        groups = data.get("Groups", [])
        group_names = [g["Name"] for g in groups]
        assert "LipSync" in group_names
        assert "EyeBlink" in group_names

        for g in groups:
            assert g["Target"] == "Parameter"
            assert isinstance(g["Ids"], list)

    def test_cdi3_json_parameter_hierarchy(self, tmp_path):
        """Verify .cdi3.json formats parameter labels, groups, and display hierarchy."""
        out_cdi = tmp_path / "model.cdi3.json"
        data = Model3Writer.generate_cdi3_json(
            parameter_ids=["ParamAngleX", "ParamAngleY", "ParamAngleZ", "ParamEyeLOpen"],
            part_ids=["PartHead", "PartHair"],
            output_path=str(out_cdi)
        )

        assert data["Version"] == 3
        assert len(data["Parameters"]) == 4

        # Check parameter naming
        p_dict = {p["Id"]: p for p in data["Parameters"]}
        assert p_dict["ParamAngleX"]["Name"] == "Angle X"
        assert p_dict["ParamAngleX"]["GroupId"] == "ParamGroupHead"
        assert p_dict["ParamEyeLOpen"]["GroupId"] == "ParamGroupEyes"

        # Check parameter groups
        g_dict = {g["Id"]: g for g in data["ParameterGroups"]}
        assert "ParamGroupHead" in g_dict
        assert g_dict["ParamGroupHead"]["Name"] == "Head Rotation"
        assert "ParamGroupEyes" in g_dict

        # Check parts
        parts_names = [p["Name"] for p in data["Parts"]]
        assert "Head" in parts_names
        assert "Hair" in parts_names
        assert out_cdi.exists()

    def test_export_model_bundle(self, tmp_path):
        """Verify export_model_bundle writes complete directory structure."""
        table = KeyformTable(model_name="FullModel")
        table.add_parameter(ParameterBinding(param_id="ParamAngleX", min_val=-30.0, default_val=0.0, max_val=30.0))
        d = DrawableKeyforms(
            drawable_id="ArtMesh_Head",
            texture_index=0,
            base_vertices=np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
            triangles=np.array([[0, 1, 2]], dtype=np.int32),
            uvs_atlas=np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]], dtype=np.float32),
        )
        table.add_drawable(d)

        dummy_page = np.zeros((512, 512, 4), dtype=np.uint8)
        dummy_page[100:400, 100:400] = [200, 150, 100, 255]

        paths = Model3Writer.export_model_bundle(
            output_dir=str(tmp_path),
            model_name="FullModel",
            keyform_table=table,
            texture_pages=[dummy_page]
        )

        assert Path(paths["model3_json"]).exists()
        assert Path(paths["moc3"]).exists()
        assert Path(paths["cdi3_json"]).exists()
        assert len(paths["textures"]) == 1
        assert Path(paths["textures"][0]).exists()
