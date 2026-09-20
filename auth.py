"""Cline Desktop credential import — reads providers.json."""
import json
import os
import time
import shutil

PROVIDERS_PATH = os.path.expanduser("~/.cline/data/settings/providers.json")


def read_cline_credentials():
    """Read stored Cline credentials from providers.json."""
    if not os.path.exists(PROVIDERS_PATH):
        return None
    with open(PROVIDERS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    auth = data.get("providers",{}).get("cline",{}).get("settings",{}).get("auth")
    if not auth or not auth.get("accessToken"):
        return None
    return auth


def save_cline_credentials(creds):
    """Write Cline credentials into providers.json."""
    if not os.path.exists(PROVIDERS_PATH):
        return False
    shutil.copy2(PROVIDERS_PATH, PROVIDERS_PATH + ".bak")
    with open(PROVIDERS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data["providers"]["cline"]["settings"]["auth"] = creds
    data["providers"]["cline"]["tokenSource"] = "oauth"
    with open(PROVIDERS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return True


def refresh_workos_token(refresh_token, client_id):
    """Exchange a WorkOS refresh token for a new access+refresh pair."""
    import urllib.request, urllib.error
    import ssl
    ctx = ssl.create_default_context()
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }).encode()
    req = urllib.request.Request(
        "https://api.workos.com/user_management/authenticate",
        data=data, headers={"Content-Type":"application/x-www-form-urlencoded"},
        method="POST")
    resp = urllib.request.urlopen(req, timeout=20, context=ctx)
    return json.loads(resp.read())
