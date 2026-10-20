"""How much of a long conversation fits in Hermes' built-in curated memory?

Hermes caps MEMORY.md at 2,200 chars (tools/memory_tool_store.py, memory_char_limit) and joins
entries with "\\n§\\n". LoCoMo ships, per conversation, one LLM-written fact per evidence turn
("observation"). Treat those facts as what a very diligent curator would have written, then
ask: with an ORACLE that already knows every future question, how many questions can a
2,200-char memory answer? Real curators do not know the questions, so this is an upper bound.
"""
import json, re, sys

DATA = sys.argv[1] if len(sys.argv) > 1 else "locomo10.json"
CAP, DELIM = 2200, len("\n§\n")
CATS = {1, 2, 3, 4}

def evidence_ids(qa):
    """LoCoMo evidence strings are sometimes malformed ("D9:1 D4:4", "D8:6; D9:17", "D:11:26", "D30:05"); normalise all."""
    return {f"D{a}:{int(b)}" for a, b in re.findall(r"D:?(\d+):0*(\d+)", " ".join(qa.get("evidence", [])))}

def facts_of(conv):
    out = {}
    for sess in conv["observation"].values():
        for items in sess.values():
            for text, dia in items:
                ids = dia if isinstance(dia, list) else [dia]
                for i in ids:
                    out[i] = text
    return out

def greedy(facts, qas, cap):
    chosen, used, covered = set(), 0, set()
    need = [(qi, set(ev)) for qi, ev in qas]
    while True:
        best, best_score = None, 0.0
        for fid, text in facts.items():
            if fid in chosen:
                continue
            cost = len(text) + (DELIM if chosen else 0)
            if used + cost > cap:
                continue
            gain = sum(1.0 / len(ev) for qi, ev in need if qi not in covered and fid in ev)
            if gain / cost > best_score:
                best, best_score = fid, gain / cost
        if best is None:
            break
        chosen.add(best)
        used += len(facts[best]) + (DELIM if len(chosen) > 1 else 0)
        for qi, ev in need:
            if ev <= chosen:
                covered.add(qi)
    return chosen, used, covered

def main():
    data = json.load(open(DATA, encoding="utf-8"))
    tot = dict(qa=0, answerable=0, fit=0, facts=0, factchars=0, convchars=0, chosen=0)
    for conv in data:
        facts = facts_of(conv)
        convchars = sum(len(t["text"]) for k, v in conv["conversation"].items()
                        if re.fullmatch(r"session_\d+", k) for t in v)
        qas = []
        for i, qa in enumerate(conv["qa"]):
            ev = evidence_ids(qa)
            if qa["category"] in CATS and ev:
                qas.append((i, ev))
        have = [(i, ev) for i, ev in qas if ev <= set(facts)]
        chosen, used, covered = greedy(facts, have, CAP)
        factchars = sum(len(t) for t in facts.values()) + DELIM * (len(facts) - 1)
        print(f"{conv['sample_id']}: conv {convchars:6d} chars | facts {len(facts):3d} = {factchars:5d} chars "
              f"({factchars/CAP:4.1f}x cap) | QA {len(qas):3d}, answerable from some fact {len(have):3d}, "
              f"oracle 2,200-char memory answers {len(covered):3d} using {len(chosen)} facts / {used} chars")
        tot["qa"] += len(qas); tot["answerable"] += len(have); tot["fit"] += len(covered)
        tot["facts"] += len(facts); tot["factchars"] += factchars; tot["convchars"] += convchars
        tot["chosen"] += len(chosen)
    print(f"\nTOTAL: {tot['qa']} questions; {tot['answerable']} ({100*tot['answerable']/tot['qa']:.1f}%) have every "
          f"evidence turn covered by a curated fact; oracle 2,200-char memory answers {tot['fit']} "
          f"({100*tot['fit']/tot['qa']:.1f}% of all, {100*tot['fit']/tot['answerable']:.1f}% of answerable)")
    n = len(data)
    print(f"per conversation: {tot['convchars']/n:.0f} chars of dialogue; curated facts {tot['factchars']/n:.0f} chars "
          f"= {tot['factchars']/n/CAP:.1f}x the cap; {tot['chosen']/n:.1f} facts fit on average")

if __name__ == "__main__":
    main()
