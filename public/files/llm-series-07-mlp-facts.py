"""Measurements for part 7 of the "How an LLM works" guide series.

A. A hand-built feed-forward (MLP) block that stores facts as "if first name X and
   last name Y then write attribute Z", in a toy vector space. Tests the ReLU
   "AND gate" against the same block with the ReLU removed.
B. The same kind of block trained by gradient descent to memorize a table of
   random facts: how many hidden neurons does it take, and how sparsely do they fire?
C. The GPT-3 parameter ledger, finished.

Usage: python llm-series-07-mlp-facts.py [--only=ABC]
Needs only NumPy.
"""
import sys
import time

import numpy as np


def unit(rng, n, d):
    v = rng.standard_normal((n, d))
    return v / np.linalg.norm(v, axis=1, keepdims=True)


# ---------------------------------------------------------------------- A
def experiment_a():
    print("\n== A. a hand-built block that stores facts ==")
    d, nf, nl, na, nfacts = 256, 20, 20, 5, 12
    rng = np.random.default_rng(0)
    first, last, attr = unit(rng, nf, d), unit(rng, nl, d), unit(rng, na, d)
    off = np.abs(first @ first.T - np.eye(nf)).max()
    print(f"directions in {d} dimensions: {nf} first names, {nl} last names, {na} attributes; "
          f"largest overlap between two different first-name directions: {off:.3f} (0 = perpendicular)")
    pairs = [(int(f), int(l)) for f, l in zip(rng.permutation(nf)[:nfacts], rng.permutation(nl)[:nfacts])]
    attr_of = {p: int(rng.integers(0, na)) for p in pairs}
    up = np.stack([first[f] + last[l] for f, l in pairs])  # one question per fact: "first == f AND last == l?"
    down = np.stack([attr[attr_of[p]] for p in pairs], axis=1)  # (d, nfacts): the answer each neuron writes

    def block(x, bias, relu=True):
        h = x @ up.T - bias
        if relu:
            h = np.maximum(h, 0)
        return h @ down.T, h

    combos = [(f, l) for f in range(nf) for l in range(nl)]
    stored = [c for c in combos if c in attr_of]
    sharing = [c for c in combos if c not in attr_of and any(c[0] == p[0] or c[1] == p[1] for p in pairs)]
    nothing = [c for c in combos if c not in attr_of and c not in sharing]
    print(f"{len(combos)} name combinations: {len(stored)} stored facts, {len(sharing)} share a first or last name "
          f"with a stored fact, {len(nothing)} share nothing")

    for relu in (True, False):
        for bias in (1.0,):
            correct, norms = 0, {"stored": [], "sharing": [], "nothing": []}
            for f, l in combos:
                x = first[f] + last[l]
                out, _ = block(x, bias, relu)
                if (f, l) in attr_of:
                    scores = attr @ out
                    correct += int(scores.argmax() == attr_of[(f, l)])
                key = "stored" if (f, l) in attr_of else ("sharing" if (f, l) in sharing else "nothing")
                norms[key].append(float(np.linalg.norm(out)))
            print(f"{'ReLU' if relu else 'no ReLU':>8}, bias -{bias}: stored facts answered correctly {correct}/{len(stored)}; "
                  f"mean size of the written vector: stored {np.mean(norms['stored']):.3f}, "
                  f"sharing one name {np.mean(norms['sharing']):.3f}, sharing nothing {np.mean(norms['nothing']):.3f}")
    # how many neurons fire for each kind of input, with ReLU
    fire = {"stored": [], "sharing": [], "nothing": []}
    for f, l in combos:
        _, h = block(first[f] + last[l], 1.0, True)
        key = "stored" if (f, l) in attr_of else ("sharing" if (f, l) in sharing else "nothing")
        fire[key].append(int((h > 1e-9).sum()))
    print("neurons (of 12) that switch on with ReLU, mean per input: "
          f"stored {np.mean(fire['stored']):.2f}, sharing one name {np.mean(fire['sharing']):.2f}, "
          f"sharing nothing {np.mean(fire['nothing']):.2f}")
    # An example with the pre-activation values.
    f, l = pairs[0]
    pre_full = float((first[f] + last[l]) @ up[0])
    other_l = next(x for x in range(nl) if x != l and (f, x) not in attr_of)
    pre_partial = float((first[f] + last[other_l]) @ up[0])
    other_f = next(x for x in range(nf) if x != f and (x, l) not in attr_of)
    pre_none = float((first[other_f] + last[other_l]) @ up[0])
    print(f"neuron 0 before its bias: full match {pre_full:.2f}, one name matches {pre_partial:.2f}, none {pre_none:.2f}")


