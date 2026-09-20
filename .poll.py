
import urllib.request, json, os
tok = os.environ["GHTOKEN"].strip()
H = {"Authorization": f"token {tok}", "Accept": "application/vnd.github+json", "User-Agent": "hermes"}
R = "https://api.github.com/repos/ErfanBagheri404/ClineDesktop2API"
req = urllib.request.Request(R + "/actions/runs?per_page=6", headers=H)
d = json.loads(urllib.request.urlopen(req, timeout=30).read())
for w in d.get("workflow_runs", []):
    print(w["name"], w["status"], w["conclusion"], w["head_sha"][:7])
