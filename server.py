"""HTTP server: Cline passthrough + OpenAI-compatible endpoints."""
import http.server
import json
import sys
import threading
import time
from upstream import do_request
from ratelimit import RateLimiter
from anthropic import anthropic_to_openai, anthropic_response, anthropic_stream_response
from logging import enabled, log_line, log_block, new_correlation_id
from desensitize import desensitize_payload

# Cline's own API surface — passed straight through to api.cline.bot.
CLINE_PASSTHROUGH_PREFIX = "/api/v1/"


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ClineDesktop2API"

    cfg = None
    limiter = None

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- routing -------------------------------------------------------

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            self.close_connection = True

    def _dispatch(self, method):
        cid = new_correlation_id()

        if self.path.startswith("/healthz"):
            self._json(200, {"status": "ok"})
            return

        if self.limiter is not None and self.path.startswith("/v1/"):
            ip = self.client_address[0]
            ok, wait = self.limiter.allow(ip)
            if not ok:
                self.send_response(429)
                self.send_header("Retry-After", str(max(1, int(wait + 0.999))))
                self._json_body(429, {"error": {"message": "rate limit exceeded, try again later",
                                                "type": "rate_limit_error"}})
                return

        if self.cfg and self.cfg.api_key and self.path.startswith("/v1/"):
            if not self._authorized():
                self._json(401, {"error": {"message": "invalid API key", "type": "authentication_error"}})
                return

        body = self._read_body()

        if self.path.startswith(CLINE_PASSTHROUGH_PREFIX):
            self._passthrough(method, body, cid)
            return

        if self.path.startswith("/v1/models"):
            self._models(cid)
            return

        if self.path.startswith("/v1/chat/completions"):
            self._chat(method, body, cid)
            return

        if self.path.startswith("/v1/messages"):
            self._anthropic(method, body, cid)
            return

        self._json(404, {"error": {"message": "unknown endpoint", "type": "not_found"}})

    # ---- handlers ------------------------------------------------------

    def _get_proxy_token(self):
        """Return a valid Cline token from the proxy's own store, or None."""
        if not getattr(self.cfg, "owned_auth", False):
            return None
        try:
            from auth import get_valid_token
            return get_valid_token()
        except Exception:
            return None

    def _passthrough(self, method, body, cid):
        """Forward Cline Desktop's own API calls verbatim."""
        fwd = {k: v for k, v in self.headers.items() if k.lower() not in ("host","connection","content-length","transfer-encoding")}
        log_line(cid, f"{method} {self.path} fwd={dict(fwd)}")
        if enabled() and body:
            log_block(cid, f"CLINE {method} {self.path}", body.decode("utf-8", "replace"))
        status, headers, rbody = do_request(method, self.path, body, dict(self.headers),
                                            proxy_token=self._get_proxy_token())
        self._raw(status, headers, rbody)

    def _models(self, cid):
        status, headers, rbody = do_request("GET", "/api/v1/models", None, dict(self.headers),
                                            proxy_token=self._get_proxy_token())
        if status != 200:
            self._raw(status, headers, rbody)
            return
        try:
            data = json.loads(rbody)
            models = data.get("data") or data.get("models") or []
            out = {"object": "list", "data": [
                {"id": m.get("id"), "object": "model", "owned_by": "cline"}
                for m in models if m.get("id")
            ]}
        except Exception as e:
            self._json(502, {"error": {"message": f"model list parse: {e}", "type": "proxy_error"}})
            return
        self._json(200, out)

    def _chat(self, method, body, cid):
        if method != "POST":
            self._json(405, {"error": {"message": "use POST", "type": "invalid_request_error"}})
            return
        if enabled() and body:
            log_block(cid, "OPENAI /v1/chat/completions", body.decode("utf-8", "replace"))
        if self.cfg and self.cfg.desensitize and body:
            body = desensitize_payload(body)
        status, headers, rbody = do_request("POST", "/api/v1/chat/completions", body, dict(self.headers),
                                            proxy_token=self._get_proxy_token())
        self._raw(status, headers, rbody, force_stream=True)

    def _anthropic(self, method, body, cid):
        if method != "POST":
            self._json(405, {"error": {"message": "use POST", "type": "invalid_request_error"}})
            return
        try:
            ar = json.loads(body)
        except Exception as e:
            self._json(400, {"error": {"message": f"bad json: {e}", "type": "invalid_request_error"}})
            return
        oai = anthropic_to_openai(ar)
        payload = json.dumps(oai).encode()
        if enabled():
            log_block(cid, "ANTHROPIC /v1/messages -> OPENAI", payload.decode())
        status, headers, rbody = do_request("POST", "/api/v1/chat/completions", payload, dict(self.headers),
                                            proxy_token=self._get_proxy_token())
        if status != 200:
            self._raw(status, headers, rbody)
            return
        model = ar.get("model", "")
        if ar.get("stream"):
            self._sse_stream(anthropic_stream_response(rbody, model))
        else:
            self._json(200, anthropic_response(rbody, model))

    # ---- helpers -------------------------------------------------------

    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n > 0 else None

    def _authorized(self):
        h = self.headers.get("Authorization", "")
        if h.lower().startswith("bearer "):
            if h[7:].strip() == self.cfg.api_key:
                return True
        return self.headers.get("x-api-key", "") == self.cfg.api_key

    def _raw(self, status, headers, body, force_stream=False):
        self.send_response(status)
        for k, v in headers.items():
            lk = k.lower()
            if lk in ("content-length", "transfer-encoding", "connection"):
                continue
            self.send_header(k, v)
        if force_stream and headers.get("Content-Type", "").startswith("text/event-stream"):
            self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        self._json_body(status, obj)

    def _json_body(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse_stream(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        for ev in events:
            self.wfile.write(ev.encode())
            self.wfile.flush()

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def log_message(self, fmt, *args):
        pass


def serve(cfg):
    from logging import enable_logging
    enable_logging(cfg.log_path)
    if cfg.rate_limit:
        Handler.limiter = RateLimiter(cfg.rate_limit)
        Handler.limiter.start_cleanup()
    Handler.cfg = cfg
    srv = http.server.ThreadingHTTPServer((cfg.bind, cfg.port), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        srv.server_close()
