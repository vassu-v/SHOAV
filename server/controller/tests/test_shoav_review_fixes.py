"""Regression tests for the gateway review findings (S1, S5 to S8, S10 to S13).

Fakes only (no browser, no network). Each test names the finding it pins.
These cover the server integration layer that calls the detector, not the
detector's own rules in guard/filters.
"""

from __future__ import annotations

import json
import logging
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.action_errors import BrowserActionError
from app.browser.services.actions import BrowserActionService
from app.guard.guard import GuardUnavailableError, ShoavGuard
from app.guard.loader import _ensure_sys_path, resolve_shoav_root
from app.models import McpToolCallRequest
from app.tool_gateway import McpToolGateway
from app.tool_gateway import gateway as gateway_module

# The flood override tests patch filters.ingress.rules, so the filter core
# must be importable regardless of test order.
_ensure_sys_path(resolve_shoav_root(None))

SID = "session-review"


class FakeLiveCall:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def guard(self, *, stage, verdict, mode, enforced, reason=None, findings=None, element_id=None):
        self.events.append({"stage": stage, "verdict": verdict, "enforced": enforced, "reason": reason})


class FakeLocator:
    def __init__(self, page: "FakePage", selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    async def scroll_into_view_if_needed(self):
        return None

    async def bounding_box(self):
        return self.page.boxes.get(self.selector)

    async def get_attribute(self, name):
        return self.page.attributes.get((self.selector, name))

    async def evaluate(self, script, *args, **kwargs):
        self.page.locator_evals.append(self.selector)
        return self.page.submit_info.get(self.selector)


class FakePage:
    def __init__(self) -> None:
        self.boxes: dict[str, dict] = {}
        self.attributes: dict = {}
        self.submit_info: dict[str, dict] = {}
        self.locator_evals: list[str] = []
        self.evaluate_result = None

    def locator(self, selector):
        return FakeLocator(self, selector)

    async def evaluate(self, script, *args):
        if callable(self.evaluate_result):
            return self.evaluate_result(script, *args)
        return self.evaluate_result


def make_gateway(guard, page: FakePage | None = None, fail: str = "open"):
    page = page or FakePage()
    session = SimpleNamespace(page=page)
    manager = SimpleNamespace(
        get_session=AsyncMock(return_value=session),
        list_sessions=AsyncMock(return_value=[{"id": SID}]),
        execute_decision=AsyncMock(return_value={"action": "click", "ok": True}),
        settings=SimpleNamespace(mcp_tool_name_style="dotted", shoav_guard_fail=fail),
    )
    gateway = McpToolGateway(manager=manager, orchestrator=SimpleNamespace(), job_queue=SimpleNamespace(), guard=guard)
    return gateway, manager, page


class SubmissionGuard(ShoavGuard):
    """Real ShoavGuard counters; deterministic submission and click answers."""

    def __init__(self, mode: str = "enforce", fail: str = "open") -> None:
        super().__init__(mode=mode, fail=fail, egress_filter=object())

    def decide_egress(self, args):
        args = dict(args or {})
        if args.get("check") == "submission":
            touched = set(args.get("touched") or [])
            flags = [i for i in args.get("snapshot") or [] if i.get("checked") and i.get("ref") not in touched]
            if flags:
                return {"verdict": "ESCALATE", "reason": "untouched pre-checked field", "flags": flags}
            return {"verdict": "ALLOW", "reason": "clean", "flags": []}
        return {"verdict": "ALLOW", "reason": "click probe clean."}


def seed_prechecked(gateway):
    state = gateway._shoav_state(SID)
    state["form_snapshot"] = [{"ref": "op-s1", "type": "checkbox", "checked": True, "label": "marketing"}]
    state["last_origin_path"] = "http://127.0.0.1/prechecked.html"


def click(element_id=None, selector=None):
    action = {"action": "click", "reason": "test"}
    if element_id:
        action["element_id"] = element_id
    if selector:
        action["selector"] = selector
    return McpToolCallRequest(name="browser.execute_action", arguments={"session_id": SID, "action": action})


FORM_SUBMIT = {"tag": "button", "type": "", "in_form": True, "form_submit": True, "text": "Submit"}
PLAIN_BUTTON = {"tag": "button", "type": "button", "in_form": True, "form_submit": False, "text": "Show details"}


class S1ElementIdSubmitTests(unittest.IsolatedAsyncioTestCase):
    async def test_element_id_click_probes_live_dom_when_cache_misses(self):
        gateway, manager, page = make_gateway(SubmissionGuard())
        seed_prechecked(gateway)  # interactables cache stays empty (snapshot only flow)
        page.submit_info['[data-operator-id="op-s3"]'] = FORM_SUBMIT
        response = await gateway.call_tool(click(element_id="op-s3"))
        self.assertTrue(response.isError)
        self.assertIn("ESCALATE", response.content[0].text)
        self.assertIn('[data-operator-id="op-s3"]', page.locator_evals)
        manager.execute_decision.assert_not_awaited()

    async def test_ref_selector_escapes_quotes(self):
        self.assertEqual(gateway_module._shoav_ref_selector('a"b'), '[data-operator-id="a\\"b"]')


class S12SubmitDefinitionTests(unittest.IsolatedAsyncioTestCase):
    async def test_type_button_near_prechecked_box_is_not_a_submit(self):
        gateway, manager, page = make_gateway(SubmissionGuard())
        seed_prechecked(gateway)
        page.submit_info["#details"] = PLAIN_BUTTON
        response = await gateway.call_tool(click(selector="#details"))
        self.assertFalse(response.isError, response.content[0].text)
        manager.execute_decision.assert_awaited_once()

    def test_submit_from_info(self):
        decide = McpToolGateway._shoav_submit_from_info
        self.assertTrue(decide(FORM_SUBMIT))
        self.assertFalse(decide(PLAIN_BUTTON))
        self.assertFalse(decide({"tag": "button", "type": "", "in_form": False, "form_submit": False, "text": "Go"}))
        self.assertFalse(decide({"tag": "input", "type": "text", "form_submit": False, "text": "submit"}))
        self.assertTrue(decide({"tag": "div", "type": "", "form_submit": False, "text": "Place order"}))
        self.assertFalse(decide({"tag": "a", "type": "", "form_submit": False, "text": "Accept cookies"}))

    def test_cache_fallback_does_not_treat_type_button_as_submit(self):
        gateway, _, _ = make_gateway(SubmissionGuard())
        state = gateway._shoav_state(SID)
        state["interactables"] = [
            {"element_id": "op-b", "type": "button", "label": "Accept cookies"},
            {"element_id": "op-s", "type": "submit", "label": "Go"},
        ]
        self.assertFalse(gateway._shoav_is_submit_control(SID, "op-b"))
        self.assertTrue(gateway._shoav_is_submit_control(SID, "op-s"))


class S5CountingTests(unittest.IsolatedAsyncioTestCase):
    def test_guard_decide_helpers_do_not_count(self):
        class Egress:
            def verify_click(self, ref, hit):
                return {"verdict": "ALLOW", "reason": "ok"}

            def verify_input(self, ref, value, focus):
                return {"verdict": "BLOCK", "reason": "no"}

        class Ingress:
            def process(self, payload, **kwargs):
                return {"verdict": "REWRITE", "payload": payload}

        guard = ShoavGuard(mode="enforce", ingress_filter=Ingress(), egress_filter=Egress())
        guard.decide_egress({"expected_ref": "op-1", "hit_result": {"found": True}})
        guard.decide_egress({"check": "input", "expected_ref": "op-1", "focus_result": {"found": True}})
        guard.decide_ingress({"text_excerpt": "hello"})
        verdict_keys = [k for k in guard.counters if k not in ("errors", "fail_open")]
        self.assertEqual({k: guard.counters[k] for k in verdict_keys}, dict.fromkeys(verdict_keys, 0))

    async def test_one_call_counts_each_stage_once_with_most_severe_verdict(self):
        guard = SubmissionGuard()
        gateway, _, _ = make_gateway(guard)
        token = gateway_module._SHOAV_CALL_TALLY.set({})
        try:
            for stage, verdict in (("egress", "ALLOW"), ("egress", "ALLOW"), ("posthoc", "ESCALATE"), ("ingress", "REWRITE")):
                await gateway._shoav_emit(None, stage=stage, tool="t", verdict=verdict, reason="r")
            self.assertEqual(guard.counters["egress_allow"], 0, "nothing counted before the call ends")
            gateway._shoav_flush_tally(gateway_module._SHOAV_CALL_TALLY.get())
        finally:
            gateway_module._SHOAV_CALL_TALLY.reset(token)
        self.assertEqual(guard.counters["egress_escalate"], 1)
        self.assertEqual(guard.counters["egress_allow"], 0)
        self.assertEqual(guard.counters["ingress_rewrite"], 1)

    async def test_submit_click_moves_exactly_one_egress_counter_by_one(self):
        guard = SubmissionGuard()
        gateway, _, page = make_gateway(guard)
        seed_prechecked(gateway)
        gateway._shoav_state(SID)["touched"] = {"op-s1"}
        page.submit_info['[data-operator-id="op-s3"]'] = FORM_SUBMIT
        response = await gateway.call_tool(click(element_id="op-s3"))
        self.assertFalse(response.isError, response.content[0].text)
        egress = {k: v for k, v in guard.counters.items() if k.startswith("egress_")}
        self.assertEqual(sum(egress.values()), 1, egress)
        self.assertEqual(egress["egress_allow"], 1)

    async def test_blocked_submit_counts_one_escalate(self):
        guard = SubmissionGuard()
        gateway, _, page = make_gateway(guard)
        seed_prechecked(gateway)
        page.submit_info['[data-operator-id="op-s3"]'] = FORM_SUBMIT
        await gateway.call_tool(click(element_id="op-s3"))
        egress = {k: v for k, v in guard.counters.items() if k.startswith("egress_")}
        self.assertEqual(egress, {"egress_allow": 0, "egress_block": 0, "egress_escalate": 1})

    async def test_flood_override_counts_final_block_not_prior_verdict(self):
        class Ingress:
            def process(self, payload, **kwargs):
                return {"verdict": "REWRITE", "payload": payload}

        guard = ShoavGuard(mode="enforce", ingress_filter=Ingress())
        gateway, _, _ = make_gateway(guard)

        async def payload(*_a, **_k):
            return {"tool": "browser.observe", "text_excerpt": "x", "raw_element_count": 10}

        gateway._shoav_build_ingress_payload = payload
        with patch("filters.ingress.rules.evaluate_flood_signal", return_value=(True, "flood")):
            spec = SimpleNamespace(name="browser.observe")
            args = SimpleNamespace(session_id=None, preset="text")
            token = gateway_module._SHOAV_CALL_TALLY.set({})
            try:
                resp = await gateway._shoav_ingress_check(spec, args, {"text_excerpt": "x"}, None)
                gateway._shoav_flush_tally(gateway_module._SHOAV_CALL_TALLY.get())
            finally:
                gateway_module._SHOAV_CALL_TALLY.reset(token)
        self.assertTrue(resp.isError)
        self.assertEqual(guard.counters["ingress_block"], 1)
        self.assertEqual(guard.counters["ingress_rewrite"], 0)


class S6NavigationOrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_page_state_survives_navigation_reset(self):
        class Ingress:
            def process(self, payload, **kwargs):
                return {"verdict": "ALLOW", "payload": payload}

        gateway, _, _ = make_gateway(ShoavGuard(mode="enforce", ingress_filter=Ingress()))
        state = gateway._shoav_state(SID)
        state["last_origin_path"] = "http://127.0.0.1/a.html"
        state["form_snapshot"] = [{"ref": "old", "checked": True, "label": "old page"}]
        state["touched"] = {"old"}
        new_controls = [{"ref": "op-new", "type": "checkbox", "checked": True, "label": "newsletter"}]

        async def payload(*_a, **_k):
            return {"tool": "browser.snapshot", "text": "t", "form_controls": new_controls}

        gateway._shoav_build_ingress_payload = payload
        spec = SimpleNamespace(name="browser.snapshot")
        result = {"url": "http://127.0.0.1/b.html", "_mcp_text": "t"}
        await gateway._shoav_ingress_check(spec, SimpleNamespace(session_id=SID), result, None)
        state = gateway._shoav_state(SID)
        self.assertEqual(state["last_origin_path"], "http://127.0.0.1/b.html")
        self.assertEqual([i["ref"] for i in state["form_snapshot"]], ["op-new"])
        self.assertEqual(state["touched"], set())


class S13IngressEscalateTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, mode):
        class Ingress:
            def process(self, payload, **kwargs):
                return {"verdict": "ESCALATE", "payload": payload, "telemetry": "suspicious page"}

        gateway, _, _ = make_gateway(ShoavGuard(mode=mode, ingress_filter=Ingress()))

        async def payload(*_a, **_k):
            return {"tool": "browser.get_html", "text": "t", "text_excerpt": "t"}

        gateway._shoav_build_ingress_payload = payload
        result = {"content": "t"}
        live = FakeLiveCall()
        resp = await gateway._shoav_ingress_check(
            SimpleNamespace(name="browser.get_html"), SimpleNamespace(session_id=SID), result, live
        )
        return resp, result, live

    async def test_enforce_withholds_result_with_guidance(self):
        resp, _, live = await self._run("enforce")
        self.assertTrue(resp.isError)
        self.assertEqual(resp.structuredContent["shoav"]["verdict"], "ESCALATE")
        self.assertIn("human takeover", resp.content[0].text)
        self.assertTrue(live.events[0]["enforced"])

    async def test_observe_notes_without_blocking(self):
        resp, result, _ = await self._run("observe")
        self.assertIsNone(resp)
        self.assertEqual(result["_shoav"]["verdict"], "ESCALATE")


