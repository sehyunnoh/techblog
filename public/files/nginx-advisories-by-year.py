#!/usr/bin/env python3
"""Count nginx security advisories by the year they were disclosed.

Sources (all from nginx.org, fetched once and cached in a directory you pass):
  - en/security_advisories.html : one <li> per advisory, with severity,
    CVE ids and the "Vulnerable:" version range
  - news.html and 2009.html ... <last year>.html : release announcements,
    which name the CVE ids each release fixed, with a date
  - en/CHANGES : release date of every mainline-line version, used to
    date the first vulnerable version of each advisory

An advisory is dated by the earliest news item that mentions one of its
CVE ids. Advisories that no news item mentions are reported separately and
fall back to the year in their CVE id.

Usage: python3 nginx-advisories-by-year.py CACHE_DIR
Python 3 standard library only.
"""
import collections
import datetime
import html
import os
import re
import sys
import urllib.request

BASE = "https://nginx.org/"
THIS_YEAR = 2026


def fetch(cache, path):
    local = os.path.join(cache, path.replace("/", "_"))
    if not os.path.exists(local):
        req = urllib.request.Request(BASE + path, headers={"User-Agent": "advisory-count/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        with open(local, "wb") as f:
            f.write(data)
    with open(local, encoding="utf-8") as f:
        return f.read()


def strip(s):
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def vkey(v):
    return tuple(int(x) for x in v.split("."))


def main():
    cache = sys.argv[1]
    os.makedirs(cache, exist_ok=True)

    # 1. advisories
    page = fetch(cache, "en/security_advisories.html")
    advisories = []
    for li in re.findall(r"<li><p>(.*?)</p></li>", page, re.S):
        parts = [strip(p) for p in re.split(r"<br\s*/?>", li)]
        title = parts[0]
        sev = next((p.split(":", 1)[1].strip() for p in parts if p.startswith("Severity:")), "")
        vuln = next((p.split(":", 1)[1].strip() for p in parts if p.startswith("Vulnerable:")), "")
        cves = list(dict.fromkeys(re.findall(r"CVE-\d{4}-\d+", li)))
        advisories.append({"title": title, "severity": sev, "vulnerable": vuln, "cves": cves})

    # 2. news items, dated
    pages = [fetch(cache, "news.html")]
    for y in range(2009, THIS_YEAR + 1):
        try:
            pages.append(fetch(cache, f"{y}.html"))
        except Exception:
            pass
    cve_date = {}
    for p in pages:
        for date, body in re.findall(r'<td class="date"><a name="[^"]*"></a>(\d{4}-\d{2}-\d{2})</td><td>(.*?)</td></tr>', p, re.S):
            if "njs" in strip(body)[:20]:
                continue  # njs releases have their own advisory page
            for c in re.findall(r"CVE-\d{4}-\d+", body):
                if c not in cve_date or date < cve_date[c]:
                    cve_date[c] = date

    # 3. version release dates from CHANGES
    changes = fetch(cache, "en/CHANGES")
    months = {m: i for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), 1)}
    vdate = {}
    texts = [changes]
    for old in ("en/CHANGES-0.5", "en/CHANGES-0.6", "en/CHANGES-0.7", "en/CHANGES-0.8"):
        try:
            texts.append(fetch(cache, old))
        except Exception:
            pass
    for t in texts:
        for v, d, m, y in re.findall(r"Changes with nginx (\d+\.\d+\.\d+)\s+(\d+) (\w{3}) (\d{4})", t):
            vdate.setdefault(v, datetime.date(int(y), months[m], int(d)))

    # credits: "*) Security: ... (CVE-x). Thanks to Y." entries in CHANGES
    credit = {}
    for entry in re.split(r"\n\s*\*\) ", changes):
        if not entry.startswith("Security:"):
            continue
        m = re.search(r"Thanks to (.*?)\.\s*$", " ".join(entry.split()))
        for c in re.findall(r"CVE-\d{4}-\d+", entry):
            credit.setdefault(c, m.group(1) if m else "(no credit line)")
    changes_2026 = set(re.findall(rf"CVE-{THIS_YEAR}-\d+", changes))

    by_year = collections.Counter()
    by_year_sev = collections.defaultdict(collections.Counter)
    undated = []
    rows = []
    for a in advisories:
        dates = [cve_date[c] for c in a["cves"] if c in cve_date]
        if dates:
            disclosed = min(dates)
            year = int(disclosed[:4])
            src = "news"
        else:
            disclosed = ""
            year = int(a["cves"][0][4:8]) if a["cves"] else None
            src = "cve-id" if a["cves"] else "none"
            undated.append(a)
        a["disclosed"], a["year"], a["src"] = disclosed, year, src
        if year:
            by_year[year] += 1
            by_year_sev[year][a["severity"].lower()] += 1
        # age: first vulnerable version -> disclosure
        m = re.match(r"(?:nginx/Windows )?(\d+\.\d+\.\d+)-", a["vulnerable"])
        age = ""
        if m and disclosed and m.group(1) in vdate:
            first = vdate[m.group(1)]
            age = round((datetime.date.fromisoformat(disclosed) - first).days / 365.25, 1)
        a["age"] = age
        rows.append(a)

    print(f"advisories on the page: {len(advisories)}")
    print(f"dated from a news item: {sum(1 for a in rows if a['src']=='news')}")
    print(f"dated from CVE id year only: {sum(1 for a in rows if a['src']=='cve-id')}")
    print(f"no CVE id and no news match: {sum(1 for a in rows if a['src']=='none')}")
    print()
    print("year  total  major  medium  minor/low  other")
    for y in sorted(by_year):
        s = by_year_sev[y]
        print(f"{y}  {by_year[y]:5d}  {s['major']:5d}  {s['medium']:6d}  {s['minor']+s['low']:9d}  "
              f"{by_year[y]-s['major']-s['medium']-s['minor']-s['low']:5d}")
    prior = sum(n for y, n in by_year.items() if y < THIS_YEAR)
    prior9 = sum(n for y, n in by_year.items() if THIS_YEAR - 9 <= y < THIS_YEAR)
    print(f"\n{THIS_YEAR}: {by_year[THIS_YEAR]}; all earlier years: {prior}; previous 9 years: {prior9}")

    print(f"\n{THIS_YEAR} release batches (date: advisories)")
    batch = collections.Counter(a["disclosed"] for a in rows if a["year"] == THIS_YEAR)
    for d in sorted(batch):
        print(f"  {d or '(undated)'}: {batch[d]}")

    print(f"\n{THIS_YEAR} advisories, oldest-bug first (age = years from first vulnerable version to disclosure)")
    this = [a for a in rows if a["year"] == THIS_YEAR]
    this.sort(key=lambda a: -(a["age"] or 0))
    for a in this:
        cr = "; ".join(sorted({credit.get(c, "?") for c in a["cves"]}))
        print(f"  {a['disclosed'] or '----------'}  {a['severity']:7s} age={a['age']!s:>5}  {a['vulnerable']:22s} {a['title']}  [{cr}]")
    ages = [a["age"] for a in this if a["age"] != ""]
    if ages:
        ages.sort()
        import statistics
        print(f"\nages known for {len(ages)}/{len(this)}; median {statistics.median(ages):.2f} years; "
              f">=10 years: {sum(1 for x in ages if x >= 10)}")

    print(f"\n{THIS_YEAR} credits (from CHANGES 'Thanks to' lines; one advisory can credit several)")
    page_2026 = {c for a in this for c in a["cves"] if c.startswith(f"CVE-{THIS_YEAR}")}
    print(f"  CVE-{THIS_YEAR} ids on advisory page: {len(page_2026)}; in CHANGES: {len(changes_2026)}; "
          f"in CHANGES but not on page: {sorted(changes_2026 - page_2026)}; on page not in CHANGES: {sorted(page_2026 - changes_2026)}")
    names = collections.Counter()
    for a in this:
        cr = {credit.get(c, "(not in CHANGES)") for c in a["cves"]}
        for line in cr:
            line = line.replace("Claude and Anthropic", "Claude & Anthropic")  # one organisation
            for n in re.split(r",\s*(?:and\s+)?|\s+and\s+", line):
                names[n.strip()] += 1
    for n, k in names.most_common():
        print(f"  {k:3d}  {n}")

    print("\nundated advisories (no news item names their CVE):")
    for a in undated:
        print(f"  {a['cves'] or '-'} {a['title']} (counted in {a['year']})")


if __name__ == "__main__":
    main()
