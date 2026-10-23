"""
Where does a trace break? Run one request through each kind of boundary and
check whether the work on the far side lands in the same trace.

Requires: opentelemetry-api, opentelemetry-sdk (measured with 1.45.1), Python 3.12.
No broker, no network beyond 127.0.0.1. The "queue" is queue.Queue and the
"database" is in-memory sqlite, so this measures how context travels (or does
not), not broker behaviour.

Usage: python trace-context-boundaries.py [N]
"""
import asyncio
import contextvars
import json
import queue
import random
import sqlite3
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased, TraceIdRatioBased
from opentelemetry.trace import Link, StatusCode

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200


def make_provider(sampler=ALWAYS_ON):
    exporter = InMemorySpanExporter()
    provider = TracerProvider(sampler=sampler)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter, provider.get_tracer("bench")


def work(tracer, i, fail=False):
    """The far-side work. Always opens one span tagged with the request id."""
    with tracer.start_as_current_span("downstream", attributes={"req.id": i}) as s:
        if fail:
            s.set_status(StatusCode.ERROR, "boom")


def score(exporter, n, linked_ok=True):
    """Per request: is the downstream span reachable from the request's root span?
    Reachable = same trace id, or (if linked_ok) a link pointing into that trace."""
    roots, downs = {}, {}
    for sp in exporter.get_finished_spans():
        rid = sp.attributes.get("req.id")
        if rid is None:
            continue
        (roots if sp.name == "POST /order" else downs)[rid] = sp
    connected = orphan = missing = 0
    for i in range(n):
        r, d = roots.get(i), downs.get(i)
        if d is None:
            missing += 1
            continue
        same = r is not None and d.context.trace_id == r.context.trace_id
        linked = (
            linked_ok
            and r is not None
            and any(l.context.trace_id == r.context.trace_id for l in d.links)
        )
        if same or linked:
            connected += 1
        else:
            orphan += 1
    return {"connected": connected, "orphan": orphan, "missing": missing}


def root(tracer, i):
    return tracer.start_as_current_span("POST /order", attributes={"req.id": i})


# ---------- boundary scenarios ----------

def s_http(propagate):
    provider, exp, tracer = make_provider()

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            ctx = extract({k.lower(): v for k, v in self.headers.items()})
            i = int(self.path.rsplit("/", 1)[1])
            with tracer.start_as_current_span("GET /stock", context=ctx, attributes={"req.id": i}):
                pass
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    for i in range(N):
        with root(tracer, i):
            headers = {}
            if propagate:
                inject(headers)
            req = urllib.request.Request(f"http://127.0.0.1:{port}/stock/{i}", headers=headers)
            urllib.request.urlopen(req).read()
    srv.shutdown()
    return score(exp, N)


def s_thread(mode):
    provider, exp, tracer = make_provider()
    with ThreadPoolExecutor(4) as ex:
        futs = []
        for i in range(N):
            with root(tracer, i):
                if mode == "default":
                    futs.append(ex.submit(work, tracer, i))
                else:  # copy_context
                    futs.append(ex.submit(contextvars.copy_context().run, work, tracer, i))
        for f in futs:
            f.result()
    return score(exp, N)


def s_asyncio(mode):
    provider, exp, tracer = make_provider()

    async def work_async(i):
        await asyncio.sleep(0)
        work(tracer, i)

    async def one(i):
        with root(tracer, i):
            if mode == "create_task":
                await asyncio.create_task(work_async(i))
            elif mode == "to_thread":
                await asyncio.to_thread(work, tracer, i)
            else:  # run_in_executor
                await asyncio.get_running_loop().run_in_executor(None, work, tracer, i)

    async def main():
        await asyncio.gather(*(one(i) for i in range(N)))

    asyncio.run(main())
    return score(exp, N)


def s_queue(carrier):
    provider, exp, tracer = make_provider()
    q = queue.Queue()

    def consumer():
        while True:
            item = q.get()
            if item is None:
                q.task_done()
                return
            i, c = item
            ctx = extract(c) if c is not None else None
            with tracer.start_as_current_span("downstream", context=ctx, attributes={"req.id": i}):
                pass
            q.task_done()

    t = threading.Thread(target=consumer)
    t.start()
    for i in range(N):
        with root(tracer, i):
            c = {}
            if carrier:
                inject(c)
            q.put((i, c if carrier else None))
    q.put(None)
    t.join()
    return score(exp, N)


