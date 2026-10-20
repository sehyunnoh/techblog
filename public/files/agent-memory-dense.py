"""Companion to fts_recall.py: (1) the same questions against a dense retriever,
(2) hit@10 split by lexical overlap, (3) token costs. Needs fastembed and tiktoken.
"""
import importlib.util, json, os, re, sys
import numpy as np
import tiktoken
from fastembed import TextEmbedding

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("fts_recall", os.path.join(HERE, "agent-memory-fts-recall.py"))
fr = importlib.util.module_from_spec(spec); spec.loader.exec_module(fr)

DATA = sys.argv[1] if len(sys.argv) > 1 else "locomo10.json"
MODEL = "BAAI/bge-small-en-v1.5"
CATS = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop"}
enc = tiktoken.get_encoding("o200k_base")

def main():
    data = json.load(open(DATA, encoding="utf-8"))
    emb = TextEmbedding(MODEL)
    rows = []  # per question: dict(cat, lex_hit10, dense_hit10, overlap, ...)
    total_tokens = 0
    top5_tokens = []
    for conv in data:
        con, ids, turns = fr.build(conv["conversation"])
        texts = [t for _, t in turns]
        total_tokens += len(enc.encode("\n".join(f"{d}: {t}" for d, t in turns)))
        E = np.array(list(emb.embed(texts)))
        qas = []
        for qa in conv["qa"]:
            ev = fr.evidence_ids(qa)
            if qa["category"] in CATS and ev:
                qas.append((qa, ev))
        # bge query instruction, as recommended for retrieval
        Q = np.array(list(emb.embed(["Represent this sentence for searching relevant passages: " + q["question"] for q, _ in qas])))
        S = Q @ E.T
        for (qa, ev), sims in zip(qas, S):
            order = np.argsort(-sims)[:10]
            dense = [ids[i] for i in order]
            lex_rows, _ = fr.hermes_path(con, qa["question"], 10, relax=True)
            lex = [ids[r - 1] for r in lex_rows]
            kws = {w.lower() for w in fr.words(fr.kw_query(qa["question"]))}
            evtext = " ".join(t for d, t in turns if d in ev).lower()
            evwords = set(re.findall(r"[a-z0-9']+", evtext))
            overlap = len(kws & evwords) / len(kws) if kws else 0.0
            top5_tokens.append(len(enc.encode("\n".join(texts[i] for i in order[:5]))))
            rows.append(dict(cat=qa["category"], lex=bool(ev & set(lex)), dense=bool(ev & set(dense)),
                             dense5=bool(ev & set(dense[:5])), lex5=bool(ev & set(lex[:5])),
                             dense1=bool(ev & set(dense[:1])), lex1=bool(ev & set(lex[:1])), overlap=overlap,
                             nev=len(ev),
                             evlen=float(np.mean([len(t) for d, t in turns if d in ev] or [np.nan]))))
    n = len(rows)
    print(f"model {MODEL}; {n} questions; all dialogue = {total_tokens/len(data):.0f} o200k tokens per conversation")
    print(f"\n{'category':12} {'n':>5} | {'lex@1':>6} {'lex@5':>6} {'lex@10':>7} | {'dense@1':>8} {'dense@5':>8} {'dense@10':>9}")
    for c in [0] + list(CATS):
        sel = [r for r in rows if c == 0 or r["cat"] == c]
        f = lambda k: 100 * sum(r[k] for r in sel) / len(sel)
        print(f"{'ALL' if c == 0 else CATS[c]:12} {len(sel):5d} | {f('lex1'):5.1f}% {f('lex5'):5.1f}% {f('lex'):6.1f}% | "
              f"{f('dense1'):7.1f}% {f('dense5'):7.1f}% {f('dense'):8.1f}%")
    print("\nhit@10 by share of question keywords that appear in the evidence turn(s):")
    for lo, hi in [(0, 0.0001), (0.0001, 0.34), (0.34, 0.67), (0.67, 1.01)]:
        sel = [r for r in rows if lo <= r["overlap"] < hi]
        if sel:
            print(f"  overlap {lo:4.2f}-{min(hi,1):4.2f}: n={len(sel):4d}  lexical {100*sum(r['lex'] for r in sel)/len(sel):5.1f}%  "
                  f"dense {100*sum(r['dense'] for r in sel)/len(sel):5.1f}%")
    print(f"\nmean tokens in top-5 dense turns: {np.mean(top5_tokens):.0f}")
    neither_rows = [r for r in rows if not (r['lex'] or r['dense'])]
    found_rows = [r for r in rows if r['lex'] or r['dense']]
    for name, grp in (("found by either", found_rows), ("found by neither", neither_rows)):
        print(f"{name}: n={len(grp)}, median evidence-turn length {np.nanmedian([r['evlen'] for r in grp]):.0f} chars, "
              f"{100*np.mean([r['nev'] > 1 for r in grp]):.0f}% need more than one turn")
    both = sum(r['lex'] and r['dense'] for r in rows); either = sum(r['lex'] or r['dense'] for r in rows)
    print(f"hit@10 lexical only {sum(r['lex'] and not r['dense'] for r in rows)}, dense only "
          f"{sum(r['dense'] and not r['lex'] for r in rows)}, both {both}, neither {n-either}")

if __name__ == "__main__":
    main()
