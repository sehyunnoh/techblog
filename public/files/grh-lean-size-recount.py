#!/usr/bin/env python3
"""Recount the size of the Lean proofs of the Generalized Riemann Hypothesis.

Reads GitHub tarballs without extracting them (stdlib only) and prints, per
snapshot: Lean files, bytes, total lines, non-blank lines, code lines (lines
with any character outside a comment), declarations by keyword, and a few
trust-relevant keywords (sorry, axiom, native_decide, ...).

Usage:
  python -I grh-lean-size-recount.py NAME=PATH.tar.gz[:SUBDIR] ...

Snapshots used in the post (download with curl -L):
  original  codeload.github.com/leanprover-community/riemann-hypothesis/tar.gz/40e56bab026552e089d7afcfeff08d2defb9c005
  alpoge    codeload.github.com/leanprover-community/riemann-hypothesis/tar.gz/0ca81d6329f57a9987329221c974350bdc370e4d
  main      codeload.github.com/leanprover-community/riemann-hypothesis/tar.gz/7c4ccbd64d02774b0a5b40a5f923f5b7a18e8abc
  grh-lean  codeload.github.com/lsernau/grh-lean/tar.gz/72fead102f663d5c7a407964a13dc0cf9d977207
            (run twice, with SUBDIR grh and grh-compact)
  mathlib   codeload.github.com/leanprover-community/mathlib4/tar.gz/56a005855ea17e0b0958f73ec801ae140b0a1679
            (SUBDIR Mathlib)

The published output came from:
  python -I -u grh-lean-size-recount.py original=original.tar.gz \\
    alpoge=alpoge.tar.gz main=main.tar.gz readable=grh-lean.tar.gz:grh \\
    compact=grh-lean.tar.gz:grh-compact mathlib=mathlib.tar.gz:Mathlib

strip_comments_slow is the original character-by-character version, kept
because the fast one was checked against it (identical code lines, modulo
whitespace, on all 2,406 files of main and grh-lean).
"""
import hashlib
import re
import sys
import tarfile
from collections import Counter

DECL = re.compile(
    r"^\s*(?:@\[[^\]]*\]\s*)*"
    r"(?:(?:private|protected|noncomputable|partial|unsafe|nonrec|scoped)\s+)*"
    r"(theorem|lemma|def|abbrev|instance|structure|class|inductive|axiom|opaque|example)\b"
)
WORDS = ["sorry", "admit", "native_decide", "implemented_by", "extern", "unsafe"]
WORD_RE = {w: re.compile(r"(?<![\w.])" + w + r"(?![\w'])") for w in WORDS}


TOKEN = re.compile(r"""/-|-/|--|'"'|\\.|"|\n""", re.S)


def strip_comments(text):
    """Return text with comments replaced by spaces (newlines kept).

    Same rules as strip_comments_slow, but jumps between tokens with a
    regex instead of looping over every character.
    """
    out = []
    n = len(text)
    keep = 0  # start of the code segment not yet copied to out
    i = 0
    depth = 0
    in_str = False
    while True:
        m = TOKEN.search(text, i)
        if not m:
            break
        t, s, i = m.group(), m.start(), m.end()
        if depth:
            if t == "\n":
                out.append("\n")
            elif t == "/-":
                depth += 1
            elif t == "-/":
                depth -= 1
                if depth == 0:
                    keep = i
            continue
        if in_str:
            if t == '"':
                in_str = False
            continue  # escapes and newlines inside strings stay as text
        if t == "/-":
            out.append(text[keep:s])
            depth = 1
        elif t == "--":
            out.append(text[keep:s])
            j = text.find("\n", s)
            i = keep = n if j < 0 else j
        elif t == '"':
            in_str = True
        # a '"' char literal or an escape outside a string: no change
    if not depth:
        out.append(text[keep:])
    return "".join(out)


