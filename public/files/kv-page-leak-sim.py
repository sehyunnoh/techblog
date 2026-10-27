"""KV-cache page reuse simulation for the Cloudflare GLM-5.3 incident (Aug 27 - Sep 9, 2026).
Run it: python kv-page-leak-sim.py   (needs numpy)

This is a MODEL of the mechanism described in Cloudflare's post and in SGLang
issue #30233 / PR #38704. It does not run SGLang and measures nothing about
Cloudflare's systems. Assumptions I chose myself (not from the sources):
  - page size 64 tokens (681,280 = 10,645 pages exactly; 1,048,576 = 16,384)
  - decode pool of 32,768 pages (2,097,152 tokens), only needs to exceed one context
  - background requests: log-normal prompt length, median 8,000 tokens, clipped
  - each background request lives a geometric number of steps (mean 40)
  - free pages are handed out last-freed-first (LIFO) unless stated otherwise
  - pages are never zeroed on free (the post says this is common practice)
Mechanism modeled: a rejected oversized request is swapped for a one-token
placeholder, still admitted, writes ONE page, and decode reserves pages for the
full prompt length. The other pages keep whatever the previous owner wrote.
"""
import heapq
import sys
from collections import deque

import numpy as np

PAGE = 64
PREFILL_POOL_TOKENS = 681_280
CONTEXT_TOKENS = 1_048_576
DECODE_PAGES = 32_768
TENANTS = 200


class Pool:
    def __init__(self, n_pages, policy, rng):
        self.n = n_pages
        self.policy = policy
        self.rng = rng
        self.owner = np.full(n_pages, -1, dtype=np.int64)  # request id that last wrote the page
        order = list(range(n_pages))
        if policy == "random":
            self.rng.shuffle(order)
        self.free = deque(order) if policy == "fifo" else order

    def n_free(self):
        return len(self.free)

    def alloc(self, k):
        if len(self.free) < k:
            return None
        if self.policy == "lifo":
            pages = [self.free.pop() for _ in range(k)]
        elif self.policy == "fifo":
            assert isinstance(self.free, deque)
            pages = [self.free.popleft() for _ in range(k)]
        else:
            pages = []
            for _ in range(k):
                i = int(self.rng.integers(len(self.free)))
                self.free[i], self.free[-1] = self.free[-1], self.free[i]
                pages.append(self.free.pop())
        return pages

    def release(self, pages):
        self.free.extend(pages)


