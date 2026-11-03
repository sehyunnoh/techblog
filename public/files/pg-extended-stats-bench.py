#!/usr/bin/env python3
"""Measure what CREATE STATISTICS changes on correlated columns (PostgreSQL 17).

Standard library only. Talks to a running server through the psql CLI.

  python pg-extended-stats-bench.py --psql /path/to/psql --port 54329 --user bench \
      --rows 3000000 --out results.json

Scenarios (all on one table `addr`, columns city/zip/state where zip and state
are functions of city, so they are perfectly correlated):
  Q1  equality filter on all three columns          (dependencies / mcv)
  Q2  GROUP BY city, zip, state                      (ndistinct)
  Q3  join of the Q1 filter against an indexed table (does a bad estimate pick a bad join?)
  Q4  filter on a combination that does not exist    (the known trap of `dependencies`)
  Q5  range filter on zip + equality on city         (what `dependencies` cannot see)

Each query is run once to warm up, then 5 times with
EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON); the median execution time is kept.
Parallel query and JIT are off for the session.
"""
import argparse, json, statistics, subprocess, sys, time

p = argparse.ArgumentParser()
p.add_argument("--psql", required=True)
p.add_argument("--port", default="54329")
p.add_argument("--user", default="bench")
p.add_argument("--db", default="postgres")
p.add_argument("--rows", type=int, default=3_000_000)
p.add_argument("--cities", type=int, default=2000)
p.add_argument("--runs", type=int, default=5)
p.add_argument("--work-mem", default="4MB", help="work_mem for the measured session")
p.add_argument("--rounds", type=int, default=3, help="how many times to cycle through all variants")
p.add_argument("--probe-city", type=int, default=123, help="city id used in the equality filters")
p.add_argument("--out", default="results.json")
a = p.parse_args()


