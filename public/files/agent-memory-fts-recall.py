"""Does Hermes-style FTS5 session search find the turn that answers a question?

Download locomo10.json from https://github.com/snap-research/locomo (data/locomo10.json), then:
    python agent-memory-fts-recall.py locomo10.json

Replays the retrieval path in hermes_state_search.py (commit 1f91fb3) against LoCoMo
(snap-research/locomo, locomo10.json): each dialogue turn is one indexed message, each
QA item names its evidence turns. Hit@k = at least one evidence turn is in the top k rows.
No LLM is involved, so the "keywords" arm is a stopword-stripping proxy for an agent that
writes a good query, not a measurement of a real agent.
"""
import json, re, sqlite3, sys

DATA = sys.argv[1] if len(sys.argv) > 1 else "locomo10.json"
KS = (1, 5, 10)
STOP = set("""a an the of to in on at for and or but is are was were be been being do does did has have had
what which who whom whose where when why how that this these those it its with from by about as into
they them their he she his her him you your i me my we our us not no yes would could should can will
might may also than then there here after before during while up down out over under again""".split())

def evidence_ids(qa):
    """LoCoMo evidence strings are sometimes malformed ("D9:1 D4:4", "D8:6; D9:17", "D:11:26", "D30:05"); normalise all."""
    return {f"D{a}:{int(b)}" for a, b in re.findall(r"D:?(\d+):0*(\d+)", " ".join(qa.get("evidence", [])))}

def words(q):
    return re.findall(r"[A-Za-z0-9']+", q.replace("'s", ""))

def and_query(q):
    return " ".join(words(q))

def kw_query(q):
    return " ".join(w for w in words(q) if w.lower() not in STOP)

def or_query(q):
    ws = words(q)
    return " OR ".join(ws) if len(ws) >= 2 else None

def search(con, table, match, limit):
    try:
        return [r[0] for r in con.execute(
            f"SELECT rowid FROM {table} WHERE {table} MATCH ? ORDER BY rank LIMIT ?", (match, limit))]
    except sqlite3.OperationalError:
        return []

def hermes_path(con, q, limit, relax=True):
    """AND on unicode61 -> trigram (all tokens >=3 chars) -> OR-relaxed, each only on a miss."""
    qa = and_query(q)
    if not qa:
        return [], "empty"
    rows = search(con, "fts", qa, limit)
    if rows:
        return rows, "and"
    toks = qa.split()
    if all(len(t) >= 3 for t in toks):
        rows = search(con, "tri", " ".join(f'"{t}"' for t in toks), limit)
        if rows:
            return rows, "trigram"
    if relax:
        oq = or_query(q)
        if oq:
            rows = search(con, "fts", oq, limit)
            if rows:
                return rows, "or"
    return [], "miss"

def build(conv):
    turns = []
    for k, v in conv.items():
        if re.fullmatch(r"session_\d+", k):
            for t in v:
                turns.append((t["dia_id"], t["text"]))
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE fts USING fts5(content)")
    con.execute("CREATE VIRTUAL TABLE tri USING fts5(content, tokenize='trigram')")
    ids = []
    for i, (d, text) in enumerate(turns, 1):
        con.execute("INSERT INTO fts(rowid, content) VALUES (?,?)", (i, text))
        con.execute("INSERT INTO tri(rowid, content) VALUES (?,?)", (i, text))
        ids.append(d)
    return con, ids, turns

def main():
    data = json.load(open(DATA, encoding="utf-8"))
    arms = {
        "A question as typed: AND, then trigram (no OR retry)": lambda con, q: hermes_path(con, q, 10, relax=False),
        "B Hermes path (AND, trigram, OR retry)": lambda con, q: hermes_path(con, q, 10, relax=True),
        "C keywords only, Hermes path": lambda con, q: hermes_path(con, kw_query(q), 10, relax=True),
    }
    cats = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop"}
    stats = {a: {c: {"n": 0, "empty": 0, **{f"hit{k}": 0 for k in KS}, "recall10": 0.0} for c in list(cats) + [0]} for a in arms}
    paths = {a: {} for a in arms}
    total_chars = total_turns = 0
    for conv in data:
        con, ids, turns = build(conv["conversation"])
        total_turns += len(turns); total_chars += sum(len(t) for _, t in turns)
        for qa in conv["qa"]:
            c = qa["category"]
            ev = evidence_ids(qa)
            if c not in cats or not ev:
                continue
            for a, fn in arms.items():
                rows, path = fn(con, qa["question"])
                paths[a][path] = paths[a].get(path, 0) + 1
                got = [ids[r - 1] for r in rows]
                for key in (c, 0):
                    s = stats[a][key]; s["n"] += 1
                    s["empty"] += (not got)
                    for k in KS:
                        s[f"hit{k}"] += bool(ev & set(got[:k]))
                    s["recall10"] += len(ev & set(got[:10])) / len(ev)
    print(f"corpus: {len(data)} conversations, {total_turns} turns, {total_chars} chars "
          f"({total_chars/len(data):.0f} chars/conversation, {total_chars/total_turns:.0f} chars/turn)")
    for a in arms:
        print(f"\n== {a}")
        print(f"{'category':12} {'n':>5} {'empty%':>7} {'hit@1':>7} {'hit@5':>7} {'hit@10':>7} {'recall@10':>10}")
        for c in [0] + list(cats):
            s = stats[a][c]; n = s["n"]
            name = "ALL" if c == 0 else cats[c]
            print(f"{name:12} {n:5d} {100*s['empty']/n:6.1f}% {100*s['hit1']/n:6.1f}% {100*s['hit5']/n:6.1f}% "
                  f"{100*s['hit10']/n:6.1f}% {100*s['recall10']/n:9.1f}%")
        print("route taken:", paths[a])

if __name__ == "__main__":
    main()
