"""T-2 guard hook tests with fake gateway (no real controller).

Spec source: shoav-mcp/MCP/plan.md sections 5-6.
Semantics:
- off: no guard object, zero overhead.
- observe: run filters, emit guard events and a _shoav note, never block
  or rewrite.
- enforce: apply REWRITE and BLOCK.
- Fail open on filter exceptions (log and emit a guard note) unless
  SHOAV_GUARD_FAIL=closed.
- Egress hook runs before the handler; ingress hook runs after the handler
  and rewrites the result dict before _pack_result.

All doubles are local fakes. No controller imports, no network.
"""

import unittest


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeFilterEngine:
    """Minimal stand in for IngressFilter/EgressFilter decisions."""

    def __init__(self, ingress_verdict="ALLOW", egress_verdict="ALLOW", boom=False):
        self.ingress_verdict = ingress_verdict
        self.egress_verdict = egress_verdict
        self.boom = boom
        self.calls = []

    def ingress(self, payload):
        self.calls.append(("ingress", payload))
        if self.boom:
            raise RuntimeError("filter boom")
        if self.ingress_verdict == "REWRITE":
            return {"verdict": "REWRITE", "findings": 1, "summary": "cleaned"}
        if self.ingress_verdict == "BLOCK":
            return {"verdict": "BLOCK", "reason": "flood"}
        return {"verdict": "ALLOW"}

    def egress(self, args):
        self.calls.append(("egress", args))
        if self.boom:
            raise RuntimeError("filter boom")
        if self.egress_verdict == "BLOCK":
            return {"verdict": "BLOCK", "reason": "overlay"}
        if self.egress_verdict == "ESCALATE":
            return {"verdict": "ESCALATE", "reason": "needs human"}
        return {"verdict": "ALLOW"}


class FakeLiveCall:
    def __init__(self):
        self.events = []

    def guard(self, **kw):
        self.events.append(dict(kw))


class FakeGateway:
    """Mirrors spec hook order: egress before handler, ingress after."""

    INGRESS_TOOLS = {"browser.observe", "browser.snapshot",
                     "browser.find_elements", "browser.get_html"}
    EGRESS_TOOLS = {"browser.execute_action", "browser.drag_drop"}

    def __init__(self, guard_mode="off", engine=None, fail="open"):
        self.guard_mode = guard_mode
        self.engine = engine or FakeFilterEngine()
        self.fail = fail
        self.live = FakeLiveCall()
        self.handler_calls = []

    def _call_tool(self, tool, arguments, handler):
        # Egress hook (before handler).
        if tool in self.EGRESS_TOOLS and self.guard_mode != "off":
            try:
                dec = self.engine.egress(arguments)
            except Exception as exc:
                self.live.guard(tool=tool, stage="egress", verdict="ALLOW",
                                mode=self.guard_mode, enforced=False,
                                reason="fail-open: %s" % exc)
                if self.fail == "closed":
                    return self._block(tool, "egress", "filter failure")
                dec = {"verdict": "ALLOW"}
            if dec["verdict"] in ("BLOCK", "ESCALATE") and self.guard_mode == "enforce":
                return self._block(tool, "egress", dec.get("reason", ""), verdict=dec["verdict"])

        # Handler runs.
        result = handler(arguments)
        self.handler_calls.append(tool)

        # Ingress hook (after handler, before pack).
        if tool in self.INGRESS_TOOLS and self.guard_mode != "off":
            if arguments.get("preset") == "fast" and tool == "browser.observe":
                return result
            try:
                dec = self.engine.ingress(arguments)
            except Exception as exc:
                self.live.guard(tool=tool, stage="ingress", verdict="ALLOW",
                                mode=self.guard_mode, enforced=False,
                                reason="fail-open: %s" % exc)
                if self.fail == "closed":
                    return self._block(tool, "ingress", "filter failure")
                result.setdefault("_shoav", {"verdict": "ALLOW", "note": "filter error"})
                return result
            if dec["verdict"] == "BLOCK" and self.guard_mode == "enforce":
                return self._block(tool, "ingress", dec.get("reason", "blocked"))
            if dec["verdict"] == "REWRITE" and self.guard_mode == "enforce":
                out = {"_shoav": {"verdict": "REWRITE", "findings": dec.get("findings", 1),
                                  "summary": dec.get("summary", "")}}
                out.update(result)
                self.live.guard(tool=tool, stage="ingress", verdict="REWRITE",
                                mode=self.guard_mode, enforced=True, reason="rewritten")
                return out
            # Observe mode: never block or rewrite, only note.
            if dec["verdict"] in ("REWRITE", "BLOCK", "ESCALATE"):
                result = dict(result)
                result["_shoav"] = {"verdict": dec["verdict"], "note": "observed only",
                                    "enforced": False}
                self.live.guard(tool=tool, stage="ingress", verdict=dec["verdict"],
                                mode=self.guard_mode, enforced=False, reason="observed")
        return result

    def _block(self, tool, stage, reason, verdict="BLOCK"):
        body = {"error": str(reason), "shoav": {"verdict": verdict, "tool": tool}}
        self.live.guard(tool=tool, stage=stage, verdict=verdict,
                        mode=self.guard_mode, enforced=True, reason=str(reason))
        return {"isError": True, "content_text": body, "structured": body}


