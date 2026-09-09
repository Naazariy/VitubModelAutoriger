"""
tests/test_cli.py
Comprehensive Unit & Integration Test Suite for the Headless Zero-Intervention CLI Pipeline.
Tests CLI argument parsing, exit codes (0 to 5), full pipeline runs, --validate integration, and root scripts.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest
from PIL import Image

from src.cli.main import (
    build_parser,
    parse_args,
    run_pipeline,
    main,
    PipelineConfig,
    PipelineRunner,
    EXIT_SUCCESS,
    EXIT_ERR_INPUT,
    EXIT_ERR_MESH,
    EXIT_ERR_DEFORMATION,
    EXIT_ERR_EXPORT,
    EXIT_ERR_VALIDATION,
)
from src.validator.structural_validator import validate_live2d_model


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_png_image(tmp_path) -> Path:
    """Generates a synthetic 512x512 RGBA character image with face and hair features."""
    img_path = tmp_path / "synthetic_avatar.png"
    arr = np.zeros((512, 512, 4), dtype=np.uint8)
    
    # Draw head circle (skin tone)
    y, x = np.ogrid[:512, :512]
    dist_from_center = np.sqrt((x - 256) ** 2 + (y - 256) ** 2)
    mask = dist_from_center <= 180
    arr[mask] = [255, 220, 195, 255]

    # Draw eyes
    eye_l = np.sqrt((x - 200) ** 2 + (y - 230) ** 2) <= 25
    eye_r = np.sqrt((x - 312) ** 2 + (y - 230) ** 2) <= 25
    arr[eye_l] = [50, 120, 240, 255]
    arr[eye_r] = [50, 120, 240, 255]

    Image.fromarray(arr).save(img_path)
    return img_path


@pytest.fixture
def mock_layer_directory(tmp_path) -> Path:
    """Generates a folder with multi-layer PNGs (face, eyes, hair)."""
    layer_dir = tmp_path / "character_layers"
    layer_dir.mkdir(parents=True, exist_ok=True)

    # 1. Hair Back
    hb = Image.new("RGBA", (300, 300), (50, 40, 60, 255))
    hb.save(layer_dir / "01_hair_back.png")

    # 2. Face Skin
    f = Image.new("RGBA", (250, 250), (255, 220, 195, 255))
    f.save(layer_dir / "02_face.png")

    # 3. Hair Front
    hf = Image.new("RGBA", (260, 200), (65, 50, 80, 255))
    hf.save(layer_dir / "03_hair_front.png")

    return layer_dir


# ---------------------------------------------------------------------------
# Test Suite: CLI Argument Parsing Unit Tests
# ---------------------------------------------------------------------------
class TestCLIArgumentParsing:
    """Tests argument parsing defaults, custom flags, and range converters."""

    def test_cli_parse_defaults(self):
        args = parse_args(["sample.png"])
        config = PipelineConfig.from_args(args)
        assert config.input_path == "sample.png"
        assert config.output_dir == "./output"
        assert config.model_name is None
        assert config.atlas_size == 4096
        assert config.grid_size == 25
        assert config.angle_x_range == (-30.0, 30.0)
        assert config.angle_y_range == (-30.0, 30.0)
        assert config.angle_z_range == (-20.0, 20.0)
        assert config.auto_depth is True
        assert config.validate is False

    def test_cli_parse_custom_flags(self):
        cmd = [
            "avatar.psd",
            "-o", "./my_output",
            "-n", "KohakuHero",
            "--resolution", "2048",
            "--grid-size", "15",
            "--angle-x-range", "-25.0,25.0",
            "--angle-y-range", "-20.0,20.0",
            "--angle-z-range", "-15.0,15.0",
            "--padding", "8",
            "--bleed-radius", "4",
            "--validate",
            "--strict",
            "--json-output"
        ]
        args = parse_args(cmd)
        config = PipelineConfig.from_args(args)
        assert config.input_path == "avatar.psd"
        assert config.output_dir == "./my_output"
        assert config.model_name == "KohakuHero"
        assert config.atlas_size == 2048
        assert config.grid_size == 15
        assert config.angle_x_range == (-25.0, 25.0)
        assert config.angle_y_range == (-20.0, 20.0)
        assert config.angle_z_range == (-15.0, 15.0)
        assert config.padding == 8
        assert config.bleed_radius == 4
        assert config.validate is True
        assert config.strict is True
        assert config.json_output is True

    def test_cli_input_flag_alias(self):
        cmd = ["-i", "character.png", "-o", "./out"]
        args = parse_args(cmd)
        config = PipelineConfig.from_args(args)
        assert config.input_path == "character.png"


# ---------------------------------------------------------------------------
# Test Suite: Exit Codes & Error Trapping
# ---------------------------------------------------------------------------
class TestCLIExitCodes:
    """Tests exit code contract across standard failure and success conditions."""

    def test_exit_code_1_on_missing_input_file(self, tmp_path):
        nonexistent = str(tmp_path / "nonexistent_file_9999.png")
        exit_code = run_pipeline([nonexistent, "-o", str(tmp_path / "out")])
        assert exit_code == EXIT_ERR_INPUT

    def test_exit_code_1_on_empty_input_argument(self):
        exit_code = run_pipeline([])
        assert exit_code == EXIT_ERR_INPUT

    def test_exit_code_0_on_valid_export(self, mock_png_image, tmp_path):
        out_dir = tmp_path / "export_success"
        exit_code = run_pipeline([
            str(mock_png_image),
            "-o", str(out_dir),
            "-n", "ValidModel",
            "--resolution", "1024",
            "--grid-size", "35"
        ])
        assert exit_code == EXIT_SUCCESS
        assert (out_dir / "ValidModel" / "ValidModel.model3.json").exists()
        assert (out_dir / "ValidModel" / "ValidModel.moc3").exists()
        assert (out_dir / "ValidModel" / "ValidModel.cdi3.json").exists()


# ---------------------------------------------------------------------------
# Test Suite: Full End-to-End Pipeline Execution
# ---------------------------------------------------------------------------
class TestFullPipelineE2E:
    """Tests complete end-to-end conversion workflows."""

    def test_e2e_single_png_with_validation(self, mock_png_image, tmp_path):
        out_dir = tmp_path / "e2e_png"
        exit_code = run_pipeline([
            str(mock_png_image),
            "-o", str(out_dir),
            "-n", "ValidatedAvatar",
            "--resolution", "1024",
            "--grid-size", "30",
            "--validate"
        ])
        assert exit_code == EXIT_SUCCESS

        model_dir = out_dir / "ValidatedAvatar"
        model3_path = model_dir / "ValidatedAvatar.model3.json"
        assert model3_path.exists()

        # Run independent verification
        report = validate_live2d_model(model3_path)
        assert report.is_valid is True
        assert report.passed is True
        assert report.total_errors == 0
        assert len(report.stages_passed) == 6

    def test_e2e_layer_directory_export(self, mock_layer_directory, tmp_path):
        out_dir = tmp_path / "e2e_dir"
        exit_code = run_pipeline([
            str(mock_layer_directory),
            "-o", str(out_dir),
            "-n", "MultiLayerAvatar",
            "--resolution", "2048",
            "--grid-size", "35",
            "--validate"
        ])
        assert exit_code == EXIT_SUCCESS

        model_dir = out_dir / "MultiLayerAvatar"
        assert (model_dir / "MultiLayerAvatar.model3.json").exists()
        assert (model_dir / "MultiLayerAvatar.moc3").exists()
        assert (model_dir / "MultiLayerAvatar.cdi3.json").exists()

        report = validate_live2d_model(model_dir)
        assert report.is_valid is True
        assert report.passed is True


# ---------------------------------------------------------------------------
# Test Suite: Subprocess Script Invocations
# ---------------------------------------------------------------------------
class TestSubprocessScriptExecution:
    """Tests root export_live2d.py and validate_live2d.py scripts via subprocess."""

    def test_root_export_live2d_script(self, mock_png_image, tmp_path):
        python_exe = sys.executable
        export_script = Path(__file__).resolve().parent.parent / "export_live2d.py"
        out_dir = tmp_path / "script_export"

        cmd = [
            python_exe,
            str(export_script),
            str(mock_png_image),
            "-o", str(out_dir),
            "-n", "ScriptModel",
            "--resolution", "1024",
            "--grid-size", "35",
            "--validate"
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        assert proc.returncode == 0
        assert (out_dir / "ScriptModel" / "ScriptModel.model3.json").exists()

    def test_root_validate_live2d_script(self, mock_png_image, tmp_path):
        python_exe = sys.executable
        export_script = Path(__file__).resolve().parent.parent / "export_live2d.py"
        validate_script = Path(__file__).resolve().parent.parent / "validate_live2d.py"
        out_dir = tmp_path / "validate_script_test"

        # 1. Export model
        subprocess.run([
            python_exe, str(export_script), str(mock_png_image),
            "-o", str(out_dir), "-n", "TestModel", "--resolution", "1024", "--grid-size", "35"
        ], check=True)

        model_dir = out_dir / "TestModel"

        # 2. Run standalone validation script
        proc = subprocess.run([
            python_exe, str(validate_script), str(model_dir)
        ], capture_output=True, text=True)

        assert proc.returncode == 0
        assert "LIVE2D 6-STAGE STRUCTURAL VALIDATION REPORT" in proc.stdout
        assert "[PASSED]" in proc.stdout
