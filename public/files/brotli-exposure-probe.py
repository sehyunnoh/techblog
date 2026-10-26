#!/usr/bin/env python3
"""
How many Brotli decoders does one machine carry, and which HTTP clients offer to use one by default?
Python 3 standard library only for the harness. Needs network access for `pip` (venvs) and,
optionally, a second Node.js binary to compare against.

  python brotli-exposure-probe.py probe                       # Accept-Encoding sent by default
  python brotli-exposure-probe.py versions --node-other PATH  # bundled-version strings
  python brotli-exposure-probe.py scan ROOT [ROOT ...]        # binaries that export a Brotli decoder

This script never builds or sends a malformed Brotli stream. It measures exposure, not exploitation.

probe     starts a local HTTP server that records the Accept-Encoding header and always answers with a
          valid Brotli body and Content-Encoding: br, then calls it from each client with default
          settings. Two questions per client: does it ask for br, and does it decode br anyway?
versions  prints what each runtime says about its bundled Brotli (process.versions.brotli, curl -V).
scan      walks the given folders and counts .exe/.dll/.node/.pyd/.so files containing the byte string
          BrotliDecoderDecompress. A lower bound: statically linked, stripped copies do not show up.
"""
import argparse
import http.server
import mmap
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import defaultdict

SEEN = []
PAYLOAD = b"hello brotli"
COMPRESSED = b""  # filled in by probe(): a valid stream made by Node's own encoder


