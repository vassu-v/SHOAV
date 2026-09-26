from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.live import LiveViewService, redact_args
from app.live.phases import find_page_state, is_sensitive_key, redact_result
from app.models import McpToolCallRequest
from app.routes.live_api import create_live_api_router, install_live_cors
from app.tool_gateway import McpToolGateway

SID = "a5af842a89e1"


def _settings(root: str) -> SimpleNamespace:
    return SimpleNamespace(
        artifact_root=root,
        live_ui_base_url="http://127.0.0.1:3100",
        live_banner_color=False,
        live_ui_origin_list=["http://127.0.0.1:3100"],
    )


def _gateway(svc, sessions):
    manager = SimpleNamespace(
        sessions={sid: object() for sid in sessions},
        list_sessions=AsyncMock(return_value=[{"id": sid} for sid in sessions]),
        create_session=AsyncMock(return_value={"id": SID}),
        observe=AsyncMock(return_value={"url": "https://example.com/"}),
        get_session_record=AsyncMock(side_effect=KeyError("x")),
        settings=SimpleNamespace(),
    )
    gateway = McpToolGateway(manager=manager, orchestrator=None, job_queue=None, tool_profile="full", live_view=svc)
    return gateway, manager


class RedactionReviewTests(unittest.TestCase):
    def test_url_query_secrets_are_scrubbed(self) -> None:
        url = "https://x.example/cb?code=1&access_token=abc&max_tokens=5#id_token=zzz"
        out = redact_args("browser.execute_action", {"action": {"action": "navigate", "url": url, "reason": "r"}})
        text = json.dumps(out)
        self.assertNotIn("abc", text)
        self.assertNotIn("zzz", text)
        self.assertIn("code=1", text)
        self.assertIn("max_tokens=5", text)
        result = redact_result("browser.observe", {"url": url, "session": {"current_url": url}})
        self.assertNotIn("abc", json.dumps(result))
        self.assertNotIn("abc", find_page_state({"url": url})[0])

    def test_eval_js_result_is_length_only(self) -> None:
        out = redact_result("browser.eval_js", {"session_id": SID, "result": "document.cookie=secretvalue"})
        self.assertEqual(set(out), {"redacted", "result_length"})
        self.assertNotIn("secretvalue", json.dumps(out))
        args = redact_args("browser.eval_js", {"session_id": SID, "expression": "xxxxxxxx"})
        self.assertEqual(args["expression_length"], 8)
        self.assertNotIn("xxxx", json.dumps(args))

    def test_typing_into_password_like_targets_is_redacted(self) -> None:
        for extra in ({"selector": "input[type=password]"}, {"selector": "#pwd"}, {"label": "Password"}):
            action = {"action": "type", "text": "hunter2", "reason": "r", **extra}
            out = redact_args("browser.execute_action", {"action": action})
            self.assertEqual(out["action"]["text"], "[redacted]", extra)
        plain = {"action": "type", "text": "cats", "selector": "#q", "reason": "r"}
        self.assertEqual(redact_args("browser.execute_action", {"action": plain})["action"]["text"], "cats")

    def test_header_style_maps_are_redacted(self) -> None:
        headers = {
            "Authorization": "Bearer a",
            "Cookie": "s=1",
            "Set-Cookie": "s=2",
            "X-Auth-Token": "t",
            "X-Auth": "u",
            "Accept": "*/*",
        }
        got = redact_result("browser.get_network_log", {"entries": [{"headers": headers}]})["entries"][0]["headers"]
        self.assertEqual({k for k, v in got.items() if v == "[redacted]"}, set(headers) - {"Accept"})

    def test_sensitive_key_boundaries(self) -> None:
        for key in ("passed", "bypass", "compass", "max_tokens", "tokens_used", "auth_profile"):
            self.assertFalse(is_sensitive_key(key), key)
        for key in ("password", "proxy_password", "totp_secret", "apiKey", "api-key", "access_token", "Set-Cookie"):
            self.assertTrue(is_sensitive_key(key), key)
        out = redact_result("browser.verify_witness", {"valid": True, "passed": 3, "bypass": 1, "max_tokens": 9})
        self.assertEqual((out["passed"], out["bypass"], out["max_tokens"]), (3, 1, 9))

    def test_drop_keys_only_at_top_level(self) -> None:
        result = {"before": {"a": 1}, "downloads": [1], "items": [{"before": "keep", "downloads": 2}]}
        out = redact_result("browser.x", result)
        self.assertNotIn("before", out)
        self.assertNotIn("downloads", out)
        self.assertEqual(out["items"][0], {"before": "keep", "downloads": 2})

    def test_lone_surrogates_are_sanitised(self) -> None:
        out = redact_args("browser.observe", {"label": "x\ud800y"})
        out["label"].encode("utf-8")
        json.dumps(out).encode("utf-8")


class RecorderReviewTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = _settings(self.tmp.name)
        self.svc = LiveViewService(self.settings)

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()

    async def test_calls_on_closed_sessions_do_not_write_or_bump_counters(self) -> None:
        await self.svc.register_session(SID)
        await self.svc.record(SID, {"event": "start"})
        await self.svc.mark_closed(SID)
        before = await self.svc.get_summary(SID)
        gateway, _ = _gateway(self.svc, [])  # manager no longer has the id
        await gateway.call_tool(McpToolCallRequest(name="browser.observe", arguments={"session_id": SID}))
        gateway2, _ = _gateway(self.svc, [SID])  # manager has it but the summary is archived
        await gateway2.call_tool(McpToolCallRequest(name="browser.observe", arguments={"session_id": SID}))
        events, _, _ = await self.svc.timeline(SID)
        self.assertEqual(len(events), 1)
        self.assertEqual((await self.svc.get_summary(SID))["tool_calls"], before["tool_calls"])
        await self.svc.mark_closed("bbbbbbbbbbbb")
        self.assertIsNone(await self.svc.get_summary("bbbbbbbbbbbb"))  # no phantom summary

    async def test_lone_surrogates_never_break_writes(self) -> None:
        bad = "x\ud800y"
        await self.svc.register_session(SID, name=bad, title=bad)
        self.assertIsNotNone(await self.svc.record(SID, {"event": "start", "args": {"q": bad}}))
        await self.svc.note_call(SID, started=True, title=bad)
        self.assertEqual(len((await self.svc.timeline(SID))[0]), 1)
        self.assertIn("x", (await self.svc.get_summary(SID))["title"])

    async def test_seq_unique_when_close_races_with_records(self) -> None:
        await self.svc.register_session(SID)
        tasks = [self.svc.record(SID, {"event": "start"}) for _ in range(25)]
        tasks.insert(10, self.svc.mark_closed(SID))
        tasks.insert(20, self.svc.reconcile({"id": SID, "state": "live"}, set()))
        await asyncio.gather(*tasks)
        events, _, _ = await LiveViewService(self.settings).timeline(SID)
        self.assertEqual([e["seq"] for e in events], list(range(1, 26)))

    async def test_timeline_paging_limit_and_byte_budget(self) -> None:
        for i in range(12):
            await self.svc.record(SID, {"event": "end", "pad": "z" * 100, "i": i})
        first, last, more = await self.svc.timeline(SID, 0, limit=5)
        self.assertEqual(([e["seq"] for e in first], last, more), ([1, 2, 3, 4, 5], 5, True))
        rest, last, more = await self.svc.timeline(SID, last, limit=50)
        self.assertEqual((len(rest), last, more), (7, 12, False))
        small, _, more = await self.svc.timeline(SID, 0, limit=50, max_bytes=300)
        self.assertTrue(0 < len(small) < 12 and more)
        fresh, last, more = await LiveViewService(self.settings).timeline(SID, 3, limit=4)  # from disk
        self.assertEqual(([e["seq"] for e in fresh], last, more), ([4, 5, 6, 7], 7, True))

    async def test_fork_session_result_carries_live_view_first(self) -> None:
        await self.svc.register_session(SID)
        gateway, manager = _gateway(self.svc, [SID])
        manager.fork_session = AsyncMock(return_value={"id": "ffffffffffff", "name": "fork", "forked_from": SID})
        response = await gateway.call_tool(
            McpToolCallRequest(name="browser.fork_session", arguments={"session_id": SID})
        )
        first = json.loads(response.content[0].text)
        self.assertEqual(list(first)[:2], ["_notice", "live_view"])
        self.assertEqual(first["live_view"]["session_id"], "ffffffffffff")
        self.assertEqual(len(response.content), 2)
        self.assertIn("AUTO BROWSER", response.content[1].text)

    async def test_cancelled_call_still_gets_an_end_event(self) -> None:
        await self.svc.register_session(SID)
        gateway, manager = _gateway(self.svc, [SID])

        async def hang(*_a, **_k):
            await asyncio.sleep(30)

        manager.observe = hang
        task = asyncio.create_task(
            gateway.call_tool(McpToolCallRequest(name="browser.observe", arguments={"session_id": SID}))
        )
        await asyncio.sleep(0.2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.sleep(0.2)
        events, _, _ = await self.svc.timeline(SID)
        self.assertEqual((events[-1]["event"], events[-1]["status"]), ("end", "error"))


class LiveApiReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = _settings(self.tmp.name)
        self.svc = LiveViewService(self.settings)
        self.live: dict = {}
        self.manager = SimpleNamespace(
            sessions=self.live,
            get_session_record=AsyncMock(side_effect=KeyError("x")),
            create_session=AsyncMock(return_value={"id": "cccccccccccc", "name": "restarted"}),
        )
        gateway = McpToolGateway(manager=SimpleNamespace(), orchestrator=None, job_queue=None, tool_profile="full")
        app = FastAPI()
        app.include_router(create_live_api_router(manager=self.manager, live_view=self.svc, tool_gateway=gateway))
        install_live_cors(app, settings=self.settings)
        self.client = TestClient(app)

        async def seed() -> None:
            await self.svc.register_session(SID, start_url="https://example.com/")
            await self.svc.mark_closed(SID)

        asyncio.run(seed())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_gone_browser_is_lazily_archived_and_state_evicted(self) -> None:
        async def make_live() -> None:
            await self.svc.register_session("dddddddddddd")
            await self.svc.record("dddddddddddd", {"event": "start"})

        asyncio.run(make_live())
        body = self.client.get("/live-api/sessions/dddddddddddd").json()
        self.assertEqual(body["state"], "archived")
        self.assertIsNotNone(body["closed_at"])
        stored = json.loads((Path(self.tmp.name) / "dddddddddddd" / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual((stored["state"], bool(stored["closed_at"])), ("archived", True))
        self.assertNotIn("dddddddddddd", self.svc._states)

    def test_timeline_endpoint_limit_and_has_more(self) -> None:
        async def more() -> None:
            await self.svc.register_session("eeeeeeeeeeee")
            for _ in range(5):
                await self.svc.record("eeeeeeeeeeee", {"event": "start"})

        asyncio.run(more())
        self.live["eeeeeeeeeeee"] = object()
        base = "/live-api/sessions/eeeeeeeeeeee/timeline"
        body = self.client.get(f"{base}?limit=3").json()
        self.assertEqual((len(body["events"]), body["last_seq"], body["has_more"]), (3, 3, True))
        body = self.client.get(f"{base}?after_seq=3&limit=100").json()
        self.assertEqual((body["last_seq"], body["has_more"]), (5, False))
        self.assertEqual(self.client.get(f"{base}?limit=5000").status_code, 422)

    def test_restart_rejects_foreign_origin_and_cross_site(self) -> None:
        url = f"/live-api/sessions/{SID}/restart"
        self.assertEqual(self.client.post(url, headers={"Origin": "http://evil.example"}).status_code, 403)
        self.assertEqual(self.client.post(url, headers={"Sec-Fetch-Site": "cross-site"}).status_code, 403)
        self.manager.create_session.assert_not_awaited()
        self.assertEqual(self.client.post(url, headers={"Origin": "http://127.0.0.1:3100"}).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 200)  # non-browser caller without Origin


if __name__ == "__main__":
    unittest.main()
