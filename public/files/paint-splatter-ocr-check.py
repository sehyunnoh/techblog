"""Re-OCR the 100 published paint-splatter images the way the paper describes, and count valid Perl.

Paper setup (McMillen, SIGBOVIK 2019): per image, try 3 Tesseract engines (legacy, LSTM, both) x
4 page-segmentation modes (4, 7, 8, 9), whitelist ASCII [32,127) where the engine allows it, language-model
features off, then keep the image if ANY combination gives a NON-EMPTY string that `perl` accepts.

Run inside WSL (Linux) with perl on PATH. Environment:
  TESSERACT       path of the tesseract binary          (default: tesseract)
  TESSDATA_PREFIX folder with a legacy+LSTM eng.traineddata (tesseract-ocr/tessdata, tag 4.1.0)
usage: python3 -I paint-splatter-ocr-check.py <dir with splatters.html and img/splatters/*.jpg>
"""
import collections, html, os, re, statistics, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

root = sys.argv[1]
tess = os.environ.get("TESSERACT", "tesseract")
page = open(os.path.join(root, "splatters.html"), encoding="utf8").read()
cells = re.findall(r'<div([^>]*)>(.*?)<br><a href="([^"]+)"', page, re.S)
author = {os.path.basename(h): (None if "invalid" in t else html.unescape(t)) for _, t, h in cells}
files = sorted(author)
WL = "tessedit_char_whitelist=" + "".join(chr(c) for c in range(32, 127))
NOLM = ["-c", "load_system_dawg=0", "-c", "load_freq_dawg=0"]
ENGINE = {0: "legacy", 1: "LSTM", 2: "legacy+LSTM"}
GRID = [(oem, psm) for oem in (0, 1, 2) for psm in (4, 7, 8, 9)]
work = tempfile.mkdtemp(prefix="ocr-")
env = dict(os.environ, OMP_THREAD_LIMIT="1")


def ocr(job):
    f, oem, psm = job
    img = os.path.join(root, "img", "splatters", f)
    if oem is None:  # plain `tesseract image stdout`
        cmd = [tess, img, "stdout"]
    else:
        cmd = [tess, img, "stdout", "--oem", str(oem), "--psm", str(psm), "-l", "eng", *NOLM]
        if oem != 1:  # the paper: only the legacy engine honours a whitelist
            cmd += ["-c", WL]
    return subprocess.run(cmd, capture_output=True, env=env, timeout=120).stdout.decode("utf8", "replace")


def valid(text):
    if not text.strip():  # empty programs do not count
        return False
    fd, path = tempfile.mkstemp(dir=work, suffix=".pl")
    with os.fdopen(fd, "wb") as fh:
        fh.write(text.encode("utf8"))
    try:
        return subprocess.run(["perl", "-c", path], cwd=work, capture_output=True, timeout=10,
                              stdin=subprocess.DEVNULL).returncode == 0
    finally:
        os.unlink(path)


jobs = [(f, None, None) for f in files] + [(f, o, p) for f in files for o, p in GRID]
with ThreadPoolExecutor(os.cpu_count() or 4) as ex:
    texts = dict(zip(jobs, ex.map(ocr, jobs)))
    ok = dict(zip(jobs, ex.map(lambda j: valid(texts[j]), jobs)))

v = lambda f, c: ok[(f, c[0], c[1])]
n_author = sum(x is not None for x in author.values())
print("tesseract:", subprocess.run([tess, "--version"], capture_output=True, text=True).stdout.splitlines()[0])
print("perl:", subprocess.run(["perl", "-e", "print $^V"], capture_output=True, text=True).stdout)
print(f"images={len(files)}  author-valid={n_author}  author-'Not valid'={len(files) - n_author}")

plain = (None, None)
print(f"\n[1] plain `tesseract image stdout` (default settings): non-empty "
      f"{sum(bool(texts[(f, None, None)].strip()) for f in files)}, valid {sum(v(f, plain) for f in files)} of 100")

print("\n[2] paper grid, valid non-empty readings per combination (of 100)")
print("engine        psm4 psm7 psm8 psm9   union")
for oem in (0, 1, 2):
    row = [sum(v(f, (oem, p)) for f in files) for p in (4, 7, 8, 9)]
    un = sum(any(v(f, (oem, p)) for p in (4, 7, 8, 9)) for f in files)
    print(f"{ENGINE[oem]:<13} " + " ".join(f"{x:>4}" for x in row) + f"   {un:>4}")
allun = sum(any(v(f, c) for c in GRID) for f in files)
print(f"any of the 12 combinations: {allun}/100   (paper: 93/100; best single 55; LSTM union 74, legacy 62, both 40)")

print("\n[3] in how many of the 12 combinations is each image valid? (histogram of images)")
per = [sum(v(f, c) for c in GRID) for f in files]
h = collections.Counter(per)
print({k: h[k] for k in range(13)})
print(f"valid in exactly 1 combination: {h[1]};  in 1-2: {h[1]+h[2]};  in >=6: {sum(h[k] for k in range(6,13))}")

print("\n[4] sanity check against the author's published strings")
hit = sum(1 for f in files if author[f] is not None and
          (author[f] or "").strip() in {texts[(f, o, p)].strip() for o, p in GRID})
print(f"author's string appears verbatim among our 12 outputs: {hit}/{n_author}")
inv = [f for f in files if author[f] is None]
print("author-'Not valid' images that ARE valid for us in >=1 combination:", sum(any(v(f, c) for c in GRID) for f in inv), "/", len(inv))
print("author-valid images that are valid for us in NO combination:", sum(not any(v(f, c) for c in GRID) for f in files if author[f] is not None))

print("\n[5] what our valid readings look like (all combinations pooled)")
vals = [texts[(f, o, p)].strip() for f in files for o, p in GRID if ok[(f, o, p)]]
ls = [len(x) for x in vals]
print(f"n={len(vals)} median length {statistics.median(ls)} max {max(ls)} multi-line {sum(chr(10) in x for x in vals)}")
print("kinds:", {"number": sum(bool(re.fullmatch(r'-?\d+', x)) for x in vals),
                 "letters only": sum(bool(re.fullmatch(r'[A-Za-z]+', x)) for x in vals)})
print("first 12 readings under LSTM psm 8:", [texts[(f, 1, 8)].strip() for f in files[:12]])
print("first 12 readings under legacy psm 8:", [texts[(f, 0, 8)].strip() for f in files[:12]])
