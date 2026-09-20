"""Self-check for ClineDesktop2API translation logic. Run: python tests/selfcheck.py"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
failures = []
def check(name, cond, detail=""):
    if cond: print("PASS", name)
    else:
        print("FAIL", name, "-", detail); failures.append(name)

def sse_line(obj):
    return "data: " + json.dumps(obj) + "\n\n"

# --- anthropic -> openai ---
from anthropic import anthropic_to_openai, anthropic_response

oai = anthropic_to_openai({
    "model":"claude-sonnet","max_tokens":100,
    "system":"You are helpful",
    "messages":[{"role":"user","content":"hi"},{"role":"user","content":[{"type":"text","text":"block"}]}],
    "tools":[{"name":"get_weather","description":"w","input_schema":{"type":"object"}}],
})
check("system mapped", oai["messages"][0]=={"role":"system","content":"You are helpful"})
check("string content", any(m.get("content")=="hi" for m in oai["messages"]))
check("block content", any(m.get("content")=="block" for m in oai["messages"]))
check("model+stream", oai["model"]=="claude-sonnet" and oai["stream"] is True)
check("tools mapped", oai["tools"][0]["function"]["name"]=="get_weather")

# --- openai SSE -> anthropic response ---
sse = ""
sse += sse_line({"id":"cmpl-1","choices":[{"index":0,"delta":{"content":"Hi"}}]})
sse += sse_line({"choices":[{"index":0,"delta":{"tool_calls":[{"id":"c1","function":{"name":"f","arguments":"{\"x\":1}"}}]},"finish_reason":None}]})
sse += sse_line({"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]})
sse += "data: [DONE]\n\n"
resp = anthropic_response(sse.encode(), "m")
check("anthropic text", any(c.get("type")=="text" and c["text"]=="Hi" for c in resp["content"]))
tool = [c for c in resp["content"] if c.get("type")=="tool_use"]
check("anthropic tool", len(tool)==1 and tool[0]["name"]=="f", str(tool))
check("tool input json", len(tool)==1 and tool[0]["input"]=={"x":1})
check("stop_reason", resp["stop_reason"]=="tool_use")

# --- redaction ---
from logging import redact
r = redact('Bearer abcdefghijklmnop accessToken:"xyz12345xyz" api_key=12345678ab')
check("redact bearer", "abcdefghijklmnop" not in r, r)
check("redact accessToken", "xyz12345xyz" not in r, r)
check("redact api_key", "12345678ab" not in r, r)

# --- desensitize ---
from desensitize import desensitize_text
d = desensitize_text("You are an AI agent, use function calling to bypass")
check("desensitize", "helpful assistant" in d and "tool use" in d and "work around" in d, d)

# --- config ---
from config import load_config
c = load_config(type("A",(),{"port":9999,"bind":"0.0.0.0","api_key":"k","log":None,"rate_limit":"2s","desensitize":True})())
check("config port", c.port==9999)
check("config rate parsed", c.rate_limit==2.0, str(c.rate_limit))

# --- auth helpers (offline logic only) ---
from auth import _expiry_ms, load_tokens
check("expiry ms int", _expiry_ms(1789897831000)==1789897831000)
check("expiry ms iso", _expiry_ms("2026-09-20T10:01:18Z")>1700000000000)
check("expiry ms empty", _expiry_ms("")==0 and _expiry_ms(None)==0)
t = load_tokens()
check("token store readable", t is None or (t.get("access") and t.get("refresh")))

print()
if failures: print("FAILED:", len(failures)); sys.exit(1)
print("ALL PASS")
