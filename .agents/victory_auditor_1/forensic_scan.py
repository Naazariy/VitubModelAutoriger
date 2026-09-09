import pathlib
import re
import sys

def audit_sources():
    src_dir = pathlib.Path("src")
    suspicious_patterns = [
        ("NotImplementedError", re.compile(r"raise\s+NotImplementedError")),
        ("TODO/FIXME", re.compile(r"\b(TODO|FIXME|HACK)\b", re.IGNORECASE)),
        ("Hardcoded Pass/Success", re.compile(r"return\s+['\"](?:SUCCESS|PASSED|PASS)['\"]")),
        ("Empty Pass", re.compile(r"def\s+[a-zA-Z0-9_]+\([^)]*\):\s*(?:pass|return\s+(?:None|True|False|0|1|['\"]['\"]))(?:\s*#.*)?\s*$", re.MULTILINE)),
    ]
    
    findings = []
    total_files = 0
    total_lines = 0
    for py_file in src_dir.rglob("*.py"):
        total_files += 1
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        total_lines += len(lines)
        for name, pat in suspicious_patterns:
            for m in pat.finditer(content):
                lineno = content[:m.start()].count("\n") + 1
                line = lines[lineno - 1]
                findings.append((py_file.as_posix(), lineno, name, line.strip()))
                
    print(f"Scanned {total_files} files ({total_lines} lines) in src/")
    print(f"Total suspicious pattern matches: {len(findings)}")
    for f in findings:
        print(f"  {f[0]}:{f[1]} [{f[2]}] -> {f[3]}")

if __name__ == "__main__":
    audit_sources()
