"""In-process live-wiring proof for gateway egress/live probes (no server/browser).

Docs ports in this file use http://127.0.0.1:18501 (controller) and
http://127.0.0.1:18631 (fixtures) only.

Covers, with a fake session whose async page.evaluate returns canned probe
payloads and gateway.py functions driven directly:
- (3) overlay element_id -> [data-operator-id] scroll/bbox/hit/verify BLOCKs,
  benign ALLOWs, unstamped element_id falls back to the selector runner flow.
- (4) FORM_STATE_SCRIPT evaluated live feeds form_controls to the engine;
  touched on click/select/type(/fill); submit/Enter verify_submission
  ESCALATEs; nav/close resets. Proved against fixtures/prechecked.html text.
- (5) FLOOD_PROBE raw counts pre-caps plus mutation feed live;
  fixtures/flood.html shape BLOCKs, benign ALLOWs.

Synthetic fixtures only. Fail-open unless closed. Target 5 untouched.
"""

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CONTROLLER = ROOT / "MCP" / "auto-browser" / "controller"
if str(CONTROLLER) not in sys.path:
    sys.path.insert(0, str(CONTROLLER))

from filters.egress.engine import EgressFilter  # noqa: E402
from filters.ingress.engine import IngressFilter  # noqa: E402
from filters.types import Verdict  # noqa: E402


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class FakeLocator:
    def __init__(self, box=None, ref=None):
        self._box = box
        self._ref = ref

    @property
    def first(self):
        return self

    async def scroll_into_view_if_needed(self):
        return None

    async def bounding_box(self):
        return dict(self._box) if isinstance(self._box, dict) else None

    async def get_attribute(self, name):
        if name == "data-operator-id":
            return self._ref
        return None


class FakePage:
    def __init__(self, *, boxes=None, refs=None, hit=None, form_controls=None,
                 flood=None, mutation=None, raise_on=None):
        self.boxes = dict(boxes or {})
        self.refs = dict(refs or {})
        self.hit = hit
        self.form_controls = form_controls
        self.flood = flood
        self.mutation = mutation
        self.raise_on = raise_on
        self.seen_scripts = []

    def locator(self, selector):
        return FakeLocator(box=self.boxes.get(selector), ref=self.refs.get(selector))

    async def evaluate(self, script, arg=None):
        self.seen_scripts.append(script if isinstance(script, str) else "")
        text = script if isinstance(script, str) else ""
        if self.raise_on and self.raise_on in text:
            raise RuntimeError("probe boom")
        if "elementFromPoint" in text:
            return dict(self.hit) if isinstance(self.hit, dict) else None
        if "MutationObserver" in text and "__shoavMutCount" in text:
            return {"installed": True}
        if "__shoavMutCount" in text:
            return dict(self.mutation) if isinstance(self.mutation, dict) else None
        if "element_count" in text or "querySelectorAll('*').length" in text:
            return dict(self.flood) if isinstance(self.flood, dict) else None
        if "checkbox" in text or "operatorId" in text:
            return list(self.form_controls) if isinstance(self.form_controls, list) else None
        return None


class FakeSession:
    def __init__(self, page):
        self.page = page


class FakeManager:
    def __init__(self, page):
        self._page = page
        self.settings = SimpleNamespace(mcp_tool_name_style="dotted")

    async def get_session(self, session_id):
        return FakeSession(self._page)

    async def list_sessions(self):
        return []


class FakeGuard:
    mode = "enforce"


class FakeLiveCall:
    def __init__(self):
        self.events = []

    async def guard(self, **kw):
        self.events.append(dict(kw))


def _gateway(page):
    from app.tool_gateway.gateway import McpToolGateway

    gw = McpToolGateway(manager=FakeManager(page), orchestrator=object(),
                        job_queue=object(), guard=FakeGuard())
    return gw


def _click_args(session_id, action="click", element_id=None, selector=None):
    decision = SimpleNamespace(action=action, element_id=element_id,
                               selector=selector, x=None, y=None, text="",
                               key=None, sensitive=False)
    return SimpleNamespace(session_id=session_id, action=decision)


