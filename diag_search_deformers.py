import os
import re

for root, dirs, files in os.walk("d:/VitubModel"):
    if ".git" in root or "__pycache__" in root or ".pytest_cache" in root or "output" in root:
        continue
    for f in files:
        if f.endswith(".py"):
            path = os.path.join(root, f)
            with open(path, "r", encoding="utf-8", errors="ignore") as fp:
                for idx, line in enumerate(fp):
                    if re.search(r"deformer", line, re.I):
                        print(f"{path}:{idx+1}: {line.strip()[:100]}")
