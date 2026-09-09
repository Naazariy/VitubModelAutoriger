"""
src/exporter/model3_writer.py
Live2D Cubism 3.0+ Metadata Generator (.model3.json and .cdi3.json).
Formats model manifests with strictly normalized forward-slash relative paths and tracking parameter groups.
"""

from dataclasses import dataclass, field
import os
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
import numpy as np
from PIL import Image

from src.core.keyform import KeyformTable


class Model3Writer:
    """
    Generates standardized Live2D Cubism 3+ metadata:
    - .model3.json: Master runtime manifest for Cubism Viewer, SDKs, and VTube Studio.
    - .cdi3.json: Combined Display Information manifest for Live2D editors and tracking palettes.
    """

    DEFAULT_PARAM_NAMES: Dict[str, Dict[str, str]] = {
        "ParamAngleX": {"name": "Angle X", "name_ja": "角度 X", "group": "ParamGroupHead"},
        "ParamAngleY": {"name": "Angle Y", "name_ja": "角度 Y", "group": "ParamGroupHead"},
        "ParamAngleZ": {"name": "Angle Z", "name_ja": "角度 Z", "group": "ParamGroupHead"},
        "ParamEyeLOpen": {"name": "Eye L Open", "name_ja": "左目 開閉", "group": "ParamGroupEyes"},
        "ParamEyeROpen": {"name": "Eye R Open", "name_ja": "右目 開閉", "group": "ParamGroupEyes"},
        "ParamEyeLSmile": {"name": "Eye L Smile", "name_ja": "左目 笑顔", "group": "ParamGroupEyes"},
        "ParamEyeRSmile": {"name": "Eye R Smile", "name_ja": "右目 笑顔", "group": "ParamGroupEyes"},
        "ParamEyeBallX": {"name": "Eyeball X", "name_ja": "目玉 X", "group": "ParamGroupEyes"},
        "ParamEyeBallY": {"name": "Eyeball Y", "name_ja": "目玉 Y", "group": "ParamGroupEyes"},
        "ParamBrowLY": {"name": "Eyebrow L Y", "name_ja": "左眉 上下", "group": "ParamGroupEyebrows"},
        "ParamBrowRY": {"name": "Eyebrow R Y", "name_ja": "右眉 上下", "group": "ParamGroupEyebrows"},
        "ParamMouthForm": {"name": "Mouth Form", "name_ja": "口 変形", "group": "ParamGroupMouth"},
        "ParamMouthOpenY": {"name": "Mouth Open", "name_ja": "口 開閉", "group": "ParamGroupMouth"},
        "ParamBodyAngleX": {"name": "Body Angle X", "name_ja": "体の回転 X", "group": "ParamGroupBody"},
        "ParamBodyAngleY": {"name": "Body Angle Y", "name_ja": "体の回転 Y", "group": "ParamGroupBody"},
        "ParamBodyAngleZ": {"name": "Body Angle Z", "name_ja": "体の回転 Z", "group": "ParamGroupBody"},
        "ParamBreath": {"name": "Breath", "name_ja": "呼吸", "group": "ParamGroupBody"},
    }

    DEFAULT_GROUP_NAMES: Dict[str, str] = {
        "ParamGroupHead": "Head Rotation",
        "ParamGroupEyes": "Eyes",
        "ParamGroupEyebrows": "Eyebrows",
        "ParamGroupMouth": "Mouth",
        "ParamGroupBody": "Body",
    }

    @classmethod
    def generate_model3_json(
        cls,
        model_name: str,
        moc_rel_path: str,
        texture_rel_paths: List[str],
        physics_rel_path: Optional[str] = None,
        cdi_rel_path: Optional[str] = None,
        pose_rel_path: Optional[str] = None,
        output_path: Optional[str] = None,
        hit_areas: Optional[List[Dict[str, str]]] = None,
        lip_sync_ids: Optional[List[str]] = None,
        eye_blink_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Generates .model3.json manifest dictionary and optionally writes it to disk.
        All relative paths are normalized with forward slashes '/'.
        """
        # Ensure forward-slash relative paths
        clean_moc = moc_rel_path.replace("\\", "/")
        clean_textures = [t.replace("\\", "/") for t in texture_rel_paths]

        file_references: Dict[str, Any] = {
            "Moc": clean_moc,
            "Textures": clean_textures,
        }

        if physics_rel_path:
            file_references["Physics"] = physics_rel_path.replace("\\", "/")
        if cdi_rel_path:
            file_references["DisplayInfo"] = cdi_rel_path.replace("\\", "/")
        if pose_rel_path:
            file_references["Pose"] = pose_rel_path.replace("\\", "/")

        # Standard LipSync and EyeBlink Groups
        ls_ids = lip_sync_ids if lip_sync_ids is not None else ["ParamMouthOpenY", "ParamMouthForm"]
        eb_ids = eye_blink_ids if eye_blink_ids is not None else ["ParamEyeLOpen", "ParamEyeROpen"]

        groups = [
            {
                "Target": "Parameter",
                "Name": "LipSync",
                "Ids": ls_ids,
            },
            {
                "Target": "Parameter",
                "Name": "EyeBlink",
                "Ids": eb_ids,
            },
        ]

        # Hit Areas
        areas = hit_areas if hit_areas is not None else [
            {"Id": "ArtMesh_Head", "Name": "Head"}
        ]

        data = {
            "Version": 3,
            "FileReferences": file_references,
            "Groups": groups,
            "HitAreas": areas,
            "Layout": {
                "CenterX": 0.0,
                "CenterY": 0.0,
                "Width": 2.0,
                "Height": 2.0,
            },
        }

        if output_path:
            out_file = Path(output_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        return data

    @classmethod
    def generate_cdi3_json(
        cls,
        parameter_ids: List[str],
        part_ids: Optional[List[str]] = None,
        output_path: Optional[str] = None,
        custom_param_names: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Generates .cdi3.json display information manifest dictionary and optionally writes it to disk.
        """
        params_meta = []
        active_group_ids = set()

        for pid in parameter_ids:
            meta = cls.DEFAULT_PARAM_NAMES.get(pid, {"name": pid, "group": ""})
            gid = meta.get("group", "")
            if gid:
                active_group_ids.add(gid)

            disp_name = (custom_param_names.get(pid) if custom_param_names else None) or meta.get("name", pid)
            params_meta.append({
                "Id": pid,
                "GroupId": gid,
                "Name": disp_name,
            })

        param_groups_meta = []
        for gid in sorted(list(active_group_ids)):
            gname = cls.DEFAULT_GROUP_NAMES.get(gid, gid)
            param_groups_meta.append({
                "Id": gid,
                "GroupId": "",
                "Name": gname,
            })

        parts_list = part_ids if part_ids is not None else ["PartHead", "PartHair", "PartFace", "PartBody"]
        parts_meta = []
        for pid in parts_list:
            display_name = pid.replace("Part_", "").replace("Part", "") or pid
            parts_meta.append({
                "Id": pid,
                "Name": display_name,
            })

        data = {
            "Version": 3,
            "Parameters": params_meta,
            "ParameterGroups": param_groups_meta,
            "Parts": parts_meta,
        }

        if output_path:
            out_file = Path(output_path)
            out_file.parent.mkdir(parents=True, exist_ok=True)
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        return data

    @classmethod
    def export_model_bundle(
        cls,
        output_dir: str,
        model_name: str,
        keyform_table: KeyformTable,
        texture_pages: List[Any],
        texture_res_folder: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Exports a complete Live2D model bundle (.moc3, .model3.json, .cdi3.json, textures) into output_dir.
        """
        from PIL import Image
        from src.exporter.moc3_writer import Moc3Writer

        out_path = Path(output_dir)
        model_folder = out_path / model_name
        model_folder.mkdir(parents=True, exist_ok=True)

        # 1. Export textures
        primary_dim = texture_pages[0].shape[0] if hasattr(texture_pages[0], 'shape') else 4096
        res_folder_name = texture_res_folder or f"{model_name}.{primary_dim}"
        tex_folder = model_folder / res_folder_name
        tex_folder.mkdir(parents=True, exist_ok=True)

        tex_rel_paths = []
        for idx, page in enumerate(texture_pages):
            tex_filename = f"texture_{idx:02d}.png"
            tex_file_path = tex_folder / tex_filename
            if isinstance(page, np.ndarray):
                Image.fromarray(page).save(tex_file_path)
            elif isinstance(page, Image.Image):
                page.save(tex_file_path)
            tex_rel_paths.append(f"{res_folder_name}/{tex_filename}")

        # 2. Export .moc3 binary
        moc_filename = f"{model_name}.moc3"
        moc_file_path = model_folder / moc_filename
        Moc3Writer.write_moc3(keyform_table, str(moc_file_path))

        # 3. Export .cdi3.json
        cdi_filename = f"{model_name}.cdi3.json"
        cdi_file_path = model_folder / cdi_filename
        cls.generate_cdi3_json(
            parameter_ids=keyform_table.parameter_ids,
            part_ids=["PartRoot"],
            output_path=str(cdi_file_path)
        )

        # 4. Export .model3.json
        model3_filename = f"{model_name}.model3.json"
        model3_file_path = model_folder / model3_filename
        cls.generate_model3_json(
            model_name=model_name,
            moc_rel_path=moc_filename,
            texture_rel_paths=tex_rel_paths,
            cdi_rel_path=cdi_filename,
            output_path=str(model3_file_path)
        )

        return {
            "model_dir": str(model_folder),
            "model3_json": str(model3_file_path),
            "moc3": str(moc_file_path),
            "cdi3_json": str(cdi_file_path),
            "textures": [str(tex_folder / f"texture_{i:02d}.png") for i in range(len(texture_pages))]
        }
