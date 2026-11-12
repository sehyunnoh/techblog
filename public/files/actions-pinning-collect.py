#!/usr/bin/env python3
"""Collect GitHub Actions workflow data for the most-starred repositories.

Usage: collect.py OUTDIR [NUM_REPOS]
Needs the `gh` CLI (authenticated) for the search and tree API calls.
Raw workflow files are fetched from raw.githubusercontent.com.
Writes OUTDIR/repos.json and OUTDIR/workflows/<owner>__<repo>/<file>.
"""
import json, os, subprocess, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

out = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
os.makedirs(out + "/workflows", exist_ok=True)


def gh(path):
    for attempt in range(3):
        r = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8")
        if r.returncode == 0:
            return json.loads(r.stdout)
        if "rate limit" in r.stderr.lower():
            time.sleep(30)
        else:
            return None
    return None


repos = []
for page in range(1, (n + 99) // 100 + 1):
    d = gh(f"search/repositories?q=stars:%3E1000+archived:false&sort=stars&order=desc&per_page=100&page={page}")
    if not d:
        break
    repos += [{"full": i["full_name"], "stars": i["stargazers_count"], "branch": i["default_branch"],
               "lang": i["language"], "pushed": i["pushed_at"]} for i in d["items"]]
    time.sleep(2.5)
repos = repos[:n]
print("repos", len(repos), flush=True)


def raw(full, branch, path):
    url = f"https://raw.githubusercontent.com/{full}/{branch}/{path}"
    try:
        return urllib.request.urlopen(url, timeout=30).read().decode("utf-8", "replace")
    except Exception:
        return None


def work(r):
    t = gh(f"repos/{r['full']}/git/trees/{r['branch']}?recursive=1")
    if not t:
        r["tree"] = "fail"
        return
    paths = [x["path"] for x in t.get("tree", [])]
    r["truncated"] = t.get("truncated", False)
    wf = [p for p in paths if p.startswith(".github/workflows/") and p.count("/") == 2
          and p.endswith((".yml", ".yaml"))]
    r["workflows"] = wf
    r["lockfile"] = ".github/workflows/actions.lock" in paths
    d = f"{out}/workflows/{r['full'].replace('/', '__')}"
    os.makedirs(d, exist_ok=True)
    for p in wf:
        body = raw(r["full"], r["branch"], p)
        if body is not None:
            open(f"{d}/{os.path.basename(p)}", "w", encoding="utf-8").write(body)
    if r["lockfile"]:
        body = raw(r["full"], r["branch"], ".github/workflows/actions.lock")
        if body is not None:
            open(f"{d}/actions.lock", "w", encoding="utf-8").write(body)


with ThreadPoolExecutor(6) as ex:
    list(ex.map(work, repos))
json.dump({"collected": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "repos": repos},
          open(out + "/repos.json", "w"), indent=1)
print("done; with workflows:", sum(1 for r in repos if r.get("workflows")),
      "lockfile:", sum(1 for r in repos if r.get("lockfile")))
