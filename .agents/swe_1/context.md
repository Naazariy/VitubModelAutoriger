# Context for SWE Orchestrator

## Task
Debug and fix the generated Live2D `.moc3` binary and metadata files so they can be successfully loaded into VTube Studio, using the provided `hiyori_vts` model as a reference.

Working directory: d:\VitubModel
Integrity mode: demo

## Requirements
1. Live2D Cubism Core Compatibility: The exported `.moc3`, `.model3.json`, and `.cdi3.json` files must strictly adhere to the formats expected by VTube Studio's Live2D Cubism Core. Currently, the generated model returns a "Could not load Live2D model" error.
2. Reference Analysis: Analyze the working reference model in `d:\VitubModel\output\hiyori_vts` to identify structural differences, missing sections (like Deformers or empty mask arrays), or JSON formatting issues that cause the crash.
3. Tool Execution: The `export_live2d.py` script successfully outputs a `.moc3` file that can be loaded in VTube Studio.
4. Verification: The team writes a diagnostic script to compare the binary Section Offset Tables and Count Tables of `hiyori_vts` against our generated `.moc3` to prove that the structural mismatch has been resolved.
