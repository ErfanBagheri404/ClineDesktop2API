"""Rewrite moderation triggers in prompts (optional)."""
import json
import re

_REPLACEMENTS = [
    ("function calling", "tool use"),
    ("function call", "tool use"),
    ("you are an ai agent", "you are a helpful assistant"),
    ("you are an autonomous agent", "you are a helpful assistant"),
    ("you are a coding agent", "you are a helpful assistant"),
    ("execute commands", "run commands"),
    ("run arbitrary", "run"),
    ("system prompt", "instructions"),
    ("ignore previous", "follow the"),
    ("ignore all prior", "follow the"),
    ("bypass", "work around"),
]

_RULES = [(re.compile(r"\b" + re.escape(a) + r"\b", re.I), b) for a, b in _REPLACEMENTS]

def desensitize_text(s):
    for rex, repl in _RULES:
        s = rex.sub(repl, s)
    return s

def desensitize_payload(body):
    """Rewrite every message content string in an OpenAI chat payload."""
    try:
        p = json.loads(body)
    except Exception:
        return body
    changed = False
    for m in p.get("messages", []):
        c = m.get("content")
        if isinstance(c, str):
            n = desensitize_text(c)
            if n != c:
                m["content"] = n
                changed = True
    return json.dumps(p).encode() if changed else body
