"""Measurements for part 3 of the "How an LLM works" guide series.

A. The cost of finding a gradient the slow way (nudge every parameter, re-run
   the network) versus one backward pass, and whether the two agree.
B. The one-neuron-per-layer chain from the textbook derivation: the three
   factors of the chain rule, multiplied, against a numerical derivative.
C. Why a weight's gradient scales with the input it multiplies: in a real batch,
   weights that hang off pixels that are always black get exactly zero gradient.
D. How good a mini-batch is as a stand-in for the full gradient: cosine
   similarity and relative error against the gradient over all 10,000 images,
   for batch sizes 1 to 1,000.
E. Whether that noisy stand-in still trains faster: the same amount of gradient
   work (10 passes over 10,000 images) spent as a few big steps or many small ones.

Usage: python llm-series-03-backpropagation.py <cache-dir>
Needs only NumPy. MNIST is downloaded once into <cache-dir>.
"""
import gzip
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

MNIST_BASE = "https://ossci-datasets.s3.amazonaws.com/mnist/"
SIZES = [784, 16, 16, 10]


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


def init(seed, dtype=np.float64):
    rng = np.random.default_rng(seed)
    ws = [rng.standard_normal((o, i)).astype(dtype) / np.sqrt(i) for i, o in zip(SIZES, SIZES[1:])]
    bs = [np.zeros(o, dtype) for o in SIZES[1:]]
    return ws, bs


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def forward(ws, bs, x):
    acts = [x]
    for w, b in zip(ws, bs):
        acts.append(sigmoid(acts[-1] @ w.T + b))
    return acts


def cost(ws, bs, x, t):
    out = forward(ws, bs, x)[-1]
    return float(((out - t) ** 2).sum(axis=1).mean())


def backprop(ws, bs, x, t):
    """Returns (grad_w, grad_b, deltas). deltas[l] is dCost/d(weighted sum) at layer l."""
    acts = forward(ws, bs, x)
    n = x.shape[0]
    a = acts[-1]
    delta = 2 * (a - t) * a * (1 - a) / n
    gw, gb, deltas = [None] * len(ws), [None] * len(bs), [None] * len(ws)
    for l in range(len(ws) - 1, -1, -1):
        deltas[l] = delta
        gw[l] = delta.T @ acts[l]
        gb[l] = delta.sum(axis=0)
        if l:
            delta = (delta @ ws[l]) * acts[l] * (1 - acts[l])
    return gw, gb, deltas


def flat(gw, gb):
    return np.concatenate([g.ravel() for g in gw] + [g.ravel() for g in gb])


# ---------------------------------------------------------------------- A
def experiment_a(x, t):
    print("\n== A. one backward pass versus nudging every parameter ==")
    xb, tb = x[:100], t[:100]
    ws, bs = init(0)
    n_params = sum(w.size for w in ws) + sum(b.size for b in bs)

    t0 = time.perf_counter()
    for _ in range(200):
        cost(ws, bs, xb, tb)
    fwd = (time.perf_counter() - t0) / 200

    t0 = time.perf_counter()
    for _ in range(200):
        gw, gb, _ = backprop(ws, bs, xb, tb)
    bwd = (time.perf_counter() - t0) / 200
    g_bp = flat(gw, gb)

    eps = 1e-6
    g_num = np.empty(n_params)
    k = 0
    t0 = time.perf_counter()
    for arrays in (ws, bs):
        for arr in arrays:
            it = np.nditer(arr, flags=["multi_index"], op_flags=["readwrite"])
            for v in it:
                old = float(v)
                arr[it.multi_index] = old + eps
                up = cost(ws, bs, xb, tb)
                arr[it.multi_index] = old - eps
                dn = cost(ws, bs, xb, tb)
                arr[it.multi_index] = old
                g_num[k] = (up - dn) / (2 * eps)
                k += 1
    slow = time.perf_counter() - t0
    # numerical gradient was filled weights-first then biases, matching flat()'s order only
    # if we reorder: flat() is [all weights..., all biases...], and so was the loop above.
    err = np.abs(g_num - g_bp)
    rel = err / (np.abs(g_bp) + 1e-12)
    print(f"parameters: {n_params:,}; batch of 100 images")
    print(f"one forward pass (cost): {fwd * 1000:.3f} ms")
    print(f"one backward pass (cost + full gradient): {bwd * 1000:.3f} ms  ({bwd / fwd:.1f}x a forward pass)")
    print(f"nudging every parameter (central differences, {2 * n_params:,} forward passes): {slow:.2f} s")
    print(f"speedup of backprop over nudging: {slow / bwd:,.0f}x")
    print(f"max absolute difference between the two gradients: {err.max():.2e}")
    print(f"max |gradient|: {np.abs(g_bp).max():.4f}; entries with relative difference above 1e-4 "
          f"(where |g| > 1e-6): {int(((rel > 1e-4) & (np.abs(g_bp) > 1e-6)).sum())}")


