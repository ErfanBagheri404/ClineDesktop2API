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

Set one env var, launch Cline through the proxy:
```
set CLINE_API_BASE_URL=http://127.0.0.1:61022
"C:\Users\mrenm\AppData\Local\Cline\cline-app.exe"
```

## Files

| File | Purpose |
|---|---|
| `main.py` | CLI entry point (`--port`, `--bind`, `--api-key`, `--log`, `--rate-limit`, `--desensitize`) |
| `server.py` | HTTP server: Cline passthrough, `/v1/models`, `/v1/chat/completions`, `/v1/messages` |
| `upstream.py` | Python OpenSSL upstream client (Cloud Armor bypass) |
| `anthropic.py` | Anthropic Messages API ↔ OpenAI chat completions translation |
| `ratelimit.py` | Per-IP token-bucket rate limiter |
| `auth.py` | Cline `providers.json` credential read/write |
| `desensitize.py` | Content moderation trigger rewriting |
| `logging.py` | Request logging with credential redaction |
| `banner.py` | Startup banner |
| `config.py` | CLI config + env var overrides |
| `auth_flow.py` | WorkOS device-code auth → Cline register → inject creds |
| `start_cline.bat` | Windows launcher with `CLINE_API_BASE_URL` set |
| `tests/selfcheck.py` | Unit tests for translation + redaction + config |

## Usage

```bash
# Start proxy
python main.py --port 61022

# In another terminal, launch Cline through it
set CLINE_API_BASE_URL=http://127.0.0.1:61022
start "" "C:\Users\mrenm\AppData\Local\Cline\cline-app.exe"
```

Or use `start_cline.bat`.

## Port

Default `61022`. Override via `--port` or `CLINE_PROXY_PORT` env var.

## Auth

Cline uses **WorkOS AuthKit** device flow (`client_01K3A541FN8TA3EPPHTD2325AR`):

1. `auth_flow.py` requests device code from `api.workos.com`
2. User confirms at `authkit.cline.bot/device?user_code=XXXX-XXXX`
3. Exchanges for Cline session tokens via `api.cline.bot/api/v1/auth/register`
4. Injects into `~/.cline/data/settings/providers.json`

## Testing

```bash
python tests/selfcheck.py   # 15 checks: anthropic translation, redaction, desensitize, config
```

## Why not Go?

Go's `crypto/tls` produces a ClientHello that Cloud Armor blocks.
`refraction-networking/utls` bypasses JA3 but forces HTTP/2 (ALPN=h2 from the Chrome profile), and Go's HTTP/1.1 transport can't read h2 frames. Python is the correct TLS stack for this upstream.
