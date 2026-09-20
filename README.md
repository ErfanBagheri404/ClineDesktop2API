# ClineDesktop2API

Local reverse proxy that fixes Cline Desktop's **"Token registration failed: 403"** error on `api.cline.bot`.

## Problem

Cline Desktop (WebView2 + Bun sidecar) sends TLS handshakes that Google Cloud Armor's **JA3/JA4 fingerprinting** flags as suspicious → HTTP 403 Forbidden.

The affected stacks: Go `crypto/tls`, Windows schannel, Bun `usockets`.
The one that passes: **Python's OpenSSL** (different ClientHello fingerprint).

## Solution

```
Cline sidecar → HTTP → localhost:61022 (this proxy) → HTTPS → api.cline.bot
                         Python OpenSSL (passes JA3 check)
```

The proxy owns the entire auth lifecycle — it does NOT depend on the Cline desktop app for tokens:

1. `--login` runs a WorkOS device-flow (prints a URL for you to confirm)
2. Registers with Cline API, stores tokens
3. On every upstream request the proxy injects a fresh token
4. If the token is near expiry it automatically refreshes via WorkOS + Cline register

The Cline app just needs `baseUrl` pointing at the proxy — it can use any dummy token.

## Files

| File | Purpose |
|---|---|
| `main.py` | CLI entry point (`--port`, `--bind`, `--api-key`, `--log`, `--rate-limit`, `--desensitize`, `--login`, `--owned-auth`) |
| `server.py` | HTTP server: Cline passthrough, `/v1/models`, `/v1/chat/completions`, `/v1/messages` |
| `upstream.py` | Python OpenSSL upstream client (Cloud Armor bypass, injects proxy token with `workos:` prefix) |
| `auth.py` | Full OAuth lifecycle: device flow, register, refresh, token store |
| `anthropic.py` | Anthropic Messages API ↔ OpenAI chat completions translation |
| `ratelimit.py` | Per-IP token-bucket rate limiter |
| `desensitize.py` | Content moderation trigger rewriting |
| `logging.py` | Request logging with credential redaction |
| `banner.py` | Startup banner |
| `config.py` | CLI config + env var overrides |
| `tests/selfcheck.py` | Unit tests |

## Setup

```bash
# First time: login (opens a browser page for you to confirm)
python main.py --login

# Start proxy (auto-enables owned auth if tokens exist)
python main.py --port 61022

# Or manually force owned-auth
python main.py --port 61022 --owned-auth
```

Then in the Cline app settings or `~/.cline/data/settings/providers.json`:
```json
{ "providers": { "cline": { "settings": { "baseUrl": "http://127.0.0.1:61022" } } } }
```

## Port

Default `61022`. Override via `--port` or `CLINE_PROXY_PORT` env var.

## Auth

Cline uses **WorkOS AuthKit** device flow (`client_01K3A541FN8TA3EPPHTD2325AR`):

1. `python main.py --login` requests device code from `api.workos.com`
2. User confirms at `authkit.cline.bot/device?user_code=XXXX-XXXX`
3. WorkOS tokens exchanged → registered with Cline API (`/api/v1/auth/register`)
4. Tokens stored in `~/.cline/data/settings/cline_proxy_auth.json` (+ mirrored to `providers.json`)
5. Auto-refresh before expiry on every upstream request

## Testing

```bash
python tests/selfcheck.py   # 19 checks
```

## Why not Go?

Go's `crypto/tls` produces a ClientHello that Cloud Armor blocks.
`refraction-networking/utls` bypasses JA3 but forces HTTP/2 (ALPN=h2 from the Chrome profile), and Go's HTTP/1.1 transport can't read h2 frames. Python is the correct TLS stack for this upstream.
