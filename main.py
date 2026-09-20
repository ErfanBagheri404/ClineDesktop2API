"""ClineDesktop2API — CLI entry point."""
import argparse

def main():
    p = argparse.ArgumentParser(description="OpenAI-compatible proxy for Cline Desktop")
    p.add_argument("--port", type=int, default=61022, help="listen port (default 61022)")
    p.add_argument("--bind", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    p.add_argument("--api-key", default=None, help="require this key on /v1/ routes")
    p.add_argument("--log", default=None, help="path to request log file")
    p.add_argument("--rate-limit", default=None, help="min interval between requests per IP (e.g. 2s)")
    p.add_argument("--desensitize", action="store_true", help="rewrite moderation triggers in prompts")
    args = p.parse_args()
    from config import load_config
    cfg = load_config(args)
    from banner import print_banner
    print_banner(cfg)
    from server import serve
    serve(cfg)


if __name__ == "__main__":
    main()
