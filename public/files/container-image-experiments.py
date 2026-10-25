#!/usr/bin/env python3
"""
Dockerfile habits and the bytes they add to an image, measured.
Python 3 standard library only. Needs the `docker` CLI, a running engine, and
container-image-anatomy.py in the same folder. Base images must already be pulled
(python:3.13-slim, python:3.13-alpine).

  python container-image-experiments.py            # all groups, a few minutes
  python container-image-experiments.py pip copy   # only the named groups
  python container-image-experiments.py --json     # machine-readable output

Every variant is built with `docker build --provenance=false --no-cache` into a tag
`exp:<name>`, saved with `docker save`, and read layer by layer. Reported per variant:
  reg   = compressed size of all layers (what a registry stores and a pull downloads)
  disk  = unpacked size summed over layers (every layer counts, even if a later one
          deletes its files)
  final = unpacked size of the merged filesystem (what a running container sees)
"""
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("anatomy", os.path.join(HERE, "container-image-anatomy.py"))
anatomy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(anatomy)
MB = anatomy.MB

SLIM = "python:3.13-slim"
PKGS = "numpy pandas requests"


def build(name, dockerfile, files=None, context=None, ignore=None):
    """Build exp:<name>. Returns (seconds, ok, tail_of_output)."""
    with tempfile.TemporaryDirectory() as td:
        ctx = context or td
        if context is None:
            for rel, data in (files or {}).items():
                path = os.path.join(td, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(data)
        df = os.path.join(td, "Dockerfile.exp")
        with open(df, "w") as f:
            f.write(dockerfile)
        if ignore is not None:  # BuildKit reads <dockerfile>.dockerignore, so the context stays untouched
            with open(df + ".dockerignore", "w") as f:
                f.write(ignore)
        t0 = time.time()
        p = subprocess.run(
            ["docker", "build", "--provenance=false", "--no-cache", "-f", df, "-t", f"exp:{name}", ctx],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        return time.time() - t0, p.returncode == 0, (p.stdout + p.stderr)[-600:]


def run_check(name, code):
    p = subprocess.run(["docker", "run", "--rm", f"exp:{name}", "python", "-c", code],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode == 0, (p.stdout + p.stderr).strip()[-200:]


def cold_import(name, module, runs=5):
    """Median seconds to `import module` in a fresh container each time (nothing cached on disk)."""
    code = f"import time; t=time.perf_counter(); import {module}; print(time.perf_counter()-t)"
    times = []
    for _ in range(runs):
        p = subprocess.run(["docker", "run", "--rm", f"exp:{name}", "python", "-c", code],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        times.append(float(p.stdout.strip().splitlines()[-1]))
    return sorted(times)[len(times) // 2]


def measure(name, dockerfile, files=None, context=None, check=None, ignore=None, import_mod=None):
    secs, ok, tail = build(name, dockerfile, files, context, ignore)
    if not ok:
        return dict(name=name, built=False, seconds=secs, error=tail)
    r = anatomy.analyze(f"exp:{name}")
    out = dict(name=name, built=True, seconds=round(secs, 1), reg=r["compressed"], disk=r["unpacked_sum"],
               final=r["merged_bytes"], layers=r["layers"])
    if check:
        out["works"], out["check_out"] = run_check(name, check)
    if import_mod:
        out["import_s"] = round(cold_import(name, import_mod), 3)
    return out


def blob(n_files, total_bytes, seed=7):
    rng = random.Random(seed)
    each = total_bytes // n_files
    return {f"data/part{i:03d}.bin": rng.randbytes(each) for i in range(n_files)}


# ------------------------------------------------------------------ groups


def group_pip():
    """pip install with and without the cache, and cleaning up in a later layer."""
    base = f"FROM {SLIM}\n"
    yield "slim only", base
    yield "pip install", base + f"RUN pip install {PKGS}\n"
    yield "pip --no-cache-dir", base + f"RUN pip install --no-cache-dir {PKGS}\n"
    yield "pip, rm cache in NEXT layer", base + f"RUN pip install {PKGS}\nRUN rm -rf /root/.cache/pip\n"
    yield "pip, rm cache SAME layer", base + f"RUN pip install {PKGS} && rm -rf /root/.cache/pip\n"
    yield "pip, cache mount", base + f"RUN --mount=type=cache,target=/root/.cache/pip pip install {PKGS}\n"


def group_copy():
    """COPY then chown, versus COPY --chown. 100 files, 40 MB of random bytes."""
    files = blob(100, 40_000_000)
    base = f"FROM {SLIM}\n"
    yield "COPY only", base + "COPY data /app/data\n", files
    yield "COPY + chown -R (next layer)", base + "COPY data /app/data\nRUN chown -R 1000:1000 /app\n", files
    yield "COPY --chown", base + "COPY --chown=1000:1000 data /app/data\n", files
    yield "COPY, rm in next layer", base + "COPY data /app/data\nRUN rm -rf /app/data\n", files


def group_apt():
    """A package that needs a compiler (psycopg2 from source), four ways."""
    check = "import psycopg2; print(psycopg2.__version__)"
    base = f"FROM {SLIM}\n"
    single = ("RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev "
              "&& pip install --no-cache-dir psycopg2 \n")
    yield "psycopg2, build deps kept", base + single, None, check
    yield ("psycopg2, apt lists removed (same RUN)",
           base + single.rstrip(" \n") + " && rm -rf /var/lib/apt/lists/*\n", None, check)
    yield ("psycopg2, multi-stage",
           f"FROM {SLIM} AS build\n"
           "RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev libpq-dev\n"
           "RUN pip wheel --no-cache-dir --wheel-dir /wheels psycopg2\n"
           f"FROM {SLIM}\n"
           "RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*\n"
           "COPY --from=build /wheels /wheels\n"
           "RUN pip install --no-cache-dir --no-index --find-links=/wheels psycopg2 && rm -rf /wheels\n",
           None, check)
    yield "psycopg2-binary wheel", base + "RUN pip install --no-cache-dir psycopg2-binary\n", None, check


def group_base():
    """The same three packages on slim and on alpine."""
    check = "import numpy, pandas, requests; print(numpy.__version__, pandas.__version__)"
    for tag, label in ((SLIM, "slim"), ("python:3.13-alpine", "alpine")):
        yield f"{label} + {PKGS}", f"FROM {tag}\nRUN pip install --no-cache-dir {PKGS}\n", None, check


def group_prune():
    """What can be left out of numpy + pandas, and what it costs at start-up."""
    site = "/usr/local/lib/python3.13/site-packages"
    check = "import pandas as pd, numpy as np; print(pd.DataFrame({'a': [1, 2]}).a.sum(), np.arange(3).sum())"
    drop = f"find {site} -type d '(' -name tests -o -name test ')' -prune -exec rm -rf {{}} +"
    base = f"FROM {SLIM}\n"

    def pip(flags=""):
        return f"pip install --no-cache-dir {flags}{PKGS}"

    yield "baseline", base + f"RUN {pip()}\n", None, check, None, "pandas"
    yield "pip --no-compile", base + f"RUN {pip('--no-compile ')}\n", None, check, None, "pandas"
    yield "delete tests dirs", base + f"RUN {pip()} && {drop}\n", None, check, None, "pandas"
    yield ("delete tests + no-compile", base + f"RUN {pip('--no-compile ')} && {drop}\n",
           None, check, None, "pandas")


def group_context():
    """COPY . . on a real project directory (node_modules and friends), with and without .dockerignore."""
    ctx = os.environ.get("CONTEXT_DIR") or os.path.abspath(os.path.join(HERE, "..", ".."))
    base = f"FROM {SLIM}\n"
    ignore = "node_modules\n.git\ndist\n.astro\n"
    yield "COPY . . (no .dockerignore)", base + "COPY . /app\n", None, None, "", None, ctx
    yield "COPY . . + .dockerignore", base + "COPY . /app\n", None, None, ignore, None, ctx


GROUPS = dict(pip=group_pip, copy=group_copy, apt=group_apt, base=group_base, prune=group_prune, context=group_context)


def run_group(fn):
    rows = []
    for item in fn():
        name, df = item[0], item[1]
        files = item[2] if len(item) > 2 else None
        check = item[3] if len(item) > 3 else None
        ignore = item[4] if len(item) > 4 else None
        import_mod = item[5] if len(item) > 5 else None
        context = item[6] if len(item) > 6 else None
        tag = "".join(c if c.isalnum() else "_" for c in name.lower())
        rows.append(measure(tag, df, files=files, context=context, check=check, ignore=ignore,
                            import_mod=import_mod) | dict(label=name))
    return rows


def show(title, rows):
    print(f"== {title}")
    print(f"  {'variant':44s} {'reg MB':>8} {'disk MB':>8} {'final MB':>9} {'build s':>8}  works  import s")
    for r in rows:
        if not r["built"]:
            print(f"  {r['label']:44s} BUILD FAILED after {r['seconds']:.0f}s: {r['error'][-160:]!r}")
            continue
        w = {True: "yes", False: "NO"}.get(r.get("works"), "-")
        imp = f"{r['import_s']:8.3f}" if "import_s" in r else "       -"
        print(f"  {r['label']:44s} {r['reg'] / MB:8.1f} {r['disk'] / MB:8.1f} {r['final'] / MB:9.1f} {r['seconds']:8.1f}  {w:5s} {imp}")
    print()


if __name__ == "__main__":
    names = [a for a in sys.argv[1:] if not a.startswith("--")] or list(GROUPS)
    all_rows = {}
    for g in names:
        all_rows[g] = run_group(GROUPS[g])
        if "--json" not in sys.argv:
            show(g, all_rows[g])
    if "--json" in sys.argv:
        print(json.dumps(all_rows, indent=1))
