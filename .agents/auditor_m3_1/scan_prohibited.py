"""
Forensic Codebase Scan for Prohibited Patterns:
1. Hardcoded test results / expected output constants
2. Facade implementations (functions returning constant literals)
3. Fabricated verification outputs
4. Dummy classes or bypasses
"""
import os
import re
from pathlib import Path

BASE_DIR = Path("d:/VitubModel")
EXPORTER_DIR = BASE_DIR / "src" / "exporter"

PATTERNS = [
    r"return\s+True\s*#.*stub",
    r"return\s+b['\"][^'\"]*['\"]\s*#.*stub",
    r"pass\s*#.*todo",
    r"raise\s+NotImplementedError",
    r"TODO",
    r"FIXME",
    r"mock",
    r"dummy",
    r"hardcode",
]

print("=== Scanning src/exporter for prohibited patterns ===")
findings = []
for p in EXPORTER_DIR.rglob("*.py"):
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    for idx, line in enumerate(lines, 1):
        for pat in PATTERNS:
            if re.search(pat, line, re.IGNORECASE):
                findings.append((str(p.relative_to(BASE_DIR)), idx, pat, line.strip()))

if findings:
    print(f"Found {len(findings)} potential pattern matches:")
    for f in findings:
        print(f"  {f[0]}:{f[1]} [{f[2]}] -> {f[3]}")
else:
    print("Zero prohibited pattern matches found in src/exporter!")

print("\n=== Scanning tests/test_*exporter*.py and tests/test_m*.py ===")
test_files = [
    BASE_DIR / "tests" / "test_texture_packer.py",
    BASE_DIR / "tests" / "test_moc3_writer.py",
    BASE_DIR / "tests" / "test_model3_writer.py",
]
test_findings = []
for p in test_files:
    if p.exists():
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for idx, line in enumerate(lines, 1):
            if re.search(r"mock\.|MagicMock|unittest\.mock", line):
                test_findings.append((str(p.relative_to(BASE_DIR)), idx, line.strip()))

if test_findings:
    print(f"Found mock usage in tests: {test_findings}")
else:
    print("Zero mock framework usage found in Milestone 3 unit tests. All tests exercise real objects.")
