"""Regression tests for bugs found by e2e/tools_smoke.py (every advertised tool, good
and bad calls). Each test pins one failure path to a clean, actionable isError result:
no bare ids, no opaque "Tool execution failed", no local paths, no HTTP 422/500, and
no sensitive typed value echoed back by a later call.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from app.action_errors import BrowserActionError
from app.approvals import ApprovalRequiredError
from app.mcp_transport import MCP_PROTOCOL_HEADER, MCP_SESSION_HEADER, McpHttpTransport
from app.models import ApprovalRecord, BrowserActionDecision, McpToolCallRequest
from app.routes.mcp import create_mcp_router
from app.tool_gateway import McpToolGateway

SID = "live-session-1"


def _missing(key):
    raise KeyError(key)


def _manager(**overrides):
    manager = SimpleNamespace(
        sessions={SID: object()},
        list_sessions=AsyncMock(return_value=[{"id": SID}]),
        get_session=AsyncMock(side_effect=lambda sid: SimpleNamespace() if sid == SID else _missing(sid)),
        get_session_record=AsyncMock(side_effect=lambda sid: {"id": sid} if sid == SID else _missing(sid)),
        observe=AsyncMock(side_effect=lambda sid, **_: _missing(sid)),
        verify_witness_chain=AsyncMock(return_value={"valid": True, "receipt_count": 0}),
        export_witness_bundle=AsyncMock(return_value={"receipts": []}),
        require_governed_approval=AsyncMock(return_value=None),
        execute_decision=AsyncMock(return_value={"action": "type", "ok": True}),
        settings=SimpleNamespace(mcp_tool_name_style="underscore"),
        approvals=SimpleNamespace(mark_executed=AsyncMock()),
    )
    for key, value in overrides.items():
        setattr(manager, key, value)
    return manager


def _gateway(manager=None, **kwargs):
    return McpToolGateway(
        manager=manager or _manager(),
        orchestrator=SimpleNamespace(list_providers=lambda: []),
        job_queue=SimpleNamespace(get_job=AsyncMock(side_effect=lambda jid: _missing(jid))),
        tool_profile="full",
        **kwargs,
    )


def _text(response) -> str:
    return "\n".join(block.text or "" for block in response.content)


class NotFoundMessageTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_session_names_the_problem_and_the_next_tool(self) -> None:
        gateway = _gateway()
        response = await gateway.call_tool(
            McpToolCallRequest(name="browser_observe", arguments={"session_id": "gone-123"})
        )
        self.assertTrue(response.isError)
        text = _text(response)
        self.assertNotEqual(text.strip(), "gone-123")
        self.assertIn("gone-123", text)
        self.assertIn("not found or is already closed", text)
        self.assertIn("browser_create_session", text)  # advertised (underscore) spelling
        self.assertIn("browser_list_sessions", text)

    async def test_unknown_agent_job_points_at_list_agent_jobs(self) -> None:
        response = await _gateway().call_tool(
            McpToolCallRequest(name="browser.get_agent_job", arguments={"job_id": "job-x"})
        )
        self.assertTrue(response.isError)
        self.assertIn("Agent job 'job-x' was not found", _text(response))
        self.assertIn("browser_list_agent_jobs", _text(response))

    async def test_descriptive_key_error_is_kept(self) -> None:
        manager = _manager(get_session=AsyncMock(side_effect=KeyError("Cron job not found: c1")))
        gateway = _gateway(manager)
        gateway._registry.get("browser.observe").handler = AsyncMock(side_effect=KeyError("Cron job not found: c1"))
        response = await gateway.call_tool(McpToolCallRequest(name="browser.observe", arguments={"session_id": SID}))
        self.assertEqual(_text(response), "Cron job not found: c1")

    async def test_witness_tools_reject_a_session_that_never_existed(self) -> None:
        manager = _manager()
        gateway = _gateway(manager)
        for tool in ("browser.verify_witness", "browser.export_witness_bundle"):
            with self.subTest(tool=tool):
                response = await gateway.call_tool(
                    McpToolCallRequest(name=tool, arguments={"session_id": "never-was"})
                )
                self.assertTrue(response.isError)
                self.assertIn("not found or is already closed", _text(response))
        manager.verify_witness_chain.assert_not_awaited()
        ok = await gateway.call_tool(McpToolCallRequest(name="browser.verify_witness", arguments={"session_id": SID}))
        self.assertFalse(ok.isError)

    async def test_governed_call_on_unknown_session_does_not_park_an_approval(self) -> None:
        manager = _manager()
        response = await _gateway(manager).call_tool(
            McpToolCallRequest(
                name="browser.eval_js",
                arguments={"session_id": "never-was", "expression": "1", "workflow_profile": "governed"},
            )
        )
        self.assertTrue(response.isError)
        self.assertIn("not found or is already closed", _text(response))
        manager.require_governed_approval.assert_not_awaited()


class BrowserErrorTests(unittest.IsolatedAsyncioTestCase):
    async def _call_with(self, exc: BaseException):
        gateway = _gateway()
        gateway._registry.get("browser.wait_for_selector").handler = AsyncMock(side_effect=exc)
        return await gateway.call_tool(
            McpToolCallRequest(name="browser.wait_for_selector", arguments={"session_id": SID, "selector": "#x"})
        )

    async def test_playwright_timeout_is_actionable(self) -> None:
        response = await self._call_with(
            PlaywrightTimeoutError("Page.wait_for_selector: Timeout 1500ms exceeded.\nCall log:\n  - waiting")
        )
        self.assertTrue(response.isError)
        text = _text(response)
        self.assertIn("timed out", text)
        self.assertIn("re-observe", text)
        self.assertNotIn("Call log", text)
        self.assertNotIn("TimeoutError", text)

    async def test_unreachable_target_is_actionable(self) -> None:
        response = await self._call_with(PlaywrightError("Page.goto: net::ERR_CONNECTION_REFUSED at http://127.0.0.1:1/"))
        self.assertIn("could not reach the target", _text(response))

    async def test_asyncio_timeout_is_actionable(self) -> None:
        response = await self._call_with(asyncio.TimeoutError())
        self.assertIn("timed out", _text(response))

    async def test_unexpected_exception_still_says_what_to_do(self) -> None:
        response = await self._call_with(ZeroDivisionError("boom"))
        text = _text(response)
        self.assertTrue(text.startswith("Tool execution failed"))
        self.assertIn("browser_wait_for_selector", text)
        self.assertIn("Retry once", text)
        self.assertNotIn("boom", text)
        self.assertNotIn("ZeroDivisionError", text)

    async def test_permission_error_is_surfaced_with_next_step(self) -> None:
        response = await self._call_with(PermissionError("approval a1 is not approved"))
        self.assertIn("Not permitted: approval a1 is not approved", _text(response))
        self.assertIn("browser_list_approvals", _text(response))


class LocalPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_action_error_drops_local_screenshot_path(self) -> None:
        manager = _manager(
            execute_decision=AsyncMock(
                side_effect=BrowserActionError(
                    "Action failed. Refresh observation and retry.",
                    action="navigate",
                    details={
                        "reason": r"page.goto failed writing C:\Users\me\data\x.png",
                        "snapshot": {
                            "screenshot_path": r"C:\Users\me\data\artifacts\s\failed.png",
                            "screenshot_url": "/artifacts/s/failed.png",
                        },
                    },
                )
            )
        )
        response = await _gateway(manager).call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={"session_id": SID, "action": {"action": "navigate", "url": "http://x/", "reason": "t"}},
            )
        )
        self.assertTrue(response.isError)
        blob = _text(response) + json.dumps(response.structuredContent)
        self.assertNotIn("C:\\", blob.replace("\\\\", "\\"))
        self.assertIn("/artifacts/s/failed.png", blob)
        self.assertIn("<path>", response.structuredContent["reason"])

    async def test_approval_required_drops_local_paths_and_adds_next_step(self) -> None:
        approval = ApprovalRecord(
            id="ap-1",
            session_id=SID,
            kind="write",
            status="pending",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            reason="needs approval",
            action=BrowserActionDecision(action="click", selector="a", reason="x", risk_category="write"),
            observation={"remote_access": {"info_path": r"\data\tunnels\reverse-ssh.json"}},
        )
        manager = _manager(execute_decision=AsyncMock(side_effect=ApprovalRequiredError(approval)))
        response = await _gateway(manager).call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={"session_id": SID, "action": {"action": "click", "selector": "a", "reason": "t"}},
            )
        )
        self.assertTrue(response.isError)
        self.assertNotIn("info_path", json.dumps(response.structuredContent))
        self.assertIn("approval_id=ap-1", response.structuredContent["next_step"])


class ExecuteApprovalTests(unittest.IsolatedAsyncioTestCase):
    async def test_governed_tool_approval_explains_how_it_is_consumed(self) -> None:
        approval = SimpleNamespace(
            action=BrowserActionDecision(
                action="request_human_takeover", reason="Approve governed MCP tool call browser.eval_js"
            )
        )
        manager = _manager(
            approvals=SimpleNamespace(get=AsyncMock(return_value=approval), mark_executed=AsyncMock()),
            execute_approval=AsyncMock(side_effect=ValueError("Unsupported action: request_human_takeover")),
        )
        response = await _gateway(manager).call_tool(
            McpToolCallRequest(name="browser.execute_approval", arguments={"approval_id": "ap-9"})
        )
        self.assertTrue(response.isError)
        self.assertIn("repeat the browser_eval_js call with approval_id=ap-9", _text(response))
        manager.execute_approval.assert_not_awaited()


class SensitiveValueTests(unittest.IsolatedAsyncioTestCase):
    async def test_sensitive_typed_value_never_reaches_a_later_result(self) -> None:
        secret = "Hunter2-Secret"
        manager = _manager(
            execute_decision=AsyncMock(
                side_effect=[
                    {"action": "type", "text_redacted": True},
                    {"action": "scroll", "before": {"active_element": {"tag": "input", "label": secret}}},
                ]
            )
        )
        gateway = _gateway(manager)
        typed = await gateway.call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={
                    "session_id": SID,
                    "action": {"action": "type", "selector": "#pw", "text": secret, "sensitive": True, "reason": "t"},
                },
            )
        )
        self.assertFalse(typed.isError)
        later = await gateway.call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={"session_id": SID, "action": {"action": "scroll", "delta_y": 100, "reason": "t"}},
            )
        )
        blob = _text(later) + json.dumps(later.structuredContent)
        self.assertNotIn(secret, blob)
        self.assertEqual(later.structuredContent["before"]["active_element"]["label"], "[redacted]")

    async def test_non_sensitive_text_is_not_redacted(self) -> None:
        manager = _manager(
            execute_decision=AsyncMock(
                side_effect=[{"action": "type"}, {"action": "scroll", "before": {"label": "hello world"}}]
            )
        )
        gateway = _gateway(manager)
        await gateway.call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={
                    "session_id": SID,
                    "action": {"action": "type", "selector": "#q", "text": "hello world", "reason": "t"},
                },
            )
        )
        later = await gateway.call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={"session_id": SID, "action": {"action": "scroll", "delta_y": 1, "reason": "t"}},
            )
        )
        self.assertEqual(later.structuredContent["before"]["label"], "hello world")

    def test_page_scripts_do_not_read_field_values_for_labels(self) -> None:
        from app import browser_scripts

        for name in ("ACTIVE_ELEMENT_SCRIPT", "INTERACTABLES_SCRIPT", "PAGE_SUMMARY_SCRIPT"):
            script = getattr(browser_scripts, name)
            with self.subTest(script=name):
                self.assertNotIn("|| el.value\n", script)
                self.assertNotIn("|| el.value ||", script)
                self.assertNotIn("|| field.value\n", script)


class SensitiveTypeBySelectorTests(unittest.IsolatedAsyncioTestCase):
    """Enforce-mode post-hoc type check must compare refs, not a selector with a ref."""

    def _gateway_with_page(self, *, focus: dict, field_ref: str | None, matches: bool = False):
        locator = SimpleNamespace(get_attribute=AsyncMock(return_value=field_ref))
        page = SimpleNamespace(
            locator=lambda _sel: SimpleNamespace(first=locator),
            evaluate=AsyncMock(side_effect=lambda script, *args: matches if args else focus),
        )
        manager = _manager(get_session=AsyncMock(return_value=SimpleNamespace(page=page)))
        return _gateway(manager)

    def _decision(self):
        return BrowserActionDecision(action="type", selector="#pw", text="Secret-123", sensitive=True, reason="t")

    async def test_selector_resolving_to_focused_ref_is_allowed(self) -> None:
        gateway = self._gateway_with_page(focus={"found": True, "ref": "op-7", "type": "password"}, field_ref="op-7")
        self.assertIsNone(await gateway._shoav_type_check(SID, self._decision(), None, "enforce"))

    async def test_selector_without_ref_uses_active_element_match(self) -> None:
        gateway = self._gateway_with_page(
            focus={"found": True, "ref": None, "type": "password"}, field_ref=None, matches=True
        )
        self.assertIsNone(await gateway._shoav_type_check(SID, self._decision(), None, "enforce"))

    async def test_real_focus_deflection_is_still_blocked(self) -> None:
        gateway = self._gateway_with_page(focus={"found": True, "ref": "op-9", "type": "password"}, field_ref="op-7")
        blocked = await gateway._shoav_type_check(SID, self._decision(), None, "enforce")
        self.assertIsNotNone(blocked)
        self.assertTrue(blocked.isError)
        self.assertIn("deflection", _text(blocked))


class EnvelopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.gateway = SimpleNamespace(list_tools=lambda: [], call_tool=AsyncMock())
        transport = McpHttpTransport(
            tool_gateway=self.gateway,
            server_name="shoav",
            server_version="0",
            session_store_path=f"{self.tmp.name}/s.json",
            manager=SimpleNamespace(sessions={}),
        )
        app = FastAPI()
        app.include_router(create_mcp_router(mcp_transport=transport, tool_gateway=self.gateway))
        self.client = TestClient(app)
        self.transport = transport

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_rest_arguments_not_an_object_is_an_iserror_result_not_422(self) -> None:
        response = self.client.post("/mcp/tools/call", json={"name": "browser_list_sessions", "arguments": [1, 2]})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["isError"])
        self.assertIn("arguments", body["content"][0]["text"])
        self.assertIn("arguments is an object", body["content"][0]["text"])
        self.gateway.call_tool.assert_not_awaited()

    def test_rest_missing_name_is_an_iserror_result(self) -> None:
        response = self.client.post("/mcp/tools/call", json={"arguments": {}})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["isError"])
        self.assertIn("name", response.json()["content"][0]["text"])

    def test_jsonrpc_bad_tools_call_params_is_readable_and_serialisable(self) -> None:
        init = self.client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t"}},
            },
        )
        sid = init.headers[MCP_SESSION_HEADER]
        version = init.json()["result"]["protocolVersion"]
        headers = {MCP_SESSION_HEADER: sid, MCP_PROTOCOL_HEADER: version}
        self.client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=headers)
        response = self.client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "x", "arguments": [1]}},
            headers=headers,
        )
        self.assertLess(response.status_code, 500)
        error = response.json()["error"]
        self.assertEqual(error["code"], -32602)
        self.assertIn("arguments", error["message"])


class StringifiedActionArgumentTests(unittest.IsolatedAsyncioTestCase):
    """F3 from the real-engine runs (docs/integration/ENGINES.md): some MCP clients send
    a nested-object argument as a JSON string instead of an object, because the
    advertised schema used to expose it as a bare $ref the client never resolved.
    """

    async def test_action_sent_as_a_json_string_is_accepted(self) -> None:
        manager = _manager()
        action_json = json.dumps({"action": "click", "selector": "#buy", "reason": "t"})
        response = await _gateway(manager).call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={"session_id": SID, "action": action_json},
            )
        )
        self.assertFalse(response.isError, _text(response))
        manager.execute_decision.assert_awaited_once()

    async def test_action_sent_as_malformed_json_string_still_fails_cleanly(self) -> None:
        response = await _gateway().call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={"session_id": SID, "action": "not json"},
            )
        )
        self.assertTrue(response.isError)
        self.assertIn("action", _text(response))

    async def test_action_sent_as_a_json_array_string_still_fails_cleanly(self) -> None:
        response = await _gateway().call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={"session_id": SID, "action": "[1, 2]"},
            )
        )
        self.assertTrue(response.isError)

    async def test_action_sent_as_a_real_object_is_unaffected(self) -> None:
        manager = _manager()
        response = await _gateway(manager).call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={
                    "session_id": SID,
                    "action": {"action": "click", "selector": "#buy", "reason": "t"},
                },
            )
        )
        self.assertFalse(response.isError, _text(response))
        manager.execute_decision.assert_awaited_once()

    def test_advertised_schema_has_no_ref_or_defs(self) -> None:
        gateway = _gateway()
        descriptors = gateway._registry.list_tools()
        execute_action = next(d for d in descriptors if d["name"] in ("browser_execute_action", "browser.execute_action"))
        blob = json.dumps(execute_action["inputSchema"])
        self.assertNotIn("$ref", blob)
        self.assertNotIn("$defs", blob)
        self.assertIn("selector", blob)


if __name__ == "__main__":
    unittest.main()
