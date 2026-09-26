from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app import events as events_module
from app.action_errors import BrowserActionError
from app.approvals import ApprovalRequiredError
from app.live import LiveViewService, build_banner, classify_phase, redact_args, truncate_value, valid_session_id
from app.live import recorder as recorder_module
from app.live.calls import current_mcp_client
from app.live.phases import PHASES, redact_result
from app.mcp_transport import MCP_INSTRUCTIONS
from app.models import McpToolCallRequest
from app.routes.live_api import create_live_api_router, install_live_cors
from app.routes.session_diagnostics import _sse_frame
from app.tool_gateway import McpToolGateway

SID = "a5af842a89e1"

# Tools that intentionally fall in the catch-all `other` phase. A new tool must be added
# to a phase table in app/live/phases.py or (consciously) to this list.
EXPECTED_OTHER = {
    "browser.approve_approval",
    "browser.cancel_agent_job",
    "browser.cdp_attach",
    "browser.create_cron_job",
    "browser.create_proxy_persona",
    "browser.delete_cron_job",
    "browser.delete_memory_profile",
    "browser.delete_proxy_persona",
    "browser.discard_agent_job",
    "browser.enable_shadow_browse",
    "browser.execute_approval",
    "browser.export_script",
    "browser.export_witness_bundle",
    "browser.find_by_vision",
    "browser.get_agent_job",
    "browser.get_auth_profile",
    "browser.get_cookies",
    "browser.get_local_storage",
    "browser.get_memory_profile",
    "browser.get_remote_access",
    "browser.list_agent_jobs",
    "browser.list_approvals",
    "browser.list_auth_profiles",
    "browser.list_cron_jobs",
    "browser.list_memory_profiles",
    "browser.list_providers",
    "browser.list_proxy_personas",
    "browser.pii_scrubber_status",
    "browser.queue_agent_run",
    "browser.queue_agent_step",
    "browser.readiness_check",
    "browser.reject_approval",
    "browser.resume_agent_job",
    "browser.save_auth_profile",
    "browser.save_auth_state",
    "browser.save_memory_profile",
    "browser.set_cookies",
    "browser.set_local_storage",
    "browser.share_session",
    "browser.stop_trace",
    "browser.trigger_cron_job",
    "browser.verify_witness",
    "harness.check_all_drifts",
    "harness.check_drift",
    "harness.get_candidate",
    "harness.get_status",
    "harness.get_trace",
    "harness.graduate",
    "harness.list_candidates",
    "harness.list_runs",
    "harness.start_convergence",
}


def _full_gateway() -> McpToolGateway:
    return McpToolGateway(
        manager=SimpleNamespace(),
        orchestrator=None,
        job_queue=None,
        tool_profile="full",
        vision_targeter=object(),
    )


class PhaseTests(unittest.TestCase):
    def test_every_registered_tool_maps_to_a_known_phase(self) -> None:
        gateway = _full_gateway()
        others = set()
        for name in gateway._registry.tools:
            phase = classify_phase(name, {})
            self.assertIn(phase, PHASES, name)
            if phase == "other":
                others.add(name)
        self.assertEqual(others, EXPECTED_OTHER)

    def test_contract_table(self) -> None:
        self.assertEqual(classify_phase("browser.create_session"), "session")
        self.assertEqual(classify_phase("browser.close_tab"), "session")
        self.assertEqual(classify_phase("browser.screenshot"), "screenshot")
        self.assertEqual(classify_phase("browser.get_html"), "read")
        self.assertEqual(classify_phase("browser.wait_for_selector"), "read")
        self.assertEqual(classify_phase("browser.execute_action"), "act")
        self.assertEqual(classify_phase("browser.eval_js"), "act")
        self.assertEqual(classify_phase("browser.request_human_takeover"), "act")
        self.assertEqual(classify_phase("something.unknown"), "other")

    def test_observe_phase_depends_on_preset(self) -> None:
        self.assertEqual(classify_phase("browser.observe", {"preset": "text"}), "read")
        self.assertEqual(classify_phase("browser.observe", {}), "screenshot")
        self.assertEqual(classify_phase("browser.observe", {"preset": "rich"}), "screenshot")


