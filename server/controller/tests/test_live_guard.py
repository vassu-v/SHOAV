"""Unit tests for C-2 live-event guard plumbing only.

Covers LiveCall.guard event emission, guard redaction helpers in
app.live.phases, and GET /live-api/guard. Does not touch gateway hooks
and does not add a phase.
"""

from __future__ import annotations

import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.live import LiveViewService
from app.live.calls import LiveCall
from app.live.phases import PHASES, redact_guard_findings, redact_guard_reason
from app.models import McpToolCallContent, McpToolCallResponse
from app.routes.live_api import create_live_api_router

SID = "a5af842a89e1"


def _settings(tmp: str) -> SimpleNamespace:
    return SimpleNamespace(
        artifact_root=tmp,
        live_ui_base_url="http://127.0.0.1:3100",
        live_banner_color=False,
        live_ui_origin_list=["http://127.0.0.1:3100"],
    )


def _ok_response() -> McpToolCallResponse:
    return McpToolCallResponse(
        content=[McpToolCallContent(text="{}")],
        structuredContent={"ok": True},
        isError=False,
    )


class GuardEventTests(unittest.IsolatedAsyncioTestCase):
    async def test_guard_emits_typed_verdict_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svc = LiveViewService(_settings(tmp))
            await svc.register_session(SID)
            call = LiveCall(svc, SimpleNamespace(sessions={SID: object()}), "browser.observe", {"session_id": SID})
            await call.begin(SID)
            await call.guard(
                stage="ingress",
                verdict="REWRITE",
                mode="enforce",
                enforced=True,
                reason="hidden text removed",
                findings=[{"kind": "hidden_text", "detail": "display:none prompt"}],
            )
            events, _, _ = await svc.timeline(SID, 0)
            verdicts = [e for e in events if e.get("type") == "guard"]
            self.assertEqual(len(verdicts), 1)
            event = verdicts[0]
            self.assertEqual(
                (event["event"], event["call_id"], event["session_id"]),
                ("verdict", call.call_id, SID),
            )
            self.assertEqual(
                (event["stage"], event["tool"], event["verdict"]),
                ("ingress", "browser.observe", "REWRITE"),
            )
            self.assertEqual((event["mode"], event["enforced"]), ("enforce", True))
            self.assertEqual(event["reason"], "hidden text removed")
            self.assertEqual(event["findings"], [{"kind": "hidden_text", "detail": "display:none prompt"}])
            self.assertIsInstance(event["seq"], int)
            self.assertTrue(event["ts"])

    async def test_guard_target_and_client_and_egress(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svc = LiveViewService(_settings(tmp))
            await svc.register_session(SID)
            call = LiveCall(svc, SimpleNamespace(sessions={SID: object()}), "browser.execute_action", {"session_id": SID})
            call.client = "claude-code"
            await call.begin(SID)
            await call.guard(
                stage="egress",
                verdict="BLOCK",
                mode="enforce",
                enforced=True,
                reason="overlay covers target",
                findings=[],
                element_id="op-s4",
            )
            events, _, _ = await svc.timeline(SID, 0)
            event = [e for e in events if e.get("type") == "guard"][0]
            self.assertEqual(event["target"], {"element_id": "op-s4"})
            self.assertEqual(event["client"], "claude-code")

    async def test_guard_summary_on_end_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svc = LiveViewService(_settings(tmp))
            await svc.register_session(SID)
            call = LiveCall(svc, SimpleNamespace(sessions={SID: object()}), "browser.observe", {"session_id": SID})
            await call.begin(SID)
            await call.guard(stage="ingress", verdict="ALLOW", mode="observe", enforced=False, reason="clean")
            await call.guard(
                stage="ingress",
                verdict="REWRITE",
                mode="observe",
                enforced=False,
                reason="rewrote",
                findings=[{"kind": "hidden_text", "detail": "x"}],
            )
            await call.finish(_ok_response())
            events, _, _ = await svc.timeline(SID, 0)
            end = [e for e in events if e.get("event") == "end"][0]
            self.assertEqual(end["type"], "tool")
            self.assertEqual(
                end["guard"],
                {
                    "verdict": "REWRITE",
                    "mode": "observe",
                    "enforced": False,
                    "count": 2,
                    "verdicts": ["ALLOW", "REWRITE"],
                },
            )

    async def test_guard_redacts_sensitive_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svc = LiveViewService(_settings(tmp))
            await svc.register_session(SID)
            call = LiveCall(svc, SimpleNamespace(sessions={SID: object()}), "browser.observe", {"session_id": SID})
            await call.begin(SID)
            await call.guard(
                stage="ingress",
                verdict="REWRITE",
                mode="enforce",
                enforced=True,
                reason="https://example.com/?token=secret",
                findings=[{"kind": "hidden_text", "detail": "https://h.example/?password=pw"}],
            )
            events, _, _ = await svc.timeline(SID, 0)
            event = [e for e in events if e.get("type") == "guard"][0]
            self.assertIn("[redacted]", event["reason"])
            self.assertNotIn("secret", event["reason"])
            self.assertIn("[redacted]", event["findings"][0]["detail"])
            self.assertNotIn("=pw", str(event["findings"]))

    async def test_guard_never_raises_and_ignores_unknown_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svc = LiveViewService(_settings(tmp))
            call = LiveCall(
                svc,
                SimpleNamespace(sessions={}, get_session_record=AsyncMock(side_effect=KeyError("x"))),
                "browser.observe",
                {"session_id": "deadbeef0000"},
            )
            await call.begin("deadbeef0000")
            await call.guard(stage="ingress", verdict="ALLOW", mode="off", enforced=False)
            events, _, _ = await svc.timeline("deadbeef0000", 0)
            self.assertEqual(events, [])

    async def test_phases_assert_unchanged(self) -> None:
        self.assertEqual(PHASES, ("session", "screenshot", "read", "act", "other"))


class GuardRedactionTests(unittest.TestCase):
    def test_reason_truncates_long_strings(self) -> None:
        out = redact_guard_reason("ab! " * 600)
        self.assertTrue(out.endswith("...[truncated]"))

    def test_reason_none_stays_none(self) -> None:
        self.assertIsNone(redact_guard_reason(None))

    def test_findings_shape_and_redaction(self) -> None:
        out = redact_guard_findings([{"kind": "hidden_text", "detail": "ab! " * 600, "extra": 1}])
        self.assertEqual(list(out[0]), ["kind", "detail"])
        self.assertTrue(out[0]["detail"].endswith("...[truncated]"))
        self.assertEqual(redact_guard_findings(None), [])
        secret = redact_guard_findings([{"kind": "k", "detail": "https://h.example/?password=pw"}])
        self.assertIn("[redacted]", secret[0]["detail"])


class GuardRouteTests(unittest.TestCase):
    def _client(self, gateway: SimpleNamespace) -> TestClient:
        with tempfile.TemporaryDirectory() as tmp:
            svc = LiveViewService(_settings(tmp))
            manager = SimpleNamespace(sessions={}, get_session_record=AsyncMock(side_effect=KeyError("x")))
            app = FastAPI()
            app.include_router(create_live_api_router(manager=manager, live_view=svc, tool_gateway=gateway))
            client = TestClient(app)
            body = client.get("/live-api/guard").json()
            self.last_tmp = tmp
            return client, body

    def test_guard_route_defaults_when_off(self) -> None:
        _, body = self._client(SimpleNamespace(list_tools=lambda: []))
        self.assertEqual(body["mode"], "off")
        self.assertTrue(body["version"])
        self.assertEqual(body["counters"], {"allow": 0, "rewrite": 0, "block": 0, "escalate": 0})

    def test_guard_route_reads_guard_object(self) -> None:
        guard = SimpleNamespace(
            mode="enforce",
            version="9",
            counters={"allow": 1, "rewrite": 2, "block": 3, "escalate": 4},
        )
        _, body = self._client(SimpleNamespace(list_tools=lambda: [], guard=guard))
        self.assertEqual(body, {"mode": "enforce", "version": "9", "counters": {"allow": 1, "rewrite": 2, "block": 3, "escalate": 4}})


if __name__ == "__main__":
    unittest.main()
