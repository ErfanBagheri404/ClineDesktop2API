#!/usr/bin/env python3
"""ClineDesktop2API — one-shot auth + launch flow."""
import json, urllib.request, ssl, time, os, shutil, sys

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def api(url, data=None, method="GET", ct="application/json"):
    kwargs = {"method": method}
    if data:
        kwargs["data"] = json.dumps(data).encode() if ct == "application/json" else urllib.parse.urlencode(data).encode()
    headers = {"Content-Type": ct}
    if ct == "application/json":
        headers = {"Content-Type": ct}
    if method != "GET":
        kwargs["headers"] = headers
    req = urllib.request.Request(url, **kwargs)
    return urllib.request.urlopen(req, timeout=30, context=ctx)

def main():
    # 1. Request device code
    import urllib.parse
    r = api("https://api.workos.com/user_management/authorize/device",
            {"client_id": "client_01K3A541FN8TA3EPPHTD2325AR"}, method="POST")
    wk = json.loads(r.read())
    print(f"OPEN: {wk['verification_uri_complete']}")
    print(f"CODE: {wk['user_code']}")
    print("Confirm in browser, then waiting...")
    sys.stdout.flush()

    # 2. Poll
    for i in range(36):
        time.sleep(5)
        try:
            r = api("https://api.workos.com/user_management/authenticate",
                    {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                     "device_code": wk["device_code"],
                     "client_id": "client_01K3A541FN8TA3EPPHTD2325AR"},
                    method="POST", ct="application/x-www-form-urlencoded")
            toks = json.loads(r.read())
            if toks.get("access_token"):
                print(f"Got tokens after {(i+1)*5}s"); break
        except urllib.error.HTTPError as e:
            body = json.loads(e.read())
            if body.get("error") == "authorization_pending":
                continue
            print(f"ERROR: {body}"); sys.exit(1)
    else:
        print("TIMEOUT"); sys.exit(1)

    # 3. Register with Cline
    reg = json.loads(api("https://api.cline.bot/api/v1/auth/register",
        {"accessToken": toks["access_token"], "refreshToken": toks["refresh_token"]},
        method="POST").read())
    print("Registered:", reg.get("data",{}).get("userInfo",{}).get("email"))

    # 4. Inject providers.json
    creds = reg["data"]
    prov_path = os.path.expanduser("~/.cline/data/settings/providers.json")
    if os.path.exists(prov_path):
        shutil.copy2(prov_path, prov_path + ".bak")
    prov = json.load(open(prov_path))
    prov["providers"]["cline"]["settings"]["auth"] = {
        "accessToken": creds["accessToken"],
        "refreshToken": creds["refreshToken"],
        "accountId": creds["userInfo"]["clineUserId"],
        "expiresAt": int(time.time()*1000) + 3600000,
    }
    prov["providers"]["cline"]["tokenSource"] = "oauth"
    with open(prov_path, "w") as f:
        json.dump(prov, f, indent=2)
    print("Injected providers.json")

    # 5. Start proxy
    os.system('start "" cmd /c "python E:\\Dev\\Projects\\ClineDesktop2API\\proxy.py"')

if __name__ == "__main__":
    main()
