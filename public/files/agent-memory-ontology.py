"""Does a typed fact layer (subject, statement, source turn) help agent-memory retrieval on LoCoMo?

Download locomo10.json from https://github.com/snap-research/locomo (data/locomo10.json), then:
    python agent-memory-ontology.py locomo10.json

Needs agent-memory-fts-recall.py in the same folder. Arms (hit@k = an evidence turn is in the top k turns):
  A  raw turns, Hermes retrieval path (AND, trigram, OR retry)           the previous post's baseline
  B  facts only: LoCoMo's LLM-written "observation" facts, same path, mapped back to their source turn
  C  facts scoped by subject: if the question names a speaker, search only that speaker's facts
  D  A and C fused with reciprocal rank fusion (k=60)
  E  C with the session date prepended to each fact (a "when" attribute on every fact)
  F  raw turns, scoped by who spoke the turn (typing without an LLM rewrite)
  G  F and C fused with reciprocal rank fusion
The facts are written by an LLM that saw the same turns the questions were built from, so B to E are
an optimistic ceiling for a fact layer, not what a live extractor would deliver.
"""
import importlib.util, json, os, re, sqlite3, sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("fr", os.path.join(HERE, "agent-memory-fts-recall.py"))
fr = importlib.util.module_from_spec(spec); spec.loader.exec_module(fr)

DATA = sys.argv[1] if len(sys.argv) > 1 else "locomo10.json"
KS = (1, 5, 10)
CATS = {1: "multi-hop", 2: "temporal", 3: "open-domain", 4: "single-hop"}

def norm_ids(raw):
    s = raw if isinstance(raw, str) else " ".join(raw)
    return [f"D{a}:{int(b)}" for a, b in re.findall(r"D:?(\d+):0*(\d+)", s)]

def load_facts(conv):
    """[(speaker, text, [dia_ids], session_date)] from the observation block."""
    out = []
    for key, per_speaker in conv["observation"].items():
        n = re.match(r"session_(\d+)_observation", key).group(1)
        date = conv["conversation"].get(f"session_{n}_date_time", "")
        for speaker, items in per_speaker.items():
            for text, ev in items:
                ids = norm_ids(ev)
                if ids:
                    out.append((speaker, text, ids, date))
    return out

def build_fact_db(facts, with_date):
    con = sqlite3.connect(":memory:")
    con.execute("CREATE VIRTUAL TABLE fts USING fts5(content)")
    con.execute("CREATE VIRTUAL TABLE tri USING fts5(content, tokenize='trigram')")
    for i, (sp, text, ids, date) in enumerate(facts, 1):
        body = f"{date} {text}" if with_date else text
        con.execute("INSERT INTO fts(rowid, content) VALUES (?,?)", (i, body))
        con.execute("INSERT INTO tri(rowid, content) VALUES (?,?)", (i, body))
    return con

def turns_from_fact_rows(rows, facts, limit=10):
    """Map ranked fact rowids to a ranked, de-duplicated list of source turns."""
    seen, out = set(), []
    for r in rows:
        for d in facts[r - 1][2]:
            if d not in seen:
                seen.add(d); out.append(d)
    return out[:limit]

def scoped_rows(con, q, facts, speaker_names, limit):
    """Same retrieval path, then keep only rows whose subject is a speaker named in the question."""
    named = {s for s in speaker_names if re.search(rf"\b{re.escape(s)}\b", q)}
    rows, _ = fr.hermes_path(con, q, 200 if named else limit, relax=True)
    if named:
        rows = [r for r in rows if facts[r - 1][0] in named]
    return rows[:limit], bool(named)

def turn_speakers(conv):
    return {t["dia_id"]: t["speaker"] for k, v in conv["conversation"].items()
            if re.fullmatch(r"session_\d+", k) for t in v}

def rrf(*lists, k=60):
    score = defaultdict(float)
    for lst in lists:
        for rank, d in enumerate(lst, 1):
            score[d] += 1.0 / (k + rank)
    return [d for d, _ in sorted(score.items(), key=lambda x: -x[1])]

