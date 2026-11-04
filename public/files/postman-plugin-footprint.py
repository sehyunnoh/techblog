"""Measure what the Postman agent plugin puts in front of a coding agent.

Reads files only. It never runs anything from the plugin repository.

Usage (from a clone checked out or exported at the commit you want to measure):
    python -I postman-plugin-footprint.py <path-to-plugin-repo-root>

Reports:
  1. size of the session-start context (hooks/session-start-context.md)
  2. size of each skill's frontmatter description (what an agent lists at startup)
  3. total SKILL.md bytes (what an agent loads when a skill is invoked)
  4. whether the hook scripts contain any obvious network call
"""
import glob
import os
import re
import sys

root = sys.argv[1]


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


ctx = read(os.path.join(root, "hooks", "session-start-context.md"))
print(f"session-start-context.md: {len(ctx.encode('utf-8'))} bytes, {len(ctx.split())} words, {ctx.count(chr(10))} lines")

rows = []
for p in sorted(glob.glob(os.path.join(root, "skills", "*", "SKILL.md"))):
    t = read(p)
    fm = re.match(r"---\n(.*?)\n---", t, re.S)
    desc = ""
    if fm:
        m = re.search(r"^description:\s*(.*?)(?=^\w[\w-]*:|\Z)", fm.group(1), re.S | re.M)
        if m:
            desc = m.group(1).strip().strip("\"'")
    rows.append((os.path.basename(os.path.dirname(p)), len(desc), len(t.encode("utf-8"))))

print(f"\n{'skill':28} {'description':>12} {'SKILL.md':>10}")
for name, d, s in rows:
    print(f"{name:28} {d:>12} {s:>10}")
print(f"{'TOTAL (' + str(len(rows)) + ' skills)':28} {sum(r[1] for r in rows):>12} {sum(r[2] for r in rows):>10}")

net = re.compile(r"curl|wget|https?://|/dev/tcp|fetch", re.I)
print("\nnetwork-looking text in hook scripts:")
for name in ("session-start", "session-start.cmd"):
    hits = [l for l in read(os.path.join(root, "hooks", name)).splitlines() if net.search(l)]
    print(f"  {name}: {len(hits)} matching lines")
