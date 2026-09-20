"""Request logging with credential redaction."""
import re
import time
import threading
import os

_BEARER_RE = re.compile(r"(?i)((?:bearer|token)\s+)[A-Za-z0-9._\-]{8,}")

_TOKEN_RE = re.compile(
    r"(?i)([\"']?(?:access_?token|refresh_?token|accesstoken|refreshtoken|"
    r"authorization|api[-_]?key|x-api-key|password)[\"']?\s*[:=]\s*)"
    r"[\"']?[^\"',\s}]{4,}[\"']?"
)

_file = None
_lock = threading.Lock()


def enable_logging(path):
    global _file
    with _lock:
        if _file:
            _file.close()
            _file = None
        if path:
            _file = open(path, "a", encoding="utf-8")
            _file.write("--- session %s ---\n" % time.strftime("%Y-%m-%d %H:%M:%S"))


def enabled():
    with _lock:
        return _file is not None


def redact(s):
    s = _BEARER_RE.sub(r"\g<1>[REDACTED]", s)
    s = _TOKEN_RE.sub(r"\g<1>[REDACTED]", s)
    return s


def log_line(cid, msg):
    with _lock:
        if _file:
            _file.write("[%s] [%s] %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), cid, redact(msg)))
            _file.flush()


def log_block(cid, label, body):
    if not enabled():
        return
    log_line(cid, "\u2500\u2500 %s \u2500\u2500" % label)
    for ln in body.rstrip("\n").split("\n"):
        log_line(cid, "  " + ln)


def new_correlation_id():
    return os.urandom(4).hex()
