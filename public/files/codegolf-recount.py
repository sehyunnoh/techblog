"""Recount the go/codegolf benchmark (bjin.github.io/go-codegolf-benchmark) from its
own published data.json, and from every earlier data.json in the site's git history.

Standard library only. Downloads about 13 MB into ./codegolf-data on first run.

    python codegolf-recount.py
"""
import json
import os
import random
import urllib.request
from statistics import mean

REPO = "bjin/go-codegolf-benchmark"
CACHE = "codegolf-data"
HEAD = "e962571532c03f4ef4d64d9f371e0770216f7975"  # 2026-11-22, the version analysed
CONTESTED = ("js", "py", "cc")
ORIGINAL4 = ("js", "py", "cc", "hs")
ASTRA, HUM = "gpt-6.2-astra-max", "humans"


def fetch(url, path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as r, open(path, "wb") as f:
            f.write(r.read())
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def data_at(sha):
    return fetch(f"https://raw.githubusercontent.com/{REPO}/{sha}/data.json",
                 os.path.join(CACHE, f"data-{sha[:10]}.json"))


def cells(d, langs=None):
    for p in d["problems"]:
        for lang, c in p["cells"].items():
            if langs is None or lang in langs:
                yield p["id"], lang, c


def score(size, ref, power=2):
    return 100 * (ref / size) ** power


def avg_score(d, who, langs, ref_fn, power=2):
    vals = []
    for _, _, c in cells(d, langs):
        e = c["entries"]
        vals.append(score(e[who]["size"], ref_fn(c), power) if who in e else 0.0)
    return mean(vals)


published_ref = lambda c: c["best"]
no_oracle_ref = lambda c: min(v["size"] for v in c["entries"].values())
human_ref = lambda c: c["entries"][HUM]["size"]

d = data_at(HEAD)
ids = [c["id"] for c in d["competitors"]]
pub = {c["id"]: c["scores"] for c in d["competitors"]}

print("== 1. Does data.json reproduce its own leaderboard?")
worst = 0.0
for who in ids:
    if who == HUM:
        continue
    for key, langs in [("overall", None), ("contested", CONTESTED)]:
        mine = avg_score(d, who, langs, published_ref)
        theirs = float(pub[who][key]["text"].rstrip("%"))
        worst = max(worst, abs(mine - theirs))
h = avg_score(d, HUM, CONTESTED, published_ref)
print(f"largest |recomputed - published| over all models: {worst:.4f} points")
print(f"humans JS/PY/C++ recomputed {h:.3f} vs published {pub[HUM]['contested']['text']}")
bad = 0
total = 0
for p in d["problems"]:
    sols = fetch(f"https://raw.githubusercontent.com/{REPO}/{HEAD}/solutions/{p['id']}.json",
                 os.path.join(CACHE, f"solutions-{p['id']}.json"))
    for lang, by in sols.items():
        for who, code in by.items():
            total += 1
            if len(code.encode("utf-8")) != p["cells"][lang]["entries"][who]["size"]:
                bad += 1
print(f"published solutions whose UTF-8 byte length != listed size: {bad} of {total}")

print("\n== 2. Cell counts on JS/PY/C++ (96 cells)")
beat = hold = tie = 0
for _, lang, c in cells(d, CONTESTED):
    e = c["entries"]
    hs = e[HUM]["size"]
    ms = min(v["size"] for k, v in e.items() if k != HUM)
    beat += ms < hs
    hold += hs < ms
    tie += hs == ms
print(f"some model shorter than human: {beat}; human shorter than every model: {hold}; tied: {tie}")
w = l = t = 0
for _, lang, c in cells(d, CONTESTED):
    a, hh = c["entries"][ASTRA]["size"], c["entries"][HUM]["size"]
    w += a < hh
    l += a > hh
    t += a == hh
print(f"Astra alone vs humans: shorter {w}, longer {l}, same {t}")
astra_bytes = sum(c["entries"][ASTRA]["size"] for *_, c in cells(d, CONTESTED))
hum_bytes = sum(c["entries"][HUM]["size"] for *_, c in cells(d, CONTESTED))
print(f"total bytes over the 96 cells: Astra {astra_bytes}, humans {hum_bytes} "
      f"({100 * (astra_bytes / hum_bytes - 1):+.2f}%)")
for lang in CONTESTED:
    ab = sum(c["entries"][ASTRA]["size"] for *_, c in cells(d, (lang,)))
    hb = sum(c["entries"][HUM]["size"] for *_, c in cells(d, (lang,)))
    print(f"  {lang}: Astra {ab} bytes, humans {hb} bytes ({100 * (ab / hb - 1):+.2f}%)")
m4 = sum(min(v["size"] for k, v in c["entries"].items() if k != HUM) < c["entries"][HUM]["size"]
         for *_, c in cells(d, ORIGINAL4))
print(f"original four languages, some model shorter than human: {m4}")

print("\n== 3. Where the oracle sets the reference")
byl = {}
for _, lang, c in cells(d):
    if c["known_best"] is not None and c["known_best"] < no_oracle_ref(c):
        byl[lang] = byl.get(lang, 0) + 1
print("cells where Known Best beats every competitor:", sum(byl.values()), byl)
gap = []
for _, lang, c in cells(d):
    if c["known_best"] is not None:
        gap.append(100 * (1 - c["known_best"] / no_oracle_ref(c)))
print(f"in those cells the oracle is on average {mean(gap):.1f}% shorter than the best competitor "
      f"(max {max(gap):.1f}%)")

print("\n== 4. Scores under three references")
print(f"{'competitor':28s} {'overall':>8s} {'no-oracle':>9s}   {'JS/PY/C++':>9s} {'no-oracle':>9s}")
rows = []
for who in ids:
    o = avg_score(d, who, None, published_ref) if who != HUM else float("nan")
    o2 = avg_score(d, who, None, no_oracle_ref) if who != HUM else float("nan")
    c1 = avg_score(d, who, CONTESTED, published_ref)
    c2 = avg_score(d, who, CONTESTED, no_oracle_ref)
    rows.append((who, o, o2, c1, c2))
    print(f"{who:28s} {o:8.3f} {o2:9.3f}   {c1:9.3f} {c2:9.3f}")


def ranks(vals):
    order = sorted(vals, key=lambda kv: -kv[1])
    return {k: i + 1 for i, (k, _) in enumerate(order)}


models = [r for r in rows if r[0] != HUM]
r_pub = ranks([(r[0], r[1]) for r in models])
r_no = ranks([(r[0], r[2]) for r in models])
moved = [(k, r_pub[k], r_no[k]) for k in r_pub if r_pub[k] != r_no[k]]
print("overall rank changes without the oracle:", moved if moved else "none")
astra_vs_h = {}
for name, ref in [("published", published_ref), ("no oracle", no_oracle_ref)]:
    a = avg_score(d, ASTRA, CONTESTED, ref)
    hh = avg_score(d, HUM, CONTESTED, ref)
    astra_vs_h[name] = (a, hh)
    print(f"JS/PY/C++ {name:9s}: Astra {a:.3f}  humans {hh:.3f}  gap {a - hh:+.3f}")
a = avg_score(d, ASTRA, CONTESTED, human_ref)
print(f"Astra scored against the human record itself (100 = tie with humans): {a:.3f}")

print("\n== 5. How much the square matters (JS/PY/C++, published reference)")
for pw, label in [(1, "linear"), (2, "squared (site)"), (3, "cubed")]:
    a = avg_score(d, ASTRA, CONTESTED, published_ref, pw)
    hh = avg_score(d, HUM, CONTESTED, published_ref, pw)
    print(f"{label:15s} Astra {a:.3f} humans {hh:.3f} gap {a - hh:+.3f}")
lin = ranks([(r[0], avg_score(d, r[0], None, published_ref, 1)) for r in models])
moved = [(k, r_pub[k], lin[k]) for k in r_pub if r_pub[k] != lin[k]]
print("overall rank changes, linear instead of squared:", moved if moved else "none")

print("\n== 6. Bootstrap over the 32 problems: Astra minus humans on JS/PY/C++")
per_problem = {}
for pid, lang, c in cells(d, CONTESTED):
    e = c["entries"]
    per_problem.setdefault(pid, []).append(
        score(e[ASTRA]["size"], c["best"]) - score(e[HUM]["size"], c["best"]))
pids = sorted(per_problem)
diffs = [mean(per_problem[p]) for p in pids]
rng = random.Random(20261126)
boots = sorted(mean(rng.choice(diffs) for _ in pids) for _ in range(20000))
print(f"gap {mean(diffs):+.3f}, 95% bootstrap interval [{boots[499]:+.3f}, {boots[19499]:+.3f}], "
      f"share of resamples where humans lead {sum(b < 0 for b in boots) / len(boots):.4f}")
pos = sum(x > 0 for x in diffs)
neg = sum(x < 0 for x in diffs)
print(f"problems where Astra's 3-language average beats humans: {pos}, humans ahead: {neg}, even: {32 - pos - neg}")
astra_lead = sorted(((x, p) for x, p in zip(diffs, pids)), reverse=True)
print("largest per-problem Astra leads:", [(p, round(x, 1)) for x, p in astra_lead[:4]])
print("chart data, per-problem gap sorted:", [(p, round(x, 2)) for x, p in astra_lead])
early = [x for x, p in zip(diffs, pids) if int(p) <= 19]
late = [x for x, p in zip(diffs, pids) if int(p) >= 20]
obs = mean(late) - mean(early)
perm = 0
for _ in range(20000):
    sh = diffs[:]
    rng.shuffle(sh)
    perm += abs(mean(sh[19:]) - mean(sh[:19])) >= abs(obs)
print(f"problems 01-19 (Rhino 1.7R4 JS): mean gap {mean(early):+.2f}; problems 20-32 (Rhino 1.7.7): "
      f"{mean(late):+.2f}; permutation p={perm / 20000:.3f}")
top4 = sum(x for x, _ in astra_lead[:4]) / 32
print(f"share of the gap from the top 4 problems: {100 * top4 / mean(diffs):.0f}%")
js_gap = {}
for lang in CONTESTED:
    a = avg_score(d, ASTRA, (lang,), published_ref)
    hh = avg_score(d, HUM, (lang,), published_ref)
    js_gap[lang] = a - hh
    print(f"{lang}: Astra {a:.3f} humans {hh:.3f} gap {a - hh:+.3f}")

print("\n== 7. Haiku 5.5 max vs xhigh, and 'shorter of the two'")
s = lg = eq = 0
for _, _, c in cells(d):
    a, b = c["entries"]["claude-haiku-5.5-max"]["size"], c["entries"]["claude-haiku-5.5-xhigh"]["size"]
    s += a < b
    lg += a > b
    eq += a == b
print(f"max shorter in {s}, longer in {lg}, equal in {eq}")
best2 = mean(score(min(c["entries"]["claude-haiku-5.5-max"]["size"],
                       c["entries"]["claude-haiku-5.5-xhigh"]["size"]), c["best"]) for *_, c in cells(d))
print(f"shorter-of-two overall: {best2:.3f}")

print("\n== 8. Same solutions, moving target: scores across the site's git history")
with urllib.request.urlopen(f"https://api.github.com/repos/{REPO}/commits?per_page=100", timeout=60) as r:
    commits = [(c["sha"], c["commit"]["author"]["date"][:10]) for c in json.load(r)][::-1]
history = []
for sha, day in commits:
    h = data_at(sha)
    hid = {c["id"] for c in h["competitors"]}
    row = {"day": day, "sha": sha[:10]}
    for who in ("gpt-6-astra-max", ASTRA, HUM):
        if who in hid:
            row[who] = avg_score(h, who, CONTESTED, published_ref)
    history.append(row)


def sizes(dd, who, langs):
    return {(pid, lang): c["entries"][who]["size"] for pid, lang, c in cells(dd, langs)
            if who in c["entries"]}


first = data_at(commits[0][0])
hum0, hum1 = sizes(first, HUM, ORIGINAL4), sizes(d, HUM, ORIGINAL4)
print(f"human records changed between first and last data.json: "
      f"{sum(hum0[k] != hum1[k] for k in hum0)} of {len(hum0)} cells")
a0, a1 = sizes(first, "gpt-6-astra-max", None), sizes(d, "gpt-6-astra-max", None)
chg = [k for k in a0 if a0[k] != a1[k]]
print(f"GPT-6 Astra cells whose size changed: {len(chg)} "
      f"({sorted({lang for _, lang in chg})}), total bytes {sum(a0.values())} -> {sum(a1.values())}")
print("JS/PY/C++ score by data.json version (only rows where something changed):")
seen = None
for row in history:
    key = tuple(round(row.get(k, -1), 3) for k in ("gpt-6-astra-max", ASTRA, HUM))
    if key != seen:
        seen = key
        print(row["day"], row["sha"], "  ".join(f"{k}={v:.3f}" for k, v in row.items()
                                                if k not in ("day", "sha")))
print("\n== 9. The 2026-11-22 JS signature change (commit 5f7882ba37)")
before_sha = next(s for s, _ in commits if s.startswith("a44eae035f"))
after_sha = next(s for s, _ in commits if s.startswith("5f7882ba37"))
b0, b1 = data_at(before_sha), data_at(after_sha)
changed_cells = set()
deltas = {}
for p0, p1 in zip(b0["problems"], b1["problems"]):
    for lang in p1["cells"]:
        e0, e1 = p0["cells"][lang]["entries"], p1["cells"][lang]["entries"]
        for who in e1:
            if who in e0 and e0[who]["size"] != e1[who]["size"]:
                changed_cells.add((p1["id"], lang))
                deltas[e0[who]["size"] - e1[who]["size"]] = deltas.get(e0[who]["size"] - e1[who]["size"], 0) + 1
print(f"competitor sizes that changed: {sum(deltas.values())}, bytes saved -> count {dict(sorted(deltas.items()))}")
print(f"cells affected: {len(changed_cells)}, languages {sorted({l for _, l in changed_cells})}, "
      f"problems {min(p for p, _ in changed_cells)}-{max(p for p, _ in changed_cells)}")
h0 = sizes(b0, HUM, ORIGINAL4)
h1 = sizes(b1, HUM, ORIGINAL4)
print(f"human records changed by it: {sum(h0[k] != h1[k] for k in h0)}")
s0 = json.load(urllib.request.urlopen(
    f"https://raw.githubusercontent.com/{REPO}/{before_sha}/solutions/21.json", timeout=60))
s1 = json.load(urllib.request.urlopen(
    f"https://raw.githubusercontent.com/{REPO}/{after_sha}/solutions/21.json", timeout=60))
print("example, problem 21 JS, GPT-6.2 Astra before:", s0["js"][ASTRA])
print("                                          after: ", s1["js"][ASTRA])


def contested_with_reverted(dd, old):
    """Score Astra and humans on the current data, but with every changed JS cell put back
    to its pre-change sizes and reference."""
    out = {}
    for who in (ASTRA, HUM):
        vals = []
        for (pid, lang, c), (_, _, c0) in zip(cells(dd, CONTESTED), cells(old, CONTESTED)):
            if (pid, lang) in changed_cells:
                vals.append(score(c0["entries"][who]["size"], c0["best"]))
            else:
                vals.append(score(c["entries"][who]["size"], c["best"]))
        out[who] = mean(vals)
    return out


rv = contested_with_reverted(d, b0)
print(f"JS/PY/C++ with those cells reverted: Astra {rv[ASTRA]:.3f} humans {rv[HUM]:.3f} "
      f"gap {rv[ASTRA] - rv[HUM]:+.3f} (current {astra_vs_h['published'][0] - astra_vs_h['published'][1]:+.3f})")
late_rev = []
for (pid, lang, c), (_, _, c0) in zip(cells(d, CONTESTED), cells(b0, CONTESTED)):
    if int(pid) >= 20:
        cc = c0 if (pid, lang) in changed_cells else c
        late_rev.append(score(cc["entries"][ASTRA]["size"], cc["best"]) - score(cc["entries"][HUM]["size"], cc["best"]))
print(f"problems 20-32 mean gap with the change reverted: {mean(late_rev):+.2f} (current {mean(late):+.2f})")

ref_moves = sum(1 for (_, _, c0), (_, _, c1) in zip(cells(first, CONTESTED), cells(d, CONTESTED))
                if c0["best"] != c1["best"])
print(f"JS/PY/C++ cells whose reference size changed since the first version: {ref_moves} of 96")
