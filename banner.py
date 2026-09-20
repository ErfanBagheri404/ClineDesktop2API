"""Startup banner."""
import sys

def print_banner(cfg):
    name = "ClineDesktop2API"
    v = "v1.0.0"
    lines = [
        f"{name} {v}",
        "OpenAI-compatible proxy for Cline Desktop (api.cline.bot)",
        f"Listening: {cfg.bind}:{cfg.port}",
        "Upstream:  https://api.cline.bot (Python TLS — bypasses Cloud Armor JA3)",
    ]
    if cfg.api_key:
        lines.append("Auth:      API key required on /v1/ routes")
    if cfg.log_path:
        lines.append(f"Log:       {cfg.log_path}")
    if cfg.rate_limit:
        lines.append(f"Rate:      1 req/{cfg.rate_limit} per IP")
    w = max(len(l) for l in lines)
    print()
    print(" " + "=" * (w + 4))
    for l in lines:
        print(f"  {l:<{w}}")
    print(" " + "=" * (w + 4))
    print()
    sys.stdout.flush()
