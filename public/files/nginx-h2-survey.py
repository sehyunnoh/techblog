#!/usr/bin/env python3
"""Survey which top domains speak HTTP/2 and what their Server header says.

Usage: python nginx-h2-survey.py top1000.csv results.csv [limit]

Input is a Tranco-style CSV ("rank,domain"). For each domain the script
  1. sends one HTTP/1.1 HEAD request over TLS to the domain on port 443, following
     up to 3 redirects (same scheme, any host), and records the status line,
     the Server header and a few CDN hints from the final response;
  2. opens one more TLS connection to the final host, offers ALPN ["h2", "http/1.1"]
     and records which protocol the server picks. No HTTP request is sent on it.
That is at most 10 requests per site (each step is retried once), spread over different sites by 16 threads.
It reads only what any browser would see. A Server header can be missing, edited
or set by a CDN, so the output is an upper bound on what is visible, not a
count of what is running. Python 3 standard library only.
"""
import csv
import http.client
import socket
import ssl
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

UA = "http2-survey/1.0 (research; one HEAD request per site)"
CTX = ssl.create_default_context()
CTX.check_hostname = False          # we only want to see what the server offers
CTX.verify_mode = ssl.CERT_NONE


def head(host, path="/"):
    conn = http.client.HTTPSConnection(host, 443, timeout=8, context=CTX)
    try:
        conn.request("HEAD", path, headers={"User-Agent": UA, "Accept": "*/*", "Host": host})
        r = conn.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}
    finally:
        conn.close()


def alpn(host):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.set_alpn_protocols(["h2", "http/1.1"])
    with socket.create_connection((host, 443), timeout=8) as s:
        with ctx.wrap_socket(s, server_hostname=host) as t:
            return t.selected_alpn_protocol() or "none"


def survey(domain):
    row = {"domain": domain, "host": domain, "status": "", "server": "", "alpn": "",
           "cdn_hint": "", "error": ""}
    host, path, h = domain, "/", {}
    try:
        for _ in range(4):
            try:
                status, h = head(host, path)
            except socket.gaierror:
                raise
            except Exception:
                status, h = head(host, path)    # one retry for resets and timeouts
            row["status"] = status
            if status in (301, 302, 303, 307, 308) and "location" in h:
                u = urllib.parse.urlparse(urllib.parse.urljoin(f"https://{host}{path}", h["location"]))
                if u.scheme == "https" and u.hostname:
                    host, path = u.hostname, (u.path or "/") + (("?" + u.query) if u.query else "")
                    continue
            break
        row["host"] = host
        row["server"] = h.get("server", "")
        hints = [k for k in ("cf-ray", "x-amz-cf-id", "x-served-by", "x-akamai-transformed", "x-fastly-request-id", "via") if k in h]
        row["cdn_hint"] = ",".join(hints)
    except Exception as e:
        row["error"] = type(e).__name__
    for attempt in range(2):            # one retry: a single reset should not look like "no h2"
        try:
            row["alpn"] = alpn(row["host"])
            break
        except Exception as e:
            row["error"] = row["error"] or type(e).__name__
    return row


def main():
    src, dst = sys.argv[1], sys.argv[2]
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
    domains = [r[1] for r in csv.reader(open(src, encoding="utf-8"))][:limit]
    with ThreadPoolExecutor(max_workers=16) as ex:
        rows = list(ex.map(survey, domains))
    with open(dst, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["domain", "host", "status", "server", "alpn", "cdn_hint", "error"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {dst}")


if __name__ == "__main__":
    main()