class S7SensitiveFocusTests(unittest.IsolatedAsyncioTestCase):
    async def test_attribute_selector_without_verified_match_blocks(self):
        gateway, _, _ = make_gateway(SubmissionGuard())
        verdict, _ = await gateway._shoav_decide_input(
            "[name=pw]", "secret", {"found": True, "ref": None, "type": "text"}, sensitive=True
        )
        self.assertEqual(verdict, "BLOCK")

    async def test_verified_selector_match_allows(self):
        gateway, _, _ = make_gateway(SubmissionGuard())
        verdict, _ = await gateway._shoav_decide_input(
            "[name=pw]", "secret", {"found": True, "ref": "[name=pw]", "type": "password"}, sensitive=True
        )
        self.assertEqual(verdict, "ALLOW")

    async def test_type_check_runs_real_match_for_attribute_selector(self):
        page = FakePage()
        matches = {"value": False}

        def evaluate(script, *args):
            if "el.matches(sel)" in script:
                return matches["value"]
            return {"found": True, "ref": None, "type": "password", "value": None}

        page.evaluate_result = evaluate
        gateway, _, _ = make_gateway(SubmissionGuard(), page)
        decision = SimpleNamespace(element_id=None, selector="[name=pw]", text="secret", sensitive=True, clear_first=True)
        blocked = await gateway._shoav_type_check(SID, decision, None, "enforce")
        self.assertIsNotNone(blocked, "focus on some other element must block")
        matches["value"] = True
        self.assertIsNone(await gateway._shoav_type_check(SID, decision, None, "enforce"))


