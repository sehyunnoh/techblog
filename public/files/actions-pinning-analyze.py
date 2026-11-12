#!/usr/bin/env python3
"""Classify `uses:` references in collected GitHub Actions workflows.

Usage: actions-pinning-analyze.py DATADIR [--transitive]
DATADIR comes from actions-pinning-collect.py (repos.json + workflows/<owner>__<repo>/*.yml).
Standard library only. --transitive fetches action.yml for the most-used actions
from raw.githubusercontent.com and checks what composite actions reference internally.
"""
import json, os, re, sys, urllib.request, collections
from concurrent.futures import ThreadPoolExecutor

data = sys.argv[1]
repos = json.load(open(data + "/repos.json"))["repos"]
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(.+?)\s*$")
SHA = re.compile(r"^[0-9a-f]{40}$")
SEMVER_FULL = re.compile(r"^v?\d+\.\d+\.\d+([-+].*)?$")
SEMVER_FLOAT = re.compile(r"^v?\d+(\.\d+)?$")


def clean(v):
    v = v.split(" #")[0].strip().strip("'\"")
    return v


def classify(ref):
    """Return (kind, ref) where kind is local/docker/sha/semver/float/branch."""
    if ref.startswith("./"):
        return "local", ""
    if ref.startswith("docker://"):
        return "docker", ""
    if "@" not in ref:
        return "other", ""
    r = ref.rsplit("@", 1)[1]
    if SHA.match(r):
        return "sha", r
    if SEMVER_FULL.match(r):
        return "semver", r
    if SEMVER_FLOAT.match(r):
        return "float", r
    return "branch", r


def first_party(ref):
    return ref.split("/", 1)[0].lower() in ("actions", "github")


uses = []  # (repo, file, ref, kind, is_reusable_workflow)
for r in repos:
    d = f"{data}/workflows/{r['full'].replace('/', '__')}"
    if not os.path.isdir(d):
        continue
    for fn in sorted(os.listdir(d)):
        if fn == "actions.lock":
            continue
        for line in open(f"{d}/{fn}", encoding="utf-8", errors="replace"):
            if line.lstrip().startswith("#"):
                continue
            m = USES.match(line)
            if not m:
                continue
            ref = clean(m.group(1))
            kind, _ = classify(ref)
            uses.append((r["full"], fn, ref, kind, ".github/workflows/" in ref))

with_wf = [r for r in repos if r.get("workflows")]
print(f"repos searched {len(repos)}, with workflow files {len(with_wf)}, "
      f"with actions.lock {sum(1 for r in repos if r.get('lockfile'))}, truncated trees {sum(1 for r in repos if r.get('truncated'))}")
print(f"uses lines {len(uses)}")

ext = [u for u in uses if u[3] not in ("local", "docker", "other")]
print("\n== all external uses by ref kind ==")
c = collections.Counter(u[3] for u in ext)
for k, v in c.most_common():
    print(f"{k:8} {v:6} {100*v/len(ext):5.1f}%")
print("\n== first-party (actions/*, github/*) vs third-party ==")
for label, sel in (("first", [u for u in ext if first_party(u[2])]), ("third", [u for u in ext if not first_party(u[2])])):
    c = collections.Counter(u[3] for u in sel)
    print(label, len(sel), {k: f"{100*v/len(sel):.1f}%" for k, v in c.most_common()})

print("\n== reusable workflow calls ==")
rw = [u for u in ext if u[4]]
print(len(rw), dict(collections.Counter(u[3] for u in rw)))

print("\n== per repo: how many repos use external actions, and pinning posture ==")
by = collections.defaultdict(list)
for u in ext:
    by[u[0]].append(u)
post = collections.Counter()
third_post = collections.Counter()
for repo, us in by.items():
    kinds = {u[3] for u in us}
    post["all sha" if kinds == {"sha"} else "no sha" if "sha" not in kinds else "mixed"] += 1
    t = [u for u in us if not first_party(u[2])]
    if t:
        k = {u[3] for u in t}
        third_post["all sha" if k == {"sha"} else "no sha" if "sha" not in k else "mixed"] += 1
print("repos with external uses", len(by), dict(post))
print("repos with third-party uses", sum(third_post.values()), dict(third_post))
print("repos with a branch ref (@main/@master etc):", sum(1 for us in by.values() if any(u[3] == "branch" for u in us)))

print("\n== lockfile repos ==")
for r in repos:
    if r.get("lockfile"):
        print(r["full"], r["stars"], "workflow files", len(r["workflows"]))

print("\n== top 25 distinct actions (ignoring ref) ==")
name = lambda ref: ref.rsplit("@", 1)[0]
cnt = collections.Counter(name(u[2]) for u in ext)
repo_cnt = collections.defaultdict(set)
for u in ext:
    repo_cnt[name(u[2])].add(u[0])
for k, v in cnt.most_common(25):
    kinds = collections.Counter(u[3] for u in ext if name(u[2]) == k)
    print(f"{k:50} {v:5} lines {len(repo_cnt[k]):4} repos  {dict(kinds)}")

if "--transitive" in sys.argv:
    print("\n== transitive: do the 150 most-used actions reference other actions with mutable refs? ==")
    top = [k for k, _ in cnt.most_common(150) if not k.startswith(("./", "docker://")) and ".github/workflows/" not in k]
    # pick the most common ref per action
    refs = {}
    for k in top:
        rs = collections.Counter(u[2].rsplit("@", 1)[1] for u in ext if name(u[2]) == k)
        refs[k] = rs.most_common(1)[0][0]

    def fetch(k):
        owner_repo = "/".join(k.split("/")[:2])
        sub = "/".join(k.split("/")[2:])
        for fn in ("action.yml", "action.yaml"):
            p = f"{sub}/{fn}" if sub else fn
            try:
                body = urllib.request.urlopen(
                    f"https://raw.githubusercontent.com/{owner_repo}/{refs[k]}/{p}", timeout=30).read().decode("utf-8", "replace")
                return k, body
            except Exception:
                continue
        return k, None

    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(fetch, top))
    n_ok = n_comp = n_nested = 0
    kinds = collections.Counter()
    runtimes = collections.Counter()
    nested_list = []
    for k, body in res:
        if body is None:
            continue
        n_ok += 1
        m = re.search(r"^\s*using:\s*['\"]?([\w.-]+)", body, re.M)
        runtimes[m.group(1) if m else "?"] += 1
        if m and m.group(1) == "composite":
            n_comp += 1
            inner = [clean(x.group(1)) for x in (USES.match(l) for l in body.splitlines()) if x]
            inner = [i for i in inner if not i.startswith("./") and "@" in i]
            if inner:
                n_nested += 1
                ks = [classify(i)[0] for i in inner]
                kinds.update(ks)
                nested_list.append((k, refs[k], [(i, classify(i)[0]) for i in inner]))
    print(f"fetched {n_ok}/{len(top)}; runtimes {dict(runtimes)}")
    print(f"composite {n_comp}; composite with nested external uses {n_nested}; nested ref kinds {dict(kinds)}")
    for k, ref, ins in nested_list:
        print(" ", k, "@", ref[:12], [f"{i.split('@')[0]}:{kd}" for i, kd in ins])
