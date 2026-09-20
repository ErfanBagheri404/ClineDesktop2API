"""Cline auth — self-contained OAuth lifecycle.

Proxy owns the whole chain; the Cline app is just a client:
  device flow (WorkOS) -> /auth/register (api.cline.bot) -> token store -> refresh

Tokens live in ~/.cline/data/settings/providers.json so the desktop app can
also read them, but nothing here depends on the app running or being valid.
"""
import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

WORKOS_BASE = "https://api.workos.com"
WORKOS_CLIENT_ID = "client_01K3A541FN8TA3EPPHTD2325AR"
CLINE_API = "https://api.cline.bot"
PROVIDERS_PATH = os.path.expanduser("~/.cline/data/settings/providers.json")
STORE_PATH = os.path.expanduser("~/.cline/data/settings/cline_proxy_auth.json")
WORKOS_PREFIX = "workos:"
REFRESH_BUFFER_MS = 5 * 60 * 1000
UA = "Cline/0.0.32"

_CTX = ssl.create_default_context()


def _post(url, payload, form=False, timeout=30):
    if form:
        data = urllib.parse.urlencode(payload).encode()
        ctype = "application/x-www-form-urlencoded"
    else:
        data = json.dumps(payload).encode()
        ctype = "application/json"
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": ctype,
        "User-Agent": UA,
        "X-CLIENT-TYPE": "cline-desktop",
    })
    try:
        r = urllib.request.urlopen(req, timeout=timeout, context=_CTX)
        return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw.decode("utf-8", "replace")}


# ---- device flow -------------------------------------------------------

def device_start():
    """Begin WorkOS device authorization. Returns the user-facing code."""
    st, d = _post(f"{WORKOS_BASE}/user_management/authorize/device",
                  {"client_id": WORKOS_CLIENT_ID})
    if st != 200:
        raise RuntimeError(f"device authorize failed: {st} {d}")
    return d


def device_poll(device_code, interval=5, expires_in=300):
    """Poll until the user confirms in their browser. Returns WorkOS tokens."""
    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        st, d = _post(f"{WORKOS_BASE}/user_management/authenticate", {
            "client_id": WORKOS_CLIENT_ID,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
        })
        if st == 200 and d.get("access_token"):
            return d
        err = (d.get("error") or "").lower()
        if err and "authorization_pending" not in err and "slow_down" not in err:
            raise RuntimeError(f"device poll failed: {st} {d}")
    raise TimeoutError("device authorization expired")


# ---- cline registration ------------------------------------------------

def register_with_cline(workos_access, workos_refresh):
    """Exchange WorkOS tokens for a Cline account token pair."""
    st, d = _post(f"{CLINE_API}/api/v1/auth/register", {
        "accessToken": workos_access,
        "refreshToken": workos_refresh,
    })
    if st != 200 or "data" not in d:
        raise RuntimeError(f"cline register failed: {st} {d}")
    return d["data"]


def refresh_workos(refresh_token):
    st, d = _post(f"{WORKOS_BASE}/user_management/authenticate", {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": WORKOS_CLIENT_ID,
    }, form=True)
    if st != 200 or not d.get("access_token"):
        raise RuntimeError(f"workos refresh failed: {st} {d}")
    return d


# ---- token store -------------------------------------------------------

def _expiry_ms(value):
    if isinstance(value, (int, float)):
        return int(value)
    if not value:
        return 0
    try:
        return int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return 0


def load_tokens():
    """Read the proxy's own token store, falling back to providers.json."""
    for path in (STORE_PATH, PROVIDERS_PATH):
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if path == PROVIDERS_PATH:
            auth = (data.get("providers", {}).get("cline", {})
                        .get("settings", {}).get("auth"))
            if not auth:
                continue
            tok = auth.get("accessToken") or ""
            return {
                "access": tok[len(WORKOS_PREFIX):] if tok.startswith(WORKOS_PREFIX) else tok,
                "refresh": auth.get("refreshToken") or "",
                "expiresAt": auth.get("expiresAt") or 0,
                "accountId": auth.get("accountId") or "",
            }
        if data.get("accessToken"):
            return {
                "access": data["accessToken"],
                "refresh": data.get("refreshToken", ""),
                "expiresAt": _expiry_ms(data.get("expiresAt")),
                "accountId": data.get("accountId", ""),
            }
    return None


def save_tokens(tokens, mirror_to_providers=True):
    """Persist tokens; optionally mirror into providers.json for the app."""
    os.makedirs(os.path.dirname(STORE_PATH), exist_ok=True)
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)
    if mirror_to_providers and os.path.exists(PROVIDERS_PATH):
        try:
            with open(PROVIDERS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("providers", {}).setdefault("cline", {}) \
                .setdefault("settings", {})["auth"] = {
                    "accessToken": WORKOS_PREFIX + tokens["access"],
                    "refreshToken": tokens["refresh"],
                    "expiresAt": tokens["expiresAt"],
                    "accountId": tokens.get("accountId", ""),
                }
            with open(PROVIDERS_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass


# ---- main entry --------------------------------------------------------

def get_valid_token(force=False):
    """Return a live access token, refreshing when near expiry."""
    tok = load_tokens()
    if not tok or not tok.get("access"):
        return None
    if not force and tok["expiresAt"] and time.time() * 1000 < tok["expiresAt"] - REFRESH_BUFFER_MS:
        return tok["access"]
    if not tok.get("refresh"):
        return tok["access"]
    try:
        nw = refresh_workos(tok["refresh"])
        reg = register_with_cline(nw["access_token"], nw["refresh_token"])
        fresh = {
            "access": reg["accessToken"],
            "refresh": reg["refreshToken"],
            "expiresAt": _expiry_ms(reg.get("expiresAt")),
            "accountId": (reg.get("userInfo") or {}).get("id", tok.get("accountId", "")),
        }
        save_tokens(fresh)
        return fresh["access"]
    except Exception:
        return tok["access"]


def login():
    """Full interactive login. Prints the URL, blocks until confirmed."""
    d = device_start()
    url = d.get("verification_uri_complete") or d.get("verification_uri")
    print(f"\n  Open this URL and confirm:\n  {url}\n")
    print(f"  Code: {d.get('user_code')}\n")
    w = device_poll(d["device_code"], d.get("interval", 5), d.get("expires_in", 300))
    reg = register_with_cline(w["access_token"], w["refresh_token"])
    tokens = {
        "access": reg["accessToken"],
        "refresh": reg["refreshToken"],
        "expiresAt": _expiry_ms(reg.get("expiresAt")),
        "accountId": (reg.get("userInfo") or {}).get("id", ""),
    }
    save_tokens(tokens)
    print("  Logged in. Tokens stored.\n")
    return tokens


if __name__ == "__main__":
    login()
