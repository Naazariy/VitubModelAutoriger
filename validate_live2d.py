#!/usr/bin/env python3
"""
validate_live2d.py - Programmatic 6-Stage Structural Validator CLI for Live2D Cubism Models.
Audits binary .moc3 headers, 64-byte aligned section tables, JSON manifests,
tracking parameter keyforms, power-of-two texture atlases, and topological non-inversion.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

# Ensure project root is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.validator.structural_validator import validate_live2d_model, ValidationReport


def build_parser() -> argparse.ArgumentParser:
    """Constructs the CLI argument parser for validate_live2d."""
    parser = argparse.ArgumentParser(
        prog="validate_live2d",
        description="6-Stage Programmatic Structural Validator for Live2D Cubism Models",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "model_path",
        nargs="?",
        default=None,
        help="Path to Live2D model directory, .model3.json manifest, or .moc3 binary file"
    )
    parser.add_argument(
        "-m", "--model",
        dest="model_flag",
        type=str,
        default=None,
        help="Path to Live2D model (alias for positional model_path)"
    )
    parser.add_argument(
        "-o", "--json-report",
        dest="json_report",
        type=str,
        default=None,
        help="Optional path to write full JSON validation report"
    )
    parser.add_argument(
        "-q", "--quiet",
        dest="quiet",
        action="store_true",
        default=False,
        help="Suppress console output, emit only exit code and errors"
    )
    parser.add_argument(
        "-v", "--verbose",
        dest="verbose",
        action="store_true",
        default=False,
        help="Display expanded diagnostic details for each stage"
    )
    parser.add_argument(
        "--no-color",
        dest="no_color",
        action="store_true",
        default=False,
        help="Disable ANSI color escapes in console output"
    )
    parser.add_argument(
        "--strict",
        dest="strict",
        action="store_true",
        default=False,
        help="Treat warnings as hard validation errors"
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main execution function for standalone validation CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    target_path = args.model_path or args.model_flag
    if not target_path:
        print("[ERROR] Missing required model path. Usage: python validate_live2d.py <model_dir_or_json>", file=sys.stderr)
        return 1

    path = Path(target_path).resolve()
    if not path.exists():
        print(f"[ERROR] Target path does not exist: {path}", file=sys.stderr)
        return 1

    # Run 6-stage structural validator
    report: ValidationReport = validate_live2d_model(path, strict=args.strict)

    # Optional JSON export
    if args.json_report:
        report_path = Path(args.json_report).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

    # Console display
    if not args.quiet:
        use_color = not args.no_color and sys.stdout.isatty() if hasattr(sys.stdout, 'isatty') else (not args.no_color)
        print(report.format_console(use_color=use_color))

    # Exit code: 0 on success, 5 on validation failure
    if report.is_valid and report.passed:
        return 0
    else:
        return 5


if __name__ == "__main__":
    sys.exit(main())