def psql(sql, session=True):
    pre = ""
    if session:
        pre = f"SET max_parallel_workers_per_gather = 0; SET jit = off; SET work_mem = '{a.work_mem}';\n"
    r = subprocess.run(
        [a.psql, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
         "-h", "127.0.0.1", "-p", a.port, "-U", a.user, "-d", a.db],
        input=pre + sql, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("psql failed:\n" + r.stderr + "\nSQL:\n" + sql)
    return r.stdout.strip()


def scalar(sql):
    out = psql(sql)
    return out.splitlines()[-1] if out else ""


def walk(node, acc):
    label = node["Node Type"]
    for k in ("Join Type", "Strategy"):
        if k in node:
            label += " " + node[k]
    extra = {k: node[k] for k in ("Hash Batches", "Original Hash Batches", "Peak Memory Usage", "HashAgg Batches", "Disk Usage", "Index Name") if k in node}
    acc.append({"type": label, **extra,
                "est": node["Plan Rows"], "actual": node["Actual Rows"], "loops": node.get("Actual Loops", 1)})
    for c in node.get("Plans", []):
        walk(c, acc)
    return acc


def explain(sql):
    runs = []
    plan = None
    for i in range(a.runs + 1):  # first run is the warm-up
        out = psql("EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON) " + sql)
        j = json.loads(out)[0]
        if i == 0:
            continue
        runs.append(j["Execution Time"])
        plan = j
    top = plan["Plan"]
    return {
        "exec_ms_median": round(statistics.median(runs), 2),
        "exec_ms_all": [round(x, 2) for x in runs],
        "planning_ms": round(plan["Planning Time"], 3),
        "nodes": walk(top, []),
    }


C = a.probe_city
Z = 10000 + C
S = C % 50
QUERIES = {
    "Q1_equality_all_three": f"SELECT count(pad) FROM addr WHERE city = {C} AND zip = {Z} AND state = {S}",
    "Q2_group_by_three": "SELECT count(*) FROM (SELECT city, zip, state, count(*) FROM addr GROUP BY city, zip, state) g",
    "Q3_join_filtered_to_orders": (f"SELECT count(o.amount) FROM addr a JOIN orders o ON o.addr_id = a.id "
                                   f"WHERE a.city = {C} AND a.zip = {Z} AND a.state = {S}"),
    "Q4_nonexistent_combo": f"SELECT count(pad) FROM addr WHERE city = {C} AND zip = {Z + 1} AND state = {S}",
    "Q5_range_zip_plus_city": f"SELECT count(pad) FROM addr WHERE city = {C} AND zip BETWEEN {Z - 23} AND {Z + 27}",
}

STAT_VARIANTS = [
    ("none", None),
    ("dependencies", "dependencies"),
    ("ndistinct", "ndistinct"),
    ("mcv", "mcv"),
    ("all_three", "ndistinct, dependencies, mcv"),
]

t0 = time.time()
print("building data ...", flush=True)
psql(f"""
DROP TABLE IF EXISTS orders; DROP TABLE IF EXISTS addr;
SELECT setseed(0.42);
CREATE TABLE addr AS
SELECT i AS id, c AS city, 10000 + c AS zip, c % 50 AS state, repeat('x', 40) AS pad
FROM (SELECT i, (random() * {a.cities - 1})::int AS c FROM generate_series(1, {a.rows}) i) s;
CREATE INDEX addr_city ON addr(city);
CREATE INDEX addr_zip ON addr(zip);
CREATE TABLE orders AS
SELECT g AS id, (random() * {a.rows - 1})::int + 1 AS addr_id, (random() * 100)::int AS amount
FROM generate_series(1, {a.rows // 2}) g;
CREATE INDEX orders_addr ON orders(addr_id);
VACUUM ANALYZE addr; VACUUM ANALYZE orders;
""", session=False)

truth = {
    "rows": int(scalar("SELECT count(*) FROM addr")),
    "addr_table_bytes": int(scalar("SELECT pg_table_size('addr')")),
    "cities": a.cities, "probe_city": C,
    "q1_actual": int(scalar(f"SELECT count(*) FROM addr WHERE city={C} AND zip={Z} AND state={S}")),
    "q2_groups_actual": int(scalar("SELECT count(*) FROM (SELECT 1 FROM addr GROUP BY city, zip, state) g")),
    "q4_actual": int(scalar(f"SELECT count(*) FROM addr WHERE city={C} AND zip={Z+1} AND state={S}")),
    "q5_actual": int(scalar(f"SELECT count(*) FROM addr WHERE city={C} AND zip BETWEEN {Z-23} AND {Z+27}")),
    "version": scalar("SHOW server_version"),
}
print("truth:", truth, flush=True)

def signature(nodes):
    return " > ".join(n["type"] + (":" + n["Index Name"] if "Index Name" in n else "") for n in nodes)


truth["work_mem"] = scalar("SHOW work_mem")  # read back from the session, not echoed from the flag
assert truth["work_mem"] == a.work_mem, f"work_mem not applied: {truth['work_mem']} != {a.work_mem}"
results = {"truth": truth, "rounds": a.rounds, "runs_per_round": a.runs, "variants": {}}
for name, _ in STAT_VARIANTS:
    results["variants"][name] = {"analyze_s": [], "ext_data_bytes": 0, "queries": {q: {"rounds": []} for q in QUERIES}}

for rnd in range(a.rounds):
    for name, kinds in STAT_VARIANTS:
        psql("DROP STATISTICS IF EXISTS addr_ext;", session=False)
        if kinds:
            psql(f"CREATE STATISTICS addr_ext ({kinds}) ON city, zip, state FROM addr;", session=False)
        t = time.time()
        psql("ANALYZE addr;", session=False)
        v = results["variants"][name]
        v["analyze_s"].append(round(time.time() - t, 2))
        if kinds:
            v["ext_data_bytes"] = int(scalar("SELECT coalesce(sum(pg_column_size(d)), 0) FROM pg_statistic_ext_data d"))
        for qn, q in QUERIES.items():
            r = explain(q)
            r["signature"] = signature(r["nodes"])
            v["queries"][qn]["rounds"].append(r)
            print(f"r{rnd} {name:13s} {qn:28s} {r['exec_ms_median']:>8} ms  {r['signature']}", flush=True)

json.dump(results, open(a.out, "w"), indent=2)
print(f"done in {time.time() - t0:.0f}s -> {a.out}")
