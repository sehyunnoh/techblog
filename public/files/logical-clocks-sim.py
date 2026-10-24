#!/usr/bin/env python3
"""
Wall clocks vs logical clocks in a replicated key-value store, simulated.
Python 3 standard library only. Deterministic: every run prints the same numbers.

  python logical-clocks-sim.py            # all three experiments (about 40 s)

Experiment 1  A client reads v1 from replica A, then writes v2 to replica B.
              v2 is causally after v1. Resolve with wall-clock last-write-wins and
              count how often v1 wins. Sweep the clock skew between replicas.
Experiment 2  20 clients, 20 hot keys, 3 replicas, asynchronous replication.
              Same event schedule for every conflict-resolution scheme. After all
              replication drains, classify every write ever made.
Experiment 3  Vector clocks with one entry per client, pruned to a fixed entry
              limit the way the Dynamo paper describes. Count the siblings.
"""
import heapq
import math
import random
import statistics

# ---------------------------------------------------------------- experiment 1


def phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def exp1(sigma, gap, trials, seed):
    rng = random.Random(seed)
    lost = 0
    for _ in range(trials):
        off_a, off_b = rng.gauss(0, sigma), rng.gauss(0, sigma)
        stamp_v1 = 0.0 + off_a  # v1 written on A at true time 0
        stamp_v2 = gap + off_b  # v2 written on B, `gap` ms later, after reading v1
        if stamp_v2 <= stamp_v1:
            lost += 1
    return lost / trials


def run_exp1():
    print("== Experiment 1: wall-clock LWW, causally later write loses ==")
    print("sigma_ms  gap_ms  measured  formula")
    for gap in (10, 100):
        for sigma in (0, 1, 2, 5, 10, 20, 50, 100):
            m = exp1(sigma, gap, 200_000, seed=11)
            f = 0.0 if sigma == 0 else phi(-gap / (sigma * math.sqrt(2)))
            print(f"{sigma:8d}  {gap:6d}  {m:8.4f}  {f:7.4f}")
    print()


# ---------------------------------------------------------------- experiment 2


class Ver:
    __slots__ = ("id", "key", "anc", "stamp", "vc")

    def __init__(self, vid, key, anc, stamp, vc):
        self.id, self.key, self.anc, self.stamp, self.vc = vid, key, anc, stamp, vc


def vc_leq(a, b):
    return all(b.get(k, 0) >= v for k, v in a.items())


class Replica:
    def __init__(self, off):
        self.off = off
        self.store = {}  # key -> list of versions (one, or siblings for vc)
        self.ctr = 0  # Lamport counter
        self.hl, self.hc = 0.0, 0  # hybrid logical clock


def hlc_receive(rep, pt, lm, cm):
    """Kulkarni et al. 2014: HLC update for a send or receive event."""
    l_old = rep.hl
    rep.hl = max(l_old, lm, pt)
    if rep.hl == l_old and rep.hl == lm:
        rep.hc = max(rep.hc, cm) + 1
    elif rep.hl == l_old:
        rep.hc += 1
    elif rep.hl == lm:
        rep.hc = cm + 1
    else:
        rep.hc = 0


def merge(rep, ver, scheme, st):
    """st counts merge decisions against ground truth (the writes' real ancestry):
    inv  = kept a version that is causally older than the one it discarded
    drop = discarded one of two concurrent versions without keeping both
    sib  = kept both of two concurrent versions"""
    cur = rep.store.get(ver.key, [])
    if scheme == "vc":
        for c in cur:
            if vc_leq(ver.vc, c.vc):  # already superseded, or a duplicate
                return
        for c in cur:
            if not vc_leq(c.vc, ver.vc):
                st["sib"] += 1
        rep.store[ver.key] = [c for c in cur if not vc_leq(c.vc, ver.vc)] + [ver]
        return
    if not cur:
        rep.store[ver.key] = [ver]
    elif cur[0].id != ver.id:
        keep, drop = (ver, cur[0]) if ver.stamp > cur[0].stamp else (cur[0], ver)
        if keep.id in drop.anc:
            st["inv"] += 1
        elif drop.id not in keep.anc:
            st["drop"] += 1
        rep.store[ver.key] = [keep]


