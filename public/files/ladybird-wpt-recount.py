"""Recount Ladybird vs Safari Technology Preview (and Chrome/Firefox) on WPT.

Uses only public wpt.fyi data: the runs API and the per-run summary_v2 files.
Python 3 standard library only.

    python ladybird-wpt-recount.py CACHE_DIR [SHA]

Each summary file maps a test path to {"s": status, "c": [passed, total]}.
"c" counts subtests. Tests with no subtests (reftests, crashtests and so on)
have c == [0, 0]; here they count as one subtest that passes if s == "P".
Two scores are reported over the tests every compared run has:
  raw  = total passing subtests (the number the Ladybird newsletter quotes)
  norm = each test scored 0..1 (passed/total), then summed, so a test with
         5,000 subtests weighs the same as a test with one
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from collections import defaultdict

API = "https://wpt.fyi/api/runs"
EXP = ["chrome[experimental]", "firefox[experimental]", "safari[experimental]", "ladybird"]
HISTORY = ["2026-06-01", "2026-07-01", "2026-08-01", "2026-09-01", "2026-10-01",
           "2026-10-15", "2026-10-22", "2026-10-25", "2026-10-27", "2026-10-31",
           "2026-11-10", "2026-11-24"]


def get_json(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read())


def aligned(products, sha=None, to=None):
    q = {"aligned": "", "max-count": "1", "products": ",".join(products), "labels": "master"}
    if sha:
        q["sha"] = sha
    if to:
        q["to"] = to
    return get_json(API + "?" + urllib.parse.urlencode(q))


def summary(run, cache):
    path = os.path.join(cache, f"{run['id']}.json")
    if not os.path.exists(path):
        with urllib.request.urlopen(run["results_url"], timeout=300) as r:
            data = r.read()
        with open(path, "wb") as f:
            f.write(data)
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] == b"\x1f\x8b":
        import gzip
        data = gzip.decompress(data)
    return json.loads(data)


def pts(v):
    p, t = v["c"]
    if t > 0:
        return p, t
    return (1 if v["s"] == "P" else 0), 1


def scores(d, tests, skip_top=()):
    raw = tot = 0
    norm = 0.0
    n = 0
    for k in tests:
        if k.split("/")[1] in skip_top:
            continue
        p, t = pts(d[k])
        raw += p
        tot += t
        norm += p / t
        n += 1
    return raw, tot, norm, n


def main():
    cache = sys.argv[1]
    sha = sys.argv[2] if len(sys.argv) > 2 else None
    os.makedirs(cache, exist_ok=True)

    runs = aligned(EXP, sha=sha)
    print("== Aligned experimental runs ==")
    for r in runs:
        print(f"  {r['browser_name']:9} {r['browser_version']:22} id={r['id']} wpt={r['revision']} {r['created_at'][:16]}")
    D = {r["browser_name"]: summary(r, cache) for r in runs}
    common = set.intersection(*(set(d) for d in D.values()))
    print(f"  tests in every run: {len(common)}")

    print("\n== Totals over common tests ==")
    print(f"  {'browser':9} {'raw pass':>10} {'of':>10} {'norm':>10} {'norm %':>7}  | without WebCryptoAPI: raw, norm")
    for b, d in D.items():
        raw, tot, norm, n = scores(d, common)
        raw2, _, norm2, _ = scores(d, common, skip_top=("WebCryptoAPI",))
        print(f"  {b:9} {raw:10,} {tot:10,} {norm:10,.1f} {100 * norm / n:6.2f}%  | {raw2:,}  {norm2:,.1f}")

    L, S = D["ladybird"], D["safari"]
    by_top = defaultdict(lambda: {"raw": 0, "norm": 0.0, "sub": 0, "tests": 0})
    for k in common:
        top = k.split("/")[1]
        lp, lt = pts(L[k])
        sp, st = pts(S[k])
        e = by_top[top]
        e["raw"] += lp - sp
        e["norm"] += lp / lt - sp / st
        e["sub"] += max(lt, st)
        e["tests"] += 1
    print("\n== Ladybird minus Safari TP, by top-level directory ==")
    print("  (raw = passing subtests; norm = per-test scores; sub = subtests; tests = test files)")
    rows = sorted(by_top.items(), key=lambda x: -x[1]["raw"])
    for top, e in rows[:15] + [("...", None)] + rows[-15:]:
        if e is None:
            print("  ...")
            continue
        print(f"  {top:28} raw {e['raw']:+8,} norm {e['norm']:+9.1f} sub {e['sub']:8,} tests {e['tests']:6,}")
    lead_raw = sum(e["raw"] for e in by_top.values())
    lead_norm = sum(e["norm"] for e in by_top.values())
    print(f"  total: raw {lead_raw:+,}  norm {lead_norm:+,.1f}")
    print(f"  directories Ladybird leads (norm > 0): {sum(1 for e in by_top.values() if e['norm'] > 0.5)}"
          f", trails (norm < 0): {sum(1 for e in by_top.values() if e['norm'] < -0.5)}, of {len(by_top)}")

    css = [k for k in common if k.startswith("/css/")]
    css0 = [k for k in css if L[k]["c"][1] == 0 and S[k]["c"][1] == 0]
    d0 = sum(pts(L[k])[0] - pts(S[k])[0] for k in css0)
    print(f"  /css: {len(css):,} files, {len(css0):,} with no subtests (reftests etc.);"
          f" those account for norm {d0:+,} of the /css difference")

    print("\n== Where the subtests are (share of all subtests vs share of test files) ==")
    sub = defaultdict(int)
    files = defaultdict(int)
    for k in common:
        top = k.split("/")[1]
        sub[top] += max(pts(L[k])[1], pts(S[k])[1])
        files[top] += 1
    T, F = sum(sub.values()), sum(files.values())
    for top, v in sorted(sub.items(), key=lambda x: -x[1])[:8]:
        print(f"  {top:14} {v:9,} subtests {100 * v / T:5.1f}%   {files[top]:6,} files {100 * files[top] / F:5.1f}%")
    for label, skip in (("without third_party (test262)", ("third_party",)),
                        ("without third_party and encoding", ("third_party", "encoding"))):
        lr, _, ln, _ = scores(L, common, skip)
        sr, _, sn, _ = scores(S, common, skip)
        print(f"  {label}: raw diff {lr - sr:+,}  norm diff {ln - sn:+,.1f}")

    print("\n== Largest test files by subtest count (Ladybird run) ==")
    big = sorted(common, key=lambda k: -L[k]["c"][1])[:10]
    for k in big:
        print(f"  {L[k]['c'][1]:7,} subtests  ladybird {L[k]['c'][0]:7,}  safari {S[k]['c'][0]:7,}  {k}")
    wc = [k for k in common if k.startswith("/WebCryptoAPI/")]
    wsub = sum(pts(L[k])[1] for k in wc)
    alls = sum(max(pts(L[k])[1], pts(S[k])[1]) for k in common)
    print(f"  WebCryptoAPI: {len(wc)} test files ({100 * len(wc) / len(common):.2f}% of files),"
          f" {wsub:,} subtests ({100 * wsub / alls:.2f}% of subtests)")
    for name, d in (("ladybird", L), ("safari", S)):
        p = sum(pts(d[k])[0] for k in wc)
        print(f"    {name}: {p:,} passing WebCryptoAPI subtests")

    print("\n== History: Ladybird vs Safari TP, aligned runs ==")
    print(f"  {'on or before':12} {'wpt sha':10} {'LB raw':>10} {'STP raw':>10} {'raw diff':>9} {'LB norm':>9} {'STP norm':>9} {'norm diff':>9}  raw diff w/o WebCrypto")
    for day in HISTORY:
        rs = aligned(["safari[experimental]", "ladybird"], to=day + "T23:59:59Z")
        if len(rs) < 2:
            print(f"  {day}: no aligned run")
            continue
        h = {r["browser_name"]: summary(r, cache) for r in rs}
        ct = set(h["ladybird"]) & set(h["safari"])
        lr, _, ln, _ = scores(h["ladybird"], ct)
        sr, _, sn, _ = scores(h["safari"], ct)
        lr2, _, _, _ = scores(h["ladybird"], ct, ("WebCryptoAPI",))
        sr2, _, _, _ = scores(h["safari"], ct, ("WebCryptoAPI",))
        print(f"  {day:12} {rs[0]['revision']:10} {lr:10,} {sr:10,} {lr - sr:+9,} {ln:9,.0f} {sn:9,.0f} {ln - sn:+9,.0f}  {lr2 - sr2:+,}")


if __name__ == "__main__":
    main()
