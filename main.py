"""ClineDesktop2API — CLI entry point with interactive menu (mirrors WorkBuddy2API)."""
import argparse
import json
import sys
import urllib.error
import urllib.request


def print_menu():
    print()
    print("  ┌─────────────────────────────────┐")
    print("  │  1. Status                       │")
    print("  │  2. Start server                 │")
    print("  │  3. List models                  │")
    print("  │  4. Test chat                    │")
    print("  │  5. Re-login                     │")
    print("  │  6. Quit                         │")
    print("  └─────────────────────────────────┘")
    print()


def show_status():
    from auth import load_tokens
    tok = load_tokens()
    print()
    if not tok:
        print("  ✗ Not logged in. Run option 5 first.")
        print()
        return
    from datetime import datetime, timezone
    exp = tok.get("expiresAt", 0)
    if exp:
        exp_str = datetime.fromtimestamp(exp / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        expired = datetime.now(timezone.utc).timestamp() * 1000 > exp
    else:
        exp_str = "unknown"
        expired = False
    print("  ✓ Authenticated")
    print(f"    User ID : {tok.get('accountId', 'N/A')}")
    print(f"    Token   : {len(tok['access'])} chars")
    print(f"    Expires : {exp_str}{' (EXPIRED)' if expired else ''}")
    print(f"    Refresh : {'yes' if tok.get('refresh') else 'no'}")
    print()


def list_models(port):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/v1/models", headers={})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        d = json.loads(r.read())
        models = d.get("data", [])
        print(f"\n  {len(models)} models available:")
        for m in models[:30]:
            print(f"    {m['id']}")
        if len(models) > 30:
            print(f"    ... and {len(models) - 30} more")
        print()
    except Exception as e:
        print(f"\n  ✗ Failed: {e}\n")


def test_chat(port):
    model = input("  Model [~openai/gpt-luna-latest]: ").strip() or "~openai/gpt-luna-latest"
    msg = input("  Message [Hello]: ").strip() or "Hello"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": msg}],
        "max_tokens": 200,
    }).encode()
    print()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        r = urllib.request.urlopen(req, timeout=120)
        d = json.loads(r.read())
        content = d.get("data", d).get("choices", [{}])[0].get("message", {}).get("content", "")
        print(f"  ✓ {content}\n")
    except urllib.error.HTTPError as e:
        print(f"  ✗ {e.code}: {e.read().decode('utf-8', 'replace')[:200]}\n")
    except Exception as e:
        print(f"  ✗ {e}\n")


def run_menu(cfg):
    while True:
        print_menu()
        choice = input("  > ").strip()
        if choice == "1":
            show_status()
        elif choice == "2":
            from banner import print_banner
            print_banner(cfg)
            from server import serve
            serve(cfg)  # blocks until Ctrl-C
        elif choice == "3":
            list_models(cfg.port)
        elif choice == "4":
            test_chat(cfg.port)
        elif choice == "5":
            from auth import login
            login()
        elif choice == "6":
            print("\n  Bye!\n")
            break
        else:
            print("\n  Invalid choice. Try again.\n")


def main():
    p = argparse.ArgumentParser(description="OpenAI-compatible proxy for Cline Desktop")
    p.add_argument("--port", type=int, default=61022, help="listen port (default 61022)")
    p.add_argument("--bind", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    p.add_argument("--api-key", default=None, help="require this key on /v1/ routes")
    p.add_argument("--log", default=None, help="path to request log file")
    p.add_argument("--rate-limit", default=None, help="min interval between requests per IP (e.g. 2s)")
    p.add_argument("--desensitize", action="store_true", help="rewrite moderation triggers in prompts")
    p.add_argument("--login", action="store_true", help="run device-code OAuth login then exit")
    p.add_argument("--no-menu", action="store_true",
                   help="start server directly instead of the interactive menu")
    p.add_argument("--owned-auth", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()

    if args.login:
        from auth import login
        login()
        return

    from config import load_config
    cfg = load_config(args)
    cfg.owned_auth = args.owned_auth

    if not cfg.owned_auth:
        from auth import load_tokens
        cfg.owned_auth = load_tokens() is not None

    # Interactive menu by default (like WorkBuddy2API); --no-menu starts server directly.
    if not args.no_menu:
        run_menu(cfg)
        return

    from banner import print_banner
    print_banner(cfg)
    from server import serve
    serve(cfg)


if __name__ == "__main__":
    main()
