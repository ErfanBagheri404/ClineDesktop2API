# ClineDesktop2API

Local reverse proxy that fixes Cline Desktop's **"Token registration failed: 403"** error on `api.cline.bot`.

## Problem

Cline Desktop (WebView2 + Bun sidecar `code-sidecar.exe`) sends TLS handshakes (JA3/JA4 fingerprint) that Google Cloud Armor flags as suspicious → HTTP **403 Forbidden** on `api.cline.bot`.

Python's OpenSSL TLS stack has a different fingerprint that **passes** the check.

## Solution

```
Cline sidecar (Bun TLS, flagged)           ← talks plain HTTP to localhost
   ↓ CLINE_API_BASE_URL=http://127.0.0.1:61022
proxy.py (local HTTP server, 61022)        ← re-originates with Python OpenSSL
   ↓ HTTPS
api.cline.bot                               ← 200 OK, fingerprint passes
```

## Files

| File | Purpose |
|---|---|
| `proxy.py` | Local reverse proxy: HTTP in on `127.0.0.1:61022`, HTTPS out to `api.cline.bot`. |
| `auth_flow.py` | WorkOS device-code auth → Cline `/register` → inject creds into `~/.cline/data/settings/providers.json`. |
| `start_cline.bat` | Launch Cline Desktop with `CLINE_API_BASE_URL` set. |

## Usage

```bash
# 1. start the proxy
python proxy.py

# 2. launch Cline pointed at it (set the env var)
set CLINE_API_BASE_URL=http://127.0.0.1:61022
"C:\Users\mrenm\AppData\Local\Cline\cline-app.exe"
```

## Port

Default `61022`. Override with env `CLINE_PROXY_PORT`.

## Auth

Cline uses **WorkOS AuthKit** device flow (`api.workos.com`, client `client_01K3A541FN8TA3EPPHTD2325AR`):

1. `POST /user_management/authorize/device` → device_code + `authkit.cline.bot/device?user_code=...`
2. User confirms code in browser
3. Poll `POST /user_management/authenticate` (grant_type device_code) → WorkOS access/refresh tokens
4. `POST api.cline.bot/api/v1/auth/register` with those tokens → Cline session tokens
5. Those get stored in `~/.cline/data/settings/providers.json` under `providers.cline.settings.auth`

The device-code exchange works from any network; only the Cline `/register` and API calls need the clean TLS fingerprint, which the proxy provides.

## Why not a TLS MITM?

The app is WebView2 + Bun. A `CLINE_API_BASE_URL` env override (read from `process.env`, confirmed in `code-sidecar.exe`) is the clean injection point — no CA trust, no cert scraping, no code patch.
