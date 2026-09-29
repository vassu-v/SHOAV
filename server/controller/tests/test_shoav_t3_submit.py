"""T3 submit regression: pre-checked consent must block submit pre-dispatch.

Spec under test: a click on a submit control (button/input type=submit)
or Enter in a form, while an untouched pre-checked consent-like control
exists, must return isError True with verdict ESCALATE in both
content[0].text and structuredContent, and the submit handler must NOT run.
A box the agent deliberately unchecked (touched, via mark_touched
semantics) must not block.

Uses fakes only: fake manager/session/page plus a fake guard that already
knows the correct submission rule. No network or browser.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.models import McpToolCallRequest
from app.tool_gateway import McpToolGateway


SESSION_ID = "session-t3"


class FakeLocator:
    @property
    def first(self):
        return self

    async def scroll_into_view_if_needed(self):
        return None

    async def bounding_box(self):
        # No geometry, so the egress clickjacking probe returns None and
        # fails open. This isolates the submit/consent decision.
        return None

    async def get_attribute(self, _name):
        return None


class FakePage:
    def locator(self, _selector):
        return FakeLocator()

    async def evaluate(self, _script, *args):
        return None


class FakeSubmissionGuard:
    """Fake guard with the correct submission rule.

    Real submission rule: any snapshot item with checked True whose ref is
    not in touched is an untouched pre-checked field and must ESCALATE.
    Click-shaped egress checks return ALLOW so they do not interfere.
    """

    def __init__(self):
        self.mode = "enforce"
        self.fail = "open"

    def decide_egress(self, args):
        args = dict(args or {})
        if args.get("check") == "submission":
            snapshot = args.get("snapshot") or []
            touched = set(args.get("touched") or [])
            flags = [
                item
                for item in snapshot
                if isinstance(item, dict)
                and bool(item.get("checked"))
                and item.get("ref") not in touched
            ]
            if flags:
                return {
                    "verdict": "ESCALATE",
                    "reason": f"{len(flags)} untouched pre-checked field(s) at submission.",
                    "flags": flags,
                }
            return {"verdict": "ALLOW", "reason": "No untouched pre-checked fields.", "flags": []}
        return {"verdict": "ALLOW", "reason": "click probe clean."}


def make_gateway():
    page = FakePage()
    session = SimpleNamespace(page=page)
    manager = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        list_sessions=AsyncMock(return_value=[{"id": SESSION_ID}]),
        execute_decision=AsyncMock(return_value={"action": "click", "ok": True}),
        settings=SimpleNamespace(mcp_tool_name_style="dotted"),
    )
    orchestrator = SimpleNamespace(list_providers=lambda: [])
    job_queue = SimpleNamespace()
    gateway = McpToolGateway(
        manager=manager,
        orchestrator=orchestrator,
        job_queue=job_queue,
        guard=FakeSubmissionGuard(),
    )
    return gateway, manager


def seed_form(gateway, *, submit_ref="op-submit", touched=()):
    state = gateway._shoav_state(SESSION_ID)
    state["interactables"] = [
        {"element_id": submit_ref, "type": "submit", "label": "Submit"},
    ]
    state["form_snapshot"] = [
        {
            "ref": "op-consent",
            "type": "checkbox",
            "checked": True,
            "label": "I agree to marketing emails",
        },
    ]
    # Mirrors GuardSessionCache.mark_touched(session_id, ref) semantics:
    # refs the agent deliberately touched must not count as pre-checked.
    state["touched"] = set(touched)
    state["last_origin_path"] = "https://example.com/form"


def assert_escalate_block(testcase, response):
    testcase.assertTrue(response.isError, "submit with untouched pre-check must be an error")
    body_text = response.content[0].text
    testcase.assertIn("ESCALATE", body_text, "content[0].text must carry verdict ESCALATE")
    structured_text = json.dumps(response.structuredContent, ensure_ascii=False)
    testcase.assertIn("ESCALATE", structured_text, "structuredContent must carry verdict ESCALATE")


class ShoavT3SubmitTests(unittest.IsolatedAsyncioTestCase):
    async def test_click_button_submit_blocked_and_handler_not_run(self):
        gateway, manager = make_gateway()
        seed_form(gateway, submit_ref="op-submit", touched=set())
        response = await gateway.call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={
                    "session_id": SESSION_ID,
                    "action": {"action": "click", "reason": "click submit", "element_id": "op-submit"},
                },
            )
        )
        assert_escalate_block(self, response)
        manager.execute_decision.assert_not_awaited()

    async def test_click_input_submit_blocked_and_handler_not_run(self):
        gateway, manager = make_gateway()
        seed_form(gateway, submit_ref="op-submit-input", touched=set())
        response = await gateway.call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={
                    "session_id": SESSION_ID,
                    "action": {
                        "action": "click",
                        "reason": "click input submit",
                        "element_id": "op-submit-input",
                    },
                },
            )
        )
        assert_escalate_block(self, response)
        manager.execute_decision.assert_not_awaited()

    async def test_enter_in_form_blocked_and_handler_not_run(self):
        gateway, manager = make_gateway()
        seed_form(gateway, submit_ref="op-submit", touched=set())
        response = await gateway.call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={
                    "session_id": SESSION_ID,
                    "action": {"action": "press", "reason": "submit with enter", "key": "Enter"},
                },
            )
        )
        assert_escalate_block(self, response)
        manager.execute_decision.assert_not_awaited()

    async def test_deliberately_untouched_box_does_not_block(self):
        gateway, manager = make_gateway()
        # Agent deliberately unchecked/touched the box, so mark_touched exempts it.
        seed_form(gateway, submit_ref="op-submit", touched={"op-consent"})
        response = await gateway.call_tool(
            McpToolCallRequest(
                name="browser.execute_action",
                arguments={
                    "session_id": SESSION_ID,
                    "action": {"action": "click", "reason": "click submit", "element_id": "op-submit"},
                },
            )
        )
        self.assertFalse(response.isError, "touched box must not block submit")
        manager.execute_decision.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
