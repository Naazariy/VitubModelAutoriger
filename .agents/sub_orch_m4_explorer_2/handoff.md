# Handoff Report: Headless Zero-Intervention CLI & Pipeline Integration Design (Milestone 4)

**Agent**: Explorer 2 (`sub_orch_m4_explorer_2`)  
**Parent Agent**: `097844e5-5bcc-4979-a2f7-1ae9636920c1` (`sub_orch_m4`)  
**Date**: 2026-08-22  
**Handoff Type**: Hard (Investigation & Architecture Design Complete)

---

## 1. Observation

### 1.1 Ingestion & Core Data Structures
- `src/importer/psd_importer.py:31-168`: `PSDImporter.load_psd()` and `load_psd_as_collection()` extract raster layers, compute canvas bounding boxes, and assign bilingual semantic categories (`SemanticClassifier.classify`).
- `src/importer/image_importer.py:31-98`: `ImageImporter.load_image()` returns `(rgba, alpha)`, `load_directory()` returns `List[LayerData]`, and `create_synthetic_layered_head()` creates a 14-layer synthetic decomposition for 100% self-contained testing.
- `src/core/layer.py:9-183`: `LayerData` encapsulates `name`, `image` (RGBA uint8), `offset_x`, `offset_y`, `z_depth_hint`, `category`, and bounding box calculations. `LayerCollection` manages layered manifests and composition.
- `src/core/mesh.py:5-243`: `Mesh` manages vertices, triangles, rest positions, edges, signed triangle areas (`compute_triangle_signed_areas()`), and topology validation (`validate_topology()`).
- `src/core/keyform.py:23-169`: `DrawableKeyforms` and `KeyformTable` encapsulate parameter bindings (`ParamAngleX`, `ParamAngleY`, `ParamAngleZ`), keyform coordinates, and multi-dimensional displacement tensors.

### 1.2 Triangulation, Depth & 3D Deformation Engine
- `src/generator/mesh_generator.py:154-410`: `MeshGenerator.generate_mesh_from_contour()` applies pure-Python SciPy Delaunay triangulation with Steiner internal grid sampling, exterior polygon clipping, and constrained boundary-pinned Laplacian smoothing.
- `src/depth/depth_model.py:46-440`: `DepthModel` computes parametric 3D depth proxies (Ellipsoid, Cylinder, Inverted Shell, Conical Bump), enforces non-penetration clearance across layers, and globally normalizes depths into `[-1.0, 1.0]`.
- `src/deformation/deformation_solver.py:15-266`: `DeformationSolver` evaluates exact SO(3) Euler rotations $R_z(\theta_z) R_y(\theta_x) R_x(\theta_y)$, depth-scaled parallax projection, anime foreshortening, and ARAP regularization.
- `src/deformation/keyform_generator.py:16-181`: `KeyformGenerator.generate_keyform_table()` constructs master keyform tables across all layers for 9-keyform Cartesian grid ($3 \times 3$ Angle X/Y) plus Angle Z roll.

### 1.3 Exporter & Validator Specifications
- `src/exporter/texture_packer.py:284-616`: `TextureAtlasPacker.pack()` implements power-of-two MaxRects bin packing with 2px Voronoi color bleed dilation and UV remapping into $[0.0, 1.0]$.
- `src/exporter/moc3_writer.py:53-408`: `Moc3Writer.write_moc3()` serializes compliant Live2D 4.0 binary files with 64-byte alignment, section offset table (160 entries), drawables, parameters, and keyforms.
- `src/exporter/model3_writer.py:18-257`: `Model3Writer.export_model_bundle()` exports `.model3.json`, `.cdi3.json`, `.moc3`, and texture PNGs with normalized forward-slash relative paths.
- `tests/conftest.py:538-653`: `CLIRunner` and `StructuralValidator` define the CLI argument parsing interface and standard exit codes:
  * 0: Success
  * 1: Input Error / Invalid Arguments
  * 2: Mesh Generation Error
  * 3: Deformation / Physics Error
  * 4: Export / Serialization Error
  * 5: Validation Error

---

## 2. Logic Chain

1. **End-to-End Coupling**: All upstream pipeline engines (Ingestion, Triangulation, Depth/Deformation, Texture Packing, MOC3/Model3 Serialization) exist and provide clean programmatic APIs. The CLI (`src/cli/main.py`) acts as the top-level orchestrator executing these steps in a strictly sequential 6-stage lifecycle.
2. **Unified Argument Parsing**: To satisfy user requirements, developer scripts, and existing test suites, the CLI must parse input files (positional or flagged), output directories, model names, texture dimensions (power-of-two), mesh grid density, rotation ranges, and validation flags.
3. **Deterministic Error Handling**: Wrapping each pipeline phase in distinct exception handlers (`InputError`, `MeshGenerationError`, `DeformationError`, `ExportError`, `ValidationError`) ensures every possible failure mode produces the exact standardized exit code (0 to 5) and informative error logs without uncaught stack traces.
4. **Seamless Wrapper Script Delegation**: `export_live2d.py` at the project root ensures project root is on `sys.path`, forwards arguments to `src.cli.main.main()`, and exits with the returned status code, enabling direct terminal commands like `python export_live2d.py input.psd -o ./output --validate`.
5. **Observability & UX**: Dual console formatting (Rich color tables when available, clean ANSI text fallback) combined with `--json-output` allows both pleasant developer experience and seamless CI/CD script automation.

---

## 3. Caveats

- **PSD Tools Dependency**: Ingesting `.psd` files requires the optional `psd-tools` package. If `psd-tools` is missing when a `.psd` file is provided, `PSDImporter` raises an `ImportError`, which the CLI catches and maps to `InputError` (exit code 1) with clear user guidance to install `psd-tools` or use PNG files.
- **GUI Launching**: When `--gui` is specified, PySide6 must be installed; if headless server environment lacks display/GUI libraries, the CLI logs a graceful warning or returns exit code 0 if model export already succeeded.

---

## 4. Conclusion

The architectural design for `src/cli/main.py` and `export_live2d.py` is fully specified with:
- Complete argument parser options and typed configuration container (`PipelineConfig`).
- 6-stage end-to-end execution flow (`PipelineRunner`).
- Standardized exit codes (`0` to `5`) and structured exception hierarchy (`PipelineException`).
- Clean root script wrapper (`export_live2d.py`) and package entrypoint (`python -m src.cli`).
- Comprehensive unit and integration test plan for `tests/test_cli.py`.

The full technical specification and complete code designs are documented in `d:\VitubModel\.agents\sub_orch_m4_explorer_2\analysis.md`.

---

## 5. Verification Method

To verify the implementation once coded:
1. **Unit and Integration Tests**:
   ```bash
   python -m pytest tests/test_cli.py -v
   ```
2. **End-to-End E2E Tests**:
   ```bash
   python -m pytest tests/e2e/test_tier1_features.py tests/e2e/test_tier4_scenarios.py -v
   ```
3. **CLI Invocation Checks**:
   - Single PNG image export:
     ```bash
     python export_live2d.py sample.png -o ./output -n SampleModel --validate
     ```
     Verify exit code is 0 and output directory contains `.model3.json`, `.moc3`, `.cdi3.json`, and `texture_00.png`.
   - Non-existent file error handling:
     ```bash
     python export_live2d.py non_existent.png
     ```
     Verify exit code is 1 (`EXIT_ERR_INPUT`).