# ---------------------------------------------------------------------- B
def experiment_b():
    print("\n== B. the chain rule on a one-neuron-per-layer network ==")
    rng = np.random.default_rng(1)
    w = rng.standard_normal(3)
    b = rng.standard_normal(3)
    a0, y = 0.7, 1.0

    def run(w):
        a, zs, acts = a0, [], [a0]
        for i in range(3):
            z = w[i] * a + b[i]
            a = sigmoid(z)
            zs.append(z)
            acts.append(a)
        return acts, zs, (a - y) ** 2

    acts, zs, c = run(w)
    # dC/dw_last = (dz/dw) * (da/dz) * (dC/da)
    dz_dw = acts[2]
    da_dz = acts[3] * (1 - acts[3])
    dc_da = 2 * (acts[3] - y)
    analytic = dz_dw * da_dz * dc_da
    eps = 1e-6
    wp, wm = w.copy(), w.copy()
    wp[2] += eps
    wm[2] -= eps
    numeric = (run(wp)[2] - run(wm)[2]) / (2 * eps)
    print(f"last-layer weight: dz/dw = {dz_dw:.4f} (the input activation), da/dz = {da_dz:.4f} "
          f"(slope of sigmoid), dC/da = {dc_da:.4f} (2 x error)")
    print(f"product {analytic:.6f}; numerical derivative {numeric:.6f}")

    # First weight: the signal has to travel back through two more layers.
    d = dc_da * da_dz
    d = d * w[2] * acts[2] * (1 - acts[2])
    d = d * w[1] * acts[1] * (1 - acts[1])
    analytic0 = acts[0] * d
    wp, wm = w.copy(), w.copy()
    wp[0] += eps
    wm[0] -= eps
    numeric0 = (run(wp)[2] - run(wm)[2]) / (2 * eps)
    print(f"first-layer weight, two layers further back: product {analytic0:.6f}; numerical {numeric0:.6f}")
    print(f"  ratio of first-layer to last-layer gradient: {abs(analytic0 / analytic):.3f}")


# ---------------------------------------------------------------------- C
def experiment_c(x, t):
    print("\n== C. weights on inputs that are never lit get no gradient ==")
    xb, tb = x[:1000], t[:1000]
    ws, bs = init(0)
    gw, gb, deltas = backprop(ws, bs, xb, tb)
    dead_pixels = np.where(xb.max(axis=0) == 0)[0]
    g1 = gw[0]
    zero_cols = int((np.abs(g1).max(axis=0) == 0).sum())
    print(f"pixels that are exactly 0 in all 1,000 images: {len(dead_pixels)} of 784")
    print(f"columns of the first-layer gradient that are exactly 0: {zero_cols} "
          f"({zero_cols * 16:,} of {g1.size:,} first-layer weights)")
    print(f"mean |gradient| for weights on the 10% brightest-on-average pixels: "
          f"{np.abs(g1[:, np.argsort(xb.mean(axis=0))[-78:]]).mean():.5f}; "
          f"on all other pixels: {np.abs(g1[:, np.argsort(xb.mean(axis=0))[:-78]]).mean():.5f}")
    print("per-layer share of the gradient's squared length:",
          [round(float((g ** 2).sum() / sum((h ** 2).sum() for h in gw)), 3) for g in gw])


