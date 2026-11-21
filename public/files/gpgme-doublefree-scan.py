#!/usr/bin/env python3
"""Scan every tag of gpg/gpgme for the stale-pointer realloc pattern behind
CVE-2026-129975 (T8557).

Usage:  python gpgme-doublefree-scan.py <path-to-gpgme-bare-clone> [out.csv]

Setup:  git clone --bare --filter=blob:none https://github.com/gpg/gpgme.git

For each tag we locate the gpg engine source (gpgme/rungpg.c, src/rungpg.c or
src/engine-gpg.c), extract read_status() and read_colon_line() (same names in
the old rungpg.c, where the argument type is GpgObject and the allocator is
sometimes xtryrealloc), and classify each:

  vulnerable : the function realloc()s a local buffer, and between that
               realloc and the line that stores the new pointer back into the
               gpg context there is at least one early `return` or `goto`.
  fixed      : the new pointer is stored into the context before any return
               that follows the realloc.
  no-realloc : the function never grows the buffer (pattern not present).
  missing    : function not found in the file.

Because a `free` of the stale context pointer happens when the context is
released, "vulnerable" means the *code shape* from the advisory is present.
It is not a proof of exploitability for any particular build.
"""
import csv
import re
import subprocess
import sys

REPO = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else None

CAND = re.compile(r"(^|/)(gpgme/rungpg\.c|src/rungpg\.c|src/engine-gpg\.c)$")


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True,
                          text=True, errors="replace").stdout


def sort_key(t):
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", t)]


def commit_date(t):
    return git("log", "-1", "--format=%ad", "--date=short", t + "^{commit}").strip()


def find_source(tag):
    names = [n for n in git("ls-tree", "-r", "--name-only", tag).splitlines()
             if CAND.search(n)]
    if not names:
        return None, None
    if len(names) > 1:
        # SVN-converted tags can hold a whole copy of the repo; prefer the
        # entry under tags/<this tag>/ and otherwise the shortest path.
        pref = [n for n in names if ("/" + tag.lower() + "/") in ("/" + n.lower())]
        names = pref or sorted(names, key=len)
    return names[0], git("show", f"{tag}:{names[0]}")


def extract(src, name):
    m = re.search(r"^%s\s*\(\s*(?:engine_gpg_t|GpgObject)\s+gpg\s*\)\s*\{" % name, src, re.M)
    if not m:
        return None
    i = src.index("{", m.start())
    depth, j = 0, i
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
        j += 1
    return None


def classify(body, field):
    if body is None:
        return "missing"
    r = re.search(r"buffer\s*=\s*(?:realloc|xtryrealloc)\s*\(", body)
    if not r:
        return "no-realloc"
    after = body[r.end():]
    store = re.search(r"gpg->%s\.buffer\s*=\s*buffer\s*;" % field, after)
    if not store:
        return "vulnerable"  # never stored back: even worse
    between = after[:store.start()]
    # The allocation-failure check right after realloc is not the bug: on
    # failure there is no new pointer to lose.  Drop it before looking for
    # other early exits.
    between = re.sub(r"if\s*\(\s*!\s*buffer\s*\)\s*(\{[^}]*\}|return[^;]*;)", "", between)
    return "vulnerable" if re.search(r"\b(return|goto)\b", between) else "fixed"


rows = []
for tag in sorted(git("tag").split(), key=sort_key):
    path, src = find_source(tag)
    if src is None:
        rows.append([tag, commit_date(tag), "", "nofile", "nofile"])
        continue
    st = classify(extract(src, "read_status"), "status")
    co = classify(extract(src, "read_colon_line"), "colon")
    rows.append([tag, commit_date(tag), path, st, co])

w = csv.writer(open(OUT, "w", newline="")) if OUT else None
if w:
    w.writerow(["tag", "date", "path", "read_status", "read_colon_line"])
    w.writerows(rows)

from collections import Counter
c = Counter((r[3], r[4]) for r in rows)
print("tags scanned:", len(rows))
for k, v in sorted(c.items()):
    print(f"  read_status={k[0]:<10} read_colon_line={k[1]:<10} {v}")
print()
print("first/last tag per class (by tag name order):")
for k in sorted(c):
    ts = [r[0] for r in rows if (r[3], r[4]) == k]
    print(f"  {k}: {ts[0]} .. {ts[-1]}")
