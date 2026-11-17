#!/usr/bin/env python3
"""Re-check "no DMARC" domains against a second resolver (dns.google).

Usage: python spamhaus-dns-crosscheck.py results.csv

The main survey uses Cloudflare. A failed lookup there would look like a
missing record, so every domain that the survey says has MX hosts but no DMARC
record is asked again through Google Public DNS. Prints how many agree.
"""
import csv
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def google_txt(name):
    url = f"https://dns.google/resolve?name={name}&type=TXT"
    for _ in range(4):
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                j = json.load(r)
            return [a["data"] for a in j.get("Answer", []) if a["type"] == 16], j["Status"]
        except Exception:
            continue
    return None, None


rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
targets = [r["domain"] for r in rows
           if int(r["mx_hosts"] or 0) > 0 and r["dmarc"] == "none-published"]


def check(d):
    ans, status = google_txt("_dmarc." + d)
    found = ans is not None and any("v=DMARC1" in a for a in ans)
    return d, found, status


with ThreadPoolExecutor(max_workers=8) as ex:
    out = list(ex.map(check, targets))
disagree = [(d, s) for d, found, s in out if found]
failed = [d for d, found, s in out if s is None]
print(f"domains with MX but no DMARC per Cloudflare: {len(targets)}")
print(f"Google Public DNS finds a DMARC record for: {len(disagree)} {disagree}")
print(f"Google lookups that failed outright: {len(failed)}")
