"""Measurements for part 4 of the "How an LLM works" guide series.

A. Sigmoid versus ReLU hidden neurons on the 784-16-16-10 network, trained with
   mini-batch SGD on MNIST. The learning rate is picked per activation on a
   held-out validation slice, then the test accuracy is reported.
B. Vanishing gradients: the size of the gradient in each layer of a network with
   eight hidden layers, at initialization, for both activations, and what happens
   when you train it.
C. What the four trained networks (two activations x two costs) say about images
   that are not digits at all (uniform random pixels). With the softmax networks the
   outputs are real probabilities.
D. Memorization: a larger network trained on 2,000 images with their true labels
   and with shuffled labels.
E. Why ReLU lost in A: the same shallow network with each hidden activation paired
   with each cost function, and a count of ReLU neurons that never switch on.

Usage: python llm-series-04-training-in-practice.py <cache-dir> [--only=ABCDE]
Needs only NumPy. MNIST is downloaded once into <cache-dir>.
"""
import gzip
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np

MNIST_BASE = "https://ossci-datasets.s3.amazonaws.com/mnist/"
F = np.float32


def mnist(cache: Path, split: str):
    cache.mkdir(parents=True, exist_ok=True)

    def fetch(name):
        p = cache / name
        if not p.exists():
            urllib.request.urlretrieve(MNIST_BASE + name, p)
        return gzip.decompress(p.read_bytes())

    x = np.frombuffer(fetch(f"{split}-images-idx3-ubyte.gz"), np.uint8, offset=16)
    y = np.frombuffer(fetch(f"{split}-labels-idx1-ubyte.gz"), np.uint8, offset=8)
    return x.reshape(-1, 784).astype(F) / 255, y


# ------------------------------------------------------------------ the network
class Net:
    """Fully connected network. hidden: 'sigmoid' or 'relu'. out: 'mse' (sigmoid outputs,
    squared-error cost, as in parts 1 to 3) or 'ce' (softmax outputs, cross-entropy cost)."""

    def __init__(self, sizes, hidden, out="mse", seed=0):
        rng = np.random.default_rng(seed)
        self.hidden, self.out = hidden, out
        gain = 2.0 if hidden == "relu" else 1.0  # He scaling for ReLU, 1/sqrt(n) for sigmoid
        self.w = [(rng.standard_normal((o, i)) * np.sqrt(gain / i)).astype(F) for i, o in zip(sizes, sizes[1:])]
        self.b = [np.zeros(o, F) for o in sizes[1:]]

    def forward(self, x):
        acts = [x]
        for l, (w, b) in enumerate(zip(self.w, self.b)):
            z = acts[-1] @ w.T + b
            if l < len(self.w) - 1:
                a = np.maximum(z, 0) if self.hidden == "relu" else 1 / (1 + np.exp(-z))
            elif self.out == "mse":
                a = 1 / (1 + np.exp(-z))
            else:
                e = np.exp(z - z.max(axis=1, keepdims=True))
                a = e / e.sum(axis=1, keepdims=True)
            acts.append(a)
        return acts

    def predict(self, x):
        return self.forward(x)[-1]

    def accuracy(self, x, y):
        return float((self.predict(x).argmax(axis=1) == y).mean())

    def grads(self, x, t):
        acts = self.forward(x)
        n = x.shape[0]
        a = acts[-1]
        delta = (2 * (a - t) * a * (1 - a) / n) if self.out == "mse" else (a - t) / n
        gw, gb = [None] * len(self.w), [None] * len(self.b)
        for l in range(len(self.w) - 1, -1, -1):
            gw[l] = delta.T @ acts[l]
            gb[l] = delta.sum(axis=0)
            if l:
                slope = (acts[l] > 0).astype(F) if self.hidden == "relu" else acts[l] * (1 - acts[l])
                delta = (delta @ self.w[l]) * slope
        return gw, gb

    def step(self, x, t, lr):
        gw, gb = self.grads(x, t)
        for l in range(len(self.w)):
            self.w[l] -= lr * gw[l]
            self.b[l] -= lr * gb[l]