class S8InputValueTests(unittest.TestCase):
    ok = staticmethod(McpToolGateway._shoav_input_value_ok)

    def test_accepts_correct_actions(self):
        self.assertTrue(self.ok("bob", "alicebob", clear_first=False, multiline=False, max_length=None))
        self.assertTrue(self.ok("bob", "bob", clear_first=True, multiline=False, max_length=None))
        self.assertTrue(self.ok("5551234567", "(555) 123-4567", clear_first=True, multiline=False, max_length=None))
        self.assertTrue(self.ok("ABCDEF", "ABC", clear_first=True, multiline=False, max_length=3))
        self.assertTrue(self.ok("hello world", "hello world\n", clear_first=True, multiline=True, max_length=None))
        self.assertTrue(self.ok("go\n", "go", clear_first=True, multiline=False, max_length=None))

    def test_rejects_tampered_values(self):
        self.assertFalse(self.ok("bob", "mallory", clear_first=True, multiline=False, max_length=None))
        self.assertFalse(self.ok("bob", "alice", clear_first=False, multiline=False, max_length=None))
        self.assertFalse(self.ok("ABCDEF", "XYZ", clear_first=True, multiline=False, max_length=3))
        self.assertFalse(self.ok("bob", None, clear_first=True, multiline=False, max_length=None))
        self.assertFalse(self.ok("hello", "attacker text", clear_first=True, multiline=True, max_length=None))


