import sys
from src.exporter.moc3_writer import Moc3Reader

h = Moc3Reader.read_from_file("output/hiyori_vts/hiyori.moc3")
m = Moc3Reader.read_from_file("output/MyAvatar2/MyAvatar2.moc3")

print("Hiyori version:", h.get("version"))
print("MyAvatar version:", m.get("version"))

print("Hiyori counts:", h.get("counts"))
print("MyAvatar counts:", m.get("counts"))

# Dump sections
def print_sections(name, parsed):
    print(f"\n--- {name} Sections ---")
    offsets = parsed.get("section_offsets", [])
    for i, off in enumerate(offsets):
        if off > 0:
            print(f"  [{i}]: 0x{off:04X}")

print_sections("Hiyori", h)
print_sections("MyAvatar", m)
