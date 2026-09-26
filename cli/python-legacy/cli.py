"""Tiny SHOAV status CLI (stdlib only, synthetic fixtures not needed)."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_CONTROLLER = "http://127.0.0.1:18501"


def http_get_json(url: str, timeout: int = 15) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    data = json.loads(body) if body.strip() else {}
    return data if isinstance(data, dict) else {"value": data}


def http_post_json(url: str, payload: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    parsed = json.loads(body) if body.strip() else {}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def call_tool(controller: str, name: str, arguments: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
    url = controller.rstrip("/") + "/mcp/tools/call"
    return http_post_json(url, {"name": name, "arguments": arguments}, timeout=timeout)


def _structured_of(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        sc = response.get("structuredContent")
        if isinstance(sc, dict):
            return sc
    return {}


def _text_blocks(response: Any) -> list[str]:
    if not isinstance(response, dict):
        return []
    blocks = response.get("content")
    if not isinstance(blocks, list):
        return []
    out: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            out.append(block["text"])
    return out


def _sid_from_dict(candidate: Any) -> str | None:
    if not isinstance(candidate, dict):
        return None
    for key in ("session_id", "id", "sid"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for nested_key in ("live_view", "result", "session", "data"):
        nested = candidate.get(nested_key)
        if isinstance(nested, dict):
            for key in ("session_id", "id", "sid"):
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
            if nested_key == "result" and isinstance(nested.get("live_view"), dict):
                inner = nested["live_view"]
                for key in ("session_id", "id", "sid"):
                    value = inner.get(key)
                    if isinstance(value, str) and value.strip():
                        return value.strip()
    return None


def session_id_of(response: Any) -> str | None:
    if not isinstance(response, dict):
        return None
    # Direct gateway shape: structuredContent holds {"id": sid, "live_view": {"session_id": sid}}.
    sid = _sid_from_dict(_structured_of(response))
    if sid:
        return sid
    # JSON-RPC wrapper shape: {"result": {"structuredContent": {...}, "content": [...]}}.
    result = response.get("result")
    if isinstance(result, dict):
        sid = _sid_from_dict(result.get("structuredContent") if isinstance(result.get("structuredContent"), dict) else {})
        if sid:
            return sid
        sid = _sid_from_dict(result)
        if sid:
            return sid
        blocks = result.get("content")
        if isinstance(blocks, list):
            for block in blocks:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    try:
                        inner = json.loads(block["text"]) if block["text"].strip().startswith("{") else {}
                    except ValueError:
                        continue
                    sid = _sid_from_dict(inner)
                    if sid:
                        return sid
    # Top level fallback for flat shapes.
    sid = _sid_from_dict(response)
    if sid:
        return sid
    # Text fallback: content[0].text is a JSON dump of the summary (has "id").
    for text in _text_blocks(response):
        if not text.strip().startswith("{"):
            continue
        try:
            inner = json.loads(text)
        except ValueError:
            continue
        sid = _sid_from_dict(inner)
        if sid:
            return sid
    return None


def create_session(
    controller: str,
    start_url: str | None = None,
    timeout: int = 15,
) -> tuple[str | None, dict[str, Any]]:
    arguments: dict[str, Any] = {}
    if start_url:
        arguments["start_url"] = start_url
    response = call_tool(controller, "browser.create_session", arguments, timeout=timeout)
    return session_id_of(response), response


def guard_status(controller: str, timeout: int = 15) -> dict[str, Any]:
    url = controller.rstrip("/") + "/live-api/guard"
    return http_get_json(url, timeout=timeout)


def session_timeline(
    controller: str,
    session_id: str,
    after_seq: int = 0,
    limit: int = 100,
    timeout: int = 15,
) -> dict[str, Any]:
    query = urllib.parse.urlencode({"after_seq": after_seq, "limit": limit})
    url = "%s/live-api/sessions/%s/timeline?%s" % (
        controller.rstrip("/"),
        urllib.parse.quote(session_id, safe=""),
        query,
    )
    return http_get_json(url, timeout=timeout)


def is_guard_event(event: dict[str, Any]) -> bool:
    if not isinstance(event, dict):
        return False
    if event.get("type") == "guard":
        return True
    if event.get("event") == "verdict" and "verdict" in event:
        return True
    guard = event.get("guard")
    return isinstance(guard, dict) and bool(guard)


def filter_guard_events(
    events: list[dict[str, Any]],
    *,
    verdict: str | None = None,
    stage: str | None = None,
    mode: str | None = None,
) -> list[dict[str, Any]]:
    out = [e for e in events if is_guard_event(e)]
    if verdict is not None:
        want = verdict.strip().upper()
        out = [e for e in out if str(e.get("verdict", "")).upper() == want]
    if stage is not None:
        want = stage.strip().lower()
        out = [e for e in out if str(e.get("stage", "")).lower() == want]
    if mode is not None:
        want = mode.strip().lower()
        out = [e for e in out if str(e.get("mode", "")).lower() == want]
    return out


def format_status_human(data: dict[str, Any]) -> str:
    counters = data.get("counters") if isinstance(data.get("counters"), dict) else {}
    lines = [
        "mode: %s" % data.get("mode", "unknown"),
        "version: %s" % data.get("version", "unknown"),
        "counters: %s" % json.dumps(counters, sort_keys=True),
    ]
    return "\n".join(lines)


def format_events_human(events: list[dict[str, Any]]) -> str:
    if not events:
        return "no guard events"
    lines = []
    for e in events:
        lines.append(
            "seq=%s stage=%s verdict=%s mode=%s enforced=%s tool=%s reason=%s" % (
                e.get("seq", "?"),
                e.get("stage", "?"),
                e.get("verdict", "?"),
                e.get("mode", "?"),
                e.get("enforced", "?"),
                e.get("tool", "?"),
                str(e.get("reason", ""))[:120],
            )
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shoav", description="Tiny SHOAV guard CLI (stdlib only).")
    parser.add_argument("--controller", default=DEFAULT_CONTROLLER, help="controller base URL")
    parser.add_argument("--timeout", type=int, default=15, help="HTTP timeout seconds")
    parser.add_argument("--json", action="store_true", help="emit raw JSON")
    sub = parser.add_subparsers(dest="command", required=True)
    status_p = sub.add_parser("status", help="GET /live-api/guard and print mode/counters")
    status_p.add_argument("--json", dest="json_sub", action="store_true", help="emit raw JSON")
    events = sub.add_parser("events", help="GET session timeline filtered to guard events")
    events.add_argument("session_id", help="session id for the timeline lookup")
    events.add_argument("--after-seq", type=int, default=0)
    events.add_argument("--limit", type=int, default=100)
    events.add_argument("--verdict", default=None, help="filter e.g. BLOCK, REWRITE, ALLOW, ESCALATE")
    events.add_argument("--stage", default=None, help="filter e.g. ingress, egress")
    events.add_argument("--mode", default=None, help="filter e.g. enforce, observe")
    events.add_argument("--json", dest="json_sub", action="store_true", help="emit raw JSON")
    create_p = sub.add_parser("create-session", help="POST browser.create_session and print the sid")
    create_p.add_argument("--start-url", default=None, help="optional start URL for the new session")
    create_p.add_argument("--json", dest="json_sub", action="store_true", help="emit raw JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = bool(getattr(args, "json", False) or getattr(args, "json_sub", False))
    try:
        if args.command == "status":
            data = guard_status(args.controller, timeout=args.timeout)
            if as_json:
                print(json.dumps(data, indent=2, sort_keys=True))
            else:
                print(format_status_human(data))
            return 0
        if args.command == "create-session":
            sid, data = create_session(args.controller, start_url=args.start_url, timeout=args.timeout)
            if not sid:
                print("shoav create-session failed: no session id in response", file=sys.stderr)
                if as_json:
                    print(json.dumps({"session_id": None, "response": data}, indent=2))
                return 1
            if as_json:
                print(json.dumps({"session_id": sid, "response": data}, indent=2))
            else:
                print("session_id: %s" % sid)
            return 0
        if args.command == "events":
            data = session_timeline(
                args.controller,
                args.session_id,
                after_seq=args.after_seq,
                limit=args.limit,
                timeout=args.timeout,
            )
            events = data.get("events") if isinstance(data.get("events"), list) else []
            guards = filter_guard_events(events, verdict=args.verdict, stage=args.stage, mode=args.mode)
            if as_json:
                print(json.dumps({"session_id": args.session_id, "guard_events": guards}, indent=2))
            else:
                print(format_events_human(guards))
            return 0
    except Exception as exc:
        print("shoav %s failed: %s" % (args.command, exc), file=sys.stderr)
        return 1
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
