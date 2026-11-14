"""Recompute von Foerster, Mora & Amiot (1960), Science 132:1291, Eq. 11:
   N(t) = 1.79e11 / (2026.87 - t)^0.99
against OWID world population (HYDE + UN WPP). Standard library only.
usage: python doomsday-recompute.py owid-world-population.csv
"""
import csv, math, sys

K, U, k = 1.79e11, 2026.87, 0.99
rows = [(int(r["year"]), float(r["population_historical"]))
        for r in csv.DictReader(open(sys.argv[1], encoding="utf8"))]
pop = dict(rows)

def paper(t): return K / (U - t) ** k

print("[1] paper formula vs OWID")
print("year   actual(B)  formula(B)  formula/actual")
for y in (1, 1000, 1500, 1700, 1800, 1900, 1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020, 2023):
    if y in pop:
        print(f"{y:5d}  {pop[y]/1e9:9.3f}  {paper(y)/1e9:10.3f}  {paper(y)/pop[y]:8.2f}")

def rms_pct(sel):
    e = [(paper(y) / n - 1) for y, n in sel]
    return math.sqrt(sum(x * x for x in e) / len(e)) * 100

hist = [(y, n) for y, n in rows if 1 <= y <= 1958]
print(f"\n[2] RMS % deviation of the paper's formula on OWID points 1..1958: {rms_pct(hist):.1f}% (n={len(hist)}; paper reports ~7% on its own 24 estimates)")

# first year the formula is >10% / >50% above actual (annual-ish points only)
for thr in (0.10, 0.50, 1.0):
    for y, n in rows:
        if y >= 1960 and paper(y) / n - 1 > thr:
            print(f"    formula exceeds actual by >{int(thr*100)}% from {y}"); break

# [3] refit with the paper's own functional form, using data up to a cutoff
def fit(sel):
    best = None
    for u10 in range(int(max(y for y, _ in sel) * 10) + 1, 30000):
        u = u10 / 10
        xs = [math.log(u - y) for y, _ in sel]; ys = [math.log(n) for _, n in sel]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        b = sum((x - mx) * (yy - my) for x, yy in zip(xs, ys)) / sxx
        a = my - b * mx
        sse = sum((yy - (a + b * x)) ** 2 for x, yy in zip(xs, ys))
        if best is None or sse < best[0]: best = (sse, u, math.exp(a), -b)
    return best

print("\n[3] refit N = K/(U-t)^k by least squares in log space")
print("fit window     U        K          k     formula(2023)/actual")
for lo, hi in ((1, 1957), (1, 1990), (1, 2023), (1800, 2023)):
    sel = [(y, n) for y, n in rows if lo <= y <= hi]
    _, u, kk, ee = fit(sel)
    chk = f"{kk/(u-2023)**ee/pop[2023]:.2f}" if u > 2023 else "singularity already passed"
    print(f"{lo:5d}-{hi:<5d}  {u:7.1f}  {kk:.3e}  {ee:5.2f}   {chk}  (n={len(sel)})")

# [4] growth rate: doubling time actual vs the paper's Eq.13 (0.445*(U-t))
print("\n[4] doubling time (years) between OWID points: actual vs paper Eq.13 at the start year")
for a, b in ((1900, 1960), (1960, 2000), (1970, 2023)):
    g = math.log(pop[b] / pop[a]) / (b - a)
    print(f"{a}-{b}: actual doubling {math.log(2)/g:5.1f} yr; paper 0.445*(U-{a}) = {0.445*(U-a):5.1f} yr")

# [5] sensitivity: refit on ~24 points like the paper (year 1 .. 1958, thinned from OWID)
print("\n[5] refit on 24 thinned points (1..1957), several thinning offsets")
base = [(y, n) for y, n in rows if 1 <= y <= 1957]
for off in range(0, 7):
    sel = base[off::7][:24] if off else base[::8][:24]
    sel = sorted(set(sel + [base[-1]]))
    _, u, kk, ee = fit(sel)
    print(f"offset {off}: n={len(sel):2d} U={u:7.1f} K={kk:.2e} k={ee:.2f}")

# [6] same refit but least squares in linear N space (closer to a plain "least squares" reading)
print("\n[6] refit with least squares on N itself (grid over U, k; K solved exactly), data 1..1957")
def fitlin(sel):
    best = None
    for u10 in range(19580, 30000, 5):
        u = u10 / 10
        for k100 in range(50, 160, 2):
            kk = k100 / 100
            f = [(u - y) ** -kk for y, _ in sel]
            KK = sum(a * n for a, (_, n) in zip(f, sel)) / sum(a * a for a in f)
            sse = sum((KK * a - n) ** 2 for a, (_, n) in zip(f, sel))
            if best is None or sse < best[0]: best = (sse, u, KK, kk)
    return best
base57 = [(y, n) for y, n in rows if 1 <= y <= 1957]
for name, sel in (("all OWID points", base57), ("thinned to ~24", base57[::8])):
    _, u, KK, kk = fitlin(sel)
    print(f"{name:16s} n={len(sel):3d}  U={u:6.1f}  K={KK:.2e}  k={kk:.2f}  (paper: U=2026.87+-5.50, K=1.79e11, k=0.99)")