class S11FailPolicyTests(unittest.IsolatedAsyncioTestCase):
    def _settings(self, fail):
        empty = tempfile.mkdtemp()
        return SimpleNamespace(shoav_guard_mode="enforce", shoav_guard_fail=fail, shoav_filters_path=empty)

    def test_fail_closed_refuses_to_start_without_filters(self):
        with self.assertRaises(GuardUnavailableError):
            ShoavGuard.from_settings(self._settings("closed"))

    def test_fail_open_returns_none_and_logs_error(self):
        with self.assertLogs("app.guard.guard", level=logging.ERROR):
            self.assertIsNone(ShoavGuard.from_settings(self._settings("open")))

    async def test_probe_failure_blocks_when_fail_closed(self):
        gateway, manager, _ = make_gateway(SubmissionGuard(fail="closed"), fail="closed")
        response = await gateway.call_tool(click(selector="#nowhere"))
        self.assertTrue(response.isError)
        self.assertEqual(response.structuredContent["shoav"]["verdict"], "BLOCK")
        manager.execute_decision.assert_not_awaited()

    async def test_probe_failure_allows_when_fail_open(self):
        gateway, manager, _ = make_gateway(SubmissionGuard())
        response = await gateway.call_tool(click(selector="#nowhere"))
        self.assertFalse(response.isError)
        manager.execute_decision.assert_awaited_once()


