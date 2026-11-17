#!/usr/bin/env python3
"""Survey email-authentication DNS records for a list of domains.

Usage: python spamhaus-dns-survey.py top1000.csv results.csv [limit]

Input is a Tranco-style CSV ("rank,domain"). For every domain it asks
Cloudflare's DNS-over-HTTPS JSON endpoint for:
  - DMARC (_dmarc.<domain> TXT): policy p=, subdomain policy sp=, pct=, rua=
  - SPF (<domain> TXT, v=spf1): record count, final "all" qualifier, and the
    number of DNS-lookup terms counted the RFC 7208 way (include, a, mx, ptr,
    exists, redirect; include/redirect are followed)
  - MX hosts, their IPv4 addresses, and forward-confirmed reverse DNS
    (PTR of the IP, then A of the PTR name must contain the same IP)
It only reads public DNS. It measures the domain's *receiving* mail servers
(MX), not the IPs that send its mail, which DNS does not reveal.
Python 3 standard library only.
"""
import csv
import json
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

DOH = "https://cloudflare-dns.com/dns-query"
TYPES = {"A": 1, "TXT": 16, "MX": 15, "PTR": 12}


@lru_cache(maxsize=None)
def query(name, rtype):
    """Return (status, [answer data strings]). status None means the lookup failed."""
    url = f"{DOH}?name={urllib.parse.quote(name)}&type={rtype}"
    req = urllib.request.Request(url, headers={"accept": "application/dns-json"})
    for _ in range(4):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                j = json.load(r)
            ans = [a["data"] for a in j.get("Answer", []) if a["type"] == TYPES[rtype]]
            return j["Status"], tuple(ans)
        except Exception:
            continue
    return None, ()


def txt(name):
    status, ans = query(name, "TXT")
    # DoH returns each TXT as one quoted string; long records are split in quotes
    return status, [re.sub(r'"\s*"', "", a).strip('"') for a in ans]


def spf_records(domain):
    status, recs = txt(domain)
    return status, [r for r in recs if r.lower().startswith("v=spf1")]


def spf_lookups(domain, seen=None, depth=0):
    """Count DNS-lookup terms per RFC 7208 section 4.6.4. Returns (count, error)."""
    seen = seen or set()
    if domain in seen or depth > 10:
        return 0, "loop"
    seen.add(domain)
    status, recs = spf_records(domain)
    if len(recs) != 1:
        return 0, "no-or-multiple-spf"
    count = 0
    for term in recs[0].split()[1:]:
        t = term.lstrip("+-~?").lower()
        if t.startswith("include:"):
            count += 1
            c, e = spf_lookups(t[8:], seen, depth + 1)
            count += c
        elif t.startswith("redirect="):
            count += 1
            c, e = spf_lookups(t[9:], seen, depth + 1)
            count += c
        elif re.match(r"(a|mx|ptr|exists)(:|/|$)", t):
            count += 1
    return count, ""


def parse_dmarc(domain):
    status, recs = txt("_dmarc." + domain)
    recs = [r for r in recs if r.lower().startswith("v=dmarc1")]
    if not recs:
        return {"dmarc": "none-published"}
    tags = dict(
        (k.strip().lower(), v.strip())
        for k, _, v in (p.partition("=") for p in recs[0].split(";") if "=" in p)
    )
    return {"dmarc": tags.get("p", "missing-p").lower(), "dmarc_sp": tags.get("sp", "").lower(),
            "dmarc_pct": tags.get("pct", ""), "dmarc_rua": "rua" in tags}


def fcrdns(ip):
    rev = ".".join(reversed(ip.split("."))) + ".in-addr.arpa"
    _, ptrs = query(rev, "PTR")
    for p in ptrs:
        host = p.rstrip(".")
        _, addrs = query(host, "A")
        if ip in addrs:
            return True
    return False if ptrs else None  # None = no PTR at all


def survey(domain):
    row = {"domain": domain}
    row.update(parse_dmarc(domain))
    status, spfs = spf_records(domain)
    row["spf_records"] = len(spfs)
    if len(spfs) == 1:
        m = re.search(r"\s([+\-~?]?)all\b", spfs[0].lower())
        row["spf_all"] = (m.group(1) or "+") + "all" if m else "no-all"
        row["spf_lookups"], row["spf_err"] = spf_lookups(domain)
    _, mxs = query(domain, "MX")
    hosts = []
    for m in mxs:
        parts = m.split()
        if len(parts) == 2:
            hosts.append(parts[1].rstrip("."))
    row["null_mx"] = hosts == [""] or any(m.strip() == "0 ." for m in mxs)
    hosts = [h for h in hosts if h]
    row["mx_hosts"] = len(hosts)
    ips, results = set(), []
    for h in hosts[:6]:
        _, addrs = query(h, "A")
        ips.update(a for a in addrs if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", a))
    for ip in sorted(ips):
        results.append(fcrdns(ip))
    row["mx_ips"] = len(ips)
    row["mx_ips_fcrdns_ok"] = sum(1 for r in results if r is True)
    row["mx_ips_no_ptr"] = sum(1 for r in results if r is None)
    return row


def main():
    src, dst = sys.argv[1], sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
    domains = [r[1] for r in csv.reader(open(src, encoding="utf-8"))][:limit]
    with ThreadPoolExecutor(max_workers=12) as ex:
        rows = list(ex.map(survey, domains))
    keys = sorted({k for r in rows for k in r}, key=lambda k: (k != "domain", k))
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {dst}")


if __name__ == "__main__":
    main()