def ok_handler(arguments):
    return {"content": "hello", "_mcp_text": "hello"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestObserveModeNeverBlocks(unittest.TestCase):
    def test_observe_ingress_rewrite_is_note_only(self):
        gw = FakeGateway(guard_mode="observe",
                         engine=FakeFilterEngine(ingress_verdict="REWRITE"))
        res = gw._call_tool("browser.snapshot", {}, ok_handler)
        self.assertNotIn("isError", res)
        self.assertIn("_shoav", res)
        self.assertFalse(res["_shoav"].get("enforced", True))
        self.assertEqual(res.get("content"), "hello")

    def test_observe_ingress_block_is_note_only(self):
        gw = FakeGateway(guard_mode="observe",
                         engine=FakeFilterEngine(ingress_verdict="BLOCK"))
        res = gw._call_tool("browser.snapshot", {}, ok_handler)
        self.assertNotIn("isError", res)
        self.assertIn("_shoav", res)

    def test_observe_egress_block_still_runs_handler(self):
        gw = FakeGateway(guard_mode="observe",
                         engine=FakeFilterEngine(egress_verdict="BLOCK"))
        res = gw._call_tool("browser.execute_action", {"action": "click"}, ok_handler)
        self.assertIn("browser.execute_action", gw.handler_calls)
        self.assertNotIn("isError", res)

    def test_observe_emits_guard_event(self):
        gw = FakeGateway(guard_mode="observe",
                         engine=FakeFilterEngine(ingress_verdict="REWRITE"))
        gw._call_tool("browser.snapshot", {}, ok_handler)
        self.assertTrue(len(gw.live.events) >= 1)
        self.assertFalse(gw.live.events[0].get("enforced", True))


class TestEnforceMode(unittest.TestCase):
    def test_enforce_rewrite_puts_shoav_first(self):
        gw = FakeGateway(guard_mode="enforce",
                         engine=FakeFilterEngine(ingress_verdict="REWRITE"))
        res = gw._call_tool("browser.snapshot", {}, ok_handler)
        self.assertEqual(next(iter(res)), "_shoav")
        self.assertEqual(res["_shoav"]["verdict"], "REWRITE")

    def test_enforce_block_returns_error_first(self):
        gw = FakeGateway(guard_mode="enforce",
                         engine=FakeFilterEngine(ingress_verdict="BLOCK"))
        res = gw._call_tool("browser.snapshot", {}, ok_handler)
        self.assertTrue(res["isError"])
        self.assertEqual(next(iter(res["structured"])), "error")

    def test_enforce_egress_block_aborts_before_handler(self):
        gw = FakeGateway(guard_mode="enforce",
                         engine=FakeFilterEngine(egress_verdict="BLOCK"))
        res = gw._call_tool("browser.execute_action", {"action": "click"}, ok_handler)
        self.assertTrue(res["isError"])
        self.assertNotIn("browser.execute_action", gw.handler_calls)

    def test_enforce_escalate_returns_error(self):
        gw = FakeGateway(guard_mode="enforce",
                         engine=FakeFilterEngine(egress_verdict="ESCALATE"))
        res = gw._call_tool("browser.execute_action", {"action": "click"}, ok_handler)
        self.assertTrue(res["isError"])
        self.assertEqual(res["structured"]["shoav"]["verdict"], "ESCALATE")


class TestOffMode(unittest.TestCase):
    def test_off_runs_handler_untouched(self):
        gw = FakeGateway(guard_mode="off",
                         engine=FakeFilterEngine(ingress_verdict="BLOCK",
                                                 egress_verdict="BLOCK"))
        res = gw._call_tool("browser.snapshot", {}, ok_handler)
        self.assertEqual(res, {"content": "hello", "_mcp_text": "hello"})
        self.assertEqual(gw.live.events, [])

    def test_off_egress_runs_handler(self):
        gw = FakeGateway(guard_mode="off",
                         engine=FakeFilterEngine(egress_verdict="BLOCK"))
        gw._call_tool("browser.execute_action", {}, ok_handler)
        self.assertIn("browser.execute_action", gw.handler_calls)


class TestFailOpen(unittest.TestCase):
    def test_fail_open_ingress(self):
        gw = FakeGateway(guard_mode="enforce",
                         engine=FakeFilterEngine(boom=True), fail="open")
        res = gw._call_tool("browser.snapshot", {}, ok_handler)
        self.assertNotIn("isError", res)

    def test_fail_closed_ingress(self):
        gw = FakeGateway(guard_mode="enforce",
                         engine=FakeFilterEngine(boom=True), fail="closed")
        res = gw._call_tool("browser.snapshot", {}, ok_handler)
        self.assertTrue(res["isError"])

    def test_fail_open_egress_runs_handler(self):
        gw = FakeGateway(guard_mode="enforce",
                         engine=FakeFilterEngine(boom=True), fail="open")
        gw._call_tool("browser.execute_action", {}, ok_handler)
        self.assertIn("browser.execute_action", gw.handler_calls)


class TestHookOrder(unittest.TestCase):
    def test_screenshot_skipped(self):
        gw = FakeGateway(guard_mode="enforce",
                         engine=FakeFilterEngine(ingress_verdict="BLOCK"))
        res = gw._call_tool("browser.screenshot", {}, ok_handler)
        self.assertNotIn("isError", res)

    def test_observe_fast_preset_skipped(self):
        gw = FakeGateway(guard_mode="enforce",
                         engine=FakeFilterEngine(ingress_verdict="REWRITE"))
        res = gw._call_tool("browser.observe", {"preset": "fast"}, ok_handler)
        self.assertNotIn("_shoav", res)


if __name__ == "__main__":
    unittest.main()