class KeyboardSubmitTests(unittest.IsolatedAsyncioTestCase):
    def test_enter_variants(self):
        is_enter = gateway_module._shoav_is_enter_key
        for key in ("Enter", "NumpadEnter", "Control+Enter", "Shift+Enter", "Return"):
            self.assertTrue(is_enter(key), key)
        for key in ("Tab", "a", "", None, "Enter+a"):
            self.assertFalse(is_enter(key), key)

    async def test_numpad_enter_and_typed_newline_are_prechecked(self):
        for action in (
            {"action": "press", "reason": "t", "key": "NumpadEnter"},
            # Interior newline: the input model strips leading and trailing
            # whitespace, so only an interior one reaches the keyboard.
            {"action": "type", "reason": "t", "selector": "#q", "text": "hello\nworld"},
        ):
            gateway, manager, _ = make_gateway(SubmissionGuard())
            seed_prechecked(gateway)
            response = await gateway.call_tool(
                McpToolCallRequest(name="browser.execute_action", arguments={"session_id": SID, "action": action})
            )
            self.assertTrue(response.isError, action)
            self.assertIn("ESCALATE", response.content[0].text)
            manager.execute_decision.assert_not_awaited()


class DragCheckTests(unittest.IsolatedAsyncioTestCase):
    async def _drag(self, hit):
        page = FakePage()
        page.evaluate_result = hit
        guard = SubmissionGuard()
        gateway, _, _ = make_gateway(guard, page)
        args = SimpleNamespace(
            session_id=SID, source_selector=None, source_x=1, source_y=1,
            target_selector=None, target_x=5, target_y=5,
        )
        live = FakeLiveCall()
        resp = await gateway._shoav_drag_check(args, live, "enforce")
        return resp, live, guard

    async def test_clean_drag_emits_one_allow(self):
        resp, live, guard = await self._drag({"found": True, "inside_target": None, "opacity": 1, "z_index": "0"})
        self.assertIsNone(resp)
        self.assertEqual([e["verdict"] for e in live.events], ["ALLOW"])
        self.assertEqual(guard.counters["egress_allow"], 1)

    async def test_escalate_drag_is_blocked_in_enforce(self):
        resp, live, _ = await self._drag({"found": False})
        self.assertTrue(resp.isError)
        self.assertEqual(resp.structuredContent["shoav"]["verdict"], "ESCALATE")
        self.assertEqual(len(live.events), 1)


