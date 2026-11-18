#!/usr/bin/env python3
"""Scan OpenJDK release tags for the Base64 AVX-512 tail code behind Java4Shell.

Usage: python java4shell-source-scan.py [out.csv]

For every "-ga" tag of a few OpenJDK repositories it downloads
src/hotspot/cpu/x86/stubGenerator_x86_64.cpp from raw.githubusercontent.com and
reports, for the Base64 decodeBlock stub:
  stub     the AVX-512 VBMI decodeBlock stub exists in this file
  mime     the Java-side decodeBlock() takes an isMIME argument (the 17.0.6 backport)
  tail     the stub has its own "final 1 to 63 bytes" path (L_finalBit) that builds
           the store mask with bzhiq(output_mask, output_mask, output_size)
  guard    a "cmpl(length, 4)" check sends padded tails shorter than 4 bytes to the
           Java code (the four lines that differ between 17.0.21.0.3 and 17.0.21.1)
Needs: git (for ls-remote) and Python 3 standard library only. About 80 downloads
of roughly 300 KB each.
"""
import csv
import re
import subprocess
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

RAW = "https://raw.githubusercontent.com/openjdk/{repo}/{tag}/{path}"
STUB = "src/hotspot/cpu/x86/stubGenerator_x86_64.cpp"
B64J = "src/java.base/share/classes/java/util/Base64.java"

REPOS = {
    "jdk11u-dev": r"jdk-11\.0\.(2|20|33|33\.1)-ga",
    "jdk17u": r"jdk-17(\.[0-9.]+)?-ga",
    "jdk21u": r"jdk-21(\.[0-9.]+)?-ga",
    "jdk25u": r"jdk-25(\.[0-9.]+)?-ga",
    "jdk": r"jdk-(1[89]|2[0-7])-ga",
}


def version_key(tag):
    nums = re.findall(r"\d+", tag)
    return [int(n) for n in nums]


def tags(repo, pattern):
    out = subprocess.run(
        ["git", "ls-remote", "--tags", f"https://github.com/openjdk/{repo}", "refs/tags/jdk-*-ga"],
        capture_output=True, text=True, check=True).stdout
    found = {l.split("refs/tags/")[1] for l in out.splitlines() if "^{}" not in l}
    return sorted((t for t in found if re.fullmatch(pattern, t)), key=version_key)


def fetch(repo, tag, path):
    url = RAW.format(repo=repo, tag=tag, path=path)
    for _ in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:
            continue
    return None


def decode_block(src):
    """Return the text of the Base64 decodeBlock stub generator, or ''."""
    m = re.search(r"address generate_base64_decodeBlock\(\)|generate_base64_decodeBlock\(\)\s*\{", src)
    if not m:
        return ""
    end = src.find("generate_updateBytesCRC32()", m.end())
    return src[m.start(): end if end > 0 else m.start() + 60000]


def inspect(job):
    repo, tag = job
    stub = fetch(repo, tag, STUB)
    java = fetch(repo, tag, B64J)
    row = {"repo": repo, "tag": tag}
    if stub is None:
        row.update(stub="fetch-failed")
        return row
    body = decode_block(stub)
    row["stub"] = "vbmi" in body.lower() and "bzhiq" in body or "base64_vbmi" in body
    row["mime"] = bool(java and re.search(r"decodeBlock\(byte\[\] src, int sp, int sl, byte\[\] dst, int dp, boolean isURL, boolean isMIME\)", java))
    row["tail"] = "bzhiq(output_mask, output_mask, output_size)" in body
    row["guard"] = bool(re.search(r"cmpl\(length, 4\);\s*__ jcc\(Assembler::less, L_bruteForce\)", body))
    return row


def main():
    dst = sys.argv[1] if len(sys.argv) > 1 else None
    jobs = [(repo, t) for repo, pat in REPOS.items() for t in tags(repo, pat)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = list(ex.map(inspect, jobs))
    print(f"{'repo':11} {'tag':22} stub  mime  tail  guard")
    for r in rows:
        f = lambda k: ("yes" if r.get(k) is True else "no" if r.get(k) is False else str(r.get(k, ""))).ljust(5)
        print(f"{r['repo']:11} {r['tag']:22} {f('stub')} {f('mime')} {f('tail')} {f('guard')}")
    if dst:
        with open(dst, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["repo", "tag", "stub", "mime", "tail", "guard"])
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