def s_sqlite(trace_col):
    provider, exp, tracer = make_provider()
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.execute("create table jobs (id integer, traceparent text)")
    for i in range(N):
        with root(tracer, i):
            c = {}
            inject(c)
            db.execute("insert into jobs values (?, ?)", (i, c.get("traceparent") if trace_col else None))
    # a poller picks the rows up later, in another thread
    def poll():
        for i, tp in db.execute("select id, traceparent from jobs").fetchall():
            ctx = extract({"traceparent": tp}) if tp else None
            with tracer.start_as_current_span("downstream", context=ctx, attributes={"req.id": i}):
                pass
    t = threading.Thread(target=poll)
    t.start()
    t.join()
    return score(exp, N)


def s_batch(mode, batch=10):
    """One consumer span per batch of messages. `mode` = parent_first | links."""
    provider, exp, tracer = make_provider()
    msgs = []
    for i in range(N):
        with root(tracer, i):
            c = {}
            inject(c)
            msgs.append((i, c))
    batch_spans = []
    for start in range(0, N, batch):
        chunk = msgs[start:start + batch]
        ctxs = [extract(c) for _, c in chunk]
        if mode == "parent_first":
            sp_ctx, links = ctxs[0], []
        else:
            sp_ctx = otel_context.Context()
            links = [Link(trace.get_current_span(c).get_span_context()) for c in ctxs]
        with tracer.start_as_current_span("process batch", context=sp_ctx, links=links) as sp:
            batch_spans.append((chunk, sp))
    # per request: can you get from the request's root to the batch span?
    roots = {s.attributes["req.id"]: s for s in exp.get_finished_spans() if s.name == "POST /order"}
    batch_done = [s for s in exp.get_finished_spans() if s.name == "process batch"]
    reach = 0
    for k, (chunk, _) in enumerate(batch_spans):
        b = batch_done[k]
        linked_traces = {l.context.trace_id for l in b.links}
        for i, _ in chunk:
            r = roots[i]
            if b.context.trace_id == r.context.trace_id or r.context.trace_id in linked_traces:
                reach += 1
    return {"reachable": reach, "unreachable": N - reach, "batch_spans": len(batch_done)}


# ---------- sampling ----------

def s_sampling(carrier, n=20000, p=0.10, fail_rate=0.05, seed=7):
    """Both sides run the same config: ParentBased(TraceIdRatioBased(p)).
    The consumer fails fail_rate of messages. How many failures can you trace
    back to a recorded request span?"""
    rng = random.Random(seed)
    provider, exp, tracer = make_provider(ParentBased(TraceIdRatioBased(p)))
    msgs = []
    fails = set()
    for i in range(n):
        if rng.random() < fail_rate:
            fails.add(i)
        with root(tracer, i):
            c = {}
            inject(c)
            msgs.append((i, c if carrier else None))
    for i, c in msgs:
        ctx = extract(c) if c is not None else None
        with tracer.start_as_current_span("downstream", context=ctx, attributes={"req.id": i}) as s:
            if i in fails:
                s.set_status(StatusCode.ERROR, "boom")
    roots = {s.attributes["req.id"]: s for s in exp.get_finished_spans() if s.name == "POST /order"}
    rec_fail = conn_fail = 0
    for s in exp.get_finished_spans():
        if s.name != "downstream" or s.status.status_code != StatusCode.ERROR:
            continue
        rec_fail += 1
        r = roots.get(s.attributes["req.id"])
        if r is not None and r.context.trace_id == s.context.trace_id:
            conn_fail += 1
    return {"failures": len(fails), "failures_recorded": rec_fail, "failures_with_request_side": conn_fail}


if __name__ == "__main__":
    results = {
        "http_propagated": s_http(True),
        "http_header_dropped": s_http(False),
        "thread_submit_default": s_thread("default"),
        "thread_copy_context": s_thread("copy"),
        "asyncio_create_task": s_asyncio("create_task"),
        "asyncio_to_thread": s_asyncio("to_thread"),
        "asyncio_run_in_executor": s_asyncio("run_in_executor"),
        "queue_no_carrier": s_queue(False),
        "queue_with_carrier": s_queue(True),
        "sqlite_no_column": s_sqlite(False),
        "sqlite_traceparent_column": s_sqlite(True),
        "batch_parent_first": s_batch("parent_first"),
        "batch_links": s_batch("links"),
        "sampling_no_carrier": s_sampling(False),
        "sampling_with_carrier": s_sampling(True),
    }
    print(f"N={N}")
    print(json.dumps(results, indent=1))
