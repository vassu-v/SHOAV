"""Regression: every egress ALLOW, BLOCK and ESCALATE must increment guard counters and emit a guard event.

Spec only, no network or browser. Uses fakes for LiveCall.guard capture plus
the real ShoavGuard counter object and the gateway egress decision helper.
Expected to FAIL on current code with egress_allow 0 egress_block 0
egress_escalate 0 after a blocked overlay click.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.guard.guard import ShoavGuard
from app.tool_gateway import McpToolGateway


class FakeLiveCall:
    """Fake LiveCall.guard event capture."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def guard(self, *, stage, verdict, mode, enforced, reason=None, findings=None, element_id=None):
        self.events.append(
            {
                "stage": stage,
                "verdict": verdict,
                "mode": mode,
                "enforced": enforced,
                "reason": reason,
                "findings": findings,
                "element_id": element_id,
            }
        )
        return None


def _gateway_with_guard(guard):
    manager = SimpleNamespace(settings=SimpleNamespace(mcp_tool_name_style="dotted"))
    return McpToolGateway(manager=manager, orchestrator=object(), job_queue=object(), guard=guard)


def _allow_hit():
    return {
        "found": True,
        "inside_target": True,
        "tag": "BUTTON",
        "ref": "op-s1",
        "opacity": 1.0,
        "z_index": "0",
        "pointer_events": "auto",
    }


def _overlay_hit():
    # Blocked overlay click: transparent overlay with huge z-index on top.
    return {
        "found": True,
        "inside_target": False,
        "tag": "DIV",
        "ref": "evil-overlay",
        "opacity": 0.0,
        "z_index": "999999",
        "pointer_events": "auto",
    }


def _missing_hit():
    return {"found": False}


class EgressCounterTests(unittest.IsolatedAsyncioTestCase):
    async def test_egress_allow_increments_and_emits(self) -> None:
        guard = ShoavGuard(mode="enforce", fail="open", egress_filter=object())
        gateway = _gateway_with_guard(guard)
        live = FakeLiveCall()
        verdict, reason = await gateway._shoav_decide_click(
            expected_ref=None, hit=_allow_hit(), selector_only=True, coord_only=False
        )
        self.assertEqual(verdict, "ALLOW")
        await gateway._shoav_emit(
            live, stage="egress", tool="browser.execute_action", verdict=verdict,
            reason=reason, enforced=False,
        )
        self.assertEqual(guard.counters["egress_allow"], 1)
        self.assertEqual(len(live.events), 1)
        self.assertEqual(live.events[0]["stage"], "egress")
        self.assertEqual(live.events[0]["verdict"], "ALLOW")

    async def test_egress_block_increments_and_emits(self) -> None:
        guard = ShoavGuard(mode="enforce", fail="open", egress_filter=object())
        gateway = _gateway_with_guard(guard)
        live = FakeLiveCall()
        verdict, reason = await gateway._shoav_decide_click(
            expected_ref=None, hit=_overlay_hit(), selector_only=True, coord_only=False
        )
        self.assertEqual(verdict, "BLOCK")
        await gateway._shoav_emit(
            live, stage="egress", tool="browser.execute_action", verdict=verdict,
            reason=reason, enforced=True,
        )
        self.assertEqual(
            guard.counters["egress_block"], 1,
            f"blocked overlay click left counters at allow={guard.counters['egress_allow']} "
            f"block={guard.counters['egress_block']} escalate={guard.counters['egress_escalate']}",
        )
        self.assertEqual(len(live.events), 1)
        self.assertEqual(live.events[0]["stage"], "egress")
        self.assertEqual(live.events[0]["verdict"], "BLOCK")

    async def test_egress_escalate_increments_and_emits(self) -> None:
        guard = ShoavGuard(mode="enforce", fail="open", egress_filter=object())
        gateway = _gateway_with_guard(guard)
        live = FakeLiveCall()
        verdict, reason = await gateway._shoav_decide_click(
            expected_ref=None, hit=_missing_hit(), selector_only=True, coord_only=False
        )
        self.assertEqual(verdict, "ESCALATE")
        await gateway._shoav_emit(
            live, stage="egress", tool="browser.execute_action", verdict=verdict,
            reason=reason, enforced=True,
        )
        self.assertEqual(guard.counters["egress_escalate"], 1)
        self.assertEqual(len(live.events), 1)
        self.assertEqual(live.events[0]["stage"], "egress")
        self.assertEqual(live.events[0]["verdict"], "ESCALATE")


if __name__ == "__main__":
    unittest.main()