def simulate(scheme, sigma, seed, n_clients=20, n_keys=20, n_rep=3, dur=20_000.0):
    rng_off = random.Random(seed * 7 + 1)
    reps = [Replica(rng_off.gauss(0, sigma)) for _ in range(n_rep)]
    crng = [random.Random(seed * 1000 + c) for c in range(n_clients)]
    last = [None] * n_clients
    heap, seq = [], 0

    def push(t, kind, data):
        nonlocal seq
        seq += 1
        heapq.heappush(heap, (t, seq, kind, data))

    for c in range(n_clients):
        push(crng[c].uniform(0, 80), "read", c)

    writes = {k: [] for k in range(n_keys)}
    vid = 0
    reads = reads_sib = 0
    vc_entries = []
    st = {"inv": 0, "drop": 0, "sib": 0}

    while heap:
        t, _, kind, data = heapq.heappop(heap)
        if kind == "read":
            c = data
            if t > dur:
                continue
            r = crng[c]
            key = r.randrange(n_keys)
            ra = r.randrange(n_rep)
            rb = ra if r.random() < 0.5 else r.randrange(n_rep)
            rt = r.uniform(2, 20)
            nxt = r.expovariate(1 / 80)
            delays = [math.exp(r.gauss(math.log(20), 0.6)) for _ in range(n_rep)]
            seen = list(reps[ra].store.get(key, []))
            reads += 1
            reads_sib += len(seen) > 1
            push(t + rt, "write", (c, key, rb, seen, delays))
            push(t + rt + nxt, "read", c)
        elif kind == "write":
            c, key, rb, seen, delays = data
            rep = reps[rb]
            ctx = list(seen) + ([last[c]] if last[c] else [])
            anc = set()
            for v in ctx:
                anc.add(v.id)
                anc |= v.anc
            vid += 1
            stamp, vc = None, None
            if scheme == "phys":
                stamp = (t + rep.off, rb, vid)
            elif scheme in ("lamport", "lamport_noctx"):
                cx = max((v.stamp[0] for v in ctx), default=0) if scheme == "lamport" else 0
                rep.ctr = max(rep.ctr, cx) + 1
                stamp = (rep.ctr, rb, vid)
            elif scheme == "hlc":
                lm, cm = max(((v.stamp[0], v.stamp[1]) for v in ctx), default=(0.0, 0))
                hlc_receive(rep, t + rep.off, lm, cm)
                stamp = (rep.hl, rep.hc, rb, vid)
            elif scheme == "vc":
                vc = {}
                for v in ctx:
                    for k, n in v.vc.items():
                        vc[k] = max(vc.get(k, 0), n)
                vc[c] = vc.get(c, 0) + 1
                vc_entries.append(len(vc))
            ver = Ver(vid, key, frozenset(anc), stamp, vc)
            last[c] = ver
            writes[key].append(ver)
            merge(rep, ver, scheme, st)
            for i in range(n_rep):
                if i != rb:
                    push(t + delays[i], "repl", (i, ver))
        else:  # repl
            i, ver = data
            rep = reps[i]
            if scheme in ("lamport", "lamport_noctx"):
                rep.ctr = max(rep.ctr, ver.stamp[0])
            elif scheme == "hlc":
                hlc_receive(rep, t + rep.off, ver.stamp[0], ver.stamp[1])
            merge(rep, ver, scheme, st)

    total = superseded = lost_conc = lost_newer = survivors = 0
    for key in range(n_keys):
        ids0 = sorted(v.id for v in reps[0].store.get(key, []))
        for rep in reps[1:]:
            assert ids0 == sorted(v.id for v in rep.store.get(key, [])), "replicas diverged"
        surv = reps[0].store.get(key, [])
        sids = {v.id for v in surv}
        anc_union = set()
        for v in surv:
            anc_union |= v.anc
        for w in writes[key]:
            total += 1
            if w.id in sids:
                survivors += 1
            elif w.id in anc_union:
                superseded += 1
            elif any(s.id in w.anc for s in surv):
                lost_newer += 1  # a write that came after the winner, yet lost
            else:
                lost_conc += 1  # concurrent with the winner, silently dropped
    return dict(
        total=total, survivors=survivors, superseded=superseded,
        lost_conc=lost_conc, lost_newer=lost_newer,
        inv=st["inv"], drop=st["drop"], sib=st["sib"],
        sib_reads=reads_sib / reads,
        vc_entries=statistics.mean(vc_entries) if vc_entries else 0,
    )


