#!/usr/bin/env python3
"""Summarise the CSV written by nginx-h2-survey.py.

Usage: python nginx-h2-analyze.py results.csv top1000.csv

Version rule used for "listed as affected" (from the Wiz Research write-up of
CVE-2026-123007, November 18, 2026): nginx OSS 1.9.5 through 1.31.8 is affected;
fixed in 1.30.7 (stable line) and 1.31.9 (mainline).
"""
import csv
import re
import sys
from collections import Counter


def pct(n, d):
    return f"{n} ({100 * n / d:.1f}%)" if d else f"{n} (n/a)"


def vt(s):
    return tuple(int(x) for x in s.split("."))


def listed_affected(v):
    v = vt(v)
    if v < (1, 9, 5):
        return False
    if (1, 30, 7) <= v < (1, 31, 0):
        return False
    if v >= (1, 31, 9):
        return False
    return True


rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
rank = {r[1]: int(r[0]) for r in csv.reader(open(sys.argv[2], encoding="utf-8"))}
n = len(rows)
answered = [r for r in rows if r["status"] or r["alpn"]]
print(f"domains: {n}; got an HTTP status or a TLS answer: {pct(len(answered), n)}")
print("status classes:", dict(Counter((r["status"][:1] + "xx") if r["status"] else "none" for r in rows).most_common()))
print("ALPN result:", dict(Counter(r["alpn"] or "no TLS answer" for r in rows).most_common()))
h2 = [r for r in rows if r["alpn"] == "h2"]
print(f"negotiate h2: {pct(len(h2), n)}; of those that answered TLS at all: {pct(len(h2), sum(1 for r in rows if r['alpn']))}")


def family(s):
    t = s.lower()
    if not t:
        return "(no Server header)"
    for key, name in [("nginx", "nginx"), ("openresty", "openresty"), ("cloudflare", "cloudflare"),
                      ("apache", "apache"), ("akamai", "akamai"), ("cloudfront", "cloudfront"),
                      ("gws", "google"), ("esf", "google"), ("sffe", "google"), ("gse", "google"),
                      ("envoy", "envoy"), ("microsoft-iis", "iis"), ("litespeed", "litespeed"),
                      ("amazons3", "s3"), ("istio", "envoy"), ("varnish", "varnish"), ("haproxy", "haproxy")]:
        if key in t:
            return name
    return "other"


fam_all = Counter(family(r["server"]) for r in answered)
fam_h2 = Counter(family(r["server"]) for r in h2)
print("\nServer header family, all answering domains:", dict(fam_all.most_common()))
print("Server header family, h2 domains:", dict(fam_h2.most_common()))

ng = [r for r in answered if re.search(r"\bnginx\b", r["server"], re.I)]
ng_h2 = [r for r in ng if r["alpn"] == "h2"]
print(f"\nServer header contains 'nginx': {len(ng)} domains; of those, h2 negotiated: {len(ng_h2)}")
ver = []
for r in ng:
    m = re.search(r"nginx/(\d+\.\d+\.\d+)", r["server"], re.I)
    if m:
        ver.append((r, m.group(1)))
print(f"  with a version number: {len(ver)}; without: {len(ng) - len(ver)}")
# Per-site lines are deliberately not printed: the flaw was disclosed one day before this run.
by_ver = Counter(v for _, v in ver)
for v in sorted(by_ver, key=vt):
    n_h2 = sum(1 for r, x in ver if x == v and r["alpn"] == "h2")
    tag = "listed affected" if listed_affected(v) else "not in listed range"
    print(f"  nginx/{v:<8} sites {by_ver[v]}  negotiating h2 {n_h2}  {tag}")
distro = sum(1 for r, v in ver if re.search(r"\((ubuntu|debian|centos|red hat|rhel)", r["server"], re.I))
print(f"  versions on distribution builds (Server header names the distro): {distro}")
aff = [(r, v) for r, v in ver if listed_affected(v)]
aff_h2 = [(r, v) for r, v in aff if r["alpn"] == "h2"]
print(f"  version in listed range: {len(aff)}; of those negotiating h2: {len(aff_h2)}")

other_ng = [r for r in answered if re.search(r"openresty", r["server"], re.I)]
print(f"\nopenresty (nginx-based, version not comparable): {len(other_ng)}; h2: {sum(r['alpn'] == 'h2' for r in other_ng)}")
print("\nrank buckets, share negotiating h2 among domains that answered TLS:")
for lo, hi in [(1, 100), (101, 300), (301, 600), (601, 1000)]:
    sub = [r for r in rows if lo <= rank[r["domain"]] <= hi and r["alpn"]]
    print(f"  ranks {lo}-{hi}: {pct(sum(r['alpn'] == 'h2' for r in sub), len(sub))}")
print("\nerrors:", dict(Counter(r["error"] for r in rows if r["error"]).most_common(6)))
