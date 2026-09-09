# Project Plan: Automated VTuber Deformation & Live2D Export Tool

## Phase 0: Survey & Scoping
- Dispatch 3 Explorers / Spec Miners:
  - Explorer 1: Codebase inventory, input data handling (PSD/PNG layer slicing/mesh generation), and deformation math (Angle X/Y/Z perspective & warping algorithms).
  - Explorer 2: Live2D file format analysis (.moc3, .cmo3, model3.json, textures, moc3 binary specification, PyLive2D/live2d sdk/intermediate formats).
  - Explorer 3: E2E test harness architecture, CLI requirements, structural validation script design, and verification walkthrough.
- Aggregate survey findings into `PROJECT.md` (Architecture, Feature Inventory, Milestones, Code Layout, Interface Contracts).

## Phase 1: Dual Track Execution
- Track A: E2E Testing Track Orchestrator
  - Design E2E test harness (`TEST_INFRA.md`).
  - Implement Tier 1 (Feature Coverage), Tier 2 (Boundary & Corner), Tier 3 (Cross-Feature Pairwise), Tier 4 (Real-World Application) test suites.
  - Publish `TEST_READY.md`.
- Track B: Implementation Track (Milestone Sub-orchestrators)
  - Milestone 1: Asset Ingestion & Mesh Generation (PSD/PNG parsing, layer extraction, automatic Delaunay/grid meshing).
  - Milestone 2: Automated 3D Deformation Engine (Angle X, Y, Z calculation, perspective warping, depth layers, deformation keyform generation).
  - Milestone 3: Live2D Export Engine & Compatibility Pipeline (generating .moc3/.cmo3/model3.json/texture atlas package compatible with Live2D Cubism & VTube Studio).
  - Milestone 4: CLI Interface & Schema/Structural Validator (zero-touch CLI execution + automated format validator script).

## Phase 2: Final Milestone & Hardening
- Phase 2.1: Pass 100% of E2E test suite (Tiers 1-4).
- Phase 2.2: Adversarial Coverage Hardening (Tier 5 - Challenger driven).
- Phase 2.3: Verification Instructions & Walkthrough validation for Live2D Cubism / VTube Studio loading.

## Phase 3: Final Review & Handoff
- Integrity audit & complete system verification.
- Human-facing completion report to Sentinel.
