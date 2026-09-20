#!/usr/bin/env python3
"""
ClineDesktop2API — local reverse proxy for Cline Desktop.

Cline's Bun sidecar gets 403'd by Cloud Armor JA3 fingerprinting.
This proxy receives plain HTTP on localhost, re-originates HTTPS to
api.cline.bot with Python's OpenSSL (passes the fingerprint check),
and streams responses back.

Usage:
    python proxy.py                  # start on 127.0.0.1:61022
    set CLINE_API_BASE_URL=http://127.0.0.1:61022
    [launch Cline Desktop]
"""
import http.server
import ssl
import sys
import os
import time
import threading
import urllib.request
import urllib.error
from urllib.parse import urlparse

UPSTREAM = "https://api.cline.bot"
PORT = int(os.environ.get("CLINE_PROXY_PORT", "61022"))
HOST = "127.0.0.1"

CTX = ssl.create_default_context()

# Headers the proxy should always forward
PASS_THROUGH = {
    "authorization", "content-type", "accept", "accept-encoding",
    "x-client-type", "x-client-version", "x-title", "x-is-multiroot",
    "x-platform", "user-agent", "x-request-id",
}
SKIP = {"host", "connection", "transfer-encoding", "proxy-connection"}


class Handler(http.server.BaseHTTPRequestHandler):
    def _proxy(self):
        upstream_url = UPSTREAM + self.path
        qs = self.headers.get("Content-Length", "0")
        body = self.rfile.read(int(qs)) if int(qs) > 0 else None

        fwd = {}
        for k, v in self.headers.items():
            lk = k.lower()
            if lk in SKIP:
                continue
            if lk in PASS_THROUGH or lk.startswith("x-"):
                fwd[k] = v
        fwd.setdefault("User-Agent", "ClineDesktop2API/1.0")
        fwd.setdefault("X-CLIENT-TYPE", "cline-sdk")

        try:
            req = urllib.request.Request(
                upstream_url, data=body, headers=fwd, method=self.command
            )
            resp = urllib.request.urlopen(req, timeout=120, context=CTX)
            status = resp.status
            rheaders = dict(resp.headers)
            rbody = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            rheaders = dict(e.headers) if hasattr(e, "headers") else {}
            try:
                rbody = e.read()
            except Exception:
                rbody = b""
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f"proxy error: {e}".encode())
            return

        self.send_response(status)
        for k, v in rheaders.items():
            if k.lower() in SKIP:
                continue
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(rbody)

        tag = time.strftime("%H:%M:%S")
        print(f"[{tag}] {self.command} {self.path} -> {status} ({len(rbody)} bytes)")
        sys.stdout.flush()

    do_GET = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_DELETE = _proxy
    do_OPTIONS = _proxy
    do_PATCH = _proxy

    def log_message(self, *a):
        pass


def main():
    server = http.server.HTTPServer((HOST, PORT), Handler)
    print(f"ClineDesktop2API proxy v1.0")
    print(f"  Listening : {HOST}:{PORT}")
    print(f"  Upstream  : {UPSTREAM}")
    print()
    print(f"  set CLINE_API_BASE_URL=http://{HOST}:{PORT}")
    print()
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