# ---------------------------------------------------------------------- D
def experiment_d(x, t):
    print("\n== D. a mini-batch gradient against the full gradient ==")
    xs, ts = x[:10_000], t[:10_000]
    ws, bs = init(0)
    # Use a partly trained network so the gradient is not just "noise at initialization".
    for _ in range(200):
        gw, gb, _ = backprop(ws, bs, xs, ts)
        for l in range(3):
            ws[l] -= 3.0 * gw[l]
            bs[l] -= 3.0 * gb[l]
    gw, gb, _ = backprop(ws, bs, xs, ts)
    full = flat(gw, gb)
    print(f"cost of the network used: {cost(ws, bs, xs, ts):.3f} (after 200 full-batch steps)")
    rng = np.random.default_rng(0)
    print(f"{'batch':>6}{'cos sim (mean)':>16}{'rel error (mean)':>18}{'ms per gradient':>17}")
    for bsz in (1, 10, 100, 1000, 10000):
        coss, rels, secs = [], [], []
        for _ in range(100 if bsz < 10000 else 3):
            idx = rng.choice(10_000, bsz, replace=False)
            t0 = time.perf_counter()
            g = flat(*backprop(ws, bs, xs[idx], ts[idx])[:2])
            secs.append(time.perf_counter() - t0)
            coss.append(float(g @ full / (np.linalg.norm(g) * np.linalg.norm(full))))
            rels.append(float(np.linalg.norm(g - full) / np.linalg.norm(full)))
        print(f"{bsz:>6}{np.mean(coss):>16.3f}{np.mean(rels):>18.3f}{np.median(secs) * 1000:>17.3f}")


# ---------------------------------------------------------------------- E
def experiment_e(x, t, xt, yt):
    print("\n== E. the same gradient work, spent in different step sizes ==")
    xs, ts = x[:10_000], t[:10_000]
    epochs, lr = 10, 3.0
    print(f"{epochs} passes over {len(xs):,} images, learning rate {lr}, seed 0, data reshuffled each pass")
    print(f"{'batch':>6}{'steps':>8}{'train cost':>12}{'test acc':>10}{'seconds':>9}")
    for bsz in (10000, 1000, 100, 10):
        ws, bs = init(0)
        rng = np.random.default_rng(0)
        t0 = time.perf_counter()
        steps = 0
        for _ in range(epochs):
            order = rng.permutation(len(xs))
            for i in range(0, len(xs), bsz):
                idx = order[i:i + bsz]
                gw, gb, _ = backprop(ws, bs, xs[idx], ts[idx])
                for l in range(3):
                    ws[l] -= lr * gw[l]
                    bs[l] -= lr * gb[l]
                steps += 1
        secs = time.perf_counter() - t0
        acc = float((forward(ws, bs, xt)[-1].argmax(axis=1) == yt).mean())
        print(f"{bsz:>6}{steps:>8}{cost(ws, bs, xs, ts):>12.3f}{acc:>10.1%}{secs:>9.1f}")


if __name__ == "__main__":
    cache = Path(sys.argv[1])
    print("python", sys.version.split()[0], "numpy", np.__version__)
    xtr, ytr = mnist(cache, "train")
    x = xtr.astype(np.float64) / 255
    t = np.eye(10)[ytr]
    experiment_a(x, t)
    experiment_b()
    experiment_c(x, t)
    experiment_d(x, t)
    xte, yte = mnist(cache, "t10k")
    experiment_e(x, t, xte.astype(np.float64) / 255, yte)