class Recorder(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        SEEN.append(self.headers.get("Accept-Encoding", "(header absent)"))
        self.send_response(200)
        self.send_header("Content-Encoding", "br")
        self.send_header("Content-Length", str(len(COMPRESSED)))
        self.end_headers()
        self.wfile.write(COMPRESSED)

    def log_message(self, format, *args):
        pass


def serve():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def make_venv(root, name, extra):
    path = os.path.join(root, name)
    subprocess.run([sys.executable, "-m", "venv", path], check=True)
    py = os.path.join(path, "Scripts" if os.name == "nt" else "bin", "python")
    subprocess.run([py, "-m", "pip", "install", "-q", "requests", "httpx", "aiohttp", *extra], check=True)
    return py


PY_CLIENTS = {
    "requests": "import requests,sys; sys.stdout.buffer.write(requests.get(sys.argv[1]).content)",
    "urllib3": "import urllib3,sys; sys.stdout.buffer.write(urllib3.PoolManager().request('GET', sys.argv[1]).data)",
    "httpx": "import httpx,sys; sys.stdout.buffer.write(httpx.get(sys.argv[1]).content)",
    "aiohttp": "import aiohttp,asyncio,sys\n"
               "async def m():\n"
               "    async with aiohttp.ClientSession() as s:\n"
               "        async with s.get(sys.argv[1]) as r: sys.stdout.buffer.write(await r.read())\n"
               "asyncio.run(m())",
    "urllib.request": "import urllib.request,sys; sys.stdout.buffer.write(urllib.request.urlopen(sys.argv[1]).read())",
}

NODE_CLIENTS = {
    "node fetch()": "fetch(process.argv[1]).then(r=>r.text()).then(t=>process.stdout.write(t))",
    "node http.get": "require('http').get(process.argv[1],r=>r.pipe(process.stdout))",
}


def run_and_record(cmd):
    before = len(SEEN)
    r = subprocess.run(cmd, capture_output=True, timeout=60)
    got = SEEN[before:]
    header = got[-1] if got else "(no request seen)"
    if r.stdout == PAYLOAD:
        body = "decoded"
    elif r.stdout == COMPRESSED:
        body = "raw br bytes"
    else:
        body = "error: " + (r.stderr.decode(errors="replace").strip().splitlines() or ["?"])[-1][:70]
    return header, body


def asks_for_br(header):
    return "YES" if "br" in [t.strip().split(";")[0] for t in header.split(",")] else "no"


def probe(args):
    global COMPRESSED
    COMPRESSED = subprocess.run(
        ["node", "-e", "process.stdout.write(require('zlib').brotliCompressSync(Buffer.from(process.argv[1])))", PAYLOAD.decode()],
        capture_output=True, check=True).stdout
    srv, url = serve()
    rows = []
    tmp = tempfile.mkdtemp(prefix="brotli-probe-")
    try:
        for tag, extra in (("no brotli pkg", []), ("brotli pkg installed", ["brotli"])):
            py = make_venv(tmp, tag.replace(" ", "-"), extra)
            ver = subprocess.run(
                [py, "-c", "import importlib.metadata as m\n"
                 "print(' '.join(f'{n} {m.version(n)}' for n in ('requests','urllib3','httpx','aiohttp')))\n"
                 "try: print('brotli', m.version('brotli'))\n"
                 "except Exception: print('brotli (not installed)')"],
                capture_output=True, text=True).stdout.strip().replace("\n", "; ")
            print(f"[{tag}] {ver}")
            for name, code in PY_CLIENTS.items():
                if name == "urllib.request" and tag != "no brotli pkg":
                    continue  # stdlib, unaffected by the venv contents
                rows.append((f"python {name} ({tag})",) + run_and_record([py, "-c", code, url]))
        for name, code in NODE_CLIENTS.items():
            rows.append((name,) + run_and_record(["node", "-e", code, url]))
        for exe in args.curl:
            rows.append((f"{exe}",) + run_and_record([exe, "-s", url]))
            rows.append((f"{exe} --compressed",) + run_and_record([exe, "-s", "--compressed", url]))
    finally:
        srv.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    w = max(len(r[0]) for r in rows)
    print()
    print(f"{'client':<{w}}  asks br  server sends br anyway -> client returns   Accept-Encoding sent")
    for label, header, body in rows:
        print(f"{label:<{w}}  {asks_for_br(header):<7}  {body:<42}  {header}")
def versions(args):
    def sh(cmd):
        return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()

    for exe in ["node"] + ([args.node_other] if args.node_other else []):
        print(sh([exe, "-p", "process.version + '  bundled brotli ' + process.versions.brotli"]), f" ({exe})")
    out = sh(["curl", "-V"]).splitlines()[0]
    print(out)
    print(sh(["dotnet", "--list-runtimes"]))


NEEDLE = b"BrotliDecoderDecompress"
EXTS = (".exe", ".dll", ".node", ".pyd", ".so")


def has_needle(path):
    try:
        if os.path.getsize(path) == 0:
            return False
        with open(path, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as m:
            return m.find(NEEDLE) != -1
    except (OSError, ValueError):
        return False


def scan(args):
    by_product = defaultdict(list)
    scanned = 0
    for root in args.roots:
        depth0 = root.rstrip("\\/").count(os.sep)
        for dirpath, dirnames, files in os.walk(root, onerror=lambda _e: None):
            if "WindowsApps" in dirpath:
                dirnames[:] = []
                continue
            for fn in files:
                if fn.lower().endswith(EXTS):
                    p = os.path.join(dirpath, fn)
                    scanned += 1
                    if has_needle(p):
                        parts = p.split(os.sep)
                        product = os.sep.join(parts[depth0 + 1: depth0 + 2 + args.depth - 1]) or parts[-1]
                        by_product[(root, product)].append(p)
    print(f"scanned {scanned} binaries, {sum(len(v) for v in by_product.values())} contain {NEEDLE.decode()}\n")
    for (root, product), paths in sorted(by_product.items(), key=lambda kv: -len(kv[1])):
        print(f"{len(paths):>4}  {os.path.join(root, product)}")
        if args.verbose:
            for p in paths:
                print("        ", p)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("probe")
    pr.add_argument("--curl", action="append", default=None, help="curl executable (repeatable)")
    pr.set_defaults(fn=probe)
    v = sub.add_parser("versions")
    v.add_argument("--node-other")
    v.set_defaults(fn=versions)
    s = sub.add_parser("scan")
    s.add_argument("roots", nargs="+")
    s.add_argument("--depth", type=int, default=1, help="folder levels below each root that name a product")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(fn=scan)
    args = ap.parse_args()
    if getattr(args, 'curl', 1) is None:
        args.curl = ['curl']
    args.fn(args)


if __name__ == "__main__":
    main()
