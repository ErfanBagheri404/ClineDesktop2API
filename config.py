"""Configuration."""
import os
import re


class Config:
    def __init__(self, args=None):
        self.port = 61022
        self.bind = "127.0.0.1"
        self.api_key = None
        self.log_path = None
        self.rate_limit = None
        self.desensitize = False
        if args:
            self.port = getattr(args, "port", self.port)
            self.bind = getattr(args, "bind", self.bind)
            self.api_key = getattr(args, "api_key", self.api_key)
            self.log_path = getattr(args, "log", self.log_path)
            self.rate_limit = getattr(args, "rate_limit", self.rate_limit)
            self.desensitize = getattr(args, "desensitize", self.desensitize)
        self.port = int(os.environ.get("CLINE_PROXY_PORT", self.port))


def _parse_interval(s):
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d+(?:\.\d+)?)(ms|s|m)?$", s)
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2) or "s"
    return n * {"ms": 0.001, "s": 1, "m": 60}[unit]


def load_config(args=None):
    c = Config(args)
    if isinstance(c.rate_limit, str):
        c.rate_limit = _parse_interval(c.rate_limit)
    return c
