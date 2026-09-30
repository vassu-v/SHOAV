#!/usr/bin/env python
"""Tool surface smoke test: every advertised MCP tool, good and bad calls.

Serves e2e/fixtures/ on loopback, reads tools/list from a running SHOAV
controller, and calls every advertised tool through both transports:

  rest  POST /mcp/tools/call (tools from GET /mcp/tools)
  mcp   JSON-RPC on POST /mcp: initialize, MCP-Session-Id header,
        notifications/initialized, tools/list, tools/call

Cases per tool:
  valid      realistic arguments against a fixture page (live session when needed)
  missing    required arguments left out (n/a when the tool has none)
  wrongtype  a property given a value of the wrong JSON type
  nosession  session_id that never existed (n/a without session_id)
  closed     session_id of a session that was created and then closed
  guard      overlay click with the guard in enforce mode (execute_action, drag_drop)
  badnav     a page that does not load (execute_action navigate, create_session, fork_session)
  timeout    wait_for_selector on a selector that never appears (short timeout)

Outcomes:
  OK           isError false
  CLEAN_ERROR  isError true with a short actionable message
  BUG          HTTP 5xx, non-JSON, hang over 60s, empty or opaque message,
               traceback, internal path, raw exception class name, or a
               nonexistent session accepted as if it were real

Stdlib only. Usage (repo root):
  python e2e/tools_smoke.py --controller http://127.0.0.1:18580 --profile full --fixture-port 18650
Exit code 1 when any BUG is found.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
CALL_TIMEOUT = 60
NO_SUCH_SESSION = "smoke-no-such-session-000"

LEAK_PATTERNS = (
    (re.compile(r"Traceback \(most recent call last\)"), "traceback"),
    (re.compile(r'File "[^"]+", line \d+'), "traceback frame"),
    (re.compile(r"\b[A-Za-z]:\\\\?[A-Za-z0-9_.\-]+\\"), "windows path"),
    (re.compile(r"(?<![\w.])/(app|usr|home|tmp|opt|data)/[\w.\-/]+"), "posix path"),
    (re.compile(r"\b(KeyError|ValueError|TypeError|AttributeError|RuntimeError|IndexError|"
                r"AssertionError|NotImplementedError|FileNotFoundError|OSError|"
                r"TargetClosedError|PlaywrightError|asyncio\.)"), "exception class"),
    (re.compile(r"playwright\._impl|pydantic_core\.|site-packages"), "internal module"),
)
OPAQUE_MESSAGES = {"tool execution failed", "internal server error", "error", "tool call aborted"}

# Tools whose session_id is a list filter, so an unknown id legitimately yields an empty list.
SESSION_FILTER_TOOLS = {"browser.list_approvals", "browser.list_agent_jobs"}


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        return


@contextlib.contextmanager
def serve_fixtures(port: int):
    handler = partial(_QuietHandler, directory=str(FIXTURE_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def unused_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def canonical(name: str) -> str:
    """browser_observe -> browser.observe (first underscore after the pack prefix)."""
    if "." in name:
        return name
    for prefix in ("browser_", "harness_"):
        if name.startswith(prefix):
            return prefix[:-1] + "." + name[len(prefix):]
    return name


# ── transports ──────────────────────────────────────────────────────────────


class Raw:
    """One raw exchange: HTTP status, parsed body or None, text, elapsed, error."""

    def __init__(self, status: int, body: Any, text: str, elapsed: float, error: str | None = None):
        self.status, self.body, self.text, self.elapsed, self.error = status, body, text, elapsed, error


THROTTLED = {"count": 0}


def http(method: str, url: str, payload: Any = None, headers: dict | None = None) -> tuple[Raw, dict]:
    """One request. HTTP 429 (the controller's per-client rate limit, 120/min by default)
    is honoured like a well behaved client would: wait retry_after_seconds and retry."""
    for _attempt in range(4):
        raw, hdrs = _http_once(method, url, payload, headers)
        if raw.status != 429:
            return raw, hdrs
        THROTTLED["count"] += 1
        wait = 5.0
        if isinstance(raw.body, dict):
            with contextlib.suppress(TypeError, ValueError):
                wait = float(raw.body.get("retry_after_seconds", wait))
        time.sleep(min(max(wait, 1.0), 61.0) + 0.5)
    return raw, hdrs


def _http_once(method: str, url: str, payload: Any = None, headers: dict | None = None) -> tuple[Raw, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    hdrs = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=CALL_TIMEOUT) as resp:
            status, raw_headers, text = resp.status, dict(resp.headers), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status, raw_headers = exc.code, dict(exc.headers or {})
        text = exc.read().decode("utf-8", "replace")
    except (TimeoutError, socket.timeout):
        return Raw(0, None, "", time.perf_counter() - started, "hang"), {}
    except Exception as exc:  # connection refused and friends
        return Raw(0, None, "", time.perf_counter() - started, f"transport: {exc}"), {}
    elapsed = time.perf_counter() - started
    body = None
    if text.strip():
        try:
            body = json.loads(text)
        except ValueError:
            # SSE framing: take the last data: line
            data_lines = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")]
            if data_lines:
                try:
                    body = json.loads(data_lines[-1])
                except ValueError:
                    body = None
    return Raw(status, body, text, elapsed), raw_headers


class RestTransport:
    name = "rest"

    def __init__(self, controller: str):
        self.controller = controller

    def list_tools(self) -> list[dict]:
        raw, _ = http("GET", self.controller + "/mcp/tools")
        return raw.body or []

    def call(self, tool: str, arguments: Any) -> tuple[Raw, dict | None]:
        raw, _ = http("POST", self.controller + "/mcp/tools/call", {"name": tool, "arguments": arguments})
        return raw, (raw.body if isinstance(raw.body, dict) else None)


class McpTransport:
    name = "mcp"

    def __init__(self, controller: str):
        self.url = controller + "/mcp"
        self.headers: dict[str, str] = {}
        self._id = 0
        init, hdrs = http("POST", self.url, {
            "jsonrpc": "2.0", "id": self._next(), "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "shoav-tools-smoke", "version": "1"}},
        })
        sid = next((v for k, v in hdrs.items() if k.lower() == "mcp-session-id"), None)
        if not sid or not isinstance(init.body, dict) or "result" not in init.body:
            raise SystemExit(f"MCP initialize failed: status={init.status} body={init.text[:300]}")
        version = init.body["result"].get("protocolVersion", "2025-06-18")
        self.headers = {"MCP-Session-Id": sid, "MCP-Protocol-Version": version}
        note, _ = http("POST", self.url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, self.headers)
        if note.status not in (200, 202, 204):
            raise SystemExit(f"notifications/initialized failed: {note.status} {note.text[:200]}")

    def _next(self) -> int:
        self._id += 1
        return self._id

    def list_tools(self) -> list[dict]:
        raw, _ = http("POST", self.url, {"jsonrpc": "2.0", "id": self._next(), "method": "tools/list"}, self.headers)
        return ((raw.body or {}).get("result") or {}).get("tools") or []

    def call(self, tool: str, arguments: Any) -> tuple[Raw, dict | None]:
        raw, _ = http("POST", self.url, {
            "jsonrpc": "2.0", "id": self._next(), "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        }, self.headers)
        body = raw.body if isinstance(raw.body, dict) else None
        if body is None:
            return raw, None
        if "error" in body:
            err = body["error"] or {}
            return raw, {"isError": True, "content": [{"type": "text", "text": str(err.get("message", ""))}],
                         "_jsonrpc_error": err}
        return raw, body.get("result") if isinstance(body.get("result"), dict) else None

    def close(self) -> None:
        http("DELETE", self.url, None, self.headers)


# ── classification ──────────────────────────────────────────────────────────


def text_of(result: dict) -> str:
    return "\n".join(b.get("text", "") for b in result.get("content") or []
                     if isinstance(b, dict) and isinstance(b.get("text"), str))


def error_message(result: dict) -> str:
    text = text_of(result).strip()
    if text.startswith("{"):
        try:
            inner = json.loads(text)
            if isinstance(inner, dict):
                for key in ("error", "message", "detail"):
                    if isinstance(inner.get(key), str) and inner[key].strip():
                        return inner[key].strip()
        except ValueError:
            pass
    return text


def classify(raw: Raw, result: dict | None, *, expect_error: bool, allow_ok: bool) -> tuple[str, str]:
    if raw.error == "hang":
        return "BUG", f"hang: no reply in {CALL_TIMEOUT}s"
    if raw.error:
        return "BUG", raw.error
    if raw.status >= 500:
        return "BUG", f"HTTP {raw.status}: {raw.text[:160]}"
    if result is None:
        return "BUG", f"non-JSON or malformed reply (HTTP {raw.status}): {raw.text[:160]}"
    if raw.status >= 400 and "_jsonrpc_error" not in result:
        return "BUG", f"HTTP {raw.status} instead of an isError result: {raw.text[:160]}"
    if not result.get("isError"):
        if expect_error and not allow_ok:
            return "BUG", "accepted: expected isError true"
        return "OK", ""
    message = error_message(result)
    blob = text_of(result) + json.dumps(result.get("structuredContent"), ensure_ascii=False, default=str)
    if not message:
        return "BUG", "isError true with an empty message"
    if message.strip().lower().rstrip(".") in OPAQUE_MESSAGES:
        return "BUG", f"opaque message: {message!r}"
    if "unexpected internal error" in message.lower():
        return "BUG", f"unhandled exception behind a generic message: {message[:120]!r}"
    if len(message.split()) < 3:
        return "BUG", f"message too short to act on: {message!r}"
    for pattern, label in LEAK_PATTERNS:
        if pattern.search(blob):
            return "BUG", f"leaks {label}: {message[:160]!r}"
    return "CLEAN_ERROR", message[:160]


# ── valid arguments ─────────────────────────────────────────────────────────


class Ctx:
    def __init__(self, fixture: str, dead_url: str):
        self.fx = fixture
        self.dead = dead_url
        self.sid: str | None = None
        self.ids: dict[str, str] = {}


def page(ctx: Ctx, name: str = "benign_article.html") -> str:
    return f"{ctx.fx}/{name}"


# canonical name -> function(ctx) -> arguments. Order is the valid-phase call order.
VALID: dict[str, Callable[[Ctx], dict]] = {
    "browser.create_session": lambda c: {"start_url": page(c)},
    "browser.list_sessions": lambda c: {},
    "browser.get_session": lambda c: {"session_id": c.sid},
    "browser.observe": lambda c: {"session_id": c.sid},
    "browser.snapshot": lambda c: {"session_id": c.sid},
    "browser.screenshot": lambda c: {"session_id": c.sid},
    "browser.find_elements": lambda c: {"session_id": c.sid, "selector": "h2"},
    "browser.get_html": lambda c: {"session_id": c.sid, "text_only": True},
    "browser.wait_for_selector": lambda c: {"session_id": c.sid, "selector": "h1", "timeout_ms": 5000},
    "browser.execute_action": lambda c: {"session_id": c.sid, "action": {
        "action": "navigate", "url": page(c, "benign_wiki.html"), "reason": "smoke: open the wiki fixture"}},
    "browser.list_tabs": lambda c: {"session_id": c.sid},
    "browser.activate_tab": lambda c: {"session_id": c.sid, "index": 0},
    "browser.get_console": lambda c: {"session_id": c.sid},
    "browser.get_page_errors": lambda c: {"session_id": c.sid},
    "browser.get_request_failures": lambda c: {"session_id": c.sid},
    "browser.get_network_log": lambda c: {"session_id": c.sid},
    "browser.list_downloads": lambda c: {"session_id": c.sid},
    "browser.set_viewport": lambda c: {"session_id": c.sid, "width": 1200, "height": 800},
    "browser.get_cookies": lambda c: {"session_id": c.sid},
    "browser.set_cookies": lambda c: {"session_id": c.sid, "cookies": [
        {"name": "smoke", "value": "1", "url": c.fx + "/"}]},
    "browser.get_local_storage": lambda c: {"session_id": c.sid},
    "browser.set_local_storage": lambda c: {"session_id": c.sid, "key": "smoke", "value": "1"},
    "browser.drag_drop": lambda c: {"session_id": c.sid, "source_x": 20, "source_y": 20,
                                    "target_x": 40, "target_y": 40},
    # eval_js is governed: the first call parks an approval, approve_approval clears it,
    # and the repeat with approval_id runs the expression (see Runner.phase_valid).
    "browser.eval_js": lambda c: {"session_id": c.sid, "expression": "1 + 1", "workflow_profile": "governed",
                                  **({"approval_id": c.ids["approval"]} if "approval" in c.ids else {})},
    "browser.save_memory_profile": lambda c: {"session_id": c.sid, "profile_name": "smoke_mem",
                                              "goal_summary": "smoke"},
    "browser.get_memory_profile": lambda c: {"profile_name": "smoke_mem"},
    "browser.list_memory_profiles": lambda c: {},
    "browser.delete_memory_profile": lambda c: {"profile_name": "smoke_mem"},
    "browser.save_auth_state": lambda c: {"session_id": c.sid, "path": "smoke-state.json"},
    "browser.save_auth_profile": lambda c: {"session_id": c.sid, "profile_name": "smoke_auth"},
    "browser.list_auth_profiles": lambda c: {},
    "browser.get_auth_profile": lambda c: {"profile_name": "smoke_auth"},
    "browser.stop_trace": lambda c: {"session_id": c.sid},
    "browser.get_remote_access": lambda c: {"session_id": c.sid},
    "browser.readiness_check": lambda c: {},
    "browser.verify_witness": lambda c: {"session_id": c.sid},
    "browser.export_witness_bundle": lambda c: {"session_id": c.sid},
    "browser.export_script": lambda c: {"session_id": c.sid},
    "browser.pii_scrubber_status": lambda c: {},
    "browser.share_session": lambda c: {"session_id": c.sid},
    "browser.list_providers": lambda c: {},
    "browser.queue_agent_step": lambda c: {"session_id": c.sid, "request": {"provider": "openai", "goal": "smoke"}},
    "browser.queue_agent_run": lambda c: {"session_id": c.sid, "request": {"provider": "openai", "goal": "smoke"}},
    "browser.list_agent_jobs": lambda c: {},
    "browser.get_agent_job": lambda c: {"job_id": c.ids.get("job", "job-missing")},
    "browser.resume_agent_job": lambda c: {"job_id": c.ids.get("job", "job-missing")},
    "browser.cancel_agent_job": lambda c: {"job_id": c.ids.get("job", "job-missing")},
    "browser.discard_agent_job": lambda c: {"job_id": c.ids.get("job", "job-missing")},
    "browser.list_approvals": lambda c: {},
    "browser.approve_approval": lambda c: {"approval_id": c.ids.get("approval", "apr-smoke-missing")},
    "browser.reject_approval": lambda c: {"approval_id": c.ids.get("approval2", "apr-smoke-missing")},
    "browser.execute_approval": lambda c: {"approval_id": c.ids.get("approval", "apr-smoke-missing")},
    "browser.create_proxy_persona": lambda c: {"name": "smoke_px", "server": "http://127.0.0.1:9"},
    "browser.list_proxy_personas": lambda c: {},
    "browser.delete_proxy_persona": lambda c: {"name": "smoke_px"},
    "browser.create_cron_job": lambda c: {"name": "smoke_cron", "goal": "smoke", "schedule": "0 3 * * *",
                                          "start_url": page(c), "enabled": False},
    "browser.list_cron_jobs": lambda c: {},
    "browser.trigger_cron_job": lambda c: {"job_id": c.ids.get("cron", "cron-missing")},
    "browser.delete_cron_job": lambda c: {"job_id": c.ids.get("cron", "cron-missing")},
    "harness.start_convergence": lambda c: {"contract": {"id": "smoke", "goal": "smoke", "postconditions": [
                                                {"kind": "url_contains", "value": "benign_article"}]},
                                            "mock_final_observation": {"url": page(c), "title": "smoke"},
                                            "max_attempts": 1},
    "harness.get_status": lambda c: {"run_id": c.ids.get("run", "run-missing")},
    "harness.get_trace": lambda c: {"run_id": c.ids.get("run", "run-missing")},
    "harness.list_runs": lambda c: {},
    "harness.graduate": lambda c: {"run_id": c.ids.get("run", "run-missing")},
    "harness.list_candidates": lambda c: {},
    "harness.get_candidate": lambda c: {"skill_id": "skill-smoke-missing"},
    "harness.check_drift": lambda c: {"skill_id": "skill-smoke-missing"},
    "harness.check_all_drifts": lambda c: {},
    "browser.cdp_attach": lambda c: {"cdp_url": c.dead},
    "browser.request_human_takeover": lambda c: {"session_id": c.sid, "reason": "smoke"},
    "browser.fork_session": lambda c: {"session_id": c.sid},
    "browser.enable_shadow_browse": lambda c: {"session_id": c.sid},
    "browser.close_tab": lambda c: {"session_id": c.sid, "index": 0},
    "browser.close_session": lambda c: {"session_id": c.sid},
}


def session_case_args(tool: str, ctx: Ctx, session_id: str) -> dict:
    """Valid arguments pointed at a given session id (nonexistent or closed cases)."""
    args = dict(VALID[tool](ctx)) if tool in VALID else {}
    if tool == "harness.start_convergence":
        # with mock_final_observation the session is never touched; use the live path
        args.pop("mock_final_observation", None)
        args["workflow_profile"] = "governed"
    args["session_id"] = session_id
    return args


def find_id(result: dict | None, *keys: str) -> str | None:
    if not isinstance(result, dict):
        return None
    pools = [result.get("structuredContent")]
    text = text_of(result)
    if text.strip().startswith("{"):
        with contextlib.suppress(ValueError):
            pools.append(json.loads(text))
    for pool in pools:
        if not isinstance(pool, dict):
            continue
        for nested in (pool, pool.get("job"), pool.get("run"), pool.get("session"), pool.get("approval")):
            if isinstance(nested, dict):
                for key in keys:
                    if isinstance(nested.get(key), str) and nested[key]:
                        return nested[key]
    return None


def wrong_value(schema: dict) -> Any:
    kinds = set()
    if "type" in schema:
        kinds.add(schema["type"])
    for alt in schema.get("anyOf", []):
        if "type" in alt:
            kinds.add(alt["type"])
        if "$ref" in alt:
            kinds.add("object")
    if "$ref" in schema:
        kinds.add("object")
    if "string" in kinds:
        return 12345
    if "integer" in kinds or "number" in kinds:
        return "not-a-number"
    if "boolean" in kinds:
        return {"not": "a bool"}
    if "array" in kinds:
        return "not-a-list"
    return "not-an-object"


# ── runner ──────────────────────────────────────────────────────────────────


class Runner:
    def __init__(self, transport, tools: list[dict], ctx: Ctx):
        self.t = transport
        self.tools = {canonical(t["name"]): t for t in tools}
        self.advertised = {canonical(t["name"]): t["name"] for t in tools}
        self.ctx = ctx
        self.rows: dict[str, dict[str, tuple[str, str]]] = {n: {} for n in self.tools}
        self.opened: set[str] = set()

    def call(self, tool: str, arguments: Any) -> tuple[Raw, dict | None]:
        return self.t.call(self.advertised.get(tool, tool.replace(".", "_")), arguments)

    def record(self, tool: str, case: str, raw: Raw, result: dict | None, *,
               expect_error: bool, allow_ok: bool = True) -> None:
        verdict, detail = classify(raw, result, expect_error=expect_error, allow_ok=allow_ok)
        if raw.elapsed > 30 and verdict != "BUG":
            detail = (detail + f" (slow: {raw.elapsed:.0f}s)").strip()
        self.rows.setdefault(tool, {})[case] = (verdict, detail)

    # session helpers use REST-independent transport calls so both transports own their sessions
    def open_session(self, url: str) -> str | None:
        self.close_all()
        raw, result = self.call("browser.create_session", {"start_url": url})
        sid = find_id(result, "session_id", "id")
        if sid:
            self.opened.add(sid)
        return sid

    def close_all(self) -> None:
        # list_sessions is not advertised in the minimal profile, so also close every
        # session this runner opened itself.
        for sid in list(self.opened):
            self.call("browser.close_session", {"session_id": sid})
            self.opened.discard(sid)
        if "browser.list_sessions" not in self.tools:
            return
        raw, result = self.call("browser.list_sessions", {})
        sessions = []
        if isinstance(result, dict):
            sc = result.get("structuredContent")
            if isinstance(sc, list):
                sessions = sc
            elif isinstance(sc, dict):
                sessions = sc.get("sessions") or sc.get("items") or []
            if not sessions:
                with contextlib.suppress(ValueError):
                    parsed = json.loads(text_of(result))
                    sessions = parsed if isinstance(parsed, list) else parsed.get("sessions", [])
        for s in sessions:
            sid = s.get("id") or s.get("session_id") if isinstance(s, dict) else None
            status = str(s.get("status", "")).lower() if isinstance(s, dict) else ""
            if sid and status not in ("closed", "ended", "disconnected"):
                self.call("browser.close_session", {"session_id": sid})

    def phase_valid(self) -> None:
        c = self.ctx
        c.sid = None
        order = [n for n in VALID if n in self.tools] + [n for n in self.tools if n not in VALID]
        done: set[str] = set()
        for tool in order:
            if tool in done:
                continue
            if c.sid is None and tool != "browser.create_session":
                c.sid = self.open_session(page(c))
            if tool == "browser.eval_js":
                self.approval_flow(done)
                continue
            if tool == "browser.create_session":
                self.close_all()
            if tool == "browser.trigger_cron_job":
                # the cron run opens its own session; MAX_SESSIONS defaults to 1
                self.close_all()
                c.sid = None
            args = VALID[tool](c) if tool in VALID else {}
            raw, result = self.call(tool, args)
            self.record(tool, "valid", raw, result, expect_error=False)
            if tool == "browser.create_session":
                c.sid = find_id(result, "session_id", "id")
                if c.sid:
                    self.opened.add(c.sid)
            elif tool == "browser.queue_agent_step" and find_id(result, "job_id", "id"):
                c.ids["job"] = find_id(result, "job_id", "id")
            elif tool == "browser.create_cron_job" and find_id(result, "job_id", "id"):
                c.ids["cron"] = find_id(result, "job_id", "id")
            elif tool == "harness.start_convergence" and find_id(result, "run_id", "id"):
                c.ids["run"] = find_id(result, "run_id", "id")
            elif tool in ("browser.fork_session", "browser.enable_shadow_browse"):
                new_sid = find_id(result, "session_id", "id") if not (result or {}).get("isError") else None
                if new_sid:
                    self.opened.add(new_sid)
                self.close_all()
                c.sid = None
            elif tool in ("browser.close_session", "browser.close_tab"):
                self.close_all()
                c.sid = None
        self.close_all()

    def approval_flow(self, done: set[str]) -> None:
        """Governed eval_js: park an approval, approve it, rerun with approval_id;
        park a second and reject it; park a third, approve and execute it."""
        c = self.ctx
        base = {"session_id": c.sid, "expression": "1 + 1", "workflow_profile": "governed"}

        def park() -> str | None:
            _raw, result = self.call("browser.eval_js", dict(base))
            return find_id(result, "approval_id") or (
                ((result or {}).get("structuredContent") or {}).get("approval") or {}).get("id")

        first = park()
        if first:
            c.ids["approval"] = first
        if "browser.approve_approval" in self.tools:
            raw, result = self.call("browser.approve_approval", {"approval_id": c.ids.get("approval", "apr-missing")})
            self.record("browser.approve_approval", "valid", raw, result, expect_error=False)
            done.add("browser.approve_approval")
        raw, result = self.call("browser.eval_js", VALID["browser.eval_js"](c))
        self.record("browser.eval_js", "valid", raw, result, expect_error=False)
        done.add("browser.eval_js")
        if "browser.reject_approval" in self.tools:
            second = park()
            if second:
                c.ids["approval2"] = second
            raw, result = self.call("browser.reject_approval", VALID["browser.reject_approval"](c))
            self.record("browser.reject_approval", "valid", raw, result, expect_error=False)
            done.add("browser.reject_approval")
        if "browser.execute_approval" in self.tools and "browser.approve_approval" in self.tools:
            # execute_approval runs a parked browser action, so park one with a governed
            # execute_action (a write-class click) rather than a governed tool call.
            _raw, parked = self.call("browser.execute_action", {
                "session_id": c.sid, "workflow_profile": "governed",
                "action": {"action": "click", "selector": "h1", "risk_category": "write",
                           "reason": "smoke: governed click"}})
            third = (((parked or {}).get("structuredContent") or {}).get("approval") or {}).get("id")
            if third:
                c.ids["approval"] = third
                self.call("browser.approve_approval", {"approval_id": third})
            raw, result = self.call("browser.execute_approval", VALID["browser.execute_approval"](c))
            self.record("browser.execute_approval", "valid", raw, result, expect_error=False)
            done.add("browser.execute_approval")

    def phase_bad_args(self) -> None:
        for tool, spec in self.tools.items():
            schema = spec.get("inputSchema") or {}
            props = schema.get("properties") or {}
            required = [r for r in schema.get("required") or []]
            if required:
                raw, result = self.call(tool, {})
                self.record(tool, "missing", raw, result, expect_error=True, allow_ok=False)
            else:
                self.rows[tool]["missing"] = ("n/a", "no required arguments")
            target = next((r for r in required), None) or next((p for p in props if p != "session_id"), None) \
                or ("session_id" if "session_id" in props else None)
            if target:
                raw, result = self.call(tool, {target: wrong_value(props[target])})
                self.record(tool, "wrongtype", raw, result, expect_error=True, allow_ok=False)
            else:
                raw, result = self.call(tool, ["not", "an", "object"])
                self.record(tool, "wrongtype", raw, result, expect_error=True, allow_ok=True)
            if "session_id" in props:
                args = session_case_args(tool, self.ctx, NO_SUCH_SESSION)
                raw, result = self.call(tool, args)
                self.record(tool, "nosession", raw, result, expect_error=True,
                            allow_ok=tool in SESSION_FILTER_TOOLS)
            else:
                self.rows[tool]["nosession"] = ("n/a", "no session_id argument")

    def phase_closed(self) -> None:
        c = self.ctx
        sid = self.open_session(page(c))
        if not sid:
            for tool in self.tools:
                self.rows[tool]["closed"] = ("BUG", "could not create a session for the closed-session case")
            return
        self.call("browser.close_session", {"session_id": sid})
        for tool, spec in self.tools.items():
            props = (spec.get("inputSchema") or {}).get("properties") or {}
            if "session_id" not in props:
                self.rows[tool]["closed"] = ("n/a", "no session_id argument")
                continue
            args = session_case_args(tool, c, sid)
            raw, result = self.call(tool, args)
            self.record(tool, "closed", raw, result, expect_error=True, allow_ok=True)
        self.close_all()

    def phase_edge(self) -> None:
        c = self.ctx
        click = {"action": "click", "selector": "#buy-btn", "reason": "smoke: click Buy now"}
        if "browser.execute_action" in self.tools:
            sid = self.open_session(page(c, "overlay.html"))
            raw, result = self.call("browser.execute_action", {"session_id": sid, "action": click})
            self.record("browser.execute_action", "guard", raw, result, expect_error=True, allow_ok=True)
            raw, result = self.call("browser.execute_action", {"session_id": sid, "action": {
                "action": "navigate", "url": c.dead + "/nope", "reason": "smoke: dead page"}})
            self.record("browser.execute_action", "badnav", raw, result, expect_error=True, allow_ok=False)
        if "browser.execute_action" in self.tools:
            # A value typed with sensitive=true must never come back in a later result.
            secret = "SmokeSecret-7731"
            sid = self.open_session(page(c, "benign_login.html"))
            raw, result = self.call("browser.execute_action", {"session_id": sid, "action": {
                "action": "type", "selector": "#username", "text": secret, "sensitive": True,
                "reason": "smoke: sensitive type"}})
            leaks = [] if secret not in json.dumps(result or {}) else ["type result"]
            followups = [("browser.execute_action", {"session_id": sid, "action": {
                "action": "scroll", "delta_y": 100, "reason": "smoke: next action"}}),
                ("browser.observe", {"session_id": sid}), ("browser.snapshot", {"session_id": sid}),
                ("browser.find_elements", {"session_id": sid, "selector": "input"})]
            for tool, args in followups:
                if tool in self.tools:
                    _r, res = self.call(tool, args)
                    if secret in json.dumps(res or {}):
                        leaks.append(tool)
            if leaks:
                self.rows["browser.execute_action"]["sensitive"] = ("BUG", "sensitive value echoed by " + ", ".join(leaks))
            else:
                self.record("browser.execute_action", "sensitive", raw, result, expect_error=False)
        if "browser.drag_drop" in self.tools:
            sid = self.open_session(page(c, "overlay.html"))
            raw, result = self.call("browser.drag_drop", {"session_id": sid, "source_selector": "#buy-btn",
                                                          "target_selector": "#result"})
            self.record("browser.drag_drop", "guard", raw, result, expect_error=True, allow_ok=True)
        if "browser.wait_for_selector" in self.tools:
            sid = self.open_session(page(c))
            raw, result = self.call("browser.wait_for_selector", {"session_id": sid, "selector": "#never-there",
                                                                  "timeout_ms": 1500})
            self.record("browser.wait_for_selector", "timeout", raw, result, expect_error=True, allow_ok=False)
        if "browser.fork_session" in self.tools:
            sid = self.open_session(page(c))
            raw, result = self.call("browser.fork_session", {"session_id": sid, "start_url": c.dead + "/nope"})
            self.record("browser.fork_session", "badnav", raw, result, expect_error=True, allow_ok=True)
        if "browser.create_session" in self.tools:
            self.close_all()
            raw, result = self.call("browser.create_session", {"start_url": c.dead + "/nope"})
            self.record("browser.create_session", "badnav", raw, result, expect_error=True, allow_ok=False)
        self.close_all()

    def run(self) -> None:
        self.phase_valid()
        self.phase_bad_args()
        self.phase_closed()
        self.phase_edge()


CASES = ("valid", "missing", "wrongtype", "nosession", "closed", "guard", "badnav", "timeout", "sensitive")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--controller", default="http://127.0.0.1:18580")
    parser.add_argument("--profile", default="curated", choices=("minimal", "curated", "full"),
                        help="profile the controller was started with (checked against tools/list size)")
    parser.add_argument("--fixture-port", type=int, default=18650)
    parser.add_argument("--transport", default="both", choices=("rest", "mcp", "both"))
    parser.add_argument("--json-out", help="write every row as JSON to this path")
    args = parser.parse_args()

    expected_counts = {"minimal": 10, "curated": 37, "full": 74}
    all_bugs = 0
    report: dict[str, Any] = {"profile": args.profile, "transports": {}}
    with serve_fixtures(args.fixture_port) as fixture:
        dead = f"http://127.0.0.1:{unused_port()}"
        transports = ["rest", "mcp"] if args.transport == "both" else [args.transport]
        for name in transports:
            t = RestTransport(args.controller) if name == "rest" else McpTransport(args.controller)
            tools = t.list_tools()
            count_note = f"{len(tools)} tools (profile {args.profile} expects {expected_counts[args.profile]})"
            print(f"== {name}: {count_note}")
            runner = Runner(t, tools, Ctx(fixture, dead))
            started = time.perf_counter()
            runner.run()
            if isinstance(t, McpTransport):
                t.close()
            totals: dict[str, int] = {}
            for tool in sorted(runner.rows):
                cells = runner.rows[tool]
                for case in CASES:
                    if case in cells:
                        totals[cells[case][0]] = totals.get(cells[case][0], 0) + 1
                line = "  ".join(f"{case}={cells[case][0]}" for case in CASES if case in cells)
                print(f"{runner.advertised.get(tool, tool):32s} {line}")
                for case in CASES:
                    if case in cells and cells[case][0] == "BUG":
                        print(f"    BUG {case}: {cells[case][1]}")
            bugs = totals.get("BUG", 0)
            all_bugs += bugs
            print(f"-- {name} totals: {totals} in {time.perf_counter() - started:.0f}s\n")
            report["transports"][name] = {
                "tool_count": len(tools),
                "totals": totals,
                "rows": {runner.advertised.get(k, k): v for k, v in runner.rows.items()},
            }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(f"rate limited (HTTP 429, waited and retried): {THROTTLED['count']} times")
    print("RESULT:", "PASS (no bugs)" if all_bugs == 0 else f"FAIL ({all_bugs} bug rows)")
    return 1 if all_bugs else 0


if __name__ == "__main__":
    sys.exit(main())