OVERLAY_HIT = {"found": True, "tag": "DIV", "ref": "evil-overlay",
               "opacity": 0.0, "z_index": "99999", "pointer_events": "auto",
               "inside_target": False}
BENIGN_HIT = {"found": True, "tag": "BUTTON", "ref": "buy-btn",
              "opacity": 1.0, "z_index": "10", "pointer_events": "auto",
              "inside_target": True}


class TestOverlayLiveProbe(unittest.TestCase):
    def test_element_id_overlay_blocks(self):
        page = FakePage(
            boxes={'[data-operator-id="buy-btn"]': {"x": 10, "y": 20, "width": 100, "height": 40}},
            hit=OVERLAY_HIT)
        gw = _gateway(page)
        spec = SimpleNamespace(name="browser.execute_action")
        args = _click_args("s1", element_id="buy-btn")
        live = FakeLiveCall()
        res = _run(gw._shoav_egress_check(spec, args, live))
        self.assertIsNotNone(res)
        self.assertTrue(res.isError)

    def test_element_id_benign_allows(self):
        page = FakePage(
            boxes={'[data-operator-id="buy-btn"]': {"x": 10, "y": 20, "width": 100, "height": 40}},
            hit=BENIGN_HIT)
        gw = _gateway(page)
        spec = SimpleNamespace(name="browser.execute_action")
        args = _click_args("s1", element_id="buy-btn")
        res = _run(gw._shoav_egress_check(spec, args, FakeLiveCall()))
        self.assertIsNone(res)

    def test_unstamped_element_id_falls_back_to_selector_runner_flow(self):
        # Product path misses (no [data-operator-id] box) but the runner
        # selector flow still sees the overlay and BLOCKs.
        page = FakePage(
            boxes={"#buy-btn": {"x": 10, "y": 20, "width": 100, "height": 40}},
            refs={"#buy-btn": "buy-btn"},
            hit=OVERLAY_HIT)
        gw = _gateway(page)
        spec = SimpleNamespace(name="browser.execute_action")
        args = _click_args("s1", element_id="buy-btn", selector="#buy-btn")
        res = _run(gw._shoav_egress_check(spec, args, FakeLiveCall()))
        self.assertIsNotNone(res)
        self.assertTrue(res.isError)

    def test_select_option_shares_click_hit_test(self):
        page = FakePage(
            boxes={'[data-operator-id="sel-1"]': {"x": 0, "y": 0, "width": 50, "height": 20}},
            hit=OVERLAY_HIT)
        gw = _gateway(page)
        spec = SimpleNamespace(name="browser.execute_action")
        args = _click_args("s1", action="select_option", element_id="sel-1")
        res = _run(gw._shoav_egress_check(spec, args, FakeLiveCall()))
        self.assertIsNotNone(res)
        self.assertTrue(res.isError)

    def test_probe_failure_fails_open(self):
        page = FakePage(boxes={}, hit=OVERLAY_HIT)
        gw = _gateway(page)
        spec = SimpleNamespace(name="browser.execute_action")
        args = _click_args("s1", element_id="ghost")
        res = _run(gw._shoav_egress_check(spec, args, FakeLiveCall()))
        self.assertIsNone(res)


