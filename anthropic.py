"""Anthropic Messages API translation: Anthropic <-> OpenAI."""
import json

def anthropic_to_openai(ar):
    """Convert Anthropic /v1/messages request to OpenAI chat payload."""
    payload = {"model": ar.get("model",""), "stream": ar.get("stream",True)}
    if "max_tokens" in ar:
        payload["max_tokens"] = ar["max_tokens"]

    # system prompt
    sys = ar.get("system")
    messages = []
    if sys:
        if isinstance(sys, str):
            messages.append({"role":"system","content":sys})
        elif isinstance(sys, list):
            messages.append({"role":"system","content":"\n".join(b.get("text","") for b in sys if b.get("type")=="text")})

    for m in ar.get("messages",[]):
        role = m.get("role","user")
        content = m.get("content","")
        if isinstance(content, str):
            messages.append({"role":role,"content":content})
        elif isinstance(content, list):
            for blk in content:
                if blk.get("type") == "text":
                    messages.append({"role":role,"content":blk["text"]})
                elif blk.get("type") == "tool_use":
                    messages.append({"role":"assistant","content":None,
                        "tool_calls":[{"id":blk.get("id",""),"type":"function",
                            "function":{"name":blk["name"],"arguments":json.dumps(blk.get("input",{}))}}]})
                elif blk.get("type") == "tool_result":
                    messages.append({"role":"tool","tool_call_id":blk.get("tool_use_id",""),
                        "content": blk.get("content","") if isinstance(blk.get("content",""), str) else json.dumps(blk.get("content",""))})
    payload["messages"] = messages

    tools = ar.get("tools")
    if tools:
        payload["tools"] = [{"type":"function","function":{k:v for k,v in {
            "name":t.get("name",""),"description":t.get("description",""),
            "parameters":t.get("input_schema")
        }.items()}} for t in tools]

    return payload


def anthropic_response(rbody, model):
    """Parse upstream OpenAI SSE and assemble single Anthropic response."""
    text, tool_calls, finish, msg_id = [], [], "end_turn", ""
    for line in rbody.decode("utf-8","replace").split("\n"):
        if not line.startswith("data: ") or line[6:] == "[DONE]":
            continue
        try:
            c = json.loads(line[6:])
        except Exception:
            continue
        if c.get("id"):
            msg_id = c["id"]
        for ch in c.get("choices",[]):
            d = ch.get("delta",{})
            if d.get("content"):
                text.append(d["content"])
            for tc in d.get("tool_calls",[]):
                if tc.get("id"):
                    tool_calls.append({"id":tc["id"],"name":tc["function"].get("name",""),"input":tc["function"].get("arguments","")})
                elif tool_calls:
                    tool_calls[-1]["input"] += tc["function"].get("arguments","")
            if ch.get("finish_reason"):
                reason_map = {"tool_calls":"tool_use","length":"max_tokens"}
                finish = reason_map.get(ch["finish_reason"],"end_turn")

    content = []
    if text:
        content.append({"type":"text","text":"".join(text)})
    for i,tc in enumerate(tool_calls):
        content.append({"type":"tool_use","id":f"toolu_{i}_{msg_id}","name":tc["name"],"input":json.loads(tc["input"] or "{}")})

    return {"id":msg_id,"type":"message","role":"assistant","content":content,
            "model":model,"stop_reason":finish,"usage":{"input_tokens":1,"output_tokens":max(1,len("".join(text))//4)}}


def anthropic_stream_response(rbody, model):
    """Yield Anthropic SSE events from upstream OpenAI SSE stream."""
    text_idx = 0
    tool_idx = 0
    in_tool = False
    in_json = False

    yield _sse("message_start", {"type":"message_start","message":{
        "id":"msg_"+"x","type":"message","role":"assistant","content":[],"model":model,
        "stop_reason":None,"usage":{"input_tokens":1,"output_tokens":0}}})

    for line in rbody.decode("utf-8","replace").split("\n"):
        if not line.startswith("data: ") or line[6:] == "[DONE]":
            continue
        try:
            c = json.loads(line[6:])
        except Exception:
            continue
        for ch in c.get("choices",[]):
            d = ch.get("delta",{})
            # text
            if d.get("content"):
                if in_tool:
                    yield _sse("content_block_stop",{"type":"content_block_stop","index":text_idx})
                    text_idx += 1
                    in_tool = False
                    in_json = False
                yield _sse("content_block_delta",{"type":"content_block_delta","index":text_idx,
                    "delta":{"type":"text_delta","text":d["content"]}})
            # tool calls
            for tc in d.get("tool_calls",[]):
                if tc.get("id"):
                    if in_tool:
                        yield _sse("content_block_stop",{"type":"content_block_stop","index":text_idx})
                        text_idx += 1
                    in_tool = True
                    in_json = False
                    tool_idx = text_idx
                    yield _sse("content_block_start",{"type":"content_block_start","index":text_idx,
                        "content_block":{"type":"tool_use","id":tc["id"],"name":tc["function"].get("name",""),"input":{}}})
                args = tc["function"].get("arguments","")
                if args and in_tool:
                    if not in_json:
                        in_json = True
                    yield _sse("content_block_delta",{"type":"content_block_delta","index":tool_idx,
                        "delta":{"type":"input_json_delta","partial_json":args}})
            # finish
            if ch.get("finish_reason"):
                if in_tool:
                    yield _sse("content_block_stop",{"type":"content_block_stop","index":text_idx})
                    in_tool = False
                reason_map = {"tool_calls":"tool_use","length":"max_tokens"}
                yield _sse("message_delta",{"type":"message_delta",
                    "delta":{"stop_reason":reason_map.get(ch["finish_reason"],"end_turn")},"usage":{"output_tokens":1}})
                yield _sse("message_stop",{"type":"message_stop"})


def _sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
