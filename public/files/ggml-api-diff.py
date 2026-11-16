#!/usr/bin/env python3
"""Count public API changes in ggml's include/ headers between release tags.

Usage: python ggml-api-diff.py <bare-or-normal-git-repo> [tag ...]
With no tags it walks every v* tag in the repo, oldest release first, and
compares each tag with the one before it. With two or more tags it compares
them in the order given.

Needs only git and the Python standard library. Reads headers with
`git show <tag>:include/<file>`, so the repo can be a blobless clone.
"""
import re
import subprocess
import sys


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def version_key(tag):
    return tuple(int(x) for x in re.findall(r"\d+", tag))


def headers(repo, tag):
    names = git(repo, "ls-tree", "--name-only", tag, "include/").split()
    return {n: git(repo, "show", f"{tag}:{n}") for n in names if n.endswith(".h")}


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", "", text)


FUNC = re.compile(
    r"(?:GGML_DEPRECATED\s*\(\s*)?"            # optional deprecation wrapper
    r"(GGML_API|GGML_BACKEND_API)\s+"          # export macro
    r"([^;{}()]*?)\b([A-Za-z_]\w*)\s*"         # return type + name
    r"\(([^;{}]*?)\)\s*(?=[;,{])",             # parameter list
    re.S)


def parse(files):
    funcs, deprecated, enums, macros, types = {}, set(), {}, set(), set()
    for raw in files.values():
        text = strip_comments(raw)
        for m in FUNC.finditer(text):
            name = m.group(3)
            sig = re.sub(r"\s+", "", m.group(2) + "(" + m.group(4) + ")")
            funcs[name] = sig
            if "GGML_DEPRECATED" in text[max(0, m.start() - 20):m.end() + 1]:
                deprecated.add(name)
        # enums: auto-increment values so a renumbering shows up
        for em in re.finditer(r"enum\s+(\w+)\s*\{(.*?)\}", text, re.S):
            ename, body = em.group(1), em.group(2)
            val = -1
            for item in body.split(","):
                item = item.strip()
                if not item:
                    continue
                nm = re.match(r"(\w+)\s*(?:=\s*([^,]+))?$", item.replace("\n", " "))
                if not nm:
                    continue
                cname, expr = nm.group(1), nm.group(2)
                if expr and re.fullmatch(r"\s*(0x[0-9a-fA-F]+|\d+)\s*", expr):
                    val = int(expr, 0)
                else:
                    val += 1
                enums.setdefault(ename, {})[cname] = val
        for dm in re.finditer(r"^\s*#\s*define\s+(\w+)", text, re.M):
            macros.add(dm.group(1))
        for tm in re.finditer(r"typedef\s+[^;{}]*?\b(\w+)\s*;", text):
            types.add(tm.group(1))
        for sm in re.finditer(r"^\s*struct\s+(\w+)\s*\{", text, re.M):
            types.add("struct " + sm.group(1))
    return dict(funcs=funcs, deprecated=deprecated, enums=enums,
                macros=macros, types=types)


def compare(a, b):
    fa, fb = a["funcs"], b["funcs"]
    out = dict(
        added=sorted(set(fb) - set(fa)),
        removed=sorted(set(fa) - set(fb)),
        changed=sorted(n for n in set(fa) & set(fb) if fa[n] != fb[n]),
        newly_deprecated=sorted(b["deprecated"] - a["deprecated"]),
        macros_added=sorted(b["macros"] - a["macros"]),
        macros_removed=sorted(a["macros"] - b["macros"]),
        types_added=sorted(b["types"] - a["types"]),
        types_removed=sorted(a["types"] - b["types"]),
    )
    ea_added, ea_removed, renumbered = [], [], []
    for en in sorted(set(a["enums"]) | set(b["enums"])):
        x, y = a["enums"].get(en, {}), b["enums"].get(en, {})
        ea_added += [f"{en}.{k}" for k in y if k not in x]
        ea_removed += [f"{en}.{k}" for k in x if k not in y]
        renumbered += [f"{en}.{k} {x[k]}->{y[k]}" for k in x if k in y and x[k] != y[k]]
    out.update(enum_added=ea_added, enum_removed=ea_removed, enum_renumbered=renumbered)
    return out


def tenure(repo_tags, parsed, last_prev, last):
    """For every function removed between two tags: first tag it appears in
    and the first tag where it carried GGML_DEPRECATED (None = removed
    without ever being marked deprecated)."""
    gone = sorted(set(parsed[last_prev]["funcs"]) - set(parsed[last]["funcs"]))
    rows = []
    for f in gone:
        first = next(t for t in repo_tags if f in parsed[t]["funcs"])
        dep = next((t for t in repo_tags if f in parsed[t]["deprecated"]), None)
        rows.append((f, first, dep))
    return rows


def main():
    repo = sys.argv[1]
    tags = sys.argv[2:]
    if not tags:
        tags = sorted((t for t in git(repo, "tag", "-l", "v*").split()), key=version_key)
    parsed = {}
    for t in tags:
        parsed[t] = parse(headers(repo, t))
    print(f"{'tag':9} {'funcs':>5} {'depr':>4} | {'+fn':>4} {'-fn':>4} {'~sig':>4} "
          f"{'+enum':>5} {'-enum':>5} {'renum':>5} {'-macro':>6} {'-type':>5}")
    rows = []
    for prev, cur in zip(tags, tags[1:]):
        d = compare(parsed[prev], parsed[cur])
        rows.append((cur, d))
        print(f"{cur:9} {len(parsed[cur]['funcs']):5} {len(parsed[cur]['deprecated']):4} | "
              f"{len(d['added']):4} {len(d['removed']):4} {len(d['changed']):4} "
              f"{len(d['enum_added']):5} {len(d['enum_removed']):5} {len(d['enum_renumbered']):5} "
              f"{len(d['macros_removed']):6} {len(d['types_removed']):5}")
    if len(tags) >= 2:
        print()
        last_prev, last = tags[-2], tags[-1]
        d = rows[-1][1]
        print(f"=== {last_prev} -> {last} detail ===")
        for k, v in d.items():
            if k == "enum_renumbered":
                continue
            print(f"{k} ({len(v)}):")
            for item in v:
                print("   ", item)
        by_enum = {}
        for r in d["enum_renumbered"]:
            by_enum[r.split(".")[0]] = by_enum.get(r.split(".")[0], 0) + 1
        print("enum_renumbered by enum:", by_enum)
        for en in by_enum:
            old, new = parsed[last_prev]["enums"][en], parsed[last]["enums"][en]
            same = [k for k in old if k in new and old[k] == new[k]]
            print(f"  {en}: {len(old)} constants before, {len(new)} after, "
                  f"{len(same)} kept the same value: {same}")
        print("removed functions (first tag seen, first tag marked GGML_DEPRECATED):")
        for f, first, dep in tenure(tags, parsed, last_prev, last):
            print(f"    {f:32} {first:9} {dep}")


if __name__ == "__main__":
    main()
