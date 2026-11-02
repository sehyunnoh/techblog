#!/usr/bin/env python3
"""Count back-branch commits in PostgreSQL's April 8 - September 25 window.

Usage:
    git clone --bare --filter=blob:none https://github.com/postgres/postgres.git pg.git
    python pg-backpatch-count.py pg.git

Only reads commit metadata (no file contents), so the blobless clone is enough.
Standard library only. For each year it looks at the stable branch of the release
that was current at the time (REL_18_STABLE in 2026, REL_17_STABLE in 2025, ...),
which branched a year earlier, so every commit in the window is a back-patch
or a branch-only change.
"""
import re
import subprocess
import sys

REPO = sys.argv[1] if len(sys.argv) > 1 else "pg.git"
# year -> stable branch that was the newest released one during that window
BRANCH = {2020: "REL_12_STABLE", 2021: "REL_13_STABLE", 2022: "REL_14_STABLE",
          2023: "REL_15_STABLE", 2024: "REL_16_STABLE", 2025: "REL_17_STABLE",
          2026: "REL_18_STABLE"}

# Credit lines that name an AI tool or an AI security product. Matched against the
# commit message only. The list comes from reading the 2026 messages, so it is
# deliberately tied to what appears there, not a general detector. Word boundaries
# matter: a bare "codex" also matches the function name DecodeXLogRecord.
AI_RE = re.compile(r"xint code|\bclaude\b|\bcodex\b|\bopenai\b|\banthropic\b|\bchatgpt\b|"
                   r"\bcopilot\b|\bgemini\b|antaisecurity|xlabai|\bLLM\b|AI-assisted", re.I)
CVE_RE = re.compile(r"^Security: *CVE", re.I | re.M)
CVE_ID = re.compile(r"CVE-\d{4}-\d+")
REPORTED = re.compile(r"^Reported-by:", re.I | re.M)


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], check=True, capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def commits(ref, since, until):
    out = git("log", ref, f"--since={since}", f"--until={until}", "--format=%x01%H%x02%B")
    for chunk in out.split("\x01")[1:]:
        h, _, body = chunk.partition("\x02")
        yield h.strip(), body


print(f"{'year':<5}{'branch':<15}{'total':>6}{'CVE-tagged':>11}{'AI-credit':>10}"
      f"{'AI,no CVE':>10}{'neither':>8}{'Reported-by':>12}{'distinct CVEs':>14}")
for year, br in BRANCH.items():
    total = cve = ai = ai_only = neither = rep = 0
    ids = set()
    for _, body in commits(br, f"{year}-04-08", f"{year}-09-26"):
        total += 1
        is_cve = bool(CVE_RE.search(body))
        is_ai = bool(AI_RE.search(body))
        cve += is_cve
        ai += is_ai
        ai_only += is_ai and not is_cve
        neither += not is_cve and not is_ai
        rep += bool(REPORTED.search(body))
        ids.update(CVE_ID.findall(body))
    print(f"{year:<5}{br:<15}{total:>6}{cve:>11}{ai:>10}{ai_only:>10}{neither:>8}{rep:>12}{len(ids):>14}")
