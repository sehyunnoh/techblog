#!/usr/bin/env python3
"""
Read-only check for the trojanized anthropic.claude-code 2.1.313 reports.

Standard library only. Nothing is written, installed, or deleted, and no file
contents leave the machine. The only network calls are GETs to the public
Open VSX API (and one POST query to the VS Code Marketplace gallery API).

Part 1: which versions do the public registries list? Is there a 2.1.313?
Part 2: which copies of the extension are installed here, and do they contain
        any of the published indicator strings?
Part 3: do the published persistence artifacts exist on this machine?

Indicators come from the public reports (Cursor notice, The CyberSec Guru,
Socket, The Hacker News). A clean result means "none of these specific
strings or files were found". It does not prove the machine is clean.

Usage: python claude-ext-ioc-probe.py
"""
import glob
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

HOME = os.path.expanduser("~")
UA = {"User-Agent": "claude-ext-ioc-probe/1.0"}

# Strings reported inside the injected loader. Plain substrings, matched in
# extension.js only.
IOC_STRINGS = [
    "svc-telemetry",
    "134.209.82.225",
    ":8099/beacon",  # a bare "/beacon" also matches the genuine https://beacon.claude-ai... URL
    "com.apple.sysmond",
    "sysmon.cmd",
    ".stk_",
    "-R '*:0:localhost:22'",
    "AAAAC3NzaC1lZDI1NTE5AAAAIDdvylCEJ/k2TpezcTfedrkHyFSK9IZ3vmP6vhY4Ss0P",
]
# Reported SHA-256 of the malicious extension.js (CyberSec Guru article).
BAD_JS_SHA256 = "ecb58cb29078d9646ad1dcdbe51526f2d9cfea06be5fb2ab183e8ecc3ab6bf15"
KEY_BLOB = "AAAAC3NzaC1lZDI1NTE5AAAAIDdvylCEJ/k2TpezcTfedrkHyFSK9IZ3vmP6vhY4Ss0P"


def redact(path):
    return path.replace(HOME, "~")


def get_json(url, data=None, headers=None):
    h = dict(UA)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def part1_registries():
    print("== 1. What the registries list")
    try:
        meta = get_json("https://open-vsx.org/api/anthropic/claude-code")
        versions = sorted(
            (v for v in meta.get("allVersions", {}) if re.match(r"\d", v)),
            key=lambda s: [int(x) for x in s.split(".")],
        )
        print(f"Open VSX latest: {meta.get('version')} ({meta.get('timestamp')})")
        print("Open VSX versions (last 8):", ", ".join(versions[-8:]))
        print("Open VSX lists 2.1.313:", "2.1.313" in versions)
        for v in ("2.1.312", "2.1.313", "2.1.314"):
            try:
                m = get_json(f"https://open-vsx.org/api/anthropic/claude-code/{v}")
                print(f"  {v}: published {m.get('timestamp')}")
            except urllib.error.HTTPError as e:
                print(f"  {v}: HTTP {e.code}")
    except Exception as e:  # network may be blocked; the local checks still run
        print("Open VSX query failed:", e)
    try:
        body = json.dumps(
            {"filters": [{"criteria": [{"filterType": 7, "value": "anthropic.claude-code"}]}], "flags": 103}
        ).encode()
        d = get_json(
            "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json;api-version=7.1-preview.1"},
        )
        vs = [v["version"] for v in d["results"][0]["extensions"][0]["versions"]]
        uniq = list(dict.fromkeys(vs))
        print("VS Code Marketplace versions (newest first, 8):", ", ".join(uniq[:8]))
        print("VS Code Marketplace lists 2.1.313:", "2.1.313" in uniq)
    except Exception as e:
        print("VS Code Marketplace query failed:", e)


def sha256(path):
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def part2_installed():
    print("\n== 2. Installed copies of the extension")
    roots = [".vscode", ".vscode-insiders", ".cursor", ".windsurf", ".antigravity", ".vscode-oss"]
    found = 0
    flagged = 0
    for r in roots:
        for d in sorted(glob.glob(os.path.join(HOME, r, "extensions", "anthropic.claude-code-*"))):
            found += 1
            name = os.path.basename(d)
            js = os.path.join(d, "extension.js")
            if not os.path.isfile(js):
                cands = glob.glob(os.path.join(d, "**", "extension.js"), recursive=True)
                js = cands[0] if cands else None
            if not js:
                print(f"  {r}/{name}: no extension.js found")
                continue
            with open(js, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            hits = [s for s in IOC_STRINGS if s in text]
            same_hash = sha256(js) == BAD_JS_SHA256
            if hits or same_hash:
                flagged += 1
            print(
                f"  {r}/{name}: extension.js {os.path.getsize(js):,} bytes, "
                f"indicator strings: {hits or 'none'}, reported-bad hash: {same_hash}"
            )
    print(f"Copies found: {found}. Flagged: {flagged}.")


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout
    except Exception as e:
        return f"(could not run {cmd[0]}: {e})"


def part3_persistence():
    print("\n== 3. Reported persistence artifacts")
    ak = os.path.join(HOME, ".ssh", "authorized_keys")
    if os.path.isfile(ak):
        t = open(ak, "r", errors="replace").read()
        print("  authorized_keys exists; contains svc-telemetry:", "svc-telemetry" in t, "; contains reported key:", KEY_BLOB in t)
    else:
        print("  authorized_keys: not present")
    paths = [
        os.path.join(HOME, ".config", ".smt"),
        os.path.join(HOME, ".config", ".smtk"),
        os.path.join(HOME, "Library", "LaunchAgents", "com.apple.sysmond.plist"),
    ]
    if sys.platform == "win32":
        startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "sysmon.cmd")
        paths.append(startup)
    paths += glob.glob(os.path.join(os.environ.get("TEMP", "/tmp"), ".stk_*"))
    for p in paths:
        print(f"  {redact(p)}: {'PRESENT' if os.path.exists(p) else 'absent'}")
    if sys.platform == "win32":
        out = run(["schtasks", "/Query", "/TN", "SysMon"])
        print("  scheduled task SysMon:", "absent" if "ERROR" in out or not out.strip() else "PRESENT")
        out = run(["powershell", "-NoProfile", "-Command", "Get-Service sshd -ErrorAction SilentlyContinue | Select -Expand Status"])
        print("  sshd service:", out.strip() or "not installed")
    else:
        cron = run(["crontab", "-l"])
        print("  crontab mentions .smt:", ".smt" in cron)


if __name__ == "__main__":
    part1_registries()
    part2_installed()
    part3_persistence()