# ---------------------------------------------------------------------- B
class MLP:
    def __init__(self, din, h, dout, seed):
        rng = np.random.default_rng(seed)
        self.p = {"W1": rng.standard_normal((din, h)) * np.sqrt(2 / din), "b1": np.zeros(h),
                  "W2": rng.standard_normal((h, dout)) * np.sqrt(2 / h), "b2": np.zeros(dout)}
        self.m = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.v = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.t = 0

    def forward(self, x):
        h = np.maximum(x @ self.p["W1"] + self.p["b1"], 0)
        z = h @ self.p["W2"] + self.p["b2"]
        e = np.exp(z - z.max(axis=1, keepdims=True))
        return h, e / e.sum(axis=1, keepdims=True)

    def step(self, x, y, lr=0.01):
        h, pr = self.forward(x)
        n = len(x)
        dz = pr.copy()
        dz[np.arange(n), y] -= 1
        dz /= n
        g = {"W2": h.T @ dz, "b2": dz.sum(axis=0)}
        dh = (dz @ self.p["W2"].T) * (h > 0)
        g["W1"], g["b1"] = x.T @ dh, dh.sum(axis=0)
        self.t += 1
        for k in self.p:  # Adam
            self.m[k] = 0.9 * self.m[k] + 0.1 * g[k]
            self.v[k] = 0.999 * self.v[k] + 0.001 * g[k] ** 2
            mh, vh = self.m[k] / (1 - 0.9**self.t), self.v[k] / (1 - 0.999**self.t)
            self.p[k] -= lr * mh / (np.sqrt(vh) + 1e-8)

    def accuracy(self, x, y):
        return float((self.forward(x)[1].argmax(axis=1) == y).mean())


def experiment_b():
    print("\n== B. a trained block memorizing random facts ==")
    nf = nl = 30
    d, nclass, steps = 64, 10, 3000
    rng = np.random.default_rng(0)
    first, last = unit(rng, nf, d), unit(rng, nl, d)
    x = np.stack([first[f] + last[l] for f in range(nf) for l in range(nl)])
    y = rng.integers(0, nclass, size=len(x))
    print(f"{len(x)} facts: (first name, last name) -> one of {nclass} random attributes; "
          f"inputs are the sum of two fixed random {d}-dimensional vectors; a guess is right {100 / nclass:.0f}% of the time; "
          f"the table holds {len(x) * np.log2(nclass):,.0f} bits")
    print(f"{'hidden neurons':>15}{'parameters':>12}{'facts recalled':>16}{'active fraction':>17}{'seconds':>9}")
    for h in (4, 8, 16, 32, 64, 128, 256, 512):
        net = MLP(d, h, nclass, seed=1)
        t0 = time.perf_counter()
        for _ in range(steps):
            net.step(x, y)
        secs = time.perf_counter() - t0
        params = sum(v.size for v in net.p.values())
        hid, _ = net.forward(x)
        print(f"{h:>15}{params:>12,}{net.accuracy(x, y):>15.1%}{(hid > 0).mean():>17.1%}{secs:>9.1f}")


# ---------------------------------------------------------------------- C
def experiment_c():
    print("\n== C. the GPT-3 ledger, finished (Brown et al. 2020, Table 2.1) ==")
    d, layers = 12_288, 96
    dff = 4 * d
    mlp_w = 2 * d * dff
    mlp_b = dff + d
    mlp_layer = mlp_w + mlp_b
    mlp_total = layers * mlp_layer
    mlp_w_total = layers * mlp_w
    attn = layers * 4 * d * d
    emb = 2 * 50_257 * d
    print(f"MLP neurons per layer: 4 x {d:,} = {dff:,}")
    print(f"one MLP, weights: 2 x {d:,} x {dff:,} = {mlp_w:,}; with biases {mlp_layer:,}")
    print(f"{layers} MLPs, weights only: {mlp_w_total:,} = {mlp_w_total / 175e9:.1%} of 175 billion; with biases {mlp_total:,}")
    print(f"ratio MLP : attention = {mlp_w_total / attn:.2f} : 1 (exactly 2 : 1 for weights)")
    total = emb + attn + mlp_total
    print(f"embedding + unembedding {emb:,}\n attention {attn:,}\n MLP {mlp_total:,}\n sum {total:,} "
          f"(headline 175,000,000,000: difference {total - 175e9:,.0f}, {abs(total - 175e9) / 175e9:.2%})")
    tied = emb // 2 + attn + mlp_total
    print(f"if the output matrix shares the embedding matrix instead of being a separate copy: sum {tied:,} "
          f"({abs(tied - 175e9) / 175e9:.2%} from 175 billion); with the 2,048 x {d:,} position table: {tied + 2048 * d:,}")
    pos = 2048 * d
    print(f"learned position embeddings (2,048 x {d:,}) would add {pos:,}; layer norms and attention biases are smaller still")
    print(f"neurons in all the MLPs of the model: {layers * dff:,}")


if __name__ == "__main__":
    only = next((a.split("=")[1] for a in sys.argv if a.startswith("--only=")), "ABC")
    print("python", sys.version.split()[0], "numpy", np.__version__)
    if "A" in only:
        experiment_a()
    if "B" in only:
        experiment_b()
    if "C" in only:
        experiment_c()