def run_exp2():
    print("== Experiment 2: mixed workload, classify every write after replication drains ==")
    cases = [
        ("phys", 0), ("phys", 20), ("phys", 100),
        ("lamport", 0), ("lamport_noctx", 0), ("hlc", 100), ("vc", 0),
    ]
    seeds = range(1, 6)
    print("per 1000 writes, merge decisions: inv = older kept over newer, drop = concurrent one discarded, sib = both kept")
    print("scheme          sigma  writes  inv  drop  sib  | final: lost_conc%  lost_newer%  | reads_w_siblings%  vc_entries")
    for scheme, sigma in cases:
        rs = [simulate(scheme, sigma, s) for s in seeds]
        tot = sum(r["total"] for r in rs)
        pct = lambda k: 100 * sum(r[k] for r in rs) / tot
        print(
            f"{scheme:14s}  {sigma:5d}  {tot:6d}  {1000 * sum(r['inv'] for r in rs) / tot:5.1f}"
            f"  {1000 * sum(r['drop'] for r in rs) / tot:5.1f}  {1000 * sum(r['sib'] for r in rs) / tot:5.1f}"
            f"  |  {pct('lost_conc'):17.2f}  {pct('lost_newer'):11.2f}  |  {100 * statistics.mean(r['sib_reads'] for r in rs):17.2f}"
            f"  {statistics.mean(r['vc_entries'] for r in rs):10.2f}"
        )
    print()


# ---------------------------------------------------------------- experiment 3


def prune_sim(pool, limit, writes, seed):
    """Sequential read-modify-write by `pool` clients. Every write has read every
    sibling, so it is a causal descendant of all of them. Any sibling left over is false."""
    rng = random.Random(seed)
    store = []  # list of (vc, ts)
    sibs_after = []
    for step in range(writes):
        c = rng.randrange(pool)
        vc, ts = {}, {}
        for svc, sts in store:
            for k, n in svc.items():
                if n > vc.get(k, 0):
                    vc[k] = n
                ts[k] = max(ts.get(k, -1), sts[k])
        vc[c] = vc.get(c, 0) + 1
        ts[c] = step
        while len(vc) > limit:
            oldest = min(ts, key=ts.get)
            del vc[oldest], ts[oldest]
        store = [(svc, sts) for svc, sts in store if not vc_leq(svc, vc)] + [(vc, ts)]
        sibs_after.append(len(store))
    return sibs_after


def run_exp3():
    print("== Experiment 3: per-client vector clock, pruned to `limit` entries ==")
    print("limit  clients  writes  sibling-writes%  mean_siblings  max_siblings")
    for limit in (10,):
        for pool in (5, 10, 11, 12, 15, 20, 50):
            sa = prune_sim(pool, limit, 2000, seed=3)
            tail = sa[500:]
            print(
                f"{limit:5d}  {pool:7d}  {len(sa):6d}  {100 * sum(s > 1 for s in tail) / len(tail):15.1f}"
                f"  {statistics.mean(tail):13.2f}  {max(sa):12d}"
            )
    print()
    print("unpruned entry count after 2000 writes = number of distinct writers (client-id clocks)")


if __name__ == "__main__":
    run_exp1()
    run_exp2()
    run_exp3()
