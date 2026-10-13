#!/usr/bin/env python3
"""How gRPC spreads calls across three backends, measured on one machine.

Needs:  pip install grpcio==1.76.0     (tested with Python 3.10 on Windows 11)
Run:    python grpc-lb-bench.py

No .proto files: the three backends are plain gRPC servers that answer
/bench.Echo/Ping with the index of the backend that handled the call, so the
client can count where every call landed.

Experiments (all on 127.0.0.1):
  E1  one channel, three addresses, default policy (pick_first)
  E2  one channel, three addresses, round_robin from the service config
  E3  one channel through a TCP-level (L4) round-robin proxy
  E4  thirty channels through the same L4 proxy, one connection each
  E5  E3 plus MAX_CONNECTION_AGE on the servers (reconnects every ~2 s)
  E6  round_robin, one backend killed mid-run, with and without a retry policy
"""
import asyncio
import collections
import itertools
import json
import statistics
import threading
import time
from concurrent import futures

import grpc

BASE = 50061
N_BACKENDS = 3
PROXY_PORT = 50070
METHOD = "/bench.Echo/Ping"


# ---------------------------------------------------------------- backends
def start_backends(extra_options=(), delay=0.0):
    servers = []
    for i in range(N_BACKENDS):
        def ping(_request, _context, i=i):
            if delay:
                time.sleep(delay)
            return str(i).encode()

        handler = grpc.method_handlers_generic_handler(
            "bench.Echo",
            {"Ping": grpc.unary_unary_rpc_method_handler(ping)},
        )
        s = grpc.server(futures.ThreadPoolExecutor(max_workers=8), options=list(extra_options))
        s.add_generic_rpc_handlers((handler,))
        s.add_insecure_port(f"127.0.0.1:{BASE + i}")
        s.start()
        servers.append(s)
    return servers


def stop_backends(servers):
    for s in servers:
        s.stop(0).wait()


