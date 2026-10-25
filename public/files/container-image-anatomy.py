#!/usr/bin/env python3
"""
Where do the bytes in a container image come from?
Python 3 standard library only. Needs the `docker` CLI and the images already pulled.

  python container-image-anatomy.py python:3.13-slim python:3.13 python:3.13-alpine
  python container-image-anatomy.py --json myapp:latest

For each image it runs `docker save`, then reads every layer of the saved archive:
  compressed   = size of the layer blob as stored in the image (what a registry transfers)
  unpacked     = sum of regular-file sizes inside the layer (what lands on disk)
  files        = regular files, symlinks and hard links in the layer
  whiteouts    = `.wh.` entries, i.e. deletions recorded by a later layer
and groups the unpacked bytes of the final filesystem by path.
"""
import gzip
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
from collections import Counter

MB = 1_000_000  # decimal MB, the unit `docker images` prints


def category(path):
    p = path.lstrip("./")
    for prefix, name in (
        ("usr/local/lib/python", "python stdlib + site-packages"),
        ("usr/local/", "python runtime (rest of /usr/local)"),
        ("usr/share/", "/usr/share (docs, locales, zoneinfo)"),
        ("usr/include/", "headers (/usr/include)"),
        ("usr/lib/gcc/", "compiler (/usr/lib/gcc)"),
        ("usr/libexec/", "compiler helpers (/usr/libexec)"),
        ("usr/lib/", "shared libraries (/usr/lib)"),
        ("lib/", "shared libraries (/lib)"),
        ("usr/bin/", "binaries (/usr/bin)"),
        ("usr/sbin/", "binaries (/usr/sbin)"),
        ("bin/", "binaries (/bin)"),
        ("sbin/", "binaries (/sbin)"),
        ("var/lib/apt/", "package manager state (apt/dpkg/apk)"),
        ("var/lib/dpkg/", "package manager state (apt/dpkg/apk)"),
        ("var/cache/", "package manager state (apt/dpkg/apk)"),
        ("lib/apk/", "package manager state (apt/dpkg/apk)"),
        ("etc/", "/etc"),
    ):
        if p.startswith(prefix):
            return name
    return "everything else"


def read_member(tf, name):
    f = tf.extractfile(name)
    if f is None:
        raise SystemExit(f"{name} is not a regular file in the saved archive")
    return f.read()


def read_layer(fileobj):
    raw = fileobj.read()
    comp = len(raw)
    data = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
    files = whiteouts = 0
    total = 0
    final = {}  # path -> size, for regular files in this layer
    deleted = []  # (directory, name) for each whiteout; name "" means "opaque directory"
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        for m in tf:
            base = os.path.basename(m.name)
            if base.startswith(".wh."):
                whiteouts += 1
                parent = os.path.dirname(m.name).lstrip("./")
                deleted.append((parent, "" if base == ".wh..wh..opq" else base[4:]))
                continue
            if m.isreg():
                files += 1
                total += m.size
                final[m.name] = m.size
            elif m.issym() or m.islnk():
                files += 1
    return comp, total, files, whiteouts, final, deleted


def analyze(image, keep_fs=False):
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "img.tar")
        subprocess.run(["docker", "save", image, "-o", out], check=True)
        with tarfile.open(out) as outer:
            manifest = json.loads(read_member(outer, "manifest.json"))[0]
            cfg = json.loads(read_member(outer, manifest["Config"]))
            hist = [h for h in cfg.get("history", []) if not h.get("empty_layer")]
            layers = []
            fs = {}  # merged filesystem: path -> size (later layers win)
            for i, name in enumerate(manifest["Layers"]):
                comp, unp, files, wh, final, deleted = read_layer(io.BytesIO(read_member(outer, name)))
                for parent, victim in deleted:  # a layer's deletions only hide lower layers
                    gone = (parent + "/" + victim).lstrip("/") if victim else parent
                    prefix = gone + "/"
                    for path in [p for p in fs if p.lstrip("./") == gone or p.lstrip("./").startswith(prefix)]:
                        del fs[path]
                created = (hist[i]["created_by"] if i < len(hist) else "?").replace("\t", " ")
                layers.append(dict(n=i, compressed=comp, unpacked=unp, files=files,
                                   whiteouts=wh, created_by=created))
                fs.update(final)
    cats = Counter()
    for path, size in fs.items():
        cats[category(path)] += size
    inspect = json.loads(subprocess.run(["docker", "image", "inspect", image],
                                        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout)[0]
    listed = subprocess.run(["docker", "image", "ls", "--format", "{{.Size}}", image],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout.split()[0]
    return dict(
        image=image,
        docker_ls=listed,
        compressed=sum(l["compressed"] for l in layers),
        unpacked_sum=sum(l["unpacked"] for l in layers),
        merged_files=len(fs),
        merged_bytes=sum(fs.values()),
        docker_size=inspect["Size"],
        layers=layers,
        categories=dict(cats.most_common()),
        fs=fs if keep_fs else None,
    )


def tree(fs, prefix, depth, n=12):
    """Largest directories `depth` levels below `prefix` in the merged filesystem."""
    sizes = Counter()
    for path, size in fs.items():
        p = path.lstrip("./")
        if p.startswith(prefix):
            parts = p[len(prefix):].lstrip("/").split("/")
            sizes["/".join(parts[:depth])] += size
    return sizes.most_common(n)


def show(r):
    print(f"== {r['image']}")
    print(f"  registry (compressed layers): {r['compressed'] / MB:8.1f} MB")
    print(f"  unpacked, sum of layers     : {r['unpacked_sum'] / MB:8.1f} MB")
    print(f"  unpacked, merged filesystem : {r['merged_bytes'] / MB:8.1f} MB  ({r['merged_files']} files)")
    print(f"  `docker image inspect` Size : {r['docker_size'] / MB:8.1f} MB")
    print(f"  `docker image ls` SIZE      : {r['docker_ls']:>8}")
    print("  layers:   compressed  unpacked   files  whiteouts  created_by")
    for l in r["layers"]:
        print(f"   {l['n']:2d}  {l['compressed'] / MB:11.1f} {l['unpacked'] / MB:9.1f} {l['files']:7d} {l['whiteouts']:9d}  {l['created_by'][:70]}")
    print("  merged filesystem by path group:")
    for name, size in r["categories"].items():
        print(f"    {size / MB:8.1f} MB  {name}")
    print()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    trees = [a[7:] for a in sys.argv[1:] if a.startswith("--tree=")]  # --tree=PREFIX:DEPTH
    results = [analyze(a, keep_fs=bool(trees)) for a in args]
    if trees:
        for r in results:
            for t in trees:
                prefix, _, depth = t.rpartition(":")
                print(f"== {r['image']}  {prefix}  (depth {depth})")
                for name, size in tree(r["fs"], prefix, int(depth)):
                    print(f"  {size / MB:8.1f} MB  {name}")
                print()
    elif "--json" in sys.argv:
        print(json.dumps([{k: v for k, v in r.items() if k != "fs"} for r in results], indent=1))
    else:
        for r in results:
            show(r)
