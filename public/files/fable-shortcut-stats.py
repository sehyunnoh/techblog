"""Recompute what the published tables in Goodhart Labs' "Fable 5.2 Tries Less on
Some Hard Tasks When a Shortcut is Available" (2026-11-24) can and cannot support.

Every input below is copied from the article's tables. No raw data was released, so
nothing here uses per-run values. Requires scipy and numpy.

    python fable-shortcut-stats.py
"""
from math import sqrt

import numpy as np
from scipy import stats

print("== 1. Count comparisons (exact tests, two-sided)")
counts = {
    # name: (k_present, n_present, k_absent, n_absent)
    "Original: quit within 3 min": (12, 17, 6, 19),
    "Original: every problem right": (0, 17, 2, 19),
    "Easier: quit within 3 min": (0, 9, 0, 8),
}
for name, (a, n1, c, n2) in counts.items():
    table = [[a, n1 - a], [c, n2 - c]]
    fisher = stats.fisher_exact(table).pvalue
    barnard = stats.barnard_exact(table).pvalue
    boschloo = stats.boschloo_exact(table).pvalue
    print(f"{name:32s} {a}/{n1} vs {c}/{n2}  Fisher p={fisher:.4f}  "
          f"Barnard p={barnard:.4f}  Boschloo p={boschloo:.4f}")

# Bonferroni across the nine task/variant comparisons the article reports.
p_quit = stats.fisher_exact([[12, 5], [6, 13]]).pvalue
print(f"Bonferroni x9 on quit-rate Fisher p: {min(1, 9 * p_quit):.3f}")

print("\n== 2. The eight runs the classifier terminated")
# The article does not say which condition they were in, or how they would have
# ended. Enumerate every allocation: k of the 8 in 'present', of which q quit fast;
# 8-k in 'absent', of which r quit fast.
print("k_present  min_p    max_p    share_of_(q,r)_with_p<0.05")
rows = []
for k in range(9):
    ps = []
    for q in range(k + 1):
        for r in range(8 - k + 1):
            t = [[12 + q, 5 + k - q], [6 + r, 13 + (8 - k) - r]]
            ps.append(stats.fisher_exact(t).pvalue)
    ps = np.array(ps)
    rows.append((k, ps.min(), ps.max(), (ps < 0.05).mean()))
    print(f"{k:9d}  {ps.min():.4f}  {ps.max():.4f}  {(ps < 0.05).mean():.2f}")
all_ps = []
for k in range(9):
    for q in range(k + 1):
        for r in range(8 - k + 1):
            t = [[12 + q, 5 + k - q], [6 + r, 13 + (8 - k) - r]]
            all_ps.append(stats.fisher_exact(t).pvalue)
all_ps = np.array(all_ps)
print(f"All {len(all_ps)} allocations: {np.sum(all_ps < 0.05)} keep p<0.05")

print("\n== 3. Minutes worked: what the means imply about runs that did NOT quit")
# Mean is printed to 0.1 min, so the true mean lies in [m-0.05, m+0.05).
# Quitters worked somewhere in [0, 3] min. Bound the mean of the non-quitters.
def nonquitter_bounds(mean, n, quitters):
    total_lo, total_hi = (mean - 0.05) * n, (mean + 0.05) * n
    rest = n - quitters
    lo = (total_lo - quitters * 3) / rest  # quitters used the full 3 minutes
    hi = total_hi / rest                   # quitters used 0 minutes
    return max(lo, 0), hi
for label, mean, n, quit in [("present", 3.9, 17, 12), ("absent", 12.3, 19, 6)]:
    lo, hi = nonquitter_bounds(mean, n, quit)
    print(f"{label:8s} {n - quit} non-quitters averaged between {lo:.2f} and {hi:.2f} min")

print("\n== 4. Break-even standard deviation for each minutes comparison")
# With only means published, a Welch/Student t-test cannot be run. Instead: the
# largest common per-run SD at which the gap would still reach p<0.05 (pooled t).
minutes = {
    "Mental arithmetic, original": (3.9, 17, 12.3, 19),
    "Mental arithmetic, easier": (9.1, 9, 7.7, 8),
    "Home valuation, impossible": (32, 11, 48, 10),
    "Home valuation, borderline": (97, 10, 93, 10),
    "Home valuation, possible": (70, 10, 67, 10),
    "LoRA repair": (136, 5, 132, 5),
    "Locked chip": (95, 5, 93, 5),
    "Chess compression": (125, 5, 149, 5),
    "Word search": (46, 5, 48, 5),
}
for name, (m1, n1, m2, n2) in minutes.items():
    tcrit = stats.t.ppf(0.975, n1 + n2 - 2)
    sd = abs(m1 - m2) / (tcrit * sqrt(1 / n1 + 1 / n2))
    pooled_mean = (m1 * n1 + m2 * n2) / (n1 + n2)
    print(f"{name:30s} gap {abs(m1 - m2):5.1f} min  break-even SD {sd:6.2f} min "
          f"({100 * sd / pooled_mean:5.1f}% of mean)")

print("\n== 5. Power of a two-sample t-test at alpha=0.05 (two-sided)")
def power(d, n):
    df = 2 * n - 2
    nc = d * sqrt(n / 2)
    tcrit = stats.t.ppf(0.975, df)
    return stats.nct.sf(tcrit, df, nc) + stats.nct.cdf(-tcrit, df, nc)
for d in (0.5, 1.0, 1.5, 2.0):
    line = "  ".join(f"n={n}:{power(d, n):.2f}" for n in (5, 10, 17, 20, 40))
    need = next(n for n in range(2, 500) if power(d, n) >= 0.8)
    print(f"d={d}: {line}  (n per arm for 80%: {need})")
print("Smallest exact two-sided Mann-Whitney p with 5 v 5:",
      f"{stats.mannwhitneyu([1,2,3,4,5],[6,7,8,9,10], method='exact').pvalue:.4f}")
print("Fisher p for 5 v 5 at 0/5 vs 5/5, 1/5 vs 5/5, 1/5 vs 4/5:",
      ", ".join(f"{stats.fisher_exact(t).pvalue:.4f}" for t in
                ([[0, 5], [5, 0]], [[1, 4], [5, 0]], [[1, 4], [4, 1]])))
print("Chart data, power at d=1.0 for n=3..40:",
      [float(round(power(1.0, n), 3)) for n in range(3, 41)])
print("Chart data, power at d=0.5 for n=3..40:",
      [float(round(power(0.5, n), 3)) for n in range(3, 41)])
