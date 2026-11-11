#!/usr/bin/env python3
"""Count Go standard-library and toolchain vulnerability entries over time.

Source: the official Go vulnerability database (https://vuln.go.dev). Standard library only.
Usage: python go-vuln-counts.py DATA_DIR
  DATA_DIR gets one JSON file per entry (downloaded on first run, reused after).
Unit of analysis: one database entry (GO-YYYY-NNNN), counted once at its `published` date,
so a fix backported to several release branches is still one entry.
"""
import collections, concurrent.futures as cf, json, os, re, sys, urllib.request

sys.stdout.reconfigure(encoding="utf-8")
BASE = "https://vuln.go.dev"
data_dir = sys.argv[1]
os.makedirs(data_dir, exist_ok=True)


def get(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


modules = json.loads(get(BASE + "/index/modules.json"))
ids = {}
for m in modules:
    if m["path"] in ("stdlib", "toolchain"):
        for v in m["vulns"]:
            ids.setdefault(v["id"], set()).add(m["path"])


def fetch(i):
    p = os.path.join(data_dir, i + ".json")
    if not os.path.exists(p):
        with open(p, "wb") as f:
            f.write(get(f"{BASE}/ID/{i}.json"))
    return i


with cf.ThreadPoolExecutor(8) as ex:
    list(ex.map(fetch, sorted(ids)))

entries = {i: json.load(open(os.path.join(data_dir, i + ".json"), encoding="utf-8")) for i in ids}
withdrawn = [i for i, e in entries.items() if e.get("withdrawn")]
live = {i: e for i, e in entries.items() if not e.get("withdrawn")}
print(f"index entries (stdlib or toolchain): {len(ids)}; in both modules: "
      f"{sum(1 for s in ids.values() if len(s) == 2)}; withdrawn: {len(withdrawn)}; counted: {len(live)}")

# published date vs the year in the ID: older vulns are sometimes added to the database late
late = [i for i, e in live.items() if int(i.split("-")[1]) < int(e["published"][:4])]
print(f"entries published in a later year than their ID year (retroactive adds): {len(late)}")

by_year = collections.Counter(e["published"][:4] for e in live.values())
print("\nentries by published year:")
for y in sorted(by_year):
    print(f"  {y}: {by_year[y]}")

by_half = collections.Counter(e["published"][:4] + ("H1" if int(e["published"][5:7]) <= 6 else "H2")
                              for e in live.values())
print("\nentries by half-year (2023 onward):")
for h in sorted(by_half):
    if h >= "2023":
        print(f"  {h}: {by_half[h]}")

by_month = collections.Counter(e["published"][:7] for e in live.values())
print("\nentries by month (2025-07 onward):")
for m in sorted(by_month):
    if m >= "2025-07":
        print(f"  {m}: {by_month[m]}")

# one entry per publication batch: what share of entries share a publish day with others
by_day = collections.Counter(e["published"][:10] for e in live.values())
print("\nlargest same-day batches:")
for d, n in by_day.most_common(8):
    print(f"  {d}: {n}")

# what do they touch
pk = collections.Counter()
for e in live.values():
    seen = set()
    for a in e["affected"]:
        for imp in a.get("ecosystem_specific", {}).get("imports", []):
            seen.add(imp["path"])
        if not a.get("ecosystem_specific", {}).get("imports"):
            seen.add("(" + a["package"]["name"] + ")")
    for s in seen:
        pk[s] += 1
print("\nmost affected packages (all years):")
for p, n in pk.most_common(12):
    print(f"  {p}: {n}")
recent = {i: e for i, e in live.items() if e["published"] >= "2026-01-01"}
pk2 = collections.Counter()
for e in recent.values():
    for a in e["affected"]:
        for imp in a.get("ecosystem_specific", {}).get("imports", []):
            pk2[imp["path"]] += 1
print("\nmost affected packages, entries published in 2026:")
for p, n in pk2.most_common(12):
    print(f"  {p}: {n}")

# credits
cred_by_year = collections.defaultdict(collections.Counter)
nocred = collections.Counter()
for e in live.values():
    y = e["published"][:4]
    cs = [c["name"] for c in e.get("credits", [])]
    if not cs:
        nocred[y] += 1
    for c in cs:
        cred_by_year[y][c] += 1
print("\nentries with no credit line, by year:", dict(sorted(nocred.items())))
for y in ("2025", "2026"):
    print(f"top credits {y}:", cred_by_year[y].most_common(10))

# any mention of an AI lab or tool in credits, summary, details or references
pat = re.compile(r"(?i:anthropic|claude|mythos|glasswing|openai|codex|big sleep|xbow|depthfirst|zeropath|aisle)|(?<![\w.])AI(?![\w.])|\bLLMs?\b")
hits = []
for i, e in live.items():
    blob = json.dumps({k: e.get(k) for k in ("credits", "summary", "details", "references")})
    m = pat.search(blob)
    if m:
        hits.append((i, e["published"][:10], m.group(0)))
print(f"\nentries whose credits/summary/details/references match an AI-related pattern: {len(hits)}")
for h in hits[:15]:
    print("  ", h)

# per patch release: entries whose newest fixed version is that release (2026 releases only)
rel = collections.Counter()
for i, e in live.items():
    fx = []
    for a in e["affected"]:
        for r in a.get("ranges", []):
            for ev in r["events"]:
                if "fixed" in ev:
                    fx.append(ev["fixed"])
    if fx:
        rel[max(fx, key=lambda v: [int(x) if x.isdigit() else 0 for x in re.split(r"[.\-]|rc", v) if x != ""])] += 1
print("\nentries by highest fixed version (2026-era versions):")
for v, n in sorted(rel.items(), key=lambda kv: kv[0]):
    if v.startswith(("1.26", "1.27", "1.25")):
        print(f"  {v}: {n}")

# who reports: distinct reporters and concentration, names normalised crudely
def norm(c):
    return re.split(r"\s*[\(\-]\s*|\s+of\s+|\s+from\s+", c)[0].strip().lower()
for y in ("2024", "2025", "2026"):
    per = collections.Counter()
    ents = [e for e in live.values() if e["published"][:4] == y]
    for e in ents:
        for n in {norm(c["name"]) for c in e.get("credits", [])}:
            per[n] += 1
    print(f"\n{y}: {len(ents)} entries, {len(per)} distinct credited names; top reporters by entries:",
          per.most_common(5))
# no-credit 2026 entries: what are they
print("\n2026 entries with no credit line:")
for i, e in sorted(live.items()):
    if e["published"][:4] == "2026" and not e.get("credits"):
        print("  ", i, e["published"][:10], e["summary"][:80])

# publication days and batch sizes per year, plus how much of 2026 is one cgo/linker-flag cluster
for y in ("2023", "2024", "2025", "2026"):
    days = collections.Counter(e["published"][:10] for e in live.values() if e["published"][:4] == y)
    sizes = sorted(days.values())
    med = sizes[len(sizes) // 2] if sizes else 0
    print(f"\n{y}: {sum(sizes)} entries on {len(days)} publication days, median batch {med}, max batch {max(sizes) if sizes else 0}")
cgo = [i for i, e in live.items() if e["published"][:10] == "2026-11-11"
       and re.search(r"cgo|linker|\.syso|pkg-config|gcc|clang|sysroot", e["summary"], re.I)]
print(f"\n2026-11-11 batch: {by_day['2026-11-11']} entries, of which {len(cgo)} are cgo/linker-flag issues:", sorted(cgo))
print("2026 entries touching cmd/go, cmd/cgo, cmd/compile or cmd/link:",
      sum(1 for e in recent.values()
          if any(imp["path"].startswith("cmd/")
                 for a in e["affected"] for imp in a.get("ecosystem_specific", {}).get("imports", []))))

# optional: cross-check against a CVE list (e.g. patrickmgarrity/Anthropic-Credited-CVEs cves.yaml)
if len(sys.argv) > 2:
    other = set(re.findall(r"CVE-\d{4}-\d+", open(sys.argv[2], encoding="utf-8").read()))
    go_cves = {a for e in live.values() for a in e.get("aliases", []) if a.startswith("CVE-")}
    print(f"\ncross-check: {len(other)} CVE ids in {os.path.basename(sys.argv[2])}, {len(go_cves)} Go CVE ids, "
          f"intersection {sorted(other & go_cves)}")
