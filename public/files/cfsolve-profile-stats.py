"""Static counts for a cfsolve checkout. Reads files only; runs nothing from the repo.

Usage: python -I cfsolve-profile-stats.py /path/to/cfsolve
"""
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
prof = root / "profiles" / "safari-26-ios"
a = json.loads((prof / "answers.json").read_text(encoding="utf-8"))
b = json.loads((prof / "challenge-page-answers.json").read_text(encoding="utf-8"))


def diffs(x, y, path=""):
    n = 0
    if type(x) is not type(y):
        return 1
    if isinstance(x, dict):
        for k in set(x) | set(y):
            n += 1 if (k not in x or k not in y) else diffs(x[k], y[k], f"{path}/{k}")
    elif isinstance(x, list):
        n += abs(len(x) - len(y)) + sum(diffs(u, v) for u, v in zip(x, y))
    elif x != y:
        n += 1
    return n


for name, j in (("answers.json", a), ("challenge-page-answers.json", b)):
    p = j["probes"]
    print(name, "probes", len(p), "fields", sum(len(v["fields"]) for v in p.values()),
          "late", sum("late" in v for v in p.values()),
          "duration_ms_sum", sum(v["duration"] for v in p.values()))
print("same reference id:", a["reference"] == b["reference"])
print("differing values between the two recordings:", diffs(a, b))

for d in ["stage2", "deobfuscate", "vm", "challenge", "capture", "session",
          "embedding_page", "http", "js"]:
    files = list((root / "src" / d).rglob("*.rs"))
    print(f"src/{d}: {len(files)} files, {sum(f.stat().st_size for f in files)} bytes")
allrs = list((root / "src").rglob("*.rs"))
print("src total:", len(allrs), "files,",
      sum(len(f.read_text(encoding="utf-8").splitlines()) for f in allrs), "lines")
