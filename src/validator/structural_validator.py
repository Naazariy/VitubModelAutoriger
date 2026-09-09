"""
src/validator/structural_validator.py
Production-Grade 6-Stage Programmatic Structural Validator for Live2D Cubism Model Bundles.
Validates binary .moc3 headers, 64-byte aligned section tables, JSON manifests,
parameter keyforms, power-of-two texture atlases, and topological non-inversion.
"""

from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import struct
from typing import Dict, List, Tuple, Optional, Any, Union
import numpy as np
from PIL import Image


@dataclass
class ValidationStageResult:
    """Detailed outcome for an individual validation stage."""
    stage_number: int
    stage_name: str
    passed: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stage_number": self.stage_number,
            "stage_name": self.stage_name,
            "passed": self.passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "details": self.details,
        }


@dataclass
class ValidationReport:
    """Master validation summary report aggregating results across all 6 stages."""
    passed: bool = True
    stages: List[ValidationStageResult] = field(default_factory=list)
    total_errors: int = 0
    total_warnings: int = 0
    model_path: str = ""
    model_name: str = ""

    @property
    def is_valid(self) -> bool:
        """Backward-compatibility alias for passed."""
        return self.passed

    @property
    def stages_passed(self) -> List[int]:
        """Returns list of 1-indexed stage numbers that passed."""
        return [s.stage_number for s in self.stages if s.passed]

    @property
    def errors(self) -> List[str]:
        """Returns flat list of all error messages across all stages."""
        errs: List[str] = []
        for s in self.stages:
            errs.extend(s.errors)
        return errs

    @property
    def warnings(self) -> List[str]:
        """Returns flat list of all warning messages across all stages."""
        warns: List[str] = []
        for s in self.stages:
            warns.extend(s.warnings)
        return warns

    def add_stage(self, stage_result: ValidationStageResult) -> None:
        """Appends a stage result and updates aggregate counters and overall status."""
        self.stages.append(stage_result)
        self.total_errors += len(stage_result.errors)
        self.total_warnings += len(stage_result.warnings)
        if not stage_result.passed:
            self.passed = False

    def to_dict(self) -> Dict[str, Any]:
        """Serializes report to dictionary for JSON output."""
        return {
            "is_valid": self.is_valid,
            "passed": self.passed,
            "total_errors": self.total_errors,
            "total_warnings": self.total_warnings,
            "stages_passed": self.stages_passed,
            "model_path": self.model_path,
            "model_name": self.model_name,
            "stages": [s.to_dict() for s in self.stages],
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def format_console(self, use_color: bool = True) -> str:
        """Renders color-coded CLI report with stage-by-stage audit details."""
        GREEN = "\033[92m" if use_color else ""
        RED = "\033[91m" if use_color else ""
        YELLOW = "\033[93m" if use_color else ""
        CYAN = "\033[96m" if use_color else ""
        BOLD = "\033[1m" if use_color else ""
        RESET = "\033[0m" if use_color else ""

        lines = []
        lines.append(f"{BOLD}{CYAN}======================================================================{RESET}")
        lines.append(f"{BOLD}{CYAN}             LIVE2D 6-STAGE STRUCTURAL VALIDATION REPORT              {RESET}")
        lines.append(f"{BOLD}{CYAN}======================================================================{RESET}")
        lines.append(f"Model Target : {self.model_path or 'N/A'}")
        lines.append(f"Model Name   : {self.model_name or 'N/A'}")
        status_str = f"{GREEN}[PASSED]{RESET}" if self.passed else f"{RED}[FAILED]{RESET}"
        lines.append(f"Overall Status: {BOLD}{status_str}{RESET} (Errors: {self.total_errors}, Warnings: {self.total_warnings})")
        lines.append(f"----------------------------------------------------------------------")

        for s in self.stages:
            tag = f"{GREEN}PASS{RESET}" if s.passed else f"{RED}FAIL{RESET}"
            lines.append(f" Stage {s.stage_number}: [{tag}] {BOLD}{s.stage_name}{RESET}")
            for err in s.errors:
                lines.append(f"   {RED}[ERROR]{RESET} {err}")
            for warn in s.warnings:
                lines.append(f"   {YELLOW}[WARN]{RESET} {warn}")
            if s.passed and not s.warnings and s.details:
                detail_strs = [f"{k}={v}" for k, v in list(s.details.items())[:5]]
                if detail_strs:
                    lines.append(f"   {CYAN}[INFO]{RESET} {', '.join(detail_strs)}")

        lines.append(f"{BOLD}{CYAN}======================================================================{RESET}")
        return "\n".join(lines)

    def get_summary_text(self, colorize: bool = False) -> str:
        """Alias for format_console."""
        return self.format_console(use_color=colorize)


class StructuralValidator:
    """
    6-Stage Structural Validator for Live2D Cubism Model Bundles:
    Stage 1: Binary MOC3 Header Integrity
    Stage 2: Section Table Offsets & Count Table Sanity
    Stage 3: JSON Manifest Schema & File Reference Conformance
    Stage 4: Parameter & Keyform Bounds Verification
    Stage 5: Texture Atlas & UV Coordinate Safety
    Stage 6: Topological Non-Inversion & Deformation Continuity
    """

    @classmethod
    def validate_stage1_moc3_header(cls, moc3_bytes: bytes) -> ValidationStageResult:
        """Stage 1: Binary MOC3 Header verification."""
        errors: List[str] = []
        warnings: List[str] = []
        details: Dict[str, Any] = {}

        if len(moc3_bytes) < 64:
            errors.append(f"Stage 1 Failed: File size too small: {len(moc3_bytes)} bytes < 64 bytes minimum header")
            return ValidationStageResult(1, "Binary MOC3 Header Integrity", False, errors, warnings, details)

        magic = moc3_bytes[:4]
        if magic != b"MOC3":
            errors.append(f"Stage 1 Failed: Magic bytes mismatch. Expected b'MOC3', got {magic}")

        version = moc3_bytes[4]
        if version not in (1, 2, 3, 4, 5):
            errors.append(f"Stage 1 Failed: Unsupported version: {version} (expected 1..5)")

        endianness = moc3_bytes[5]
        if endianness != 0:
            errors.append(f"Stage 1 Failed: Invalid Endianness flag: {endianness} (expected 0 for Little-Endian)")

        details["magic"] = magic.decode("ascii", errors="replace")
        details["version"] = version
        details["endianness"] = "little-endian" if endianness == 0 else f"invalid({endianness})"
        details["file_size_bytes"] = len(moc3_bytes)

        return ValidationStageResult(
            stage_number=1,
            stage_name="Binary MOC3 Header Integrity",
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details=details
        )

    @classmethod
    def validate_stage2_section_tables(cls, moc3_bytes: bytes) -> ValidationStageResult:
        """Stage 2: Section Table offsets, 64-byte alignment, count table and canvas sanity."""
        errors: List[str] = []
        warnings: List[str] = []
        details: Dict[str, Any] = {}

        if len(moc3_bytes) < 64:
            errors.append("Stage 2 Failed: Binary size too small (< 64 bytes)")
            return ValidationStageResult(2, "Section Table Offsets & Count Table Sanity", False, errors, warnings, details)

        # 64-byte alignment check of physical file size
        if len(moc3_bytes) % 64 != 0:
            warnings.append(f"Total MOC3 binary size ({len(moc3_bytes)} bytes) is not 64-byte aligned (remainder {len(moc3_bytes) % 64})")

        # Section table at 0x0040 (640 bytes = 160 uint32s)
        if len(moc3_bytes) >= 704:
            section_offsets = list(struct.unpack_from("<160I", moc3_bytes, 64))
            active_count = 0
            prev_offset = 0
            for idx, off in enumerate(section_offsets):
                if off > 0:
                    if off % 64 != 0 and idx not in (3, 11, 33, 50, 90):
                        errors.append(f"Section offset [{idx}] at {hex(off)} violates 64-byte alignment (offset % 64 != 0)")
                    elif off % 8 != 0:
                        errors.append(f"Section offset [{idx}] at {hex(off)} violates 8-byte alignment")
                    if off >= len(moc3_bytes):
                        errors.append(f"Section offset [{idx}] at {hex(off)} exceeds binary size ({len(moc3_bytes)} bytes)")
                    elif off < 0x0740 and idx != 0:
                        errors.append(f"Section offset [{idx}] at {hex(off)} is below header/map area (0x0740)")
                    
                    if off < prev_offset and off < len(moc3_bytes):
                        errors.append(f"Section offset [{idx}] at {hex(off)} violates monotonicity (< previous {hex(prev_offset)})")
                    prev_offset = off
                    active_count += 1

            details["active_sections"] = active_count

            # CountInfoTable at Section 0 (0x07C0)
            cnt_off = section_offsets[0] if section_offsets[0] > 0 else 0x07C0
            if len(moc3_bytes) >= cnt_off + 92:
                counters = struct.unpack_from("<23I", moc3_bytes, cnt_off)
                details["parts"] = counters[0]
                details["deformers"] = counters[1]
                details["warp_deformers"] = counters[2]
                details["rotation_deformers"] = counters[3]
                details["art_meshes"] = counters[4]
                details["parameters"] = counters[5]
                details["part_keyforms"] = counters[6]
                details["warp_deformer_keyforms"] = counters[7]
                details["rotation_deformer_keyforms"] = counters[8]
                details["art_mesh_keyforms"] = counters[9]
                details["keyform_positions"] = counters[10]
                details["keys"] = counters[14]
                details["uvs"] = counters[15]
                details["position_indices"] = counters[16]

                if counters[0] < 1:
                    warnings.append(f"CountInfoTable: Parts count is {counters[0]} (expected >= 1)")
                if counters[4] < 1:
                    errors.append(f"Count table sanity check failed: ArtMeshes count is 0")
                if counters[5] < 1:
                    errors.append(f"Count table sanity check failed: Parameters count is 0")
                if counters[15] < 1:
                    errors.append(f"Count table sanity check failed: UV count is 0")
                if counters[16] < 1:
                    errors.append(f"Count table sanity check failed: Position indices count is 0")

                # Deformer consistency checks
                if counters[1] > 0:
                    if counters[1] != counters[2] + counters[3]:
                        errors.append(f"Count table deformer mismatch: total deformers ({counters[1]}) != warp ({counters[2]}) + rotation ({counters[3]})")
                
                # Check astronomical corrupted counts
                if any(c > 10_000_000 for c in counters):
                    errors.append("Count table sanity check failed: Contains astronomical/corrupted count (> 10M)")

            # CanvasInfo at Section 1 (0x0840)
            canvas_off = section_offsets[1] if section_offsets[1] > 0 else 0x0840
            if len(moc3_bytes) >= canvas_off + 21:
                canvas_fields = struct.unpack_from("<5fB", moc3_bytes, canvas_off)
                details["canvas_width"] = canvas_fields[3]
                details["canvas_height"] = canvas_fields[4]
                details["pixels_per_unit"] = canvas_fields[0]
                if canvas_fields[3] <= 0 or canvas_fields[4] <= 0:
                    errors.append(f"Invalid Canvas dimensions: {canvas_fields[3]}x{canvas_fields[4]}")
        else:
            errors.append("Stage 2 Failed: MOC3 binary too short to contain 160-slot SectionOffsetTable (requires >= 704 bytes)")

        return ValidationStageResult(
            stage_number=2,
            stage_name="Section Table Offsets & Count Table Sanity",
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details=details
        )

    validate_stage2_section_offsets_and_counts = validate_stage2_section_tables

    @classmethod
    def validate_stage3_json_manifest(
        cls,
        model_dir: Path,
        model3_path: Path
    ) -> Tuple[ValidationStageResult, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Stage 3: JSON Manifest schema (.model3.json & .cdi3.json) and path conformance."""
        errors: List[str] = []
        warnings: List[str] = []
        details: Dict[str, Any] = {}
        model3_data: Optional[Dict[str, Any]] = None
        cdi3_data: Optional[Dict[str, Any]] = None

        if not model3_path.exists():
            errors.append(f"model3.json not found: {model3_path}")
            return ValidationStageResult(3, "JSON Manifest & File Reference Conformance", False, errors, warnings, details), None, None

        try:
            with open(model3_path, "r", encoding="utf-8") as f:
                model3_data = json.load(f)
        except Exception as e:
            errors.append(f"Invalid JSON syntax in {model3_path.name}: {e}")
            return ValidationStageResult(3, "JSON Manifest & File Reference Conformance", False, errors, warnings, details), None, None

        # Version check
        v = model3_data.get("Version")
        if v != 3:
            errors.append(f"model3.json: Expected Version == 3, got {v}")
        details["version"] = v

        file_refs = model3_data.get("FileReferences", {})
        if not file_refs:
            errors.append("model3.json: Missing FileReferences")
            return ValidationStageResult(3, "JSON Manifest & File Reference Conformance", False, errors, warnings, details), model3_data, None

        # Moc file check
        moc_rel = file_refs.get("Moc")
        if not moc_rel:
            errors.append("model3.json: Missing FileReferences.Moc")
        else:
            if "\\" in moc_rel:
                errors.append(f"model3.json: Moc path contains Windows backslash: '{moc_rel}'")
            moc_full = model_dir / moc_rel
            if not moc_full.exists():
                errors.append(f"model3.json: Moc file does not exist: {moc_full}")
            details["moc_file"] = moc_rel

        # Textures check
        tex_list = file_refs.get("Textures", [])
        if not tex_list:
            errors.append("model3.json: FileReferences.Textures is empty")
        else:
            details["texture_count"] = len(tex_list)
            for tex_rel in tex_list:
                if "\\" in tex_rel:
                    errors.append(f"model3.json: Texture path contains Windows backslash: '{tex_rel}'")
                tex_full = model_dir / tex_rel
                if not tex_full.exists():
                    errors.append(f"model3.json: Texture file does not exist: {tex_full}")

        # DisplayInfo (.cdi3.json) check
        cdi_rel = file_refs.get("DisplayInfo")
        if cdi_rel:
            if "\\" in cdi_rel:
                errors.append(f"model3.json: DisplayInfo path contains Windows backslash: '{cdi_rel}'")
            cdi_full = model_dir / cdi_rel
            if not cdi_full.exists():
                warnings.append(f"model3.json: DisplayInfo file does not exist: {cdi_full}")
            else:
                try:
                    with open(cdi_full, "r", encoding="utf-8") as f:
                        cdi3_data = json.load(f)
                    if cdi3_data.get("Version") != 3:
                        warnings.append(f"cdi3.json: Expected Version == 3, got {cdi3_data.get('Version')}")
                except Exception as e:
                    warnings.append(f"cdi3.json: Failed to parse JSON: {e}")

        # Physics check if present
        phys_rel = file_refs.get("Physics")
        if phys_rel:
            if "\\" in phys_rel:
                errors.append(f"model3.json: Physics path contains Windows backslash: '{phys_rel}'")
            phys_full = model_dir / phys_rel
            if not phys_full.exists():
                warnings.append(f"model3.json: Physics file not found: {phys_full}")

        return ValidationStageResult(
            stage_number=3,
            stage_name="JSON Manifest & File Reference Conformance",
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details=details
        ), model3_data, cdi3_data

    @classmethod
    def validate_stage4_parameter_bounds(
        cls,
        cdi3_data: Optional[Dict[str, Any]],
        moc3_parsed: Optional[Dict[str, Any]] = None,
        keyform_table: Optional[Any] = None
    ) -> ValidationStageResult:
        """Stage 4: Parameter IDs, keyform counts, monotonic key values, and range bounds."""
        errors: List[str] = []
        warnings: List[str] = []
        details: Dict[str, Any] = {}

        param_ids: List[str] = []
        
        # Extract parameter IDs from CDI
        if cdi3_data and "Parameters" in cdi3_data:
            param_ids = [p.get("Id", "") for p in cdi3_data["Parameters"] if isinstance(p, dict)]
        
        # Extract from moc3 parsed info if available
        if moc3_parsed and "parameter_ids" in moc3_parsed:
            for pid in moc3_parsed["parameter_ids"]:
                if pid and pid not in param_ids:
                    param_ids.append(pid)

        # Extract from KeyformTable if available
        if keyform_table:
            if hasattr(keyform_table, 'parameter_ids'):
                for pid in keyform_table.parameter_ids:
                    if pid not in param_ids:
                        param_ids.append(pid)

        details["parameters_found"] = param_ids

        # Check required tracking parameters
        required_params = ["ParamAngleX", "ParamAngleY"]
        for rp in required_params:
            if rp not in param_ids:
                if not param_ids:
                    # If no cdi or param info at all, issue warning/error based on context
                    warnings.append(f"Parameter {rp} not found in model metadata")
                else:
                    errors.append(f"Missing required parameter: {rp}")

        if "ParamAngleZ" not in param_ids:
            warnings.append("Optional parameter ParamAngleZ not declared in metadata")

        # Check parameter ranges if keyform_table provided
        if keyform_table and hasattr(keyform_table, 'parameter_ranges'):
            for pid, (min_v, def_v, max_v) in keyform_table.parameter_ranges.items():
                if min_v >= max_v:
                    errors.append(f"Invalid parameter range for {pid}: min ({min_v}) >= max ({max_v})")
                if not (min_v <= def_v <= max_v):
                    errors.append(f"Default value out of bounds for {pid}: default ({def_v}) not in [{min_v}, {max_v}]")

        if keyform_table and hasattr(keyform_table, 'parameters') and keyform_table.parameters:
            for p in keyform_table.parameters:
                if p.min_val >= p.max_val:
                    errors.append(f"Invalid parameter range for {p.param_id}: min ({p.min_val}) >= max ({p.max_val})")
                if not (p.min_val <= p.default_val <= p.max_val):
                    errors.append(f"Default value out of bounds for {p.param_id}: default ({p.default_val}) not in [{p.min_val}, {p.max_val}]")
                if p.key_values:
                    # Check monotonicity
                    for k_idx in range(len(p.key_values) - 1):
                        if p.key_values[k_idx] >= p.key_values[k_idx + 1]:
                            errors.append(f"Non-monotonic key values for {p.param_id}: {p.key_values}")
                            break

        return ValidationStageResult(
            stage_number=4,
            stage_name="Parameter & Keyform Bounds Verification",
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details=details
        )

    @classmethod
    def validate_stage5_textures_and_uvs(
        cls,
        model_dir: Path,
        texture_rel_paths: List[str],
        moc3_parsed: Optional[Dict[str, Any]] = None,
        keyform_table: Optional[Any] = None
    ) -> ValidationStageResult:
        """Stage 5: Texture Atlas PNG dimensions (power-of-two), RGBA8 channels, UV coordinates in [0.0, 1.0]."""
        errors: List[str] = []
        warnings: List[str] = []
        details: Dict[str, Any] = {}
        tex_dims: List[Tuple[int, int]] = []

        if not texture_rel_paths:
            errors.append("No texture paths provided for Stage 5 verification")
            return ValidationStageResult(5, "Texture Atlas & UV Coordinate Safety", False, errors, warnings, details)

        for tex_rel in texture_rel_paths:
            tex_full = model_dir / tex_rel
            if not tex_full.exists():
                errors.append(f"Texture file does not exist: {tex_full}")
                continue

            try:
                with Image.open(tex_full) as img:
                    w, h = img.size
                    tex_dims.append((w, h))

                    # Check power-of-two
                    is_pot_w = (w > 0) and ((w & (w - 1)) == 0)
                    is_pot_h = (h > 0) and ((h & (h - 1)) == 0)
                    if not (is_pot_w and is_pot_h):
                        errors.append(f"Texture dimensions {w}x{h} for {tex_rel} are not power-of-two")

                    # Check standard dimension range [512, 8192]
                    if w < 512 or h < 512 or w > 8192 or h > 8192:
                        warnings.append(f"Texture dimensions {w}x{h} outside standard range [512, 8192]")

                    # Check RGBA mode
                    if img.mode != "RGBA":
                        warnings.append(f"Texture format is {img.mode}, expected RGBA (4-channel 32-bit)")

            except Exception as e:
                errors.append(f"Cannot load texture image {tex_full}: {e}")

        details["texture_dimensions"] = tex_dims

        # Check UV coordinates if keyform_table or parsed moc is available
        if keyform_table and hasattr(keyform_table, 'drawables'):
            for d in keyform_table.drawables:
                if hasattr(d, 'uvs_atlas') and len(d.uvs_atlas) > 0:
                    uvs = np.asarray(d.uvs_atlas, dtype=np.float32)
                    if np.any(np.isnan(uvs)) or np.any(np.isinf(uvs)):
                        errors.append(f"NaN or Inf UV coordinates found in drawable {getattr(d, 'drawable_id', 'unknown')}")
                    elif np.any(uvs < -1e-4) or np.any(uvs > 1.0 + 1e-4):
                        errors.append(f"UV coordinates out of bounds in drawable {getattr(d, 'drawable_id', 'unknown')}")

        return ValidationStageResult(
            stage_number=5,
            stage_name="Texture Atlas & UV Coordinate Safety",
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details=details
        )

    @classmethod
    def validate_stage6_topology_and_deformation(
        cls,
        moc3_bytes: Optional[bytes] = None,
        keyform_table: Optional[Any] = None,
        drawables: Optional[List[Any]] = None
    ) -> ValidationStageResult:
        """Stage 6: Topological non-inversion (signed triangle area preservation > -1e-4) and vertex continuity."""
        errors: List[str] = []
        warnings: List[str] = []
        details: Dict[str, Any] = {}
        total_triangles_checked = 0
        inverted_triangles_found = 0

        target_drawables = []
        if drawables:
            target_drawables = drawables
        elif keyform_table and hasattr(keyform_table, 'drawables'):
            target_drawables = keyform_table.drawables

        if target_drawables:
            for d in target_drawables:
                base_v = np.asarray(d.base_vertices, dtype=np.float32)
                tris = np.asarray(d.triangles, dtype=np.int32)
                d_id = getattr(d, 'drawable_id', 'ArtMesh')

                # Check vertex count limit (Live2D uint16 index limit)
                if len(base_v) > 65535:
                    errors.append(f"ArtMesh {d_id} vertex count ({len(base_v)}) exceeds Live2D uint16 limit (65535)")

                # Check finite coordinates
                if np.any(np.isnan(base_v)) or np.any(np.isinf(base_v)):
                    errors.append(f"NaN or Inf vertex coordinates found in rest pose of {d_id}")

                # Check index bounds
                if len(tris) > 0:
                    if np.min(tris) < 0 or np.max(tris) >= len(base_v):
                        errors.append(f"Index out of range in triangles of {d_id}: max index {np.max(tris)} >= {len(base_v)}")
                    elif np.max(tris) > 65535:
                        errors.append(f"Triangle index {np.max(tris)} in {d_id} exceeds Live2D uint16 limit (65535)")

                # Check keyforms deformation positions
                deformed_dict = getattr(d, 'deformed_positions', {})
                if deformed_dict:
                    for key_tuple, kf_pos in deformed_dict.items():
                        kf_arr = np.asarray(kf_pos, dtype=np.float32)
                        if np.any(np.isnan(kf_arr)) or np.any(np.isinf(kf_arr)):
                            errors.append(f"NaN or Inf vertex coordinates in keyform {key_tuple} of {d_id}")
                            continue

                        # Check triangle signed areas
                        for tri in tris:
                            i0, i1, i2 = int(tri[0]), int(tri[1]), int(tri[2])
                            if i0 < len(kf_arr) and i1 < len(kf_arr) and i2 < len(kf_arr):
                                p0, p1, p2 = kf_arr[i0], kf_arr[i1], kf_arr[i2]
                                v1 = p1 - p0
                                v2 = p2 - p0
                                signed_area = 0.5 * (v1[0] * v2[1] - v1[1] * v2[0])
                                total_triangles_checked += 1
                                if signed_area < -1e-4:
                                    inverted_triangles_found += 1
                                    errors.append(
                                        f"Inverted triangle ({i0},{i1},{i2}) with signed area {signed_area:.6f} "
                                        f"in keyform {key_tuple} of {d_id}"
                                    )
                                    break  # Record one error per keyform to prevent flood

        details["total_triangles_checked"] = total_triangles_checked
        details["inverted_triangles_found"] = inverted_triangles_found

        return ValidationStageResult(
            stage_number=6,
            stage_name="Topological Non-Inversion & Deformation Continuity",
            passed=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            details=details
        )


def validate_live2d_model(
    model_entry_path: Union[str, Path],
    strict: bool = False,
    keyform_table: Optional[Any] = None
) -> ValidationReport:
    """
    Executes the comprehensive 6-stage structural validation on a Live2D model bundle.
    
    Args:
        model_entry_path: Path to model directory, .model3.json manifest, or .moc3 binary file.
        strict: If True, treats any warnings as validation failures.
        keyform_table: Optional in-memory KeyformTable for deep geometry verification.

    Returns:
        ValidationReport: Summary report detailing outcomes, errors, warnings, and metrics.
    """
    path = Path(model_entry_path).resolve()
    report = ValidationReport(model_path=str(path))

    if not path.exists():
        err = f"Model path does not exist: {path}"
        report.add_stage(ValidationStageResult(1, "File Existence", False, [err], []))
        return report

    # Determine files
    model_dir: Path
    model3_path: Optional[Path] = None
    moc3_path: Optional[Path] = None

    if path.is_dir():
        model_dir = path
        report.model_name = model_dir.name
        model3_files = list(model_dir.glob("*.model3.json"))
        if model3_files:
            model3_path = model3_files[0]
        moc3_files = list(model_dir.glob("*.moc3"))
        if moc3_files:
            moc3_path = moc3_files[0]
    elif path.suffix.lower() == ".json":
        model3_path = path
        model_dir = path.parent
        report.model_name = path.stem.replace(".model3", "")
    elif path.suffix.lower() == ".moc3":
        moc3_path = path
        model_dir = path.parent
        report.model_name = path.stem
        # Check if sibling .model3.json exists
        sibling_model3 = model_dir / f"{path.stem}.model3.json"
        if sibling_model3.exists():
            model3_path = sibling_model3
    else:
        model_dir = path.parent
        report.model_name = path.stem

    # -----------------------------------------------------------------------
    # Stage 3 first to locate referenced .moc3 and textures
    # -----------------------------------------------------------------------
    model3_data = None
    cdi3_data = None
    tex_rel_paths: List[str] = []

    if model3_path is not None:
        stage3_res, model3_data, cdi3_data = StructuralValidator.validate_stage3_json_manifest(
            model_dir=model_dir,
            model3_path=model3_path
        )
        if model3_data and "FileReferences" in model3_data:
            f_refs = model3_data["FileReferences"]
            if "Moc" in f_refs and not moc3_path:
                moc3_path = model_dir / f_refs["Moc"]
            if "Textures" in f_refs:
                tex_rel_paths = list(f_refs["Textures"])
    else:
        stage3_res = ValidationStageResult(
            3, "JSON Manifest & File Reference Conformance", False,
            ["No .model3.json found in model directory"], []
        )

    # -----------------------------------------------------------------------
    # Stage 1 & 2: Binary MOC3 Header and Section Tables
    # -----------------------------------------------------------------------
    moc3_bytes: Optional[bytes] = None
    moc3_parsed: Optional[Dict[str, Any]] = None

    if moc3_path and moc3_path.exists():
        try:
            with open(moc3_path, "rb") as f:
                moc3_bytes = f.read()
        except Exception as e:
            moc3_bytes = None

    if moc3_bytes is not None:
        stage1_res = StructuralValidator.validate_stage1_moc3_header(moc3_bytes)
        stage2_res = StructuralValidator.validate_stage2_section_tables(moc3_bytes)
        try:
            from src.exporter.moc3_writer import Moc3Reader
            moc3_parsed = Moc3Reader.parse_bytes(moc3_bytes)
        except Exception:
            moc3_parsed = None
    else:
        stage1_res = ValidationStageResult(
            1, "Binary MOC3 Header Integrity", False,
            [f"MOC3 binary file not found or unreadable: {moc3_path}"], []
        )
        stage2_res = ValidationStageResult(
            2, "Section Table Offsets & Count Table Sanity", False,
            ["Cannot validate section tables without .moc3 binary"], []
        )

    # -----------------------------------------------------------------------
    # Stage 4: Parameter Bounds
    # -----------------------------------------------------------------------
    stage4_res = StructuralValidator.validate_stage4_parameter_bounds(
        cdi3_data=cdi3_data,
        moc3_parsed=moc3_parsed,
        keyform_table=keyform_table
    )

    # -----------------------------------------------------------------------
    # Stage 5: Texture Atlas & UV Coordinates
    # -----------------------------------------------------------------------
    if not tex_rel_paths:
        # Check textures subfolder directly if not specified in JSON
        for p in model_dir.glob("*/*.png"):
            rel_p = str(p.relative_to(model_dir)).replace("\\", "/")
            tex_rel_paths.append(rel_p)

    stage5_res = StructuralValidator.validate_stage5_textures_and_uvs(
        model_dir=model_dir,
        texture_rel_paths=tex_rel_paths,
        moc3_parsed=moc3_parsed,
        keyform_table=keyform_table
    )

    # -----------------------------------------------------------------------
    # Stage 6: Topology & Non-Inversion
    # -----------------------------------------------------------------------
    stage6_res = StructuralValidator.validate_stage6_topology_and_deformation(
        moc3_bytes=moc3_bytes,
        keyform_table=keyform_table
    )

    # Aggregate stages in numerical order 1..6
    report.add_stage(stage1_res)
    report.add_stage(stage2_res)
    report.add_stage(stage3_res)
    report.add_stage(stage4_res)
    report.add_stage(stage5_res)
    report.add_stage(stage6_res)

    if strict and report.total_warnings > 0:
        report.passed = False

    return report
