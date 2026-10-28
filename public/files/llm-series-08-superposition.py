"""Measurements for part 8 of the "How an LLM works" guide series.

A. How many nearly perpendicular directions fit in 100 dimensions? Random vectors,
   then vectors pushed apart by gradient descent, against the Welch bound.
B. Does a sum of a few active directions let you read back which ones were active?
   Random directions, N features in 100 dimensions, k active at a time.
C. A tiny trained autoencoder with 20 features and 5 hidden dimensions: how many
   features does it keep as the inputs get sparser?

Usage: python llm-series-08-superposition.py [--only=ABC] [--big]
Needs only NumPy.
"""
import math
import sys
import time

import numpy as np


def unit(rng, n, d, dtype=np.float32):
    v = rng.standard_normal((n, d)).astype(dtype)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def welch(n, d):
    """Lower bound on the largest |cosine| among n unit vectors in d dimensions."""
    return 0.0 if n <= d else math.sqrt((n - d) / (d * (n - 1)))


# ---------------------------------------------------------------------- A
def angle_stats(v, label, chunk=2000):
    n = len(v)
    mx, outside_1, outside_5, count, s2 = 0.0, 0, 0, 0, 0.0
    c1, c5 = math.cos(math.radians(89)), math.cos(math.radians(85))
    for i in range(0, n, chunk):
        g = v[i:i + chunk] @ v.T
        rows = np.arange(g.shape[0])
        g[rows, i + rows] = 0.0  # ignore each vector against itself
        a = np.abs(g)
        mx = max(mx, float(a.max()))
        outside_1 += int((a > c1).sum())
        outside_5 += int((a > c5).sum())
        s2 += float((g.astype(np.float64) ** 2).sum())
        count += g.size - g.shape[0]
    print(f"{label}: largest |cos| {mx:.3f} (a pair {math.degrees(math.acos(mx)):.1f} degrees apart); "
          f"rms cos {math.sqrt(s2 / count):.4f}; pairs outside 89-91 degrees {outside_1 / count:.1%}; "
          f"outside 85-95 degrees {outside_5 / count:.1%}")
    return mx


def push_apart(n, steps, lr, tau, report, seed=0, d=100):
    """Gradient descent on the sum of max(0, |cos| - tau)^2 over all pairs, vectors kept at unit length."""
    rng = np.random.default_rng(seed)
    v = unit(rng, n, d)
    angle_stats(v, f"{n:,} random vectors")
    print(f"pushing them apart: tau = {tau}, step size {lr}")
    t0 = time.perf_counter()
    for step in range(1, steps + 1):
        g = v @ v.T
        np.fill_diagonal(g, 0.0)
        a = np.abs(g)
        e = np.where(a > tau, (a - tau) * np.sign(g), 0.0).astype(np.float32)
        v = v - lr * (e @ v) / n
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        if step in report:
            print(f"  step {step:>3} ({time.perf_counter() - t0:.0f}s): ", end="")
            angle_stats(v, "after")
    return v


def experiment_a(big):
    print("\n== A. how many nearly perpendicular directions fit in 100 dimensions? ==")
    d = 100
    print("Welch lower bound on the largest |cos| for N unit vectors in 100 dimensions:")
    for n in (100, 101, 200, 1000, 2000, 10_000):
        b = welch(n, d)
        print(f"  N = {n:>6}: >= {b:.4f}  (a pair at most {math.degrees(math.acos(b)):.1f} degrees from perpendicular on one side)")
    eps = math.cos(math.radians(89))
    print(f"if every pair had to be within 89-91 degrees (|cos| <= {eps:.5f}), Welch's relative bound allows at most "
          f"{d * (1 - eps**2) / (1 - d * eps**2):.0f} vectors in {d} dimensions")
    print()
    push_apart(2000, 300, 20.0, 0.15, {1, 50, 150, 300})
    print()
    if big:
        push_apart(10_000, 150, 20.0, 0.15, {1, 50, 100, 150})
    else:
        rng = np.random.default_rng(0)
        angle_stats(unit(rng, 10_000, d), "10,000 random vectors")
        print("(run with --big to also attempt the 10,000-vector optimization, which takes about 6 minutes)")


