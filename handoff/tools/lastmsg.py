"""lastmsg.py FILE: print the last assistant text (or SubagentHandback report) in a subagent JSONL transcript."""
import json, sys
last = None
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    try:
        d = json.loads(line)
    except ValueError:
        continue
    m = d.get("message") or {}
    if d.get("type") != "assistant" or not isinstance(m.get("content"), list):
        continue
    for c in m["content"]:
        if c.get("type") == "text" and c["text"].strip():
            last = c["text"]
        elif c.get("type") == "tool_use" and "andback" in c.get("name", ""):
            last = json.dumps(c.get("input"))[:6000]
print(last)
