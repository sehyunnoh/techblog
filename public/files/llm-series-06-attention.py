"""Measurements for part 6 of the "How an LLM works" guide series.

A. One attention head in NumPy, and a leak test for the causal mask: change one
   token and see which outputs move.
B. The attention pattern is n x n: time and memory for one head as the number of
   tokens grows.
C. GPT-3's attention parameters, as arithmetic.
D. A tiny attention layer trained from scratch with hand-written backpropagation
   on an associative-recall task (a few key/value pairs, then a key, answer with
   its value). Compares learned attention against attention frozen to uniform.

Usage: python llm-series-06-attention.py [--only=ABCD]
Needs only NumPy.
"""
import sys
import time

import numpy as np


# ---------------------------------------------------------------------- A
def softmax_rows(s):
    e = np.exp(s - s.max(axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def attention(x, wq, wk, wv, causal=True):
    """x: (n, d). Returns (output (n, dv), pattern (n, n)); row i = how position i spreads its attention."""
    q, k, v = x @ wq, x @ wk, x @ wv
    s = q @ k.T / np.sqrt(wq.shape[1])
    if causal:
        s = np.where(np.tril(np.ones_like(s, dtype=bool)), s, -np.inf)
    a = softmax_rows(s)
    return a @ v, a


def experiment_a():
    print("\n== A. one head, and the causal mask ==")
    rng = np.random.default_rng(0)
    n, d, dk = 16, 32, 8
    x = rng.standard_normal((n, d))
    wq, wk, wv = (rng.standard_normal((d, dk)) for _ in range(3))
    out, a = attention(x, wq, wk, wv)
    print(f"pattern shape {a.shape}; every row sums to 1: {np.allclose(a.sum(axis=1), 1)}; "
          f"entries above the diagonal are exactly 0: {bool((a[np.triu_indices(n, 1)] == 0).all())}")
    print("row 0 (first token) can only look at itself:", np.round(a[0, :3], 3).tolist())
    print("row 5:", np.round(a[5, :8], 3).tolist())
    for causal in (True, False):
        x2 = x.copy()
        j = 10
        x2[j] += rng.standard_normal(d)  # change the token at position 10
        o1, _ = attention(x, wq, wk, wv, causal)
        o2, _ = attention(x2, wq, wk, wv, causal)
        diff = np.abs(o1 - o2).max(axis=1)
        before, after = diff[:j], diff[j:]
        print(f"causal={causal}: after changing position {j}: largest output change at positions before it "
              f"{before.max():.3g}, at positions {j} and after {after.min():.3g} to {after.max():.3g}")


# ---------------------------------------------------------------------- B
def experiment_b():
    print("\n== B. the n x n pattern: one head, d_k = 128, float32 ==")
    rng = np.random.default_rng(0)
    dk = 128
    rows = []
    for n in (256, 512, 1024, 2048, 4096, 8192):
        q = rng.standard_normal((n, dk), dtype=np.float32)
        k = rng.standard_normal((n, dk), dtype=np.float32)
        v = rng.standard_normal((n, dk), dtype=np.float32)
        mask = np.tril(np.ones((n, n), dtype=bool))
        times = []
        for _ in range(5):
            t0 = time.perf_counter()
            s = q @ k.T
            s *= np.float32(1 / np.sqrt(dk))
            s = np.where(mask, s, np.float32(-np.inf))
            s -= s.max(axis=1, keepdims=True)
            np.exp(s, out=s)
            s /= s.sum(axis=1, keepdims=True)
            _ = s @ v
            times.append(time.perf_counter() - t0)
        ms = float(np.median(times)) * 1000
        rows.append((n, ms))
        mb = n * n * 4 / 2**20
        prev = f"{ms / rows[-2][1]:.2f}x" if len(rows) > 1 else "-"
        print(f"n = {n:>5}: pattern {mb:8.1f} MiB, median time {ms:9.2f} ms, vs previous (2x tokens): {prev}")
    print("a pure O(n^2) cost would show 4.00x per doubling; a linear cost 2.00x")


# ---------------------------------------------------------------------- C
def experiment_c():
    print("\n== C. GPT-3 attention parameters (Brown et al. 2020, Table 2.1) ==")
    d, heads, dh, layers, ctx = 12_288, 96, 128, 96, 2_048
    per_head = 4 * d * dh  # W_Q, W_K, and the value map as two d x dh matrices (down and up)
    per_layer = heads * per_head
    total = layers * per_layer
    print(f"one head: 4 matrices of {d:,} x {dh} = {per_head:,}")
    print(f"one layer, {heads} heads: {per_layer:,}  (check: 4 x d^2 = {4 * d * d:,})")
    print(f"{layers} layers: {total:,}  = {total / 175e9:.1%} of 175 billion")
    entries = ctx * ctx
    print(f"one pattern at {ctx:,} tokens: {entries:,} entries; across {heads} heads and {layers} layers: "
          f"{entries * heads * layers:,} entries ({entries * heads * layers * 2 / 2**30:.1f} GiB at 2 bytes each)")


# ---------------------------------------------------------------------- D
NK, NV, NP, D = 8, 8, 3, 16  # key vocabulary, value vocabulary, pairs per sequence, width


def make_batch(rng, b):
    keys = np.stack([rng.permutation(NK)[:NP] for _ in range(b)])  # distinct keys per sequence
    vals = rng.integers(0, NV, size=(b, NP))
    which = rng.integers(0, NP, size=b)
    return keys, vals, which, vals[np.arange(b), which]


class Tiny:
    """One attention head over [pair, pair, pair, query]; the answer is read from the query position."""

    def __init__(self, seed, learn_qk=True, dtype=np.float64):
        rng = np.random.default_rng(seed)
        g = lambda *shape: (rng.standard_normal(shape) * 0.3).astype(dtype)
        self.p = {"Ek": g(NK, D), "Ev": g(NV, D), "Wq": g(D, D), "Wk": g(D, D), "Wv": g(D, D), "Wo": g(D, NV)}
        self.learn_qk = learn_qk
        if not learn_qk:
            self.p["Wq"][:] = 0  # all scores 0: uniform attention
            self.p["Wk"][:] = 0

    def forward(self, keys, vals, which):
        p, b = self.p, keys.shape[0]
        qk = keys[np.arange(b), which]
        x = np.concatenate([p["Ek"][keys] + p["Ev"][vals], p["Ek"][qk][:, None, :]], axis=1)  # (b, 4, D)
        q, k, v = x[:, 3] @ p["Wq"], x @ p["Wk"], x @ p["Wv"]
        s = np.einsum("bd,bjd->bj", q, k) / np.sqrt(D)
        a = softmax_rows(s)  # (b, 4): the query position's attention over all 4 positions
        z = np.einsum("bj,bjd->bd", a, v)
        logits = z @ p["Wo"]
        return dict(x=x, q=q, k=k, v=v, a=a, z=z, logits=logits, keys=keys, vals=vals, qk=qk)

    def loss_and_grads(self, keys, vals, which, target):
        p, c = self.p, self.forward(keys, vals, which)
        b = keys.shape[0]
        pr = softmax_rows(c["logits"])
        loss = float(-np.log(pr[np.arange(b), target] + 1e-12).mean())
        dl = pr.copy()
        dl[np.arange(b), target] -= 1
        dl /= b
        g = {k: np.zeros_like(v) for k, v in p.items()}
        g["Wo"] = c["z"].T @ dl
        dz = dl @ p["Wo"].T
        da = np.einsum("bd,bjd->bj", dz, c["v"])
        dv = c["a"][:, :, None] * dz[:, None, :]
        ds = c["a"] * (da - (c["a"] * da).sum(axis=1, keepdims=True))
        dq = np.einsum("bj,bjd->bd", ds, c["k"]) / np.sqrt(D)
        dk = ds[:, :, None] * c["q"][:, None, :] / np.sqrt(D)
        x = c["x"]
        g["Wq"] = x[:, 3].T @ dq
        g["Wk"] = np.einsum("bjd,bje->de", x, dk)
        g["Wv"] = np.einsum("bjd,bje->de", x, dv)
        dx = dk @ p["Wk"].T + dv @ p["Wv"].T
        dx[:, 3] += dq @ p["Wq"].T
        np.add.at(g["Ek"], keys, dx[:, :NP])
        np.add.at(g["Ev"], vals, dx[:, :NP])
        np.add.at(g["Ek"], c["qk"], dx[:, 3])
        if not self.learn_qk:
            g["Wq"][:] = 0
            g["Wk"][:] = 0
        return loss, g

    def accuracy(self, keys, vals, which, target):
        return float((self.forward(keys, vals, which)["logits"].argmax(axis=1) == target).mean())


def experiment_d():
    print("\n== D. a tiny attention layer, trained by hand-written backprop ==")
    rng = np.random.default_rng(1)
    net = Tiny(0)
    # 1. check the hand-written gradient against nudging parameters
    keys, vals, which, target = make_batch(rng, 32)
    _, g = net.loss_and_grads(keys, vals, which, target)
    worst = 0.0
    chk = np.random.default_rng(2)
    for name in ("Wq", "Wk", "Wv", "Wo", "Ek", "Ev"):
        for _ in range(4):
            idx = tuple(int(chk.integers(0, s)) for s in net.p[name].shape)
            eps = 1e-6
            net.p[name][idx] += eps
            up = net.loss_and_grads(keys, vals, which, target)[0]
            net.p[name][idx] -= 2 * eps
            dn = net.loss_and_grads(keys, vals, which, target)[0]
            net.p[name][idx] += eps
            num, ana = (up - dn) / (2 * eps), g[name][idx]
            worst = max(worst, abs(num - ana) / (abs(num) + abs(ana) + 1e-9))
    print(f"gradient check on 24 sampled parameters (6 matrices x 4): largest relative difference {worst:.2e}")

    # 2. train two models: learned attention, and attention frozen to uniform
    test = make_batch(np.random.default_rng(99), 5000)
    steps, lr, bs = 3000, 0.5, 64
    results = {}
    for name, learn in (("learned attention", True), ("uniform attention (Wq = Wk = 0, frozen)", False)):
        net = Tiny(0, learn_qk=learn)
        train_rng = np.random.default_rng(3)
        log = []
        t0 = time.perf_counter()
        for step in range(steps + 1):
            if step in (0, 100, 300, 1000, 3000):
                log.append((step, net.accuracy(*test)))
            if step == steps:
                break
            kb, vb, wb, tb = make_batch(train_rng, bs)
            _, g = net.loss_and_grads(kb, vb, wb, tb)
            for k in net.p:
                net.p[k] -= lr * g[k]
        results[name] = (net, log)
        print(f"{name}: accuracy on 5,000 fresh sequences at steps {[s for s, _ in log]}: "
              f"{[round(a * 100, 1) for _, a in log]}  ({time.perf_counter() - t0:.1f}s); chance = {100 / NV:.1f}")

    # 3. what did the learned head attend to?
    net = results["learned attention"][0]
    keys, vals, which, target = test
    c = net.forward(keys, vals, which)
    b = len(keys)
    a_match = c["a"][np.arange(b), which]
    a_other = (c["a"][:, :NP].sum(axis=1) - a_match) / (NP - 1)
    a_self = c["a"][:, 3]
    print(f"attention at the query position, averaged over 5,000 sequences: on the matching pair {a_match.mean():.3f}; "
          f"on each of the two other pairs {a_other.mean():.3f}; on itself {a_self.mean():.3f} (uniform would be 0.250)")
    print(f"sequences where the matching pair gets the most attention: {(c['a'][:, :NP].argmax(axis=1) == which).mean():.1%}")
    i = 0
    print(f"example: keys {keys[i].tolist()}, values {vals[i].tolist()}, asked for key {int(keys[i][which[i]])} "
          f"(position {int(which[i])}) -> answer {int(target[i])}, predicted {int(c['logits'][i].argmax())}; "
          f"attention over [pair0, pair1, pair2, query] = {np.round(c['a'][i], 3).tolist()}")
    # Without attention the model can see WHICH values are in the sequence but not which key they belong to.
    # Best possible guess = the most repeated value among the three: E[max count / 3].
    p_distinct = NV * (NV - 1) * (NV - 2) / NV**3
    p_pair = 3 * NV * (NV - 1) / NV**3
    p_triple = NV / NV**3
    best_bag = p_distinct / 3 + p_pair * 2 / 3 + p_triple * 1.0
    print(f"best possible accuracy knowing only which values appear (not which key goes with which): {best_bag:.1%}")
    nu = results["uniform attention (Wq = Wk = 0, frozen)"][0]
    cu = nu.forward(*test[:3])
    print(f"uniform model attention is {np.round(cu['a'][0], 3).tolist()} on every sequence by construction")


if __name__ == "__main__":
    only = next((a.split("=")[1] for a in sys.argv if a.startswith("--only=")), "ABCD")
    print("python", sys.version.split()[0], "numpy", np.__version__)
    if "A" in only:
        experiment_a()
    if "B" in only:
        experiment_b()
    if "C" in only:
        experiment_c()
    if "D" in only:
        experiment_d()
