"""A minimal Backend for Frontend, measured against calling the services directly.
Run it: python bff-demo.py   (Python 3.10+, standard library only)

Three small "services" run on localhost and return deliberately verbose JSON, the
way a general-purpose API does. A mobile home screen needs a little from each:
  profile          -> name and avatar, and a "segment" the recommendations depend on
  orders           -> the 3 newest orders (id, status, total)
  recommendations  -> 5 items for that segment (title, image)

Three ways to build that screen:
  direct    the client calls the services itself: profile first, then orders and
            recommendations in parallel (recommendations need the segment)
  bff-m     one call to a mobile BFF that does the same fan-out server side and
            trims the answer to exactly what the screen shows
  bff-d     one call to a desktop BFF that returns a richer payload (10 orders,
            12 recommendations, more fields)

Everything here is simulated by me, not measured on a real network:
  - each service takes 15 ms to answer (time.sleep)
  - the client-to-server hop costs one round trip (RTT) per sequential request,
    simulated by sleeping RTT milliseconds before each request or parallel batch
  - the server-to-server hops are on localhost and cost nothing extra
What it does measure for real: request counts, bytes of JSON, and the wall-clock
cost of the Python plumbing. gzip sizes use zlib level 6 as a stand-in for what
a real web server would send.
"""
import json
import random
import statistics
import sys
import threading
import time
import urllib.request
import zlib
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVICE_MS = 15
RUNS = 30
RNG = random.Random(20261027)


def words(n):
    return " ".join(RNG.choice(["alpha", "river", "stone", "cloud", "ember", "north", "violet", "quiet"])
                    for _ in range(n))


def make_profile():
    p = {"id": 42, "name": "Dana Whitfield", "avatar": "https://img.example/u/42.jpg",
         "segment": "frequent", "email": "dana@example.com", "joined": "2021-03-04"}
    for i in range(18):
        p[f"pref_{i}"] = words(3)
    p["address"] = {"line1": words(3), "line2": words(2), "city": "Leeds", "zip": "LS1 4AB", "country": "GB"}
    return p


def make_order(i):
    o = {"id": 9000 - i, "status": RNG.choice(["shipped", "pending", "delivered"]), "total": round(RNG.uniform(5, 300), 2),
         "currency": "GBP", "created": f"2026-10-{(i % 27) + 1:02d}", "payment": {"method": "card", "last4": "4242"},
         "shipping": {"carrier": "RM", "tracking": words(1) + str(i), "address": words(5)}}
    o["lines"] = [{"sku": f"S{i}{j}", "title": words(3), "qty": RNG.randint(1, 3), "price": round(RNG.uniform(1, 90), 2),
                   "notes": words(6)} for j in range(4)]
    return o


def make_rec(i):
    return {"id": i, "title": words(3), "image": f"https://img.example/r/{i}.jpg", "description": words(25),
            "price": round(RNG.uniform(3, 120), 2), "rating": round(RNG.uniform(2, 5), 1),
            "tags": [words(1) for _ in range(6)], "debug": {"model": "rec-v7", "score": RNG.random(), "features": words(12)}}


PROFILE = make_profile()
ORDERS = [make_order(i) for i in range(30)]
RECS = [make_rec(i) for i in range(40)]


class Upstream(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(SERVICE_MS / 1000)
        if self.path.startswith("/profile"):
            body = PROFILE
        elif self.path.startswith("/orders"):
            body = ORDERS
        else:
            body = RECS
        self.send(body)

    def send(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


def get(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read())


UP = "http://127.0.0.1:18001"


class Bff(BaseHTTPRequestHandler):
    """One handler, two experiences. In a real system these would be two services."""

    def do_GET(self):
        profile = get(f"{UP}/profile")
        with ThreadPoolExecutor(2) as ex:
            f_orders = ex.submit(get, f"{UP}/orders")
            f_recs = ex.submit(get, f"{UP}/recs?segment={profile['segment']}")
            orders, recs = f_orders.result(), f_recs.result()
        if self.path == "/mobile/home":
            body = {"name": profile["name"], "avatar": profile["avatar"],
                    "orders": [{"id": o["id"], "status": o["status"], "total": o["total"]} for o in orders[:3]],
                    "recs": [{"title": r["title"], "image": r["image"]} for r in recs[:5]]}
        else:
            body = {"profile": {k: profile[k] for k in ("name", "avatar", "email", "joined", "address")},
                    "orders": [{k: o[k] for k in ("id", "status", "total", "currency", "created", "lines")}
                               for o in orders[:10]],
                    "recs": [{k: r[k] for k in ("title", "image", "description", "price", "rating")}
                             for r in recs[:12]]}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


def serve(handler, port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def raw(url):
    with urllib.request.urlopen(url) as r:
        return r.read()


def run_direct(rtt):
    sizes = []
    time.sleep(rtt)                                   # request 1: profile
    p = raw(f"{UP}/profile")
    sizes.append(p)
    seg = json.loads(p)["segment"]
    time.sleep(rtt)                                   # requests 2 and 3 in parallel: one RTT
    with ThreadPoolExecutor(2) as ex:
        a = ex.submit(raw, f"{UP}/orders")
        b = ex.submit(raw, f"{UP}/recs?segment={seg}")
        sizes += [a.result(), b.result()]
    return 3, sizes


def run_bff(path, rtt):
    time.sleep(rtt)
    return 1, [raw(f"http://127.0.0.1:18002{path}")]


def measure(label, fn, rtt_ms):
    times = []
    n, sizes = 0, []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        n, sizes = fn(rtt_ms / 1000)
        times.append((time.perf_counter() - t0) * 1000)
    total = sum(len(s) for s in sizes)
    gz = sum(len(zlib.compress(s, 6)) for s in sizes)
    return dict(label=label, requests=n, bytes=total, gzip=gz,
                median=statistics.median(times), p90=sorted(times)[int(RUNS * 0.9) - 1])


def main():
    serve(Upstream, 18001)
    serve(Bff, 18002)
    time.sleep(0.3)
    print(f"service time {SERVICE_MS} ms each, {RUNS} runs per cell, one simulated RTT per sequential client request")
    print()
    for rtt in (0, 80, 250):
        print(f"client RTT {rtt} ms")
        print(f"  {'variant':<8} {'client reqs':>11} {'JSON bytes':>11} {'gzip bytes':>11} {'median ms':>10} {'p90 ms':>8}")
        for label, fn in (("direct", run_direct),
                          ("bff-m", lambda r: run_bff("/mobile/home", r)),
                          ("bff-d", lambda r: run_bff("/desktop/home", r))):
            m = measure(label, fn, rtt)
            print(f"  {m['label']:<8} {m['requests']:>11} {m['bytes']:>11,} {m['gzip']:>11,} "
                  f"{m['median']:>10.0f} {m['p90']:>8.0f}")
        print()


if __name__ == "__main__":
    sys.exit(main())