def main():
    data = json.load(open(DATA, encoding="utf-8"))
    arms = ["A raw turns (baseline)", "B facts only", "C facts, subject-scoped", "D A+C fused (RRF)", "E C + session date", "F raw turns, speaker-scoped", "G F+C fused (RRF)"]
    st = {a: {c: {"n": 0, **{f"hit{k}": 0 for k in KS}} for c in list(CATS) + [0]} for a in arms}
    cov = {"covered": [0, 0], "uncovered": [0, 0]}  # [questions, arm C hits]
    named_n = named_hits = unnamed_n = unnamed_hits = 0
    fact_chars = turn_chars = n_facts = n_turns = covered_turns = 0
    for conv in data:
        con, ids, turns = fr.build(conv["conversation"])
        facts = load_facts(conv)
        spk = turn_speakers(conv)
        fact_turns = {d for f in facts for d in f[2]}
        speakers = [conv["conversation"]["speaker_a"], conv["conversation"]["speaker_b"]]
        fdb, fdb_date = build_fact_db(facts, False), build_fact_db(facts, True)
        n_facts += len(facts); n_turns += len(turns)
        fact_chars += sum(len(f[1]) for f in facts); turn_chars += sum(len(t) for _, t in turns)
        covered_turns += len({d for f in facts for d in f[2]} & set(ids))
        for qa in conv["qa"]:
            c = qa["category"]; ev = fr.evidence_ids(qa)
            if c not in CATS or not ev:
                continue
            q = qa["question"]
            a_rows, _ = fr.hermes_path(con, q, 10, relax=True)
            A = [ids[r - 1] for r in a_rows]
            b_rows, _ = fr.hermes_path(fdb, q, 10, relax=True)
            B = turns_from_fact_rows(b_rows, facts)
            c_rows, named = scoped_rows(fdb, q, facts, speakers, 10)
            C = turns_from_fact_rows(c_rows, facts)
            D = rrf(A, C)[:10]
            e_rows, _ = scoped_rows(fdb_date, q, facts, speakers, 10)
            E = turns_from_fact_rows(e_rows, facts)
            named_set = {s_ for s_ in speakers if re.search(rf"\b{re.escape(s_)}\b", q)}
            f_rows, _ = fr.hermes_path(con, q, 200 if named_set else 10, relax=True)
            if named_set:
                f_rows = [r for r in f_rows if spk[ids[r - 1]] in named_set]
            F = [ids[r - 1] for r in f_rows[:10]]
            key_cov = "covered" if ev & fact_turns else "uncovered"
            cov[key_cov][0] += 1; cov[key_cov][1] += bool(ev & set(C[:10]))
            for name, got in zip(arms, (A, B, C, D, E, F, rrf(F, C)[:10])):
                for key in (c, 0):
                    s = st[name][key]; s["n"] += 1
                    for k in KS:
                        s[f"hit{k}"] += bool(ev & set(got[:k]))
            hit = bool(ev & set(C[:10]))
            if named: named_n += 1; named_hits += hit
            else: unnamed_n += 1; unnamed_hits += hit
    print(f"corpus: {len(data)} conversations, {n_turns} turns ({turn_chars} chars), {n_facts} facts ({fact_chars} chars)")
    print(f"turns that are the source of at least one fact: {covered_turns}/{n_turns} ({100*covered_turns/n_turns:.1f}%)")
    print(f"fact layer size vs raw turns: {100*fact_chars/turn_chars:.1f}% of the characters")
    for a in arms:
        print(f"\n== {a}")
        print(f"{'category':12} {'n':>5} {'hit@1':>7} {'hit@5':>7} {'hit@10':>7}")
        for c in [0] + list(CATS):
            s = st[a][c]; n = s["n"]
            print(f"{'ALL' if c == 0 else CATS[c]:12} {n:5d} " + " ".join(f"{100*s[f'hit{k}']/n:6.1f}%" for k in KS))
    for k_, (n_, h_) in cov.items():
        print(f"questions whose evidence turn is {k_} by the fact layer: {n_} ({100*n_/1536:.1f}%), arm C hit@10 = {100*h_/max(n_,1):.1f}%")
    print(f"\nC when the question names a speaker: {named_hits}/{named_n} = {100*named_hits/named_n:.1f}% hit@10")
    print(f"C when it does not:                 {unnamed_hits}/{unnamed_n} = {100*unnamed_hits/max(unnamed_n,1):.1f}% hit@10")

if __name__ == "__main__":
    main()