def sgd(net, x, t, epochs, lr, batch, seed=0, on_epoch=None):
    rng = np.random.default_rng(seed)
    for ep in range(1, epochs + 1):
        order = rng.permutation(len(x))
        for i in range(0, len(x), batch):
            idx = order[i:i + batch]
            net.step(x[idx], t[idx], lr)
        if on_epoch:
            on_epoch(ep)


def onehot(y):
    return np.eye(10, dtype=F)[y]


# ---------------------------------------------------------------------- A
def experiment_a(xtr, ytr, xte, yte):
    print("\n== A. sigmoid versus ReLU, 784-16-16-10, mini-batch 100, 10 epochs ==")
    x, y = xtr[:55_000], ytr[:55_000]
    xv, yv = xtr[55_000:], ytr[55_000:]
    t = onehot(y)
    grid = {"sigmoid": [1.0, 3.0, 10.0], "relu": [0.03, 0.1, 0.3, 1.0]}
    best = {}
    for act, rates in grid.items():
        for lr in rates:
            net = Net([784, 16, 16, 10], act, "mse", seed=0)
            curve = []
            t0 = time.perf_counter()
            sgd(net, x, t, 10, lr, 100, on_epoch=lambda ep: curve.append(net.accuracy(xv, yv)))
            secs = time.perf_counter() - t0
            ok = np.isfinite(net.w[0]).all()
            print(f"{act:>8} lr {lr:<5} validation accuracy per epoch 1,2,5,10: "
                  f"{curve[0]:.1%} {curve[1]:.1%} {curve[4]:.1%} {curve[9]:.1%}  ({secs:.0f}s, finite={ok})")
            if act not in best or curve[-1] > best[act][0]:
                best[act] = (curve[-1], lr, net, curve)
    print("\nbest learning rate per activation (by validation accuracy at epoch 10), test accuracy:")
    for act, (v, lr, net, curve) in best.items():
        print(f"{act:>8}: lr {lr}, validation {v:.1%}, test {net.accuracy(xte, yte):.1%}; validation by epoch:"
              f" {[round(c * 100, 1) for c in curve]}")
    return {f"{a}+mse": b[2] for a, b in best.items()}


# ---------------------------------------------------------------------- B
def experiment_b(xtr, ytr, xte, yte):
    print("\n== B. eight hidden layers of 16 neurons ==")
    sizes = [784] + [16] * 8 + [10]
    xb, tb = xtr[:1000], onehot(ytr[:1000])
    norms = {}
    for act in ("sigmoid", "relu"):
        net = Net(sizes, act, "mse", seed=0)
        gw, _ = net.grads(xb, tb)
        norms[act] = [float(np.linalg.norm(g)) for g in gw]
        print(f"{act:>8} gradient norm per weight matrix, first layer to last:")
        print("         " + "  ".join(f"{v:.2e}" for v in norms[act]))
        print(f"         first-layer / last-layer = {norms[act][0] / norms[act][-1]:.2e}")
    print("\ntraining the deep networks, 5 epochs, mini-batch 100, 55,000 images")
    x, y = xtr[:55_000], ytr[:55_000]
    t = onehot(y)
    for act, rates in {"sigmoid": [3.0, 10.0], "relu": [0.1, 0.3]}.items():
        for lr in rates:
            net = Net(sizes, act, "mse", seed=0)
            sgd(net, x, t, 5, lr, 100)
            print(f"{act:>8} lr {lr:<5} test accuracy after 5 epochs: {net.accuracy(xte, yte):.1%}")


# ---------------------------------------------------------------------- C
def experiment_c(nets, xte, yte):
    print("\n== C. images that are not digits ==")
    rng = np.random.default_rng(0)
    noise = rng.random((1000, 784), dtype=F)
    for act, net in nets.items():
        on_real = net.predict(xte).max(axis=1)
        on_noise = net.predict(noise)
        mx = on_noise.max(axis=1)
        cls = np.bincount(on_noise.argmax(axis=1), minlength=10)
        print(f"{act:>13}: mean top output on real test images {on_real.mean():.3f}; "
              f"on 1,000 noise images {mx.mean():.3f}; noise images with top output >= 0.9: {(mx >= 0.9).sum()}; "
              f">= 0.5: {(mx >= 0.5).sum()}")
        print(f"          digit chosen for the noise images: {cls.tolist()}")
        print(f"          real test images with top output >= 0.9: {(on_real >= 0.9).mean():.1%}")


