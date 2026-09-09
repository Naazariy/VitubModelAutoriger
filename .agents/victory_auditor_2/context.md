# Independent Victory Audit Context

## Working Directory
d:\VitubModel\.agents\victory_auditor_2

## Workspace
d:\VitubModel

## Original User Request
d:\VitubModel\.agents\ORIGINAL_REQUEST.md

## Scope to Audit
Debug and fix the generated Live2D `.moc3` binary and metadata files so they can be successfully loaded into VTube Studio, using the provided `hiyori_vts` model as a reference.

Acceptance Criteria:
1. The `export_live2d.py` script successfully outputs a `.moc3` file that can be loaded in VTube Studio.
2. The team writes a diagnostic script to compare the binary Section Offset Tables and Count Tables of `hiyori_vts` against our generated `.moc3` to prove that the structural mismatch has been resolved.
