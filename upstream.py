"""Upstream HTTP client — Python OpenSSL bypasses Cloud Armor JA3."""
import ssl
import urllib.request
import urllib.error
import json
import time
from reqlog import enabled, log_line

UPSTREAM = "https://api.cline.bot"
CTX = ssl.create_default_context()
UA = "Cline/0.0.32"
HEADERS_TO_DROP = frozenset(["host", "connection", "transfer-encoding"])
PASS_HEADERS = frozenset([
    "authorization", "content-type", "accept", "accept-encoding",
    "x-client-type", "x-client-version", "x-title", "x-platform",
    "user-agent", "x-is-multiroot",
])

# Cline's backend recognizes the desktop client via these headers and applies
# free-model pricing accordingly. Chat POSTs arrive without them, so we inject
# defaults so the upstream never mistakes us for an external/API consumer.
DESKTOP_HEADERS = {
    "X-CLIENT-TYPE": "cline-desktop",
    "X-CLIENT-VERSION": "0.0.32",
    "HTTP-Referer": "https://cline.bot",
    "X-IS-MULTIROOT": "false",
    "X-PLATFORM": "Cline Desktop",
    "X-PLATFORM-VERSION": "0.0.32",
    "X-Title": "Cline",
}


def _normalize_path(path):
    """Cline Desktop posts chat to {baseUrl}/chat/completions with no API prefix.

    Upstream expects /api/v1/... so map the bare forms onto it.
    """
    if path.startswith("/api/v1/"):
        return path
    if path.startswith("/v1/"):
        return "/api/v1/" + path[4:]
    for bare in ("/chat/completions", "/models", "/responses", "/completions"):
        if path == bare or path.startswith(bare + "?"):
            return "/api/v1" + path
    return path


# Free-tier model IDs, fetched live from /api/v1/ai/cline/recommended-models
# and cached. Requests for the same model without the cline-free/ prefix are
# billed, so we rewrite them when the desktop headers are present.
_free_cache = {"ids": [], "t": 0.0}
_FREE_TTL = 600.0


def _free_model_ids():
    """Return the set of free-tier model IDs (cached 10 min)."""
    if _free_cache["ids"] and time.time() - _free_cache["t"] < _FREE_TTL:
        return _free_cache["ids"]
    try:
        url = UPSTREAM + "/api/v1/ai/cline/recommended-models"
        req = urllib.request.Request(url, headers=dict(DESKTOP_HEADERS, **{"User-Agent": UA}))
        resp = urllib.request.urlopen(req, timeout=15, context=CTX)
        data = json.loads(resp.read())
        ids = [m.get("id") for m in data.get("free", []) if m.get("id")]
        _free_cache["ids"] = ids
        _free_cache["t"] = time.time()
        return ids
    except Exception:
        return _free_cache["ids"]


def rewrite_to_free(body, headers=None):
    """Rewrite paid model IDs to their cline-free/ equivalents when the
    request looks like a desktop client. Returns the (possibly new) body."""
    if not body:
        return body
    try:
        raw = body if isinstance(body, str) else body.decode("utf-8", "replace")
        j = json.loads(raw)
    except Exception:
        return body
    model = j.get("model") or ""
    if not model or model.startswith(("cline-free/", "~")):
        return body
    base = model.split("/")[-1]
    free = f"cline-free/{base}"
    if free in _free_model_ids():
        j["model"] = free
        return json.dumps(j).encode()
    return body


def do_request(method, path, body=None, headers=None, timeout=120,
               proxy_token=None):
    """Forward to api.cline.bot with clean TLS fingerprint.

    If *proxy_token* is provided, it replaces any Authorization header so
    the upstream always sees a valid token regardless of what the client sent.
    """
    url = UPSTREAM + _normalize_path(path)
    fwd = {}
    if headers:
        for k, v in headers.items():
            if k.lower() not in HEADERS_TO_DROP:
                fwd[k] = v
    fwd.setdefault("User-Agent", "ClineDesktop2API/1.0")
    fwd.setdefault("X-CLIENT-TYPE", "cline-desktop")

    # Inject desktop-identifying headers so Cline applies free-model pricing.
    for k, v in DESKTOP_HEADERS.items():
        fwd.setdefault(k, v)

    if proxy_token:
        fwd["Authorization"] = f"Bearer workos:{proxy_token}"

    data = rewrite_to_free(body, fwd)
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