class RedactionTests(unittest.TestCase):
    def test_sensitive_keys_are_redacted_case_insensitively(self) -> None:
        out = redact_args(
            "browser.create_session",
            {
                "proxy_password": "hunter2",
                "totp_secret": "JBSWY3DP",
                "Authorization": "Bearer x",
                "api-key": "k",
                "start_url": "https://example.com",
            },
        )
        self.assertEqual(out["proxy_password"], "[redacted]")
        self.assertEqual(out["totp_secret"], "[redacted]")
        self.assertEqual(out["Authorization"], "[redacted]")
        self.assertEqual(out["api-key"], "[redacted]")
        self.assertEqual(out["start_url"], "https://example.com")

    def test_sensitive_action_text_is_redacted(self) -> None:
        args = {"session_id": SID, "action": {"action": "type", "text": "s3cret", "sensitive": True, "reason": "login"}}
        out = redact_args("browser.execute_action", args)
        self.assertEqual(out["action"]["text"], "[redacted]")
        self.assertEqual(out["action"]["reason"], "login")
        plain = {"action": {"action": "type", "text": "hello", "reason": "search"}}
        self.assertEqual(redact_args("browser.execute_action", plain)["action"]["text"], "hello")

    def test_special_tools_are_replaced_by_descriptions(self) -> None:
        self.assertEqual(
            redact_args("browser.eval_js", {"session_id": SID, "expression": "document.cookie"}),
            {"session_id": SID, "redacted": True, "expression_length": 15},
        )
        self.assertEqual(
            redact_args("browser.set_cookies", {"session_id": SID, "cookies": [{"name": "a"}] * 3}),
            {"session_id": SID, "redacted": True, "keys": 3},
        )
        self.assertNotIn("v", json.dumps(redact_args("browser.set_local_storage", {"key": "k", "value": "v"})))
        self.assertEqual(redact_result("browser.get_cookies", {"cookies": [{"value": "x"}]}), {"redacted": True})

    def test_result_drops_internal_noise(self) -> None:
        out = redact_result("browser.observe", {"url": "u", "session": {"id": "x", "remote_access": {"a": 1}}})
        self.assertNotIn("remote_access", out["session"])


class TruncationTests(unittest.TestCase):
    def test_long_strings_are_cut_at_500(self) -> None:
        out = truncate_value({"a": "x" * 2000})
        self.assertTrue(out["a"].endswith("...[truncated]"))
        self.assertEqual(len(out["a"]), 500 + len("...[truncated]"))

    def test_whole_value_stays_under_budget_and_valid_json(self) -> None:
        big = {"items": [{"text": "y" * 400, "n": i} for i in range(200)]}
        out = truncate_value(big)
        self.assertLessEqual(len(json.dumps(out)), 4000 + 100)
        json.dumps(out)

    def test_non_serialisable_values_do_not_raise(self) -> None:
        cyc: dict = {}
        cyc["self"] = cyc
        out = truncate_value({"b": b"abc", "s": {1, 2}, "p": Path("/x"), "o": object(), "cyc": cyc, "f": float("nan")})
        json.dumps(out)
        self.assertEqual(out["b"], "[3 bytes]")

    def test_small_values_pass_through(self) -> None:
        self.assertEqual(truncate_value({"a": [1, "b", None]}), {"a": [1, "b", None]})


class BannerTests(unittest.TestCase):
    def test_banner_is_60_columns_without_ansi(self) -> None:
        banner = build_banner(SID, f"http://127.0.0.1:3100/s/{SID}")
        lines = banner.split("\n")
        self.assertEqual(len(lines), 5)
        self.assertTrue(all(len(line) == 60 for line in lines), lines)
        self.assertNotIn("\x1b", banner)
        self.assertIn(f"session  {SID}", lines[2])
        self.assertIn(f"watch    http://127.0.0.1:3100/s/{SID}", lines[3])
        self.assertTrue(lines[0].startswith("┌") and lines[4].startswith("└"))

    def test_long_url_overflows_intact_instead_of_being_cut(self) -> None:
        url = "https://very-long-hostname.example.internal.example.com/prefix/path/s/" + SID
        lines = build_banner(SID, url).split("\n")
        self.assertIn(url, lines[3])
        self.assertTrue(lines[3].endswith(url))
        self.assertEqual([len(lines[i]) for i in (0, 1, 2, 4)], [60] * 4)


class RecorderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = SimpleNamespace(
            artifact_root=self.tmp.name, live_ui_base_url="http://127.0.0.1:3100", live_banner_color=False
        )
        self.svc = LiveViewService(self.settings)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_seq_is_monotonic_under_concurrency(self) -> None:
        results = await asyncio.gather(*(self.svc.record(SID, {"event": "start", "n": i}) for i in range(60)))
        seqs = sorted(r["seq"] for r in results)
        self.assertEqual(seqs, list(range(1, 61)))
        lines = (Path(self.tmp.name) / SID / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual([json.loads(line)["seq"] for line in lines], list(range(1, 61)))

    async def test_timeline_persists_and_reloads_after_restart(self) -> None:
        await self.svc.register_session(SID, name="n", start_url="https://example.com")
        for _ in range(3):
            await self.svc.record(SID, {"event": "start"})
        fresh = LiveViewService(self.settings)  # simulates a controller restart
        events, last, _ = await fresh.timeline(SID, 0)
        self.assertEqual((len(events), last), (3, 3))
        nxt = await fresh.record(SID, {"event": "end"})
        self.assertEqual(nxt["seq"], 4)
        events, last, _ = await fresh.timeline(SID, 2)
        self.assertEqual([e["seq"] for e in events], [3, 4])
        summary = await fresh.get_summary(SID)
        self.assertEqual(summary["start_url"], "https://example.com")

    async def test_events_are_published_on_the_sse_bus_with_seq(self) -> None:
        queue = events_module.subscribe(SID)
        try:
            await self.svc.record(SID, {"event": "start", "tool": "browser.observe"})
            payload = queue.get_nowait()
        finally:
            events_module.unsubscribe(SID, queue)
        event = json.loads(payload)
        self.assertEqual((event["type"], event["seq"], event["session_id"]), ("tool", 1, SID))
        self.assertTrue(_sse_frame(payload).startswith("id: 1\ndata: {"))
        self.assertEqual(_sse_frame('{"event":"observe"}'), 'data: {"event":"observe"}\n\n')
        self.assertNotIn(SID, events_module._SESSION_QUEUES)  # no subscriber leak

    async def test_invalid_session_ids_never_touch_disk(self) -> None:
        for bad in ("../evil", "a/b", "..", "a.b", "", "x" * 200, "..\\evil"):
            self.assertFalse(valid_session_id(bad), bad)
            self.assertIsNone(await self.svc.record(bad, {"event": "start"}))
            self.assertEqual(await self.svc.timeline(bad), ([], 0, False))
            self.assertIsNone(await self.svc.get_summary(bad))
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    async def test_timeline_is_capped_with_a_note(self) -> None:
        with patch.object(recorder_module, "MAX_PERSISTED_EVENTS", 5):
            for _ in range(8):
                await self.svc.record(SID, {"event": "start"})
        lines = (Path(self.tmp.name) / SID / "timeline.jsonl").read_text(encoding="utf-8").splitlines()
        parsed = [json.loads(line) for line in lines]
        self.assertEqual(len(parsed), 6)  # 5 events + the cap note
        self.assertEqual(parsed[-1]["type"], "note")
        events, last, _ = await self.svc.timeline(SID, 0)  # live tail still has everything
        self.assertEqual(last, 9)

    async def test_record_failure_never_raises(self) -> None:
        with patch.object(LiveViewService, "_append_line", side_effect=OSError("disk full")):
            event = await self.svc.record(SID, {"event": "start"})
        self.assertEqual(event["seq"], 1)

    async def test_archive_stale_marks_live_summaries_without_a_browser(self) -> None:
        await self.svc.register_session(SID)
        await self.svc.register_session("bbbbbbbbbbbb")
        fresh = LiveViewService(self.settings)
        count = await fresh.archive_stale({"bbbbbbbbbbbb"})
        self.assertEqual(count, 1)
        self.assertEqual((await fresh.get_summary(SID))["state"], "archived")
        self.assertEqual((await fresh.get_summary("bbbbbbbbbbbb"))["state"], "live")
        events, _, _ = await fresh.timeline(SID)
        self.assertEqual(events[-1]["event"], "archived")


async def _session_record(session_id: str) -> dict:
    if session_id != SID:
        raise KeyError(session_id)
    return {"id": SID, "name": "adopted", "created_at": "2026-01-01T00:00:00Z", "current_url": "https://example.com/"}


def _make_gateway(live_view, *, sessions=None, created=None):
    manager = SimpleNamespace(
        sessions={item["id"]: object() for item in (sessions or []) if item.get("live", True) is not False},
        list_sessions=AsyncMock(return_value=sessions if sessions is not None else []),
        create_session=AsyncMock(return_value=created or {"id": SID}),
        observe=AsyncMock(
            return_value={
                "url": "https://example.com/",
                "title": "Example",
                "screenshot_url": f"/artifacts/{SID}/a.png",
                "session": {"id": SID, "current_url": "https://example.com/", "title": "Example"},
            }
        ),
        execute_decision=AsyncMock(return_value={"action": "click", "after": {"url": "https://iana.org/x"}}),
        close_session=AsyncMock(return_value={"closed": True, "session": {"id": SID}}),
        get_session_record=AsyncMock(side_effect=_session_record),
        require_governed_approval=AsyncMock(return_value=None),
        settings=SimpleNamespace(),
    )
    gateway = McpToolGateway(
        manager=manager, orchestrator=None, job_queue=None, tool_profile="full", live_view=live_view
    )
    return gateway, manager


class GatewayLiveViewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = SimpleNamespace(
            artifact_root=self.tmp.name, live_ui_base_url="http://127.0.0.1:3100", live_banner_color=False
        )
        self.svc = LiveViewService(self.settings)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def _events(self, sid=SID):
        events, _, _ = await self.svc.timeline(sid)
        return events

    async def test_explicit_create_session_returns_banner_and_records_events(self) -> None:
        created = {"id": SID, "name": "s", "created_at": "2026-01-01T00:00:00Z", "current_url": "https://example.com/"}
        gateway, _ = _make_gateway(self.svc, created=created)
        token = current_mcp_client.set("claude-code")
        try:
            response = await gateway.call_tool(
                McpToolCallRequest(name="browser.create_session", arguments={"start_url": "https://example.com/"})
            )
        finally:
            current_mcp_client.reset(token)
        self.assertFalse(response.isError)
        block = response.structuredContent["live_view"]
        self.assertEqual(block["session_id"], SID)
        self.assertEqual(block["url"], f"http://127.0.0.1:3100/s/{SID}")
        self.assertEqual(response.content[-1].text, block["banner"])
        self.assertIn(f"watch    http://127.0.0.1:3100/s/{SID}", block["banner"])
        first = json.loads(response.content[0].text)
        self.assertEqual(first["id"], SID)
        self.assertEqual(list(first)[:2], ["_notice", "live_view"])  # first keys of block 0
        self.assertEqual(first["live_view"], block)
        self.assertIn("banner", first["_notice"])
        events = await self._events()
        self.assertEqual([(e["event"], e["seq"]) for e in events], [("start", 1), ("end", 2)])
        self.assertEqual(events[0]["call_id"], events[1]["call_id"])
        self.assertEqual(events[0]["phase"], "session")
        self.assertEqual(events[1]["status"], "ok")
        self.assertEqual(events[1]["client"], "claude-code")
        summary = await self.svc.get_summary(SID)
        self.assertEqual(summary["start_url"], "https://example.com/")
        self.assertEqual(summary["tool_calls"], 1)

    async def test_implicit_session_creation_carries_banner_on_the_observe_result(self) -> None:
        gateway, manager = _make_gateway(self.svc)
        response = await gateway.call_tool(McpToolCallRequest(name="browser.observe", arguments={"preset": "text"}))
        self.assertFalse(response.isError)
        manager.create_session.assert_awaited_once()
        self.assertEqual(response.structuredContent["live_view"]["session_id"], SID)
        self.assertEqual(len(response.content), 2)
        self.assertIn("AUTO BROWSER  live view", response.content[1].text)
        self.assertEqual(list(json.loads(response.content[0].text))[:2], ["_notice", "live_view"])
        events = await self._events()
        self.assertEqual([e["event"] for e in events], ["start", "end"])
        self.assertEqual(events[0]["phase"], "read")  # preset=text
        self.assertEqual(events[1]["screenshot_url"], f"/artifacts/{SID}/a.png")
        # A second call reuses the session and gets no banner.
        gateway2, _ = _make_gateway(self.svc, sessions=[{"id": SID}])
        again = await gateway2.call_tool(McpToolCallRequest(name="browser.observe", arguments={}))
        self.assertNotIn("live_view", again.structuredContent)
        self.assertNotIn("live_view", again.content[0].text)
        self.assertNotIn("_notice", again.structuredContent)
        self.assertEqual(len(again.content), 1)
        self.assertEqual((await self._events())[2]["phase"], "screenshot")

    async def test_underscore_tool_names_are_recorded_under_the_canonical_name_and_phase(self) -> None:
        # Gemini-based clients (agy) call browser_observe; it must be the same tool, same phase.
        gateway, _ = _make_gateway(self.svc, sessions=[{"id": SID}])
        response = await gateway.call_tool(McpToolCallRequest(name="browser_observe", arguments={"preset": "text"}))
        self.assertFalse(response.isError)
        events = await self._events()
        self.assertEqual({e["tool"] for e in events}, {"browser.observe"})
        self.assertEqual(events[0]["phase"], "read")

    async def test_implicit_resolution_ignores_stored_dead_sessions(self) -> None:
        dead = [{"id": "dead00000000", "live": False, "status": "closed"}]
        gateway, manager = _make_gateway(self.svc, sessions=dead)
        response = await gateway.call_tool(McpToolCallRequest(name="browser.observe", arguments={}))
        self.assertFalse(response.isError)
        manager.create_session.assert_awaited_once()
        gateway2, manager2 = _make_gateway(self.svc, sessions=[*dead, {"id": SID, "live": True}])
        await gateway2.call_tool(McpToolCallRequest(name="browser.observe", arguments={}))
        manager2.create_session.assert_not_awaited()
        manager2.observe.assert_awaited_once()

    async def test_banner_printed_once_to_console(self) -> None:
        gateway, _ = _make_gateway(self.svc, sessions=[])
        with patch.object(LiveViewService, "print_banner") as printer:
            await gateway.call_tool(McpToolCallRequest(name="browser.observe", arguments={}))
            gateway2, _ = _make_gateway(self.svc, sessions=[{"id": SID}])
            await gateway2.call_tool(McpToolCallRequest(name="browser.observe", arguments={}))
        printer.assert_called_once_with(SID)

    async def test_execute_action_is_redacted_and_summarised(self) -> None:
        gateway, _ = _make_gateway(self.svc, sessions=[{"id": SID}])
        await gateway.call_tool(McpToolCallRequest(name="browser.observe", arguments={}))
        await gateway.call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={
                    "action": {"action": "type", "selector": "#q", "text": "pw", "sensitive": True, "reason": "r"}
                },
            )
        )
        events = await self._events()
        start = [e for e in events if e["event"] == "start" and e["tool"] == "browser.execute_action"][0]
        self.assertEqual(start["session_id"], SID)  # resolved from the implicit session
        self.assertEqual(start["args"]["action"]["text"], "[redacted]")
        self.assertEqual(start["phase"], "act")
        end = events[-1]
        self.assertIn("click ok", end["result_summary"])

    async def test_errors_produce_an_end_event_with_error_status(self) -> None:
        cases = [
            (ApprovalRequiredError.__new__(ApprovalRequiredError), "approval"),
            (BrowserActionError("nope", code="boom", action="x"), "nope"),
            (RuntimeError("kaput"), "kaput"),
            (Exception("hidden"), "Tool execution failed"),
        ]
        await self.svc.register_session(SID)
        for exc, expected in cases:
            with self.subTest(expected=expected):
                gateway, manager = _make_gateway(self.svc, sessions=[{"id": SID}])
                if isinstance(exc, ApprovalRequiredError):
                    exc.payload = {"error": "approval", "approval_id": "a1"}
                manager.observe = AsyncMock(side_effect=exc)
                response = await gateway.call_tool(
                    McpToolCallRequest(name="browser.observe", arguments={"session_id": SID})
                )
                self.assertTrue(response.isError)
                events = await self._events()
                self.assertEqual(events[-1]["event"], "end")
                self.assertEqual(events[-1]["status"], "error")
                self.assertIn(expected, events[-1]["result_summary"])
                self.assertNotIn("screenshot_url", events[-1])

    async def test_validation_error_on_known_session_is_recorded(self) -> None:
        await self.svc.register_session(SID)
        gateway, _ = _make_gateway(self.svc, sessions=[{"id": SID}])
        response = await gateway.call_tool(
            McpToolCallRequest(name="browser.observe", arguments={"session_id": SID, "limit": 9999})
        )
        self.assertTrue(response.isError)
        events = await self._events()
        self.assertEqual([e["event"] for e in events], ["start", "end"])
        self.assertEqual(events[1]["status"], "error")

    async def test_unknown_session_and_sessionless_calls_are_not_recorded(self) -> None:
        gateway, _ = _make_gateway(self.svc, sessions=[{"id": SID}])
        await gateway.call_tool(McpToolCallRequest(name="browser.list_sessions", arguments={}))
        await gateway.call_tool(
            McpToolCallRequest(name="browser.observe", arguments={"session_id": "deadbeef0000", "limit": 0})
        )
        await gateway.call_tool(McpToolCallRequest(name="nope.nothing", arguments={}))
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    async def test_close_session_archives_the_summary(self) -> None:
        gateway, _ = _make_gateway(self.svc, sessions=[])
        await gateway.call_tool(McpToolCallRequest(name="browser.observe", arguments={}))
        gateway2, _ = _make_gateway(self.svc, sessions=[{"id": SID}])
        await gateway2.call_tool(McpToolCallRequest(name="browser.close_session", arguments={}))
        summary = await self.svc.get_summary(SID)
        self.assertEqual(summary["state"], "archived")
        self.assertIsNotNone(summary["closed_at"])
        events = await self._events()
        self.assertEqual(events[-1]["tool"], "browser.close_session")

    async def test_two_clients_calling_concurrently_get_gapless_seq(self) -> None:
        await self.svc.register_session(SID)
        gateway, _ = _make_gateway(self.svc, sessions=[{"id": SID}])

        async def call(name: str):
            token = current_mcp_client.set(name)
            try:
                await gateway.call_tool(McpToolCallRequest(name="browser.observe", arguments={}))
            finally:
                current_mcp_client.reset(token)

        await asyncio.gather(*(call(f"client-{i % 2}") for i in range(10)))
        events = await self._events()
        self.assertEqual([e["seq"] for e in events], list(range(1, 21)))
        self.assertEqual({e["client"] for e in events}, {"client-0", "client-1"})

    async def test_recorder_failure_does_not_break_the_tool_call(self) -> None:
        gateway, _ = _make_gateway(self.svc, sessions=[{"id": SID}])
        await self.svc.register_session(SID)
        with patch.object(LiveViewService, "record", side_effect=RuntimeError("boom")):
            response = await gateway.call_tool(McpToolCallRequest(name="browser.observe", arguments={}))
        self.assertFalse(response.isError)

    async def test_gateway_without_live_view_is_unchanged(self) -> None:
        gateway, _ = _make_gateway(None, sessions=[{"id": SID}])
        response = await gateway.call_tool(McpToolCallRequest(name="browser.observe", arguments={}))
        self.assertFalse(response.isError)
        self.assertNotIn("live_view", response.structuredContent)


class LiveApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = SimpleNamespace(
            artifact_root=self.tmp.name,
            live_ui_base_url="http://127.0.0.1:3100",
            live_banner_color=False,
            live_ui_origin_list=["http://127.0.0.1:3100"],
        )
        self.svc = LiveViewService(self.settings)
        self.live: dict = {}
        self.manager = SimpleNamespace(
            sessions=self.live,
            get_session_record=AsyncMock(side_effect=KeyError("x")),
            create_session=AsyncMock(return_value={"id": "cccccccccccc", "name": "restarted"}),
        )
        self.gateway = _full_gateway()
        app = FastAPI()
        app.include_router(create_live_api_router(manager=self.manager, live_view=self.svc, tool_gateway=self.gateway))
        install_live_cors(app, settings=self.settings)
        self.client = TestClient(app)
        # One archived session with a timeline on disk.
        asyncio.run(self._seed())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def _seed(self) -> None:
        await self.svc.register_session(SID, name="old", start_url="https://example.com/")
        await self.svc.record(SID, {"event": "start", "tool": "browser.observe"})
        await self.svc.record(SID, {"event": "end", "tool": "browser.observe", "status": "ok"})
        await self.svc.mark_closed(SID)

    def test_list_and_get_archived_session(self) -> None:
        body = self.client.get("/live-api/sessions").json()
        self.assertEqual([s["id"] for s in body["sessions"]], [SID])
        item = body["sessions"][0]
        self.assertEqual(item["state"], "archived")
        self.assertEqual(item["live_url"], f"http://127.0.0.1:3100/s/{SID}")
        self.assertEqual(self.client.get(f"/live-api/sessions/{SID}").json()["start_url"], "https://example.com/")

    def test_timeline_reads_archived_session_from_disk(self) -> None:
        body = self.client.get(f"/live-api/sessions/{SID}/timeline").json()
        self.assertEqual(body["last_seq"], 2)
        self.assertEqual([e["seq"] for e in body["events"]], [1, 2])
        self.assertEqual(body["session"]["state"], "archived")
        after = self.client.get(f"/live-api/sessions/{SID}/timeline?after_seq=1").json()
        self.assertEqual([e["seq"] for e in after["events"]], [2])

    def test_unknown_and_malicious_ids_are_404(self) -> None:
        for bad in ("ffffffffffff", "..%2F..%2Fetc", "a.b", "%2e%2e"):
            self.assertEqual(self.client.get(f"/live-api/sessions/{bad}/timeline").status_code, 404, bad)
            self.assertEqual(self.client.get(f"/live-api/sessions/{bad}").status_code, 404, bad)
            self.assertEqual(self.client.post(f"/live-api/sessions/{bad}/restart").status_code, 404, bad)

    def test_restart_creates_a_live_session_at_the_start_url(self) -> None:
        response = self.client.post(f"/live-api/sessions/{SID}/restart")
        self.assertEqual(response.status_code, 200)
        session = response.json()["session"]
        self.assertEqual(session["id"], "cccccccccccc")
        self.assertEqual(session["start_url"], "https://example.com/")
        self.manager.create_session.assert_awaited_once_with(start_url="https://example.com/")

    def test_restart_of_a_live_session_is_409(self) -> None:
        self.live[SID] = object()
        self.assertEqual(self.client.post(f"/live-api/sessions/{SID}/restart").status_code, 409)
        self.manager.create_session.assert_not_awaited()
        self.assertEqual(self.client.get(f"/live-api/sessions/{SID}").json()["state"], "live")

    def test_restart_when_session_limit_is_hit_is_409(self) -> None:
        self.manager.create_session = AsyncMock(side_effect=RuntimeError("Session limit reached"))
        self.assertEqual(self.client.post(f"/live-api/sessions/{SID}/restart").status_code, 409)

    def test_tools_catalogue(self) -> None:
        body = self.client.get("/live-api/tools").json()
        self.assertEqual(body["instructions"], MCP_INSTRUCTIONS)
        tools = {t["name"]: t for t in body["tools"]}
        self.assertEqual(len(tools), len(self.gateway._registry.tools))
        self.assertEqual(
            set(tools["browser.execute_action"]), {"name", "description", "phase", "read_only", "required"}
        )
        self.assertEqual(tools["browser.execute_action"]["phase"], "act")
        self.assertIn("action", tools["browser.execute_action"]["required"])
        self.assertTrue(tools["browser.get_html"]["read_only"])
        self.assertIn("live_view", tools["browser.create_session"]["description"])
        self.assertIn("REQUIRED", MCP_INSTRUCTIONS)

    def test_cors_only_for_allowed_origin_on_live_paths(self) -> None:
        ok = self.client.get("/live-api/tools", headers={"Origin": "http://127.0.0.1:3100"})
        self.assertEqual(ok.headers["access-control-allow-origin"], "http://127.0.0.1:3100")
        self.assertNotIn("access-control-allow-credentials", ok.headers)
        bad = self.client.get("/live-api/tools", headers={"Origin": "http://evil.example"})
        self.assertNotIn("access-control-allow-origin", bad.headers)
        pre = self.client.options(
            "/live-api/sessions/x/restart",
            headers={"Origin": "http://127.0.0.1:3100", "Access-Control-Request-Method": "POST"},
        )
        self.assertEqual(pre.status_code, 204)
        self.assertIn("POST", pre.headers["access-control-allow-methods"])