# ---------------------------------------------------------------------- D
def experiment_d(xtr, ytr, xte, yte):
    print("\n== D. memorization: 784-256-256-10, 2,000 training images, 400 epochs ==")
    n = 2000
    x = xtr[:n]
    rng = np.random.default_rng(0)
    for name, labels in (("true labels", ytr[:n]), ("shuffled labels", rng.permutation(ytr[:n]))):
        net = Net([784, 256, 256, 10], "relu", "ce", seed=0)
        t = onehot(labels)
        log = []

        def on_epoch(ep):
            if ep in (1, 5, 10, 20, 50, 100, 200, 300, 400):
                log.append((ep, net.accuracy(x, labels), net.accuracy(xte, yte)))

        sgd(net, x, t, 400, 0.05, 50, on_epoch=on_epoch)
        params = sum(w.size + b.size for w, b in zip(net.w, net.b))
        print(f"{name} ({params:,} parameters):")
        for ep, tr, te in log:
            print(f"   epoch {ep:>3}: training accuracy {tr:.1%}, test accuracy (true test labels) {te:.1%}")


# ---------------------------------------------------------------------- E
def experiment_e(xtr, ytr, xte, yte):
    print("\n== E. 2 x 2: hidden activation x cost function, 784-16-16-10, mini-batch 100, 10 epochs ==")
    x, y = xtr[:55_000], ytr[:55_000]
    xv, yv = xtr[55_000:], ytr[55_000:]
    t = onehot(y)
    grids = {"mse": [0.1, 0.3, 1.0, 3.0], "ce": [0.03, 0.1, 0.3, 1.0]}
    nets = {}
    for out in ("mse", "ce"):
        for act in ("sigmoid", "relu"):
            best = None
            for lr in grids[out]:
                net = Net([784, 16, 16, 10], act, out, seed=0)
                sgd(net, x, t, 10, lr, 100)
                v = net.accuracy(xv, yv)
                if best is None or v > best[0]:
                    best = (v, lr, net)
            v, lr, net = best
            nets[f"{act}+{out}"] = net
            line = f"{act:>8} + {out:<3}: best lr {lr}, validation {v:.1%}, test {net.accuracy(xte, yte):.1%}"
            if act == "relu":
                hid = net.forward(xv)[1:-1]
                dead = sum(int((h.max(axis=0) == 0).sum()) for h in hid)
                line += f"; hidden ReLU neurons that never fire on 5,000 validation images: {dead} of {sum(h.shape[1] for h in hid)}"
            print(line)
    # How many ReLU neurons are dead at initialization, before any training?
    net = Net([784, 16, 16, 10], "relu", "mse", seed=0)
    hid = net.forward(xv)[1:-1]
    print("at initialization (seed 0), never-firing hidden ReLU neurons:",
          sum(int((h.max(axis=0) == 0).sum()) for h in hid), "of 32")
    return nets


if __name__ == "__main__":
    cache = Path(sys.argv[1])
    only = next((a.split("=")[1] for a in sys.argv if a.startswith("--only=")), "ABCDE")
    print("python", sys.version.split()[0], "numpy", np.__version__)
    xtr, ytr = mnist(cache, "train")
    xte, yte = mnist(cache, "t10k")
    nets = {}
    if "A" in only or "C" in only:
        nets.update(experiment_a(xtr, ytr, xte, yte))
    if "B" in only:
        experiment_b(xtr, ytr, xte, yte)
    if "E" in only or "C" in only:
        nets.update(experiment_e(xtr, ytr, xte, yte))
    if "C" in only:
        experiment_c({k: nets[k] for k in ("sigmoid+mse", "relu+mse", "sigmoid+ce", "relu+ce")}, xte, yte)
    if "D" in only:
        experiment_d(xtr, ytr, xte, yte)
    if "E" in only:
        experiment_e(xtr, ytr, xte, yte)
