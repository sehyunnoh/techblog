"""Scan OpenSSL release tags for the EVP_EncodeBlock length pattern (CVE-2026-121481).

For every release tag we fetch crypto/evp/encode.c and record:
  - whether EVP_EncodeBlock exists,
  - the type of the accumulator that returns the encoded length (int / unsigned / size_t),
  - whether the function or its helper contains any dlen upper-bound guard.
Usage: python openssl-encodeblock-scan.py > openssl-encodeblock-scan-output.txt
"""
import re, subprocess, urllib.request, concurrent.futures as cf, collections

def tags():
    out = subprocess.check_output(["git", "ls-remote", "--tags", "https://github.com/openssl/openssl.git"], text=True)
    names = [l.split("refs/tags/")[1] for l in out.splitlines() if "^{}" not in l]
    keep = []
    for n in names:
        if re.fullmatch(r"openssl-\d+\.\d+\.\d+", n) or re.fullmatch(r"OpenSSL_\d+_\d+_\d+[a-z]*", n):
            keep.append(n)
    return sorted(keep)

def fetch(tag):
    url = f"https://raw.githubusercontent.com/openssl/openssl/{tag}/crypto/evp/encode.c"
    for _ in range(3):
        try:
            return urllib.request.urlopen(url, timeout=30).read().decode("latin-1")
        except Exception:
            pass
    return None

def body(src, name):
    m = re.search(r"^(?:static )?int\s+%s\s*\([^;{]*\)(?:\s*\{|[ \t]*\n(?:[^{};]*;[ \t]*\n)+\s*\{)" % name, src, re.S | re.M)
    if not m:
        return None
    i = m.end(); depth = 1
    while depth and i < len(src):
        depth += (src[i] == "{") - (src[i] == "}")
        i += 1
    return src[m.start():i]

def classify(tag):
    src = fetch(tag)
    if src is None:
        return tag, "fetch-failed", "", ""
    pub = body(src, "EVP_EncodeBlock")
    if pub is None:
        return tag, "no-EVP_EncodeBlock", "", ""
    helper = body(src, "evp_encodeblock_int")
    work = helper if helper else pub
    decl = re.search(r"^\s*(unsigned\s+int|unsigned|size_t|int)\s+[^;(]*\bret\b", work, re.M)
    ret_type = decl.group(1).replace("unsigned int", "unsigned") if decl else "?"
    if ret_type == "?" and "(int)" in pub:
        ret_type = "size_t-cast-to-int"
    if "encode_base64_avx2" in src:
        ret_type += "+avx2"
    guard = bool(re.search(r"INT_MAX|OPENSSL_assert\s*\(\s*dlen|dlen\s*<\s*0|dlen\s*>\s*\(", pub + (helper or "")))
    return tag, "has", ret_type, "guard" if guard else "no-guard"

if __name__ == "__main__":
    ts = tags()
    with cf.ThreadPoolExecutor(12) as ex:
        rows = list(ex.map(classify, ts))
    print("tag,status,ret_type,length_guard")
    for r in rows:
        print(",".join(r))
    c = collections.Counter((r[1], r[2], r[3]) for r in rows)
    print("\n# totals over", len(rows), "release tags")
    for k, v in sorted(c.items()):
        print(k, v)