class TransportAndLimitTests(unittest.TestCase):
    def test_initialize_instructions_and_client_name_reach_the_gateway(self) -> None:
        from app.mcp_transport import MCP_PROTOCOL_HEADER, MCP_SESSION_HEADER, McpHttpTransport
        from app.models import McpToolCallContent, McpToolCallResponse

        seen: list = []

        async def call_tool(_request):
            seen.append(current_mcp_client.get())
            return McpToolCallResponse(content=[McpToolCallContent(text="{}")], structuredContent={})

        gateway = SimpleNamespace(list_tools=lambda: [], call_tool=call_tool)
        transport = McpHttpTransport(tool_gateway=gateway, server_name="t", server_version="0")
        app = FastAPI()

        @app.post("/mcp")
        async def mcp(request: Request):
            return await transport.handle_post_request(request)

        client = TestClient(app)
        init = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "clientInfo": {"name": "claude-code"}},
            },
        )
        instructions = init.json()["result"]["instructions"]
        for needle in (
            "browser.create_session",
            "reason",
            "element_id",
            "selector_hint",
            "live_view",
            "banner",
            "_notice",
            "first content block",
        ):
            self.assertIn(needle, instructions)
        headers = {MCP_SESSION_HEADER: init.headers[MCP_SESSION_HEADER], MCP_PROTOCOL_HEADER: "2025-06-18"}
        client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "x", "arguments": {}}},
        )
        self.assertEqual(seen, ["claude-code"])
        self.assertIsNone(current_mcp_client.get())

    def test_session_limit_error_names_the_live_url(self) -> None:
        from app.browser.services.sessions import BrowserSessionService

        manager = SimpleNamespace(
            sessions={SID: object()},
            settings=SimpleNamespace(
                max_sessions=1, session_isolation_mode="shared_browser_node", live_ui_base_url="http://127.0.0.1:3100"
            ),
        )
        with self.assertRaises(RuntimeError) as ctx:
            BrowserSessionService(manager).check_limit()
        self.assertIn(f"http://127.0.0.1:3100/s/{SID}", str(ctx.exception))
        self.assertIn("show this watch link", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
