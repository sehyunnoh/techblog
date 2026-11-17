#!/usr/bin/env python3
"""Summarise the CSV written by spamhaus-dns-survey.py.

Usage: python spamhaus-dns-analyze.py results.csv top1000.csv
"""
import csv
import sys
from collections import Counter


def pct(n, d):
    return f"{n} ({100 * n / d:.1f}%)" if d else f"{n} (n/a)"


rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
rank = {r[1]: int(r[0]) for r in csv.reader(open(sys.argv[2], encoding="utf-8"))}
for r in rows:
    r["rank"] = rank[r["domain"]]
    r["has_mx"] = int(r["mx_hosts"] or 0) > 0
    r["null_mx"] = r["null_mx"] == "True"


def block(title, sub):
    n = len(sub)
    print(f"\n=== {title}: {n} domains ===")
    d = Counter(r["dmarc"] for r in sub)
    print("DMARC p=:", {k: pct(v, n) for k, v in d.most_common()})
    pub = [r for r in sub if r["dmarc"] != "none-published"]
    print("  with a DMARC record:", pct(len(pub), n))
    print("  of those, p=none:", pct(sum(r["dmarc"] == "none" for r in pub), len(pub)),
          "| has rua:", pct(sum(r["dmarc_rua"] == "True" for r in pub), len(pub)),
          "| pct below 100:", pct(sum(r["dmarc_pct"] not in ("", "100") for r in pub), len(pub)))
    print("  enforcing (quarantine or reject):",
          pct(sum(r["dmarc"] in ("quarantine", "reject") for r in sub), n))
    spf = [r for r in sub if int(r["spf_records"]) >= 1]
    print("SPF published:", pct(len(spf), n), "| more than one SPF record:",
          pct(sum(int(r["spf_records"]) > 1 for r in sub), n))
    one = [r for r in sub if int(r["spf_records"]) == 1]
    print("  final qualifier:", dict(Counter(r["spf_all"] for r in one).most_common()))
    look = [int(r["spf_lookups"]) for r in one if r["spf_lookups"] != ""]
    print("  lookup count: over 10:", pct(sum(x > 10 for x in look), len(look)),
          "| 8 to 10:", pct(sum(8 <= x <= 10 for x in look), len(look)),
          "| max:", max(look) if look else "n/a")


block("all", rows)
mx = [r for r in rows if r["has_mx"]]
block("domains with at least one MX host", mx)
print(f"\nnull MX (declares it accepts no mail): {pct(sum(r['null_mx'] for r in rows), len(rows))}")
print(f"no MX and not null MX: {pct(sum((not r['has_mx']) and not r['null_mx'] for r in rows), len(rows))}")

with_ip = [r for r in mx if int(r["mx_ips"]) > 0]
ok = [r for r in with_ip if int(r["mx_ips_fcrdns_ok"]) == int(r["mx_ips"])]
nop = [r for r in with_ip if int(r["mx_ips_no_ptr"]) > 0]
bad = [r for r in with_ip if int(r["mx_ips_fcrdns_ok"]) + int(r["mx_ips_no_ptr"]) < int(r["mx_ips"])]
print(f"\nMX hosts with IPv4 addresses: {len(with_ip)} domains")
print("  every MX IP passes forward-confirmed rDNS:", pct(len(ok), len(with_ip)))
print("  at least one MX IP has no PTR record:", pct(len(nop), len(with_ip)))
print("  at least one MX IP has a PTR that does not resolve back:", pct(len(bad), len(with_ip)))
print("  total MX IPs:", sum(int(r["mx_ips"]) for r in with_ip),
      "| passing:", sum(int(r["mx_ips_fcrdns_ok"]) for r in with_ip),
      "| no PTR:", sum(int(r["mx_ips_no_ptr"]) for r in with_ip))

print("\n=== DMARC enforcing share by rank bucket (all domains) ===")
for lo, hi in [(1, 100), (101, 300), (301, 600), (601, 1000)]:
    sub = [r for r in rows if lo <= r["rank"] <= hi]
    e = sum(r["dmarc"] in ("quarantine", "reject") for r in sub)
    nn = sum(r["dmarc"] == "none" for r in sub)
    np_ = sum(r["dmarc"] == "none-published" for r in sub)
    print(f"ranks {lo}-{hi}: enforcing {e}, p=none {nn}, no record {np_} of {len(sub)}")

print("\nSample of SPF over 10 lookups:")
for r in sorted((r for r in rows if r["spf_lookups"] not in ("",) and int(r["spf_lookups"]) > 10),
                key=lambda r: r["rank"])[:12]:
    print(f"  #{r['rank']} {r['domain']} lookups={r['spf_lookups']}")
