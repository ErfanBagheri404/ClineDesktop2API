"""Upstream HTTP client — Python OpenSSL bypasses Cloud Armor JA3."""
import ssl
import urllib.request
import urllib.error
import json
import time
from logging import enabled, log_line

UPSTREAM = "https://api.cline.bot"
CTX = ssl.create_default_context()
HEADERS_TO_DROP = frozenset(["host", "connection", "transfer-encoding"])
PASS_HEADERS = frozenset([
    "authorization", "content-type", "accept", "accept-encoding",
    "x-client-type", "x-client-version", "x-title", "x-platform",
    "user-agent", "x-is-multiroot",
])

def do_request(method, path, body=None, headers=None, timeout=120):
    url = UPSTREAM + path
    fwd = {}
    if headers:
        for k, v in headers.items():
            if k.lower() not in HEADERS_TO_DROP:
                fwd[k] = v
    fwd.setdefault("User-Agent", "ClineDesktop2API/1.0")
    fwd.setdefault("X-CLIENT-TYPE", "cline-sdk")

    data = body.encode() if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, headers=fwd, method=method)
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=CTX)
        elapsed = time.time() - t0
        rbody = resp.read()
        if enabled():
            log_line("---", f"{method} {path} -> {resp.status} ({len(rbody)} bytes, {elapsed:.1f}s)")
        return resp.status, dict(resp.headers), rbody
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        rbody = e.read() if hasattr(e, "read") else b""
        if enabled():
            log_line("---", f"{method} {path} -> {e.code} ({len(rbody)} bytes, {elapsed:.1f}s)")
        return e.code, dict(e.headers) if hasattr(e, "headers") else {}, rbody
    except Exception as e:
        elapsed = time.time() - t0
        if enabled():
            log_line("---", f"{method} {path} -> ERR {e} ({elapsed:.1f}s)")
        return 502, {}, json.dumps({"error": {"message": str(e), "type": "proxy_error"}}).encode()