class Sim:
    def __init__(self, seed, policy="lifo", util=0.5):
        self.rng = np.random.default_rng(seed)
        self.pool = Pool(DECODE_PAGES, policy, self.rng)
        self.util = util
        self.live = {}            # rid -> pages
        self.heap = []            # (finish_step, rid)
        self.step_no = 0
        self.next_rid = 0
        self.finish_seq = {}      # rid -> order in which it finished
        self.n_finished = 0
        self.tenant = {}

    def _new_len(self):
        t = int(self.rng.lognormal(np.log(8000), 1.1))
        return min(max(t, 100), 400_000)

    def _finish_due(self):
        while self.heap and self.heap[0][0] <= self.step_no:
            _, rid = heapq.heappop(self.heap)
            self.pool.release(self.live.pop(rid))
            self.finish_seq[rid] = self.n_finished
            self.n_finished += 1

    def step(self, arrivals=True):
        self.step_no += 1
        self._finish_due()
        if not arrivals:
            return
        used = self.pool.n - self.pool.n_free()
        if used < self.util * self.pool.n:
            rid = self.next_rid
            self.next_rid += 1
            k = -(-self._new_len() // PAGE)
            pages = self.pool.alloc(k)
            if pages is None:
                return
            self.pool.owner[pages] = rid      # prefill writes every page it owns
            self.tenant[rid] = int(self.rng.integers(TENANTS))
            self.live[rid] = pages
            life = int(self.rng.geometric(1 / 40))
            heapq.heappush(self.heap, (self.step_no + life, rid))

    def warm(self, steps):
        for _ in range(steps):
            self.step()

    def oversized_request(self, prompt_tokens):
        """Inject the rejected-then-admitted request. Returns stats on what decode reads."""
        n = -(-prompt_tokens // PAGE)
        while self.pool.n_free() < n:         # queue until decode has room
            self.step(arrivals=False)
        vid = self.next_rid
        self.next_rid += 1
        victim_tenant = -1
        pages = self.pool.alloc(n)
        assert pages is not None
        # prefill wrote exactly one page (the placeholder token); the rest is untouched
        first = pages[0]
        read_owners = self.pool.owner[pages[1:]]
        self.pool.owner[first] = vid
        foreign = read_owners[read_owners >= 0]
        never_written = int((read_owners < 0).sum())
        tenants = {self.tenant[int(o)] for o in np.unique(foreign)}
        ages = [self.n_finished - self.finish_seq[int(o)] for o in np.unique(foreign)
                if int(o) in self.finish_seq]
        out = dict(
            pages=n,
            foreign_pages=int(foreign.size),
            never_written=never_written,
            foreign_frac=foreign.size / n,
            distinct_requests=int(np.unique(foreign).size),
            distinct_tenants=len(tenants),
            median_age=float(np.median(ages)) if ages else float("nan"),
            max_age=int(max(ages)) if ages else -1,
        )
        self.pool.release(pages)              # victim's reply is sent; pages go back unzeroed
        self.finish_seq[vid] = self.n_finished
        self.tenant[vid] = victim_tenant
        self.n_finished += 1
        return out


def trials(seed, warm_steps, policy="lifo", util=0.5, n=30, tokens=None):
    """n independent servers, one oversized request each, so earlier victims
    do not leave their own residue behind for later ones."""
    res = []
    for i in range(n):
        s = Sim(seed + i, policy, util)
        s.warm(warm_steps)
        t = tokens if tokens else int(s.rng.integers(PREFILL_POOL_TOKENS + 1, CONTEXT_TOKENS + 1))
        res.append(s.oversized_request(t))
    return res


def summarize(res, key):
    v = np.array([r[key] for r in res], dtype=float)
    return v


def main():
    seed = 20261027
    print(f"page={PAGE} tokens, prefill pool={PREFILL_POOL_TOKENS // PAGE} pages, "
          f"context={CONTEXT_TOKENS // PAGE} pages, decode pool={DECODE_PAGES} pages")
    print()

    print("A. Fraction of the oversized request's context that is another request's leftovers,")
    print("   by how much traffic the pool has seen first (LIFO allocator, 50% utilization)")
    print("   warm_steps  mean_foreign_frac  never_written_frac  detected_by_content_check")
    for w in (0, 1, 5, 20, 100, 500, 3000):
        r = trials(seed, w)
        ff = summarize(r, "foreign_frac")
        nw = np.array([x["never_written"] / x["pages"] for x in r])
        det = float(np.mean([x["foreign_pages"] > 0 for x in r]))
        print(f"   {w:>9}  {ff.mean():>17.3f}  {nw.mean():>18.3f}  {det:>25.2f}")
    print()

    print("B. After warm-up (3000 steps): who is exposed, by allocator policy and utilization")
    print("   policy util  foreign_frac  distinct_requests  distinct_tenants  median_age_in_finishes")
    for policy in ("lifo", "fifo", "random"):
        for util in (0.3, 0.6):
            r = trials(seed, 3000, policy, util)
            print(f"   {policy:>6} {util:.1f}  {summarize(r, 'foreign_frac').mean():>12.3f}  "
                  f"{summarize(r, 'distinct_requests').mean():>17.1f}  "
                  f"{summarize(r, 'distinct_tenants').mean():>16.1f}  "
                  f"{np.nanmedian(summarize(r, 'median_age')):>22.0f}")
    print()

    print("C. 100 oversized requests (one per server) on a warm pool (3000 steps, LIFO, 50%)")
    r = trials(seed, 3000, n=100)
    print("   HTTP status of every reply: 200 (the stale pages decode as normal tokens)")
    print(f"   replies with >=1 foreign page : {sum(x['foreign_pages'] > 0 for x in r)} / 100")
    print(f"   foreign share of context      : min {summarize(r, 'foreign_frac').min():.4f} "
          f"max {summarize(r, 'foreign_frac').max():.4f}")
    print(f"   foreign tenants per reply     : min {summarize(r, 'distinct_tenants').min():.0f} "
          f"median {np.median(summarize(r, 'distinct_tenants')):.0f} "
          f"max {summarize(r, 'distinct_tenants').max():.0f}")
    print()

    print("D. Smallest and largest rejected prompt, warm pool")
    for tok in (PREFILL_POOL_TOKENS + 1, 850_000, CONTEXT_TOKENS):
        r = trials(seed, 3000, tokens=tok)
        print(f"   {tok:>9} tokens -> pages {r[0]['pages']:>6}, "
              f"foreign share {summarize(r, 'foreign_frac').mean():.3f}")


if __name__ == "__main__":
    sys.exit(main())
