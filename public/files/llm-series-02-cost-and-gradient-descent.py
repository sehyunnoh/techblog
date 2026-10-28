"""Measurements for part 2 of the "How an LLM works" guide series.

A. Cost of an untrained 784-16-16-10 network (squared-error cost).
B. Gradient descent on a one-parameter bumpy function: where you start decides
   where you end, and the step size can make it diverge.
C. What a gradient entry means: nudge single parameters and compare the change
   in cost with what the gradient predicted.
D. Full-batch gradient descent on the real network: cost and accuracy curves,
   five random starts, and a learning-rate sweep.

The function `grads` computes the gradient with backpropagation. How and why it
works is the subject of part 3; here it is a black box that is checked against
finite differences in experiment C.

Usage: python llm-series-02-cost-and-gradient-descent.py <cache-dir> [json-out] [--only=ABCD]
Needs only NumPy. MNIST is downloaded once into <cache-dir>.
"""
import gzip
import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

MNIST_BASE = "https://ossci-datasets.s3.amazonaws.com/mnist/"
SIZES = [784, 16, 16, 10]
N_TRAIN = 10_000  # first 10,000 training images keep each run to seconds
STEPS = 1500


def mnist(cache: Path, split: str):
    cache.mkdir(parents=True, exist_ok=True)

    def fetch(name):
        p = cache / name
        if not p.exists():
            urllib.request.urlretrieve(MNIST_BASE + name, p)
        return gzip.decompress(p.read_bytes())

    x = np.frombuffer(fetch(f"{split}-images-idx3-ubyte.gz"), np.uint8, offset=16)
    y = np.frombuffer(fetch(f"{split}-labels-idx1-ubyte.gz"), np.uint8, offset=8)
    return x.reshape(-1, 784), y


def init(seed, dtype=np.float32):
    rng = np.random.default_rng(seed)
    ws = [rng.standard_normal((o, i)).astype(dtype) / np.sqrt(i) for i, o in zip(SIZES, SIZES[1:])]
    bs = [np.zeros(o, dtype) for o in SIZES[1:]]
    return ws, bs


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def forward(ws, bs, x):
    """x: (n, 784). Returns the list of activations, one (n, size) array per layer."""
    acts = [x]
    for w, b in zip(ws, bs):
        acts.append(sigmoid(acts[-1] @ w.T + b))
    return acts


def cost(ws, bs, x, t):
    """Mean over images of the sum over outputs of (output - target)^2."""
    out = forward(ws, bs, x)[-1]
    return float(((out - t) ** 2).sum(axis=1).mean())


def accuracy(ws, bs, x, y):
    return float((forward(ws, bs, x)[-1].argmax(axis=1) == y).mean())


def grads(ws, bs, x, t):
    """Gradient of `cost` with respect to every weight and bias (backpropagation)."""
    acts = forward(ws, bs, x)
    n = x.shape[0]
    a = acts[-1]
    delta = 2 * (a - t) * a * (1 - a) / n
    gw, gb = [None] * len(ws), [None] * len(bs)
    for l in range(len(ws) - 1, -1, -1):
        gw[l] = delta.T @ acts[l]
        gb[l] = delta.sum(axis=0)
        if l:
            delta = (delta @ ws[l]) * acts[l] * (1 - acts[l])
    return gw, gb


# ---------------------------------------------------------------------- A
def experiment_a(xt, t, yt):
    print("\n== A. cost of an untrained network ==")
    costs, accs = [], []
    for seed in range(20):
        ws, bs = init(seed)
        costs.append(cost(ws, bs, xt, t))
        accs.append(accuracy(ws, bs, xt, yt))
    print(f"cost over 20 random starts (10,000 test images): mean {np.mean(costs):.3f}, "
          f"min {min(costs):.3f}, max {max(costs):.3f}")
    # A network that outputs 0.1 for everything, and one that outputs all zeros.
    flat = float(((np.full((len(t), 10), 0.1) - t) ** 2).sum(axis=1).mean())
    zeros = float((t ** 2).sum(axis=1).mean())
    print(f"reference costs: all outputs 0.1 -> {flat:.3f}; all outputs 0 -> {zeros:.3f}")
    ws, bs = init(0)
    out = forward(ws, bs, xt[:1])[-1][0]
    print("seed 0, first image, label", int(yt[0]), "outputs", np.round(out, 2).tolist(),
          "cost for this image", round(float(((out - t[0]) ** 2).sum()), 3))


# ---------------------------------------------------------------------- B
def experiment_b():
    print("\n== B. gradient descent in one dimension ==")

    def f(x):
        return 0.1 * x**4 - 0.8 * x**2 + 0.3 * x

    def df(x):
        return 0.4 * x**3 - 1.6 * x + 0.3

    xs = np.linspace(-4, 4, 4001)
    ys = f(xs)
    interior = (ys[1:-1] < ys[:-2]) & (ys[1:-1] < ys[2:])
    minima = xs[1:-1][interior]
    print("local minima of f at x =", np.round(minima, 3).tolist(), "values", np.round(f(minima), 3).tolist())

    res = {}
    for start in (-3.0, -1.0, 0.5, 3.0):
        x = start
        for _ in range(200):
            x -= 0.1 * df(x)
        res[start] = (x, f(x))
        print(f"start {start:+.1f}, lr 0.1, 200 steps -> x = {x:+.3f}, f = {f(x):+.3f}")

    # Step size: too small, fine, too large.
    for lr in (0.01, 0.1, 0.5, 1.2):
        x = -3.0
        hist = [x]
        for _ in range(50):
            x -= lr * df(x)
            hist.append(x)
            if abs(x) > 1e6:
                break
        print(f"start -3.0, lr {lr}: after {len(hist) - 1} steps x = {hist[-1]:.4g}, f = {f(hist[-1]):.4g}")
    return {"minima": minima.tolist()}