# ---------------------------------------------------------------------- B
def experiment_b():
    print("\n== B. reading back which features are active, 100 dimensions ==")
    d, trials = 100, 1000
    rng = np.random.default_rng(0)
    ns = (100, 300, 1000, 3000, 10_000)
    ks = (1, 2, 3, 5, 10)
    print(f"exact recovery of the active set (top-k dot products), {trials} trials each")
    print(f"{'features N':>11}" + "".join(f"{'k=' + str(k):>9}" for k in ks))
    for n in ns:
        v = unit(rng, n, d)
        row = []
        for k in ks:
            ok = 0
            for _ in range(trials):
                active = rng.choice(n, size=k, replace=False)
                x = v[active].sum(axis=0)
                got = np.argpartition(-(v @ x), k)[:k]
                ok += set(got.tolist()) == set(active.tolist())
            row.append(ok / trials)
        print(f"{n:>11,}" + "".join(f"{r:>9.1%}" for r in row))


# ---------------------------------------------------------------------- C
def train_toy(sparsity, seed, n=20, m=5, steps=6000, batch=1024):
    rng = np.random.default_rng(seed)
    W = (rng.standard_normal((m, n)) * 0.3)
    b = np.zeros(n)
    params = {"W": W, "b": b}
    mom = {k: np.zeros_like(v) for k, v in params.items()}
    var = {k: np.zeros_like(v) for k, v in params.items()}
    for t in range(1, steps + 1):
        mask = rng.random((batch, n)) > sparsity
        x = mask * rng.random((batch, n))
        h = x @ W.T
        z = h @ W + b
        y = np.maximum(z, 0)
        dz = 2 * (y - x) / batch * (z > 0)
        gW = h.T @ dz + (dz @ W.T).T @ x
        gb = dz.sum(axis=0)
        for k, g in (("W", gW), ("b", gb)):
            mom[k] = 0.9 * mom[k] + 0.1 * g
            var[k] = 0.999 * var[k] + 0.001 * g**2
            params[k] -= 0.01 * (mom[k] / (1 - 0.9**t)) / (np.sqrt(var[k] / (1 - 0.999**t)) + 1e-8)
    return W, float(((y - x) ** 2).sum(axis=1).mean())


def experiment_c():
    print("\n== C. a trained autoencoder: 20 features squeezed into 5 dimensions ==")
    print("each feature is 0 (with probability = sparsity) or a random value in [0, 1]; 3 random starts per row")
    print(f"{'sparsity':>9}{'features kept (norm > 0.5)':>30}{'loss per input':>16}{'largest cosine among kept':>27}")
    for s in (0.0, 0.5, 0.8, 0.9, 0.95, 0.99):
        kept, losses, coss = [], [], []
        for seed in range(3):
            W, loss = train_toy(s, seed)
            norms = np.linalg.norm(W, axis=0)
            idx = np.where(norms > 0.5)[0]
            kept.append(len(idx))
            losses.append(loss)
            if len(idx) > 1:
                u = W[:, idx] / norms[idx]
                c = np.abs(u.T @ u)
                np.fill_diagonal(c, 0)
                coss.append(float(c.max()))
        print(f"{s:>9}{str(kept):>30}{np.mean(losses):>16.4f}{(max(coss) if coss else float('nan')):>27.3f}")


if __name__ == "__main__":
    only = next((a.split("=")[1] for a in sys.argv if a.startswith("--only=")), "ABC")
    print("python", sys.version.split()[0], "numpy", np.__version__)
    if "A" in only:
        experiment_a("--big" in sys.argv)
    if "B" in only:
        experiment_b()
    if "C" in only:
        experiment_c()
