"""Measurements for part 1 of the "How an LLM works" guide series.

Two independent experiments:

A. A next-word "function" built by counting. It reads this blog's own Markdown,
   counts which word follows each pair of words, and then samples from those
   counts in a loop. This is the shape of an LLM (context in, probabilities
   out, sample, append) with a lookup table where the neural network would be.

B. The 784-16-16-10 network from the classic digit-recognition demo, with random
   weights. Counts its parameters, runs the forward pass, and measures how well
   an untrained network does on the 10,000 MNIST test images.

Usage: python llm-series-01-next-word-and-network.py <repo-root> <cache-dir>
Needs only NumPy. MNIST is downloaded once into <cache-dir>.
"""
import gzip
import re
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

MNIST_BASE = "https://ossci-datasets.s3.amazonaws.com/mnist/"


# ---------------------------------------------------------------- experiment A
def load_words(repo: Path) -> list[str]:
    words: list[str] = []
    files = sorted(
        list((repo / "src/content/blog").glob("*.md*"))
        + list((repo / "src/content/guides").glob("*.md*"))
    )
    files = [f for f in files if not f.name.startswith("_")]
    for f in files:
        text = f.read_text(encoding="utf-8")
        text = re.sub(r"^---.*?---", " ", text, count=1, flags=re.S)  # frontmatter
        text = re.sub(r"```.*?```", " ", text, flags=re.S)  # code fences
        text = re.sub(r"<[^>]+>", " ", text)  # tags
        text = re.sub(r"\[\^\d+\].*", " ", text)  # footnotes
        text = re.sub(r"\(https?://[^)]*\)", " ", text)  # link targets
        words += re.findall(r"[a-z']+|[.,]", text.lower())
    print(f"corpus: {len(files)} files, {len(words):,} tokens, {len(set(words)):,} distinct")
    return words


def experiment_a(repo: Path) -> None:
    print("\n== A. next word by counting ==")
    words = load_words(repo)
    table: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for a, b, c in zip(words, words[1:], words[2:]):
        table[(a, b)][c] += 1
    print(f"distinct two-word contexts seen: {len(table):,}")

    def dist(ctx: tuple[str, str]) -> list[tuple[str, float]]:
        c = table[ctx]
        n = sum(c.values())
        return [(w, k / n) for w, k in c.most_common()]

    for ctx in [("the", "model"), ("a", "large"), ("the", "cache")]:
        d = dist(ctx)
        n = sum(table[ctx].values())
        top = ", ".join(f"{w} {p:.1%}" for w, p in d[:5])
        print(f"after {ctx[0]!r} {ctx[1]!r} (seen {n}x, {len(d)} distinct next words): {top}")

    # The generation loop: pick from the distribution, append, repeat.
    for seed in (1, 2, 3):
        rng = np.random.default_rng(seed)
        out = ["a", "large"]
        for _ in range(14):
            d = dist((out[-2], out[-1]))
            if not d:
                break
            ws, ps = zip(*d)
            out.append(str(rng.choice(ws, p=ps)))
        print(f"seed {seed}: {' '.join(out)}")

    # Greedy (always take the most likely word) is deterministic.
    out = ["a", "large"]
    seen = set()
    for _ in range(14):
        key = (out[-2], out[-1])
        if key in seen:
            break
        seen.add(key)
        d = dist(key)
        if not d:
            break
        out.append(d[0][0])
    print("greedy:", " ".join(out))


# ---------------------------------------------------------------- experiment B
def mnist(cache: Path):
    cache.mkdir(parents=True, exist_ok=True)

    def fetch(name: str) -> bytes:
        p = cache / name
        if not p.exists():
            urllib.request.urlretrieve(MNIST_BASE + name, p)
        return gzip.decompress(p.read_bytes())

    x = np.frombuffer(fetch("t10k-images-idx3-ubyte.gz"), np.uint8, offset=16)
    y = np.frombuffer(fetch("t10k-labels-idx1-ubyte.gz"), np.uint8, offset=8)
    return x.reshape(-1, 784).astype(np.float32) / 255.0, y


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def experiment_b(cache: Path) -> None:
    print("\n== B. the 784-16-16-10 network, untrained ==")
    sizes = [784, 16, 16, 10]
    total = 0
    for i, (n_in, n_out) in enumerate(zip(sizes, sizes[1:]), 1):
        w, b = n_in * n_out, n_out
        total += w + b
        print(f"layer {i}: {n_in} -> {n_out}: {w:,} weights + {b} biases = {w + b:,}")
    print(f"total parameters: {total:,}")

    x, y = mnist(cache)
    print(f"test images: {x.shape[0]:,}, pixel range {x.min():.1f} to {x.max():.1f}")

    accs = []
    for seed in range(20):
        rng = np.random.default_rng(seed)
        ws = [rng.standard_normal((o, i)).astype(np.float32) for i, o in zip(sizes, sizes[1:])]
        bs = [rng.standard_normal(o).astype(np.float32) for o in sizes[1:]]
        a = x.T  # one column per image
        for w, b in zip(ws, bs):
            a = sigmoid(w @ a + b[:, None])
        accs.append(float((a.argmax(axis=0) == y).mean()))
        if seed == 0:
            print("seed 0, first test image, label", int(y[0]), "output:", np.round(a[:, 0], 2))
            hist = np.bincount(a.argmax(axis=0), minlength=10)
            print("seed 0, how often each digit is the answer over 10,000 images:", hist.tolist())
    accs_a = np.array(accs)
    print(
        f"random-weight accuracy over 20 seeds: mean {accs_a.mean():.1%}, "
        f"min {accs_a.min():.1%}, max {accs_a.max():.1%}"
    )
    print("share of the 10 classes in the test set:", np.round(np.bincount(y) / len(y), 3).tolist())

    # The same network written as one function call on a single image.
    rng = np.random.default_rng(0)
    ws = [rng.standard_normal((o, i)).astype(np.float32) for i, o in zip(sizes, sizes[1:])]
    bs = [rng.standard_normal(o).astype(np.float32) for o in sizes[1:]]
    a = x[0]
    for w, b in zip(ws, bs):
        a = sigmoid(w @ a + b)
    print("single-image forward pass output shape:", a.shape, "sum of outputs:", round(float(a.sum()), 2))


if __name__ == "__main__":
    repo, cache = Path(sys.argv[1]), Path(sys.argv[2])
    print("python", sys.version.split()[0], "numpy", np.__version__)
    experiment_a(repo)
    experiment_b(cache)
