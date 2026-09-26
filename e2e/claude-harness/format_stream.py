"""Render `claude -p --output-format stream-json --verbose` output as a readable transcript.

Usage: python format_stream.py < stream.jsonl
Shows only what the agent said and which MCP tools it called, with short results.
"""
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

calls = {}


def clip(value, n=220):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def result_text(block):
    content = block.get("content")
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
    return content if isinstance(content, str) else ""


for raw in sys.stdin:
    raw = raw.strip()
    if not raw:
        continue
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        continue
    kind = ev.get("type")
    if kind == "system" and ev.get("subtype") == "init":
        tools = ev.get("tools", [])
        builtin = [t for t in tools if not t.startswith("mcp__")]
        print(f"[init] model={ev.get('model')}  tools={len(tools)}  built-in tools={builtin or 'none'}")
        for s in ev.get("mcp_servers", []):
            print(f"[init] mcp server {s.get('name')}: {s.get('status')}")
        print()
    elif kind == "assistant":
        for b in ev["message"].get("content", []):
            if b.get("type") == "text" and b["text"].strip():
                print(f"AGENT  {b['text'].strip()}\n")
            elif b.get("type") == "tool_use":
                calls[b["id"]] = b["name"]
                print(f"CALL   {b['name'].replace('mcp__auto-browser__', '')}  {clip(b.get('input', {}), 160)}")
    elif kind == "user":
        content = ev["message"].get("content")
        if isinstance(content, list):
            for b in content:
                if b.get("type") == "tool_result":
                    name = calls.get(b.get("tool_use_id"), "?").replace("mcp__auto-browser__", "")
                    flag = "ERROR " if b.get("is_error") else ""
                    text = result_text(b)
                    if "AUTO BROWSER" in text and "watch" in text:
                        print(f"  <-   {name} {flag}(banner shown below)")
                        print("\n".join("       " + ln for ln in text.splitlines() if ln.strip()))
                    else:
                        print(f"  <-   {name} {flag}{clip(text)}")
    elif kind == "result":
        print("\n--- result ---")
        print(f"turns={ev.get('num_turns')}  duration={ev.get('duration_ms', 0) / 1000:.1f}s  cost=${ev.get('total_cost_usd', 0):.4f}  error={ev.get('is_error')}")
        if ev.get("result"):
            print(f"\nFINAL  {ev['result'].strip()}")
