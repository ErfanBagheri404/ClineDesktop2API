
import urllib.request, json, os
tok = os.environ["GHTOKEN"].strip()
H = {"Authorization": f"token {tok}", "Accept": "application/vnd.github+json",
     "Content-Type": "application/json", "User-Agent": "hermes"}
R = "https://api.github.com/repos/ErfanBagheri404/ClineDesktop2API"
req = urllib.request.Request(R + "/actions/runs?per_page=10", headers=H)
d = json.loads(urllib.request.urlopen(req, timeout=30).read())
for w in d.get("workflow_runs", []):
    if w["name"] == "Release" and w["status"] in ("queued", "pending", "in_progress"):
        print("cancelling", w["id"], w["status"], w["head_sha"][:7])
        rq = urllib.request.Request(f"{R}/actions/runs/{w['id']}/cancel", method="POST", headers=H)
        try:
            urllib.request.urlopen(rq, timeout=30)
            print("  cancelled")
        except urllib.error.HTTPError as e:
            print("  err", e.code, e.read()[:150])
