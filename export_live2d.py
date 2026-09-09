#!/usr/bin/env python3
"""
export_live2d.py - Root CLI Entrypoint for Automated VTuber Key Deformation & Live2D Export.
Transforms layered PSDs, PNG images, or layer folders into fully functional Live2D Cubism models.
"""

import os
from pathlib import Path
import sys

# Ensure project root is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from src.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
