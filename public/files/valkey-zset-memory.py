#!/usr/bin/env python3
"""Measure per-member memory of a Valkey sorted set (skiplist vs B+ tree).

Usage: valkey-zset-memory.py <valkey-server binary> <order: seq|rand> <members> <member_len> [runs]

Starts a fresh server (no persistence), inserts <members> members into one sorted set with
pipelined ZADD, and reports used_memory growth per member, plus OBJECT ENCODING.
Member strings are exactly <member_len> bytes, scores are 0..N-1 (inserted in order or shuffled).
"""
import random, socket, subprocess, sys, time

binary, order, n, mlen = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
runs = int(sys.argv[5]) if len(sys.argv) > 5 else 1
PORT = 7391


def resp(*parts):
    out = [b"*%d\r\n" % len(parts)]
    for p in parts:
        p = p if isinstance(p, bytes) else str(p).encode()
        out.append(b"$%d\r\n%s\r\n" % (len(p), p))
    return b"".join(out)


class Conn:
    def __init__(self):
        self.s = socket.create_connection(("127.0.0.1", PORT))
        self.f = self.s.makefile("rb")

    def cmd(self, *parts):
        self.s.sendall(resp(*parts))
        return self.read()

    def read(self):
        line = self.f.readline()
        t, rest = line[:1], line[1:-2]
        if t in (b"+", b"-"):
            return rest.decode()
        if t == b":":
            return int(rest)
        if t == b"$":
            ln = int(rest)
            if ln < 0:
                return None
            data = self.f.read(ln + 2)[:-2]
            return data.decode()
        raise RuntimeError(line)


def info(c, key):
    for ln in c.cmd("INFO", "memory").splitlines():
        if ln.startswith(key + ":"):
            return int(ln.split(":")[1])


def member(i):
    return (b"m%0*d" % (mlen - 1, i))[:mlen]


results = []
for run in range(runs):
    srv = subprocess.Popen([binary, "--port", str(PORT), "--save", "", "--appendonly", "no",
                            "--daemonize", "no", "--loglevel", "warning"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    try:
        c = Conn()
        base = info(c, "used_memory")
        ids = list(range(n))
        if order == "rand":
            random.Random(run + 1).shuffle(ids)
        t0 = time.time()
        B = 20000
        for i in range(0, n, B):
            buf = b"".join(resp("ZADD", "z", j, member(j)) for j in ids[i:i + B])
            c.s.sendall(buf)
            for _ in range(min(B, n - i)):
                c.read()
        dt = time.time() - t0
        used = info(c, "used_memory")
        enc = c.cmd("OBJECT", "ENCODING", "z")
        card = c.cmd("ZCARD", "z")
        mu = c.cmd("MEMORY", "USAGE", "z")
        ver = [l for l in c.cmd("INFO", "server").splitlines() if l.startswith("valkey_version")][0]
        results.append((used - base, mu))
        print(f"{ver} order={order} n={card} mlen={mlen} run={run+1} enc={enc} "
              f"used_delta={used-base} per_member={(used-base)/n:.2f}B "
              f"MEMORY_USAGE={mu} ({mu/n:.2f}B/member) insert_s={dt:.1f}", flush=True)
    finally:
        try:
            Conn().cmd("SHUTDOWN", "NOSAVE")
        except Exception:
            srv.kill()
        srv.wait()
        time.sleep(0.5)