# ------------------------------------------------------- L4 (TCP) proxy
class TcpProxy:
    """Hands each new TCP connection to the next backend. Never looks inside HTTP/2."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.rr = itertools.count()
        self.ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self.ready.wait()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        server = self.loop.run_until_complete(asyncio.start_server(self._handle, "127.0.0.1", PROXY_PORT))
        self.server = server
        self.ready.set()
        self.loop.run_forever()

    async def _handle(self, reader, writer):
        port = BASE + next(self.rr) % N_BACKENDS
        try:
            up_r, up_w = await asyncio.open_connection("127.0.0.1", port)
        except OSError:
            writer.close()
            return

        async def pipe(r, w):
            try:
                while data := await r.read(65536):
                    w.write(data)
                    await w.drain()
            except (ConnectionError, OSError):
                pass
            finally:
                try:
                    w.close()
                except Exception:
                    pass

        await asyncio.gather(pipe(reader, up_w), pipe(up_r, writer))

    def stop(self):
        self.loop.call_soon_threadsafe(self.server.close)
        self.loop.call_soon_threadsafe(self.loop.stop)


# ------------------------------------------------------------- helpers
ROUND_ROBIN = json.dumps({"loadBalancingConfig": [{"round_robin": {}}]})
RETRY = json.dumps(
    {
        "loadBalancingConfig": [{"round_robin": {}}],
        "methodConfig": [
            {
                "name": [{"service": "bench.Echo"}],
                "retryPolicy": {
                    "maxAttempts": 3,
                    "initialBackoff": "0.01s",
                    "maxBackoff": "0.1s",
                    "backoffMultiplier": 2,
                    "retryableStatusCodes": ["UNAVAILABLE"],
                },
            }
        ],
    }
)
ALL = ",".join(f"127.0.0.1:{BASE + i}" for i in range(N_BACKENDS))
MULTI = f"ipv4:{ALL}"
PROXY = f"127.0.0.1:{PROXY_PORT}"


def channel(target, service_config=None):
    opts = [("grpc.use_local_subchannel_pool", 1)]  # one real connection per channel
    if service_config:
        opts.append(("grpc.service_config", service_config))
    return grpc.insecure_channel(target, options=opts)


def call_many(ch, n, pause=0.0):
    stub = ch.unary_unary(METHOD, request_serializer=lambda b: b, response_deserializer=lambda b: b)
    seen, lat, errs = [], [], collections.Counter()
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            seen.append((time.perf_counter(), int(stub(b"x", timeout=2))))
            lat.append((time.perf_counter() - t0) * 1000)
        except grpc.RpcError as e:
            errs[e.code().name] += 1
        if pause:
            time.sleep(pause)
    return seen, lat, errs


def dist(seen):
    c = collections.Counter(i for _, i in seen)
    return [c.get(i, 0) for i in range(N_BACKENDS)]


def row(name, seen, lat):
    p50 = statistics.median(lat) if lat else float("nan")
    print(f"{name:52s} {str(dist(seen)):>20s}   p50 {p50:5.2f} ms")


# --------------------------------------------------------- experiments
def main():
    print(f"grpcio {grpc.__version__}, {N_BACKENDS} backends, 3000 calls per row\n")
    print(f"{'setup':52s} {'calls per backend':>20s}")

    servers = start_backends()
    for name, target, cfg in [
        ("E1 direct, pick_first (default)", MULTI, None),
        ("E2 direct, round_robin", MULTI, ROUND_ROBIN),
    ]:
        ch = channel(target, cfg)
        seen, lat, _ = call_many(ch, 3000)
        row(name, seen, lat)
        ch.close()

    proxy = TcpProxy()
    ch = channel(PROXY)
    seen, lat, _ = call_many(ch, 3000)
    row("E3 via L4 proxy, 1 channel", seen, lat)
    ch.close()

    seen_all, lat_all = [], []
    chans = [channel(PROXY) for _ in range(30)]
    for c in chans:
        s, l, _ = call_many(c, 100)
        seen_all += s
        lat_all += l
        c.close()
    row("E4 via L4 proxy, 30 channels x 100 calls", seen_all, lat_all)
    proxy.stop()
    stop_backends(servers)
    time.sleep(0.5)

    # E5: servers close connections after about 2 s, so the client must reconnect.
    servers = start_backends(
        [("grpc.max_connection_age_ms", 2000), ("grpc.max_connection_age_grace_ms", 500)]
    )
    proxy = TcpProxy()
    ch = channel(PROXY)
    t0 = time.perf_counter()
    seen, lat, _ = call_many(ch, 3000, pause=0.004)
    row("E5 via L4 proxy, 1 channel, max_connection_age 2 s", seen, lat)
    buckets = collections.defaultdict(collections.Counter)
    for t, i in seen:
        buckets[int(t - t0)][i] += 1
    print("   backend that served each second:")
    for sec in sorted(buckets):
        print(f"     t={sec:2d}s  " + ", ".join(f"b{i}:{n}" for i, n in sorted(buckets[sec].items())))
    ch.close()
    proxy.stop()
    stop_backends(servers)
    time.sleep(0.5)

    # E6: 16 threads call concurrently, backend 1 is killed 0.5 s in. Five repetitions each.
    print("\nE6 round_robin, 16 concurrent callers x 200 calls, backend 1 killed at 0.5 s:")
    for label, cfg in [("no retry policy", ROUND_ROBIN), ("retry up to 3 attempts on UNAVAILABLE", RETRY)]:
        runs, last = [], {}
        for _ in range(5):
            servers = start_backends(delay=0.005)
            ch = channel(MULTI, cfg)
            stub = ch.unary_unary(METHOD, request_serializer=lambda b: b, response_deserializer=lambda b: b)
            errs, lock = collections.Counter(), threading.Lock()

            def worker():
                for _ in range(200):
                    try:
                        stub(b"x", timeout=2)
                    except grpc.RpcError as e:
                        with lock:
                            errs[e.code().name] += 1
                    time.sleep(0.002)

            threading.Timer(0.5, lambda: servers[1].stop(0)).start()
            threads = [threading.Thread(target=worker) for _ in range(16)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            runs.append(sum(errs.values()))
            if errs:
                last = dict(errs)
            ch.close()
            stop_backends(servers)
            time.sleep(0.5)
        print(f"  {label:42s} failed of 3200: {runs}   (status codes seen: {last if any(runs) else 'none'})")


if __name__ == "__main__":
    main()