# ---------------------------------------------------------------------- C
def experiment_c(xt, t):
    print("\n== C. what a gradient entry means ==")
    ws, bs = init(0, np.float64)
    x, tt = xt[:200].astype(np.float64) / 255, t[:200].astype(np.float64)
    gw, gb = grads(ws, bs, x, tt)
    base = cost(ws, bs, x, tt)
    eps = 1e-5
    rng = np.random.default_rng(0)
    # Eight distinct parameters: one weight on a corner pixel (pixel 0, always black), one on a
    # centre pixel (pixel 400), and six drawn at random from all three layers.
    picks = [(0, 3, 0), (0, 3, 400)]
    while len(picks) < 8:
        layer = int(rng.integers(0, 3))
        pick = (layer, int(rng.integers(0, ws[layer].shape[0])), int(rng.integers(0, ws[layer].shape[1])))
        if pick not in picks:
            picks.append(pick)
    print(f"cost on 200 images: {base:.5f}; nudge each parameter by {eps}")
    print(f"{'parameter':<18}{'gradient':>12}{'cost change / nudge':>22}")
    worst = 0.0
    for layer, i, j in picks:
        ws[layer][i, j] += eps
        num = (cost(ws, bs, x, tt) - base) / eps
        ws[layer][i, j] -= eps
        g = gw[layer][i, j]
        worst = max(worst, abs(num - g) / (abs(g) + 1e-12))
        print(f"W{layer + 1}[{i},{j}]".ljust(18) + f"{g:12.6f}{num:22.6f}")
    print(f"largest relative difference over these 8: {worst:.2e}")
    allg = np.concatenate([g.ravel() for g in gw + gb])
    print(f"gradient entries: {allg.size:,}; largest |g| {np.abs(allg).max():.4f}, "
          f"median |g| {np.median(np.abs(allg)):.6f}")
    per_layer = [float(np.linalg.norm(g)) for g in gw]
    print("gradient norm per weight matrix:", np.round(per_layer, 4).tolist())


# ---------------------------------------------------------------------- D
def train(seed, lr, x, t, y, xt, yt, steps=STEPS, every=50):
    ws, bs = init(seed)
    curve = []
    t0 = time.perf_counter()
    for step in range(steps + 1):
        if step % every == 0:
            curve.append((step, cost(ws, bs, x, t), accuracy(ws, bs, xt, yt)))
        if step == steps:
            break
        gw, gb = grads(ws, bs, x, t)
        for l in range(len(ws)):
            ws[l] -= lr * gw[l]
            bs[l] -= lr * gb[l]
    secs = time.perf_counter() - t0
    return curve, secs, ws, bs


def experiment_d(x, t, y, xt, yt, out):
    print(f"\n== D. gradient descent on the real network ({N_TRAIN:,} training images, {STEPS} full-batch steps) ==")
    lr = 3.0
    runs = {}
    for seed in range(5):
        curve, secs, ws, bs = train(seed, lr, x, t, y, xt, yt)
        runs[seed] = curve
        c0, cN = curve[0], curve[-1]
        print(f"seed {seed}, lr {lr}: cost {c0[1]:.3f} -> {cN[1]:.3f}, test accuracy {c0[2]:.1%} -> {cN[2]:.1%}, {secs:.0f}s")
        if seed == 0:
            for s, c, a in curve:
                if s in (0, 50, 100, 200, 400, 800, 1500):
                    print(f"   step {s:>5}: cost {c:.3f}, test accuracy {a:.1%}")
    finals = [(r[-1][1], r[-1][2]) for r in runs.values()]
    print("final cost per seed:", [round(c, 3) for c, _ in finals],
          "accuracy per seed:", [round(a, 3) for _, a in finals])

    print("\nlearning-rate sweep, seed 0")
    sweep = {}
    for lr in (0.1, 0.5, 1.0, 3.0, 10.0, 30.0, 100.0):
        curve, secs, *_ = train(0, lr, x, t, y, xt, yt, steps=500, every=100)
        sweep[lr] = curve
        print(f"lr {lr:>6}: cost after 500 steps {curve[-1][1]:.3f}, test accuracy {curve[-1][2]:.1%}"
              f"  (cost at steps {[s for s, _, _ in curve]}: {[round(c, 3) for _, c, _ in curve]})")
    if out:
        Path(out).write_text(json.dumps({"runs": runs, "sweep": {str(k): v for k, v in sweep.items()}}))


if __name__ == "__main__":
    cache = Path(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
    only = next((a.split("=")[1] for a in sys.argv if a.startswith("--only=")), "ABCD")
    print("python", sys.version.split()[0], "numpy", np.__version__)
    xtr, ytr = mnist(cache, "train")
    xte, yte = mnist(cache, "t10k")
    x = xtr[:N_TRAIN].astype(np.float32) / 255
    y = ytr[:N_TRAIN]
    xt = xte.astype(np.float32) / 255
    t = np.eye(10, dtype=np.float32)[y]
    tt = np.eye(10, dtype=np.float32)[yte]
    if "A" in only:
        experiment_a(xt, tt, yte)
    if "B" in only:
        experiment_b()
    if "C" in only:
        experiment_c(xte, tt)
    if "D" in only:
        experiment_d(x, t, y, xt, yte, out)
