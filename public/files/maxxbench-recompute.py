import json, random, sys, statistics as st
from collections import Counter

g = json.load(open(sys.argv[1]))
models, tasks = g["models"], g["tasks"]
ids = [m["id"] for m in models]
name = {m["id"]: m["name"] for m in models}

# per-cell attempts
att = Counter()
missing = Counter()
rate = {i: [] for i in ids}  # per task rate or None
for t in tasks:
    for i in ids:
        c = t["cells"].get(i)
        if not c:
            rate[i].append(None); missing[i] += 1; continue
        n = c["passed"] + c["failed"]
        att[n] += 1
        rate[i].append(c["rate"] if n else None)
print("attempts per cell histogram:", dict(att))
print("missing cells per model:", {name[k]: v for k, v in missing.items() if v})

random.seed(0)
B = 4000


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs)


def boot(i):
    xs = [x for x in rate[i] if x is not None]
    bs = sorted(sum(random.choices(xs, k=len(xs))) / len(xs) for _ in range(B))
    return bs[int(.025 * B)], bs[int(.975 * B)]


print("\nRecomputed MaxxBench (mean of per-task rates), 95% bootstrap CI over tasks")
rows = []
for i in ids:
    lo, hi = boot(i)
    rows.append((mean(rate[i]), lo, hi, name[i]))
rows.sort(reverse=True)
for m, lo, hi, n in rows:
    print(f"{n:22s} {100*m:5.1f}  [{100*lo:5.1f}, {100*hi:5.1f}]  width {100*(hi-lo):4.1f}")

# paired bootstrap for selected pairs
def paired(a, b):
    ia, ib = ids[[name[x] for x in ids].index(a)], ids[[name[x] for x in ids].index(b)]
    d = [x - y for x, y in zip(rate[ia], rate[ib]) if x is not None and y is not None]
    bs = sorted(sum(random.choices(d, k=len(d))) / len(d) for _ in range(B))
    return sum(d) / len(d), bs[int(.025 * B)], bs[int(.975 * B)]


print("\nPaired bootstrap differences (pp)")
for a, b in [("Claude Opus 5.5", "GPT-6 Astra"), ("Claude Opus 5.5", "GPT-5.6 Sol"),
             ("GPT-6 Astra", "GPT-5.6 Sol"), ("Claude Opus 5.5", "Claude Sonnet 5.5"),
             ("Claude Opus 5.5", "Gemini 3.8 Flash"), ("Claude Opus 5", "Claude Fable 5")]:
    m, lo, hi = paired(a, b)
    print(f"{a} - {b}: {100*m:+.1f} [{100*lo:+.1f}, {100*hi:+.1f}]")

# how many leaderboard neighbours are statistically separable (paired CI excludes 0)
order = [r[3] for r in rows]
sep = 0
tot = 0
for x in range(len(order)):
    for y in range(x + 1, len(order)):
        m, lo, hi = paired(order[x], order[y])
        tot += 1
        if lo > 0 or hi < 0:
            sep += 1
print(f"\npairs separable at 95% (paired bootstrap): {sep}/{tot}")

# attempts agreement: tasks where the two attempts disagree
dis = {i: sum(1 for t in tasks if t['cells'].get(i) and t['cells'][i]['passed'] == 1 and t['cells'][i]['failed'] == 1) for i in ids}
print("\nTasks with split attempts (1 pass + 1 fail) per model:", {name[k]: v for k, v in dis.items()})