class FloodFanoutForwardingTests(unittest.TestCase):
    def test_probe_facts_forwarded(self):
        payload: dict = {}
        McpToolGateway._shoav_add_flood_facts(payload, {"element_count": 730, "text_chars": 9, "interactive_fanout": 720})
        self.assertEqual(payload, {"raw_element_count": 730, "raw_text_chars": 9, "raw_interactive_fanout": 720})

    def test_override_passes_fanout_when_rule_accepts_it(self):
        seen = {}

        def rule(raw_element_count=None, raw_text_chars=None, raw_interactive_fanout=None, mutations_per_second=None):
            seen["fanout"] = raw_interactive_fanout
            return raw_interactive_fanout and raw_interactive_fanout > 100, "fanout"

        with patch("filters.ingress.rules.evaluate_flood_signal", rule):
            out = McpToolGateway._shoav_apply_live_flood_override(
                {"raw_interactive_fanout": 720}, {"verdict": "REWRITE"}
            )
        self.assertEqual(seen["fanout"], 720)
        self.assertEqual(out["verdict"], "BLOCK")

    def test_override_tolerates_older_rule_without_fanout(self):
        def rule(raw_element_count=None, raw_text_chars=None, mutations_per_second=None):
            return False, ""

        with patch("filters.ingress.rules.evaluate_flood_signal", rule):
            out = McpToolGateway._shoav_apply_live_flood_override(
                {"raw_interactive_fanout": 720}, {"verdict": "ALLOW"}
            )
        self.assertEqual(out["verdict"], "ALLOW")


class S10DispatchRecheckTests(unittest.IsolatedAsyncioTestCase):
    def _service(self, mode="enforce"):
        manager = SimpleNamespace(settings=SimpleNamespace(
            shoav_guard_mode=mode, default_viewport_width=800, default_viewport_height=600,
        ))
        return BrowserActionService(manager)

    async def test_recheck_runs_after_mouse_move_and_before_mousedown(self):
        order: list[str] = []

        class Mouse:
            async def move(self, x, y):
                if not order or order[-1] != "move":
                    order.append("move")

            async def down(self):
                order.append("down")

            async def up(self):
                order.append("up")

        session = SimpleNamespace(page=SimpleNamespace(mouse=Mouse()), mouse_position=(0, 0))

        async def verify(x, y):
            order.append("verify")

        await self._service().click_human_like(session, 10, 10, verify=verify)
        self.assertEqual(order, ["move", "verify", "down", "up"])

    async def test_swapped_in_overlay_aborts_click(self):
        class Locator:
            async def evaluate(self, script, arg, timeout=None):
                return {"ok": False, "tag": "DIV", "opacity": "0", "z_index": "999999"}

        service = self._service()
        verify = service.overlay_recheck(SimpleNamespace(page=None), Locator())
        with self.assertRaises(BrowserActionError) as ctx:
            await verify(10, 10)
        self.assertEqual(ctx.exception.code, "shoav_overlay_recheck")
        self.assertIn("human takeover", ctx.exception.message)

    async def test_clean_target_passes(self):
        class Locator:
            async def evaluate(self, script, arg, timeout=None):
                return {"ok": True, "tag": "BUTTON"}

        verify = self._service().overlay_recheck(SimpleNamespace(page=None), Locator())
        await verify(10, 10)

    def test_recheck_only_in_enforce(self):
        self.assertTrue(self._service("enforce").guard_recheck_enabled())
        self.assertFalse(self._service("observe").guard_recheck_enabled())
        self.assertFalse(self._service("off").guard_recheck_enabled())

    async def test_gateway_counts_recheck_abort_as_egress_block(self):
        guard = SubmissionGuard()
        gateway, manager, page = make_gateway(guard)
        page.boxes["#buy"] = {"x": 0, "y": 0, "width": 10, "height": 10}
        page.evaluate_result = {"found": True, "inside_target": True, "tag": "BUTTON", "opacity": 1, "z_index": "0"}
        manager.execute_decision.side_effect = BrowserActionError("aborted", code="shoav_overlay_recheck", action="click")
        response = await gateway.call_tool(click(selector="#buy"))
        self.assertTrue(response.isError)
        self.assertEqual(guard.counters["egress_block"], 1)
        self.assertEqual(guard.counters["egress_allow"], 0)


if __name__ == "__main__":
    unittest.main()
