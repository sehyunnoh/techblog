"""Measurements for part 5 of the "How an LLM works" guide series.

A. Softmax and temperature on a real next-word distribution (word counts from
   this blog's own Markdown, as in part 1).
B. The numerical trap in softmax: float32 overflow, and the subtract-the-max fix.
C. The first lines of the GPT-3 parameter ledger: embedding and unembedding.
D. Directions in an embedding space. Embeddings here are NOT from a neural
   network: they are built from word co-occurrence counts in the text8 corpus
   (PPMI followed by a truncated SVD), which is a classic count-based method
   that shows the same kind of structure.

Usage: python llm-series-05-tokens-embeddings-softmax.py <repo-root> <text8.zip> [--only=ABCD]
Needs NumPy and SciPy. text8 is the first 100 MB of cleaned English Wikipedia
(http://mattmahoney.net/dc/text8.zip, 31 MB).
"""
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------- A
def load_words(repo: Path) -> list[str]:
    words: list[str] = []
    files = sorted(list((repo / "src/content/blog").glob("*.md*")) + list((repo / "src/content/guides").glob("*.md*")))
    files = [f for f in files if not f.name.startswith("_")]
    for f in files:
        text = f.read_text(encoding="utf-8")
        text = re.sub(r"^---.*?---", " ", text, count=1, flags=re.S)
        text = re.sub(r"```.*?```", " ", text, flags=re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\[\^\d+\].*", " ", text)
        text = re.sub(r"\(https?://[^)]*\)", " ", text)
        words += re.findall(r"[a-z']+|[.,]", text.lower())
    print(f"corpus: {len(files)} files, {len(words):,} tokens")
    return words


def softmax(z):
    e = np.exp(z - z.max())
    return e / e.sum()


def experiment_a(repo: Path):
    print("\n== A. softmax and temperature on a real next-word distribution ==")
    words = load_words(repo)
    table: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for a, b, c in zip(words, words[1:], words[2:]):
        table[(a, b)][c] += 1
    ctx = ("the", "model")
    c = table[ctx]
    vocab = [w for w, _ in c.most_common()]
    counts = np.array([c[w] for w in vocab], dtype=np.float64)
    logits = np.log(counts)  # a stand-in for a network's raw scores
    print(f"context {ctx}: seen {int(counts.sum())} times, {len(vocab)} distinct next words; "
          f"top three {[(w, int(c[w])) for w in vocab[:3]]}")
    print(f"{'T':>6}{'top-1 prob':>12}{'entropy (bits)':>16}{'effective words':>17}{'distinct in 1,000 draws':>25}")
    rng = np.random.default_rng(0)
    for T in (0.1, 0.25, 0.5, 1.0, 2.0, 5.0):
        p = softmax(logits / T)
        h = float(-(p * np.log2(p + 1e-300)).sum())
        draws = rng.choice(len(vocab), size=1000, p=p)
        print(f"{T:>6}{p.max():>12.3f}{h:>16.2f}{2 ** h:>17.1f}{len(set(draws.tolist())):>25}")
    print(f"uniform over {len(vocab)} words would be {np.log2(len(vocab)):.2f} bits")
    # raw scores vs probabilities
    raw = np.array([2.0, 1.0, 0.1])
    print("raw scores", raw.tolist(), "-> softmax", np.round(softmax(raw), 3).tolist(),
          "sum", round(float(softmax(raw).sum()), 3))


# ---------------------------------------------------------------------- B
def experiment_b():
    print("\n== B. softmax and float32 ==")
    z = np.array([10.0, 9.0, 8.0], dtype=np.float32)
    for name, T in (("T = 1", 1.0), ("T = 0.1", 0.1), ("T = 0.01", 0.01)):
        s = z / np.float32(T)
        with np.errstate(over="ignore", invalid="ignore"):
            naive = np.exp(s) / np.exp(s).sum()
        stable = np.exp(s - s.max()) / np.exp(s - s.max()).sum()
        print(f"{name}: scores {s.tolist()}  naive {np.round(naive, 4).tolist()}  subtract-max {np.round(stable, 4).tolist()}")
    print("largest float32 input to exp that does not overflow:",
          float(np.log(np.finfo(np.float32).max)))


# ---------------------------------------------------------------------- C
def experiment_c():
    print("\n== C. GPT-3 ledger, first lines (Brown et al. 2020, Table 2.1) ==")
    vocab, d, total = 50_257, 12_288, 175_000_000_000
    emb = vocab * d
    print(f"embedding matrix {vocab:,} x {d:,} = {emb:,}")
    print(f"embedding + unembedding = {2 * emb:,}  ({2 * emb / total:.2%} of 175 billion)")
    print(f"one token is a point in a space with {d:,} coordinates; a prompt of 2,048 tokens is {2048 * d:,} numbers")


# ---------------------------------------------------------------------- D
V = 20_000
WINDOW = 5
DIM = 100


def build_embeddings(zip_path: Path):
    import scipy.sparse as sp
    from scipy.sparse.linalg import svds

    t0 = time.perf_counter()
    with zipfile.ZipFile(zip_path) as z:
        words = z.read("text8").decode().split()
    print(f"text8: {len(words):,} tokens, {len(set(words)):,} distinct")
    freq = Counter(words)
    vocab = [w for w, _ in freq.most_common(V)]
    idx = {w: i for i, w in enumerate(vocab)}
    ids = np.fromiter((idx.get(w, -1) for w in words), dtype=np.int32, count=len(words))
    covered = float((ids >= 0).mean())
    print(f"vocabulary: top {V:,} words, covering {covered:.1%} of tokens")

    C = sp.csr_matrix((V, V), dtype=np.float32)
    for k in range(1, WINDOW + 1):
        a, b = ids[:-k], ids[k:]
        m = (a >= 0) & (b >= 0)
        a, b = a[m], b[m]
        part = sp.coo_matrix((np.ones(len(a), np.float32), (a, b)), shape=(V, V)).tocsr()
        C = C + part + part.T
    print(f"co-occurrence matrix: window +/-{WINDOW}, {C.nnz:,} nonzero cells, {time.perf_counter() - t0:.0f}s so far")

    # Positive pointwise mutual information, with the usual 0.75 smoothing of the context distribution.
    C = C.tocoo()
    total = float(C.data.sum())
    row = np.asarray(C.sum(axis=1)).ravel()
    col = np.asarray(C.sum(axis=0)).ravel() ** 0.75
    col = col / col.sum()
    pmi = np.log((C.data / total) / ((row[C.row] / total) * col[C.col]))
    keep = pmi > 0
    M = sp.coo_matrix((pmi[keep].astype(np.float32), (C.row[keep], C.col[keep])), shape=(V, V)).tocsr()
    print(f"PPMI matrix: {M.nnz:,} nonzero cells")
    u, s, _ = svds(M, k=DIM)
    order = np.argsort(-s)
    emb = (u[:, order] * np.sqrt(s[order])).astype(np.float32)
    emb /= np.linalg.norm(emb, axis=1, keepdims=True)
    print(f"embeddings: {emb.shape}, built in {time.perf_counter() - t0:.0f}s")
    return vocab, idx, emb


def nearest(emb, idx, vocab, vec, exclude, n=5):
    sims = emb @ (vec / np.linalg.norm(vec))
    for w in exclude:
        sims[idx[w]] = -9
    top = np.argsort(-sims)[:n]
    return [(vocab[i], round(float(sims[i]), 3)) for i in top]


ANALOGIES = {
    "capital-country": [("paris", "france", "rome", "italy"), ("berlin", "germany", "madrid", "spain"),
                        ("tokyo", "japan", "moscow", "russia"), ("athens", "greece", "lisbon", "portugal"),
                        ("london", "england", "vienna", "austria"), ("cairo", "egypt", "beijing", "china"),
                        ("warsaw", "poland", "stockholm", "sweden"), ("ottawa", "canada", "canberra", "australia")],
    "gender": [("king", "queen", "man", "woman"), ("brother", "sister", "son", "daughter"),
               ("father", "mother", "uncle", "aunt"), ("prince", "princess", "boy", "girl"),
               ("husband", "wife", "actor", "actress"), ("he", "she", "his", "her")],
    "verb-tense": [("walking", "walked", "swimming", "swam"), ("going", "went", "taking", "took"),
                   ("seeing", "saw", "writing", "wrote"), ("running", "ran", "eating", "ate")],
    "plural": [("car", "cars", "house", "houses"), ("tree", "trees", "book", "books"),
               ("city", "cities", "country", "countries"), ("child", "children", "man", "men")],
}


def experiment_d(zip_path: Path):
    print("\n== D. directions in a count-based embedding space ==")
    vocab, idx, emb = build_embeddings(zip_path)
    print("\nnearest neighbours (cosine):")
    for w in ("king", "paris", "tower", "bank"):
        if w in idx:
            print(f"  {w}: {nearest(emb, idx, vocab, emb[idx[w]], [w])}")

    print("\nanalogies a:b :: c:? computed as  b - a + c  (a, b, c excluded from the answers)")
    for cat, items in ANALOGIES.items():
        used = hit1 = hit5 = 0
        misses = []
        for a, b, c, d in items:
            if not all(w in idx for w in (a, b, c, d)):
                continue
            used += 1
            res = nearest(emb, idx, vocab, emb[idx[b]] - emb[idx[a]] + emb[idx[c]], [a, b, c], 5)
            top = [w for w, _ in res]
            hit1 += top[0] == d
            hit5 += d in top
            if top[0] != d:
                misses.append(f"{a}:{b}::{c}:{top[0]} (wanted {d})")
        print(f"  {cat}: {used} usable, top-1 {hit1}, top-5 {hit5}" + (f"; misses: {misses}" if misses else ""))
    for a, b, c in (("king", "queen", "man"), ("paris", "france", "italy")):
        pass
    k = nearest(emb, idx, vocab, emb[idx["king"]] - emb[idx["man"]] + emb[idx["woman"]], ["king", "man", "woman"], 5)
    print("\nking - man + woman ->", k)

    # A direction measured with a dot product: "plural" from a few pairs, tested on others.
    train = [("cat", "cats"), ("dog", "dogs"), ("year", "years"), ("day", "days"), ("war", "wars")]
    direction = np.mean([emb[idx[p]] - emb[idx[s]] for s, p in train if s in idx and p in idx], axis=0)
    direction /= np.linalg.norm(direction)
    test_s = ["car", "house", "tree", "book", "city", "river", "school", "game"]
    test_p = ["cars", "houses", "trees", "books", "cities", "rivers", "schools", "games"]
    ps = [float(emb[idx[w]] @ direction) for w in test_s if w in idx]
    pp = [float(emb[idx[w]] @ direction) for w in test_p if w in idx]
    wins = sum(p > s for s, p in zip(ps, pp))
    print(f"\n'plural' direction built from {len(train)} pairs; on {len(ps)} unseen pairs the plural scored higher "
          f"{wins} times; mean projection singular {np.mean(ps):.3f}, plural {np.mean(pp):.3f}")


if __name__ == "__main__":
    repo, z = Path(sys.argv[1]), Path(sys.argv[2])
    only = next((a.split("=")[1] for a in sys.argv if a.startswith("--only=")), "ABCD")
    print("python", sys.version.split()[0], "numpy", np.__version__)
    if "A" in only:
        experiment_a(repo)
    if "B" in only:
        experiment_b()
    if "C" in only:
        experiment_c()
    if "D" in only:
        experiment_d(z)
