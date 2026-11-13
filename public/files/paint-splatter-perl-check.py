"""Recompute "93% of paint splatters are valid Perl programs" from the author's published gallery.

Input: splatters.html from https://www.mcmillen.dev/sigbovik/ (the per-image Perl source the
author chose; 7 of the 100 are marked "Not valid" and have no text).
We do NOT re-run OCR here, so we can only check the 93 published sources and build baselines.

usage: python -I paint-splatter-perl-check.py <dir containing splatters.html> [samples_per_cell]
"""
import html, os, random, re, subprocess, sys, tempfile, statistics, collections
from concurrent.futures import ThreadPoolExecutor

data_dir = sys.argv[1]
N = int(sys.argv[2]) if len(sys.argv) > 2 else 200
page = open(os.path.join(data_dir, "splatters.html"), encoding="utf8").read()
cells = re.findall(r"<div([^>]*)>(.*?)<br>", page, re.S)
srcs = [html.unescape(h) for _, h in cells if "invalid" not in h]
n_total, n_invalid = len(cells), len(cells) - len(srcs)
work = tempfile.mkdtemp(prefix="splat-")  # empty cwd for every perl run


def perl(args, text):
    """Write text to a file and run perl on it. Returns (rc, stdout, stderr)."""
    fd, path = tempfile.mkstemp(dir=work, suffix=".pl")
    with os.fdopen(fd, "wb") as f:
        f.write(text.encode("utf8"))
    try:
        p = subprocess.run(["perl", *args, path], cwd=work, capture_output=True, timeout=10, stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout.decode("utf8", "replace"), p.stderr.decode("utf8", "replace")
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    finally:
        os.unlink(path)


def ok(args, text):
    return perl(args, text)[0] == 0


print(f"cells={n_total} marked-invalid={n_invalid} published-sources={len(srcs)}")
print("perl:", subprocess.run(["perl", "-e", "print $^V"], capture_output=True, text=True).stdout)

# --- A. the published sources -------------------------------------------------
with ThreadPoolExecutor(8) as ex:
    c_plain = list(ex.map(lambda s: ok(["-c"], s), srcs))
    c_strict = list(ex.map(lambda s: ok(["-c", "-Mstrict"], s), srcs))
    runs = list(ex.map(lambda s: perl([], s), srcs))
lens = [len(s) for s in srcs]
print("\n[A] published sources")
print(f"perl -c ok: {sum(c_plain)}/{len(srcs)}   -> {sum(c_plain)}/{n_total} of all cells")
print(f"perl -c -Mstrict ok: {sum(c_strict)}/{len(srcs)}   -> {sum(c_strict)}/{n_total} of all cells")
print(f"run: exit 0 = {sum(r[0]==0 for r in runs)}, printed something = {sum(bool(r[1]) for r in runs)}, "
      f"died/errored at runtime = {sum(r[0]!=0 for r in runs)}")
print(f"length: median {statistics.median(lens)}, mean {statistics.mean(lens):.1f}, max {max(lens)}; "
      f"<=3 chars: {sum(l<=3 for l in lens)}, <=5: {sum(l<=5 for l in lens)}, >=10: {sum(l>=10 for l in lens)}")
kind = collections.Counter()
for s in srcs:
    if re.fullmatch(r"-?\d+", s): kind["number"] += 1
    elif re.fullmatch(r"[A-Za-z]+", s): kind["bareword (letters only)"] += 1
    elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", s): kind["identifier"] += 1
    else: kind["other (punctuation etc.)"] += 1
print("kinds:", dict(kind))
strict_fail = [s for s, a, b in zip(srcs, c_plain, c_strict) if a and not b]
print(f"valid without strict but not with strict: {len(strict_fail)}")
print("  e.g.", strict_fail[:12])
print("not valid even without strict (our perl):", [s for s, a in zip(srcs, c_plain) if not a])
print("run printed something:", [(s, r[1][:20]) for s, r in zip(srcs, runs) if r[1]][:10])
print("run died:", [(s, r[2].strip().splitlines()[0][:60]) for s, r in zip(srcs, runs) if r[0] != 0][:10])

# --- B. baselines: random strings --------------------------------------------
rng = random.Random(20261113)
obs_alpha = sorted(set("".join(srcs)))
ascii_alpha = [chr(c) for c in range(32, 127)]
print(f"\n[B] baselines (observed alphabet = {len(obs_alpha)} chars, printable ASCII = {len(ascii_alpha)})")


def rate(alpha, length, n):
    ss = ["".join(rng.choice(alpha) for _ in range(length)) for _ in range(n)]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda s: ok(["-c"], s), ss))
    return sum(res), n


# matched: same length distribution as the 93 sources, random chars from the observed alphabet
for name, alpha in (("observed-alphabet", obs_alpha), ("printable-ASCII", ascii_alpha)):
    ss = ["".join(rng.choice(alpha) for _ in range(l)) for l in lens for _ in range(10)]
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda s: ok(["-c"], s), ss))
    print(f"matched lengths, {name}: {sum(res)}/{len(ss)} = {100*sum(res)/len(ss):.1f}% valid")

print("\nvalid rate by length (perl -c), N=%d per cell" % N)
print("len  observed-alphabet  printable-ASCII")
for L in (1, 2, 3, 4, 6, 10, 20, 38):
    a = rate(obs_alpha, L, N)
    b = rate(ascii_alpha, L, N)
    print(f"{L:>3}  {100*a[0]/a[1]:6.1f}% ({a[0]}/{a[1]})   {100*b[0]/b[1]:6.1f}% ({b[0]}/{b[1]})")

# a non-trivial length bar: how long is the longest published source that is not a bare word / number?
print("\nlongest published sources:", sorted(srcs, key=len, reverse=True)[:5])