def strip_comments_slow(text):
    """Return text with comments replaced by spaces (newlines kept).

    Handles nested /- -/ block comments, -- line comments, and string
    literals (so "--" inside a string is not a comment). Char literals
    like '"' are handled for the common cases.
    """
    out = []
    i, n, depth = 0, len(text), 0
    in_str = False
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if depth:
            if c == "/" and nxt == "-":
                depth += 1
                out.append("  ")
                i += 2
            elif c == "-" and nxt == "/":
                depth -= 1
                out.append("  ")
                i += 2
            else:
                out.append("\n" if c == "\n" else " ")
                i += 1
        elif in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(nxt)
                i += 2
                continue
            if c == '"':
                in_str = False
            i += 1
        else:
            if c == "/" and nxt == "-":
                depth = 1
                out.append("  ")
                i += 2
            elif c == "-" and nxt == "-":
                j = text.find("\n", i)
                j = n if j < 0 else j
                out.append(" " * (j - i))
                i = j
            elif c == "'" and i + 2 < n and text[i + 2] == "'" :
                out.append(text[i:i + 3])
                i += 3
            elif c == '"':
                in_str = True
                out.append(c)
                i += 1
            else:
                out.append(c)
                i += 1
    return "".join(out)


def count(path, subdir=None):
    st = Counter()
    decls = Counter()
    words = Counter()
    per_dir = Counter()
    hashes = Counter()
    hash_bytes = {}
    longest = Counter()
    with tarfile.open(path, "r:gz") as tf:
        for m in tf:
            if not m.isfile() or not m.name.endswith(".lean"):
                continue
            parts = m.name.split("/")[1:]  # drop the tarball's top folder
            if subdir and (not parts or parts[0] != subdir):
                continue
            data = tf.extractfile(m).read()
            text = data.decode("utf-8", errors="replace")
            lines = text.split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            code = strip_comments(text).split("\n")[: len(lines)]
            n_code = sum(1 for l in code if l.strip())
            st["files"] += 1
            st["bytes"] += len(data)
            st["lines"] += len(lines)
            st["nonblank"] += sum(1 for l in lines if l.strip())
            st["code"] += n_code
            st["code_bytes"] += sum(len(l.strip()) for l in code)
            for l in code:
                mm = DECL.match(l)
                if mm:
                    decls[mm.group(1)] += 1
                for w, rx in WORD_RE.items():
                    words[w] += len(rx.findall(l))
                L = len(l.rstrip())
                if L > 200:
                    longest[">200"] += 1
            key = "/".join(parts[: 3 if not subdir else 2][:-1]) or "."
            per_dir[key] += n_code
            h = hashlib.sha1(data).hexdigest()
            hashes[h] += 1
            hash_bytes[h] = len(data)
    dup_files = sum(c - 1 for c in hashes.values() if c > 1)
    dup_bytes = sum((c - 1) * hash_bytes[h] for h, c in hashes.items() if c > 1)
    return st, decls, words, per_dir, dup_files, dup_bytes, longest


def main():
    rows = []
    for arg in sys.argv[1:]:
        name, spec = arg.split("=", 1)
        path, _, sub = spec.partition(":")
        st, decls, words, per_dir, dupf, dupb, longest = count(path, sub or None)
        rows.append((name, st, decls))
        print(f"== {name} ({spec})")
        for k in ["files", "bytes", "lines", "nonblank", "code", "code_bytes"]:
            print(f"  {k:12s} {st[k]:>14,}")
        print(f"  bytes/code line {st['bytes'] / max(st['code'], 1):.1f}")
        print(f"  code lines >200 chars {longest['>200']:,}")
        print(f"  duplicate files {dupf:,} ({dupb:,} bytes)")
        print("  declarations " + ", ".join(f"{k} {v:,}" for k, v in decls.most_common()))
        print("  declarations total " + f"{sum(decls.values()):,}")
        print("  keywords " + ", ".join(f"{w} {words[w]:,}" for w in WORDS))
        print("  top folders by code lines:")
        for d, v in per_dir.most_common(8):
            print(f"    {v:>12,}  {d}")
    if rows:
        base = rows[0][1]
        print("== relative to", rows[0][0])
        for name, st, decls in rows:
            print(
                f"  {name:14s} code {st['code'] / base['code']:8.4%}  "
                f"bytes {st['bytes'] / base['bytes']:8.4%}  "
                f"decls {sum(decls.values()):>10,}"
            )


if __name__ == "__main__":
    main()
