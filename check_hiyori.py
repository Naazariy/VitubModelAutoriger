"""
check_hiyori.py
Structural inspection script for Live2D Cubism .moc3 binary models.
Verifies Deformer hierarchy, CountInfoTable counters (Parts, Deformers, WarpDeformers, RotationDeformers),
parameter bindings, and keyform float arrays.
"""

import sys
from pathlib import Path
import struct
from src.exporter.moc3_writer import Moc3Reader


def inspect_moc3(file_path: str = "output/hiyori_vts/hiyori.moc3"):
    path = Path(file_path)
    if not path.exists():
        print(f"File not found: {file_path}")
        return

    print(f"=== Inspecting MOC3: {path.name} ({path.resolve()}) ===")
    parsed = Moc3Reader.read_from_file(str(path))
    counts = parsed.get("counts", {})

    print(f"Magic: {parsed.get('magic')}, Version: {parsed.get('version')}, Total Size: {parsed.get('total_size')} bytes")
    print(f"64-byte Aligned: {parsed.get('is_64_aligned')}")
    print("\n--- Model Counts ---")
    for k, v in counts.items():
        print(f"  {k:30s}: {v}")

    # Confirm presence of deformers (Counts > 0)
    n_def = counts.get("deformers", 0)
    n_warp = counts.get("warp_deformers", 0)
    n_rot = counts.get("rotation_deformers", 0)
    print(f"\nDeformer Verification: Total={n_def}, Warp={n_warp}, Rotation={n_rot} (Presence confirmed: {n_def > 0})")

    deformer_ids = parsed.get("deformer_ids", [])
    if deformer_ids:
        print(f"Deformer IDs ({len(deformer_ids)} total): {deformer_ids[:10]}")

    art_mesh_ids = parsed.get("art_mesh_ids", [])
    if art_mesh_ids:
        print(f"ArtMesh IDs ({len(art_mesh_ids)} total): {art_mesh_ids[:10]}")

    param_ids = parsed.get("parameter_ids", [])
    if param_ids:
        print(f"Parameter IDs ({len(param_ids)} total): {param_ids[:10]}")

    def print_floats(name, section_idx, count):
        offsets = parsed.get("section_offsets", [])
        if section_idx < len(offsets) and offsets[section_idx] > 0:
            off = offsets[section_idx]
            data = open(str(path), "rb").read()
            try:
                floats = struct.unpack_from(f"<{count}f", data, off)
                print(f"{name}: {[round(x, 4) for x in floats[:10]]}")
            except Exception as e:
                print(f"{name}: Failed to unpack ({e})")
        else:
            print(f"{name}: Section {section_idx} not present (offset 0)")

    print("\n--- Keyform Sections ---")
    print_floats("PartKeyforms (Sec 58)", 58, 10)
    if counts.get("warp_deformer_keyforms", 0) > 0:
        print_floats("WarpDeformerKeyforms Opacities (Sec 59)", 59, min(10, counts["warp_deformer_keyforms"]))
    if counts.get("rotation_deformer_keyforms", 0) > 0:
        print_floats("RotationDeformerKeyforms Angles (Sec 62)", 62, min(10, counts["rotation_deformer_keyforms"]))
    print_floats("ArtMeshKeyforms Opacities (Sec 68)", 68, 10)
    print_floats("ArtMeshKeyforms DrawOrders (Sec 69)", 69, 10)


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "output/hiyori_vts/hiyori.moc3"
    inspect_moc3(target)