class TestFormStateLiveProbe(unittest.TestCase):
    def test_prechecked_html_content_matches_canned_controls(self):
        html = (ROOT / "fixtures" / "prechecked.html").read_text(encoding="utf-8")
        self.assertIn("mkt-optin", html)
        self.assertIn("checked", html)
        self.assertIn("marketing", html.lower())

    def test_form_controls_evaluated_live_and_flagged(self):
        controls = [{"element_id": "mkt-optin", "ref": "mkt-optin", "tag": "INPUT",
                     "type": "checkbox", "checked": True,
                     "label": "Subscribe to the marketing newsletter and share my data"}]
        page = FakePage(form_controls=controls)
        gw = _gateway(page)
        live_controls = _run(gw._shoav_form_controls("s1"))
        self.assertEqual(live_controls, controls)
        payload = {"interactables": [], "text_excerpt": "Signup",
                   "accessibility_outline": {"nodes": []}}
        from filters.session_state import SessionState

        state = SessionState()
        res = IngressFilter().process(payload, form_controls=live_controls, session_state=state)
        self.assertEqual(res["verdict"], Verdict.REWRITE)
        out = EgressFilter().verify_submission(state)
        self.assertEqual(out["verdict"], Verdict.ESCALATE)

    def test_touched_submit_allows_and_nav_close_reset(self):
        from filters.session_state import SessionState

        state = SessionState()
        payload = {"interactables": [], "text_excerpt": "Signup",
                   "accessibility_outline": {"nodes": []}}
        controls = [{"ref": "mkt-optin", "type": "checkbox", "checked": True,
                     "label": "share my data with marketing partners"}]
        IngressFilter().process(payload, form_controls=controls, session_state=state)
        state.mark_touched("mkt-optin")
        self.assertEqual(EgressFilter().verify_submission(state)["verdict"], Verdict.ALLOW)
        state.reset_for_navigation()
        self.assertEqual(state.touched_refs, set())
        self.assertIsNone(state.initial_form_snapshot)

        page = FakePage(boxes={"#mkt-optin": {"x": 1, "y": 1, "width": 10, "height": 10}},
                        refs={"#mkt-optin": "mkt-optin"})
        gw = _gateway(page)
        gw._shoav_state("s1")["touched"].add("pre")
        spec = SimpleNamespace(name="browser.execute_action")
        _run(gw._shoav_posthoc_check(spec, _click_args("s1", selector="#mkt-optin"),
                                     {"url": "http://127.0.0.1:18631/prechecked.html"}, FakeLiveCall()))
        self.assertIn("mkt-optin", gw._shoav_state("s1")["touched"])
        close_spec = SimpleNamespace(name="browser.close_session")
        _run(gw._shoav_posthoc_check(close_spec, SimpleNamespace(session_id="s1"), {}, None))
        self.assertEqual(gw._shoav_state("s1")["touched"], set())


class TestFloodLiveProbe(unittest.TestCase):
    def test_flood_probe_counts_flow_pre_caps_and_block(self):
        flood = {"element_count": 720, "text_chars": 900}
        page = FakePage(flood=flood, mutation={"count": 1, "seconds": 5.0, "rate": 0.2})
        gw = _gateway(page)
        self.assertEqual(_run(gw._shoav_flood_probe("s1")), flood)
        mut = _run(gw._shoav_mutation_feed("s1"))
        self.assertIn("rate", mut)
        payload = {"interactables": [], "text_excerpt": "Catalog",
                   "accessibility_outline": {"nodes": []}}
        res = IngressFilter().process(payload, raw_element_count=720,
                                      raw_text_chars=900, mutation=mut)
        self.assertEqual(res["verdict"], Verdict.BLOCK)

    def test_flood_html_shape_blocks_benign_allows(self):
        html = (ROOT / "fixtures" / "flood.html").read_text(encoding="utf-8")
        self.assertIn("720", html)
        payload = {"interactables": [], "text_excerpt": "Catalog",
                   "accessibility_outline": {"nodes": []}}
        self.assertEqual(IngressFilter().process(
            payload, raw_element_count=720)["verdict"], Verdict.BLOCK)
        self.assertEqual(IngressFilter().process(
            payload, raw_element_count=40, raw_text_chars=800,
            mutation_rate=2.0)["verdict"], Verdict.ALLOW)


class TestProbeSingleSource(unittest.TestCase):
    def test_connectors_form_script_matches_filters_canonical(self):
        from connectors.egress_args import FORM_STATE_SCRIPT as conn
        from filters.ingress.scripts import FORM_STATE_SCRIPT as canon

        self.assertEqual(conn, canon)


if __name__ == "__main__":
    unittest.main()
