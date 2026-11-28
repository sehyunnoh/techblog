"""Measure how far behind upstream the pinned plugins in anthropics/claude-plugins-official are,
and how long automated SHA-bump PRs wait.

Usage: python -I marketplace-pin-lag.py <out.json>
Needs a GitHub token in the GITHUB_TOKEN env var (read-only public API access is enough).
Standard library only.
"""
import json, os, sys, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone

MKT_REPO = "anthropics/claude-plugins-official"
MKT_REF = "05790c0871eea870c8c1103bb4a72542472f1ec0"  # last commit touching marketplace.json at measurement time
TOKEN = os.environ["GITHUB_TOKEN"]
NOW = datetime.now(timezone.utc)


def api(path, params=None):
    url = "https://api.github.com/" + path.lstrip("/")
    if params:
        url += "?" + urllib.parse.urlencode(params)
    for attempt in range(5):
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + TOKEN,
            "Accept": "application/vnd.github+json",
            "User-Agent": "marketplace-lag-recount",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and attempt < 4:
                time.sleep(20 * (attempt + 1))
                continue
            if e.code in (404, 409, 422):
                return {"_error": e.code}
            raise
    raise RuntimeError(url)


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def owner_repo(url):
    u = url.removesuffix(".git").rstrip("/")
    if "github.com/" not in u:
        return None
    parts = u.split("github.com/")[1].split("/")
    return parts[0] + "/" + parts[1]


def main(out):
    raw = api(f"repos/{MKT_REPO}/contents/.claude-plugin/marketplace.json", {"ref": MKT_REF})
    import base64
    mkt = json.loads(base64.b64decode(raw["content"]))
    plugins = []
    for p in mkt["plugins"]:
        s = p["source"]
        if isinstance(s, str) or "sha" not in s:
            plugins.append({"name": p["name"], "kind": "local" if isinstance(s, str) else s.get("source")})
            continue
        repo = owner_repo(s.get("url") or s.get("repo") or "")
        if s.get("source") == "git-subdir" and not repo and s.get("repo"):
            repo = s["repo"]
        rec = {"name": p["name"], "kind": s["source"], "repo": repo, "sha": s["sha"],
               "path": s.get("path"), "ref": s.get("ref")}
        if not repo:
            rec["error"] = "non-github"
            plugins.append(rec)
            continue
        meta = api(f"repos/{repo}")
        if "_error" in meta:
            rec["error"] = f"repo {meta['_error']}"
            plugins.append(rec)
            continue
        # Always measure against the upstream default branch. Entries that also carry a `ref`
        # (usually a release tag) are recorded with it so they can be reported separately.
        branch = meta["default_branch"]
        pin = api(f"repos/{meta['full_name']}/commits/{s['sha']}")
        if "_error" in pin:
            rec["error"] = f"pin {pin['_error']}"
            plugins.append(rec)
            continue
        rec["pin_date"] = pin["commit"]["committer"]["date"]
        if rec["path"]:
            # commits touching the plugin's subdirectory after the pinned commit's date
            n, page = 0, 1
            while True:
                cs = api(f"repos/{meta['full_name']}/commits", {
                    "sha": branch, "path": rec["path"], "since": rec["pin_date"], "per_page": 100, "page": page})
                if "_error" in cs:
                    rec["error"] = f"commits {cs['_error']}"
                    break
                n += sum(1 for c in cs if c["sha"] != s["sha"] and c["commit"]["committer"]["date"] > rec["pin_date"])
                if len(cs) < 100:
                    break
                page += 1
            rec["behind"] = n
        else:
            cmp = api(f"repos/{meta['full_name']}/compare/{s['sha']}...{branch}")
            if "_error" in cmp:
                rec["error"] = f"compare {cmp['_error']}"
            else:
                rec["behind"] = cmp["ahead_by"]
        rec["pin_age_days"] = round((NOW - ts(rec["pin_date"])).total_seconds() / 86400, 1)
        plugins.append(rec)
        print(rec["name"], rec.get("behind"), rec.get("pin_age_days"), rec.get("error", ""), file=sys.stderr)

    def search(q):
        items, page = [], 1
        while True:
            r = api("search/issues", {"q": q, "per_page": 100, "page": page})
            items += r["items"]
            if len(r["items"]) < 100 or len(items) >= 1000:
                return items, r["total_count"]
            page += 1

    open_prs, open_total = search(f"repo:{MKT_REPO} is:pr is:open \"bump(\" in:title")
    open_rows = [{"number": i["number"], "title": i["title"], "created_at": i["created_at"],
                  "age_days": round((NOW - ts(i["created_at"])).total_seconds() / 86400, 1)} for i in open_prs]

    merged_rows = []
    for lo, hi in [("2026-09-01", "2026-09-30"), ("2026-10-01", "2026-10-31"), ("2026-11-01", "2026-11-30")]:
        items, total = search(f"repo:{MKT_REPO} is:pr is:merged \"bump(\" in:title created:{lo}..{hi}")
        for i in items:
            m = i.get("pull_request", {}).get("merged_at")
            if m:
                merged_rows.append({"number": i["number"], "created_at": i["created_at"], "merged_at": m,
                                    "hours": round((ts(m) - ts(i["created_at"])).total_seconds() / 3600, 2)})
        print(lo, "merged total", total, "fetched", len(items), file=sys.stderr)

    json.dump({"measured_at": NOW.isoformat(), "marketplace_ref": MKT_REF, "plugins": plugins,
               "open_bump_prs_total": open_total, "open_bump_prs": open_rows, "merged_bump_prs": merged_rows},
              open(out, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
