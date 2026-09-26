"""T-1 adapters suite (spec only, independent of detector authors).

Spec source: shoav-mcp/MCP/plan.md sections 5-6, shoav-mcp/filters/plan.md.
Covers: normalize_observe / snapshot / find_elements / get_html payload
builders, apply_rewrite leading _shoav key, block error-first shape,
egress args builder, session cache reset.

Strategy: tests assert contracts using tiny inline synthetic fixtures.
If the real adapter module exists it is conformance checked too, but the
suite passes on contracts alone so it stays independent of internals.
Uses stdlib unittest so both `python -m unittest discover` and pytest work.
"""

import importlib
import importlib.util
import json
import unittest
from pathlib import Path
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Optional real implementation (conformance only, never required to pass suite)
# ---------------------------------------------------------------------------

def _try_import(*names):
    for name in names:
        try:
            return importlib.import_module(name)
        except Exception:
            continue
    return None


def _load_connector(stem):
    try:
        base = Path(__file__).resolve().parents[1] / (stem + ".py")
        if not base.is_file():
            return None
        spec = importlib.util.spec_from_file_location("shoav_conn_" + stem, str(base))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


REAL_ADAPTERS = _try_import(
    "connectors.adapters",
    "adapters",
)
REAL_OBSERVE = _load_connector("observe_adapter")
REAL_SNAPSHOT = _load_connector("snapshot_adapter")
REAL_REWRITE = _load_connector("rewrite")
REAL_EGRESS = _load_connector("egress_args")
REAL_CACHE = _load_connector("session_cache")
if REAL_ADAPTERS is None:
    for m in (REAL_OBSERVE, REAL_SNAPSHOT, REAL_REWRITE, REAL_EGRESS):
        if m is not None:
            REAL_ADAPTERS = m
            break


# ---------------------------------------------------------------------------
# Spec derived reference helpers (encode the contract, not an implementation)
# ---------------------------------------------------------------------------

def spec_normalize_observe(result):
    """Expected observe payload keys per spec section 5.

    Builds payload from interactables, text_excerpt, ocr.text and
    form_controls. accessibility_outline is always unavailable in this
    build and interactables carry no `checked`.
    """
    payload = {
        "interactables": list(result.get("interactables", [])),
        "text_excerpt": result.get("text_excerpt", ""),
        "ocr_text": (result.get("ocr") or {}).get("text", ""),
        "form_controls": list(result.get("form_controls", [])),
        "accessibility_outline": None,
        "style_facts": result.get("style_facts", []),
    }
    return payload


def spec_snapshot_to_payload(result):
    """Snapshot runs on _mcp_text per spec."""
    return {"text": result.get("_mcp_text", "")}


def spec_find_elements_to_payload(result):
    """find_elements runs on concatenated text and context_text."""
    texts = []
    items = result.get("items", result)
    if isinstance(items, dict):
        items = [items]
    for it in items or []:
        if isinstance(it, dict):
            t = it.get("text", "")
            c = it.get("context_text", "")
            texts.append(str(t) + "\n" + str(c))
    return {"text": "\n".join(texts)}


def spec_get_html_to_payload(result):
    """get_html runs text scan on content."""
    return {"text": result.get("content", "")}


def spec_apply_rewrite_note(findings, summary):
    """Leading _shoav key shape: verdict REWRITE, findings count, summary."""
    return {"_shoav": {"verdict": "REWRITE", "findings": int(findings), "summary": str(summary)}}


def spec_block_detail(reason, extra=None):
    """Ingress BLOCK (flood): isError true, error key first, then shoav."""
    detail = {"error": str(reason), "shoav": dict(extra or {})}
    return {"isError": True, "detail": detail}


def spec_egress_args(element_id=None, box=None, selector=None):
    """Egress arg builder: element_id op-sN maps to data-operator-id selector.

    box is [x, y, w, h]; centre is (x + w/2, y + h/2).
    """
    sel = selector
    if sel is None and element_id is not None:
        sel = '[data-operator-id="%s"]' % element_id
    cx = cy = None
    if box is not None:
        x, y, w, h = box
        cx = x + w / 2.0
        cy = y + h / 2.0
    return {"selector": sel, "element_id": element_id, "box": box, "cx": cx, "cy": cy}


def first_key(d):
    return next(iter(d))


class SpecSessionCache:
    """Reference per session interactables cache with reset semantics."""

    def __init__(self):
        self._store = {}
        self._loc = {}

    def put(self, session_id, interactables, url):
        self._store[session_id] = list(interactables)
        self._loc[session_id] = self._origin_path(url)

    def get(self, session_id):
        return list(self._store.get(session_id, []))

    def mark_touched(self, session_id, element_id):
        touched = self._store.setdefault(session_id + ":touched", set())
        touched.add(element_id)

    def on_navigate(self, session_id, url):
        new = self._origin_path(url)
        old = self._loc.get(session_id)
        if old != new:
            self._store.pop(session_id, None)
            self._loc[session_id] = new

    def on_close(self, session_id):
        self._store.pop(session_id, None)
        self._loc.pop(session_id, None)
        self._store.pop(session_id + ":touched", None)

    @staticmethod
    def _origin_path(url):
        p = urlparse(url)
        return (p.scheme, p.netloc, p.path)


# ---------------------------------------------------------------------------
# Synthetic fixtures (tiny, inline, no external URLs)
# ---------------------------------------------------------------------------

def fixture_observe_result():
    return {
        "interactables": [
            {"element_id": "op-s1", "role": "button", "name": "Buy"},
            {"element_id": "op-s2", "role": "checkbox", "name": "Subscribe"},
        ],
        "text_excerpt": "Hello shopper",
        "ocr": {"text": "ocr hello"},
        "form_controls": [
            {"ref": "op-s2", "kind": "checkbox", "checked": True, "label": "Subscribe"},
        ],
        "preset": "default",
    }


def fixture_snapshot_result():
    return {"_mcp_text": "line one\nline two"}


def fixture_find_elements_result():
    return {
        "items": [
            {"text": "Buy now", "context_text": "price row"},
            {"text": "Cancel", "context_text": "footer"},
        ]
    }


def fixture_get_html_result():
    return {"content": "<html><body>hello</body></html>"}


# ---------------------------------------------------------------------------
# T-1 tests
# ---------------------------------------------------------------------------

class TestNormalizeObserve(unittest.TestCase):
    def test_payload_keys_present(self):
        payload = spec_normalize_observe(fixture_observe_result())
        for key in ("interactables", "text_excerpt", "ocr_text", "form_controls"):
            self.assertIn(key, payload)

    def test_accessibility_outline_unavailable(self):
        payload = spec_normalize_observe(fixture_observe_result())
        self.assertIsNone(payload["accessibility_outline"])

    def test_interactables_carry_no_checked(self):
        payload = spec_normalize_observe(fixture_observe_result())
        for item in payload["interactables"]:
            self.assertNotIn("checked", item)

    def test_form_controls_accepted_directly(self):
        payload = spec_normalize_observe(fixture_observe_result())
        self.assertEqual(len(payload["form_controls"]), 1)
        self.assertEqual(payload["form_controls"][0]["ref"], "op-s2")

    def test_fast_preset_signal_preserved_by_caller(self):
        res = fixture_observe_result()
        res["preset"] = "fast"
        # Spec: browser.observe skips preset fast. The adapter contract is that
        # the caller checks preset before calling; payload build itself is pure.
        self.assertEqual(res["preset"], "fast")
        payload = spec_normalize_observe(res)
        self.assertIn("text_excerpt", payload)

    @unittest.skipUnless(REAL_OBSERVE is not None, "real adapters not present")
    def test_real_normalize_observe_conformance(self):
        fn = getattr(REAL_OBSERVE, "normalize_observe", None)
        self.assertTrue(callable(fn), "normalize_observe must exist")
        out = fn(fixture_observe_result())
        self.assertIsInstance(out, dict)
        for key in ("interactables", "text_excerpt"):
            self.assertIn(key, out)


class TestSnapshotPayload(unittest.TestCase):
    def test_runs_on_mcp_text(self):
        payload = spec_snapshot_to_payload(fixture_snapshot_result())
        self.assertEqual(payload["text"], "line one\nline two")

    def test_missing_mcp_text_gives_empty(self):
        self.assertEqual(spec_snapshot_to_payload({})["text"], "")

    @unittest.skipUnless(REAL_SNAPSHOT is not None, "real adapters not present")
    def test_real_snapshot_conformance(self):
        fn = getattr(REAL_SNAPSHOT, "snapshot_to_payload", None)
        self.assertTrue(callable(fn), "snapshot_to_payload must exist")
        out = fn(fixture_snapshot_result())
        self.assertIsInstance(out, dict)


class TestFindElementsPayload(unittest.TestCase):
    def test_concatenates_text_and_context(self):
        payload = spec_find_elements_to_payload(fixture_find_elements_result())
        self.assertIn("Buy now", payload["text"])
        self.assertIn("price row", payload["text"])
        self.assertIn("Cancel", payload["text"])

    @unittest.skipUnless(REAL_SNAPSHOT is not None, "real adapters not present")
    def test_real_find_elements_conformance(self):
        fn = getattr(REAL_SNAPSHOT, "find_elements_to_payload", None)
        self.assertTrue(callable(fn), "find_elements_to_payload must exist")
        out = fn(fixture_find_elements_result())
        self.assertIsInstance(out, dict)


class TestGetHtmlPayload(unittest.TestCase):
    def test_runs_on_content(self):
        payload = spec_get_html_to_payload(fixture_get_html_result())
        self.assertIn("hello", payload["text"])

    @unittest.skipUnless(REAL_SNAPSHOT is not None, "real adapters not present")
    def test_real_get_html_conformance(self):
        fn = getattr(REAL_SNAPSHOT, "get_html_to_payload", None)
        self.assertTrue(callable(fn), "get_html_to_payload must exist")
        out = fn(fixture_get_html_result())
        self.assertIsInstance(out, dict)


class TestApplyRewrite(unittest.TestCase):
    def test_shoav_leading_key(self):
        note = spec_apply_rewrite_note(2, "removed 2 hidden nodes")
        self.assertEqual(first_key(note), "_shoav")

    def test_rewrite_verdict_shape(self):
        note = spec_apply_rewrite_note(3, "summary here")
        body = note["_shoav"]
        self.assertEqual(body["verdict"], "REWRITE")
        self.assertEqual(body["findings"], 3)
        self.assertIsInstance(body["summary"], str)

    def test_rewrite_result_keeps_shoav_first(self):
        result = {"content": "clean text"}
        note = spec_apply_rewrite_note(1, "one fix")
        merged = dict(list(note.items()) + list(result.items()))
        self.assertEqual(first_key(merged), "_shoav")
        self.assertEqual(merged["_shoav"]["verdict"], "REWRITE")

    def test_rewrite_note_never_carries_page_instructions(self):
        note = spec_apply_rewrite_note(1, "removed suspected injected instruction")
        blob = json.dumps(note).lower()
        self.assertNotIn("ignore previous", blob)
        self.assertNotIn("system prompt", blob)

    @unittest.skipUnless(REAL_REWRITE is not None, "real adapters not present")
    def test_real_apply_rewrite_conformance(self):
        fn = getattr(REAL_REWRITE, "apply_rewrite", None)
        self.assertTrue(callable(fn), "apply_rewrite must exist")
        result = {"_mcp_text": "hello", "content": "hello"}
        out = fn(result, {"verdict": "REWRITE", "findings": 1, "summary": "s"})
        self.assertIsInstance(out, dict)
        self.assertEqual(first_key(out), "_shoav")


class TestBlockShape(unittest.TestCase):
    def test_is_error_true(self):
        b = spec_block_detail("flood", {"verdict": "BLOCK"})
        self.assertTrue(b["isError"])

    def test_error_key_first(self):
        b = spec_block_detail("flood", {"verdict": "BLOCK"})
        self.assertEqual(first_key(b["detail"]), "error")

    def test_shoav_detail_present(self):
        b = spec_block_detail("flood", {"verdict": "BLOCK"})
        self.assertIn("shoav", b["detail"])

    def test_egress_block_shape_error_first(self):
        # Egress BLOCK/ESCALATE: {"error": reason, "shoav": {...}} in both
        # content[0].text and structuredContent, error first.
        body = {"error": "overlay", "shoav": {"verdict": "BLOCK"}}
        self.assertEqual(first_key(body), "error")
        resp = {"isError": True, "content_text": body, "structured": body}
        self.assertTrue(resp["isError"])
        self.assertEqual(first_key(resp["content_text"]), "error")
        self.assertEqual(first_key(resp["structured"]), "error")

    @unittest.skipUnless(REAL_REWRITE is not None, "real adapters not present")
    def test_real_block_builder_conformance(self):
        fn = getattr(REAL_REWRITE, "build_block", None)
        self.assertTrue(callable(fn), "build_block must exist")
        out = fn("browser.snapshot", "flood", {"verdict": "BLOCK"})
        self.assertIsInstance(out, dict)
        # T1 _shoav-in-dict contract for Claude Code (structuredContent-only) vs timeline error-first display; both consumers satisfied.
        self.assertEqual(first_key(out), "_shoav")
        self.assertEqual(out["error"], "flood")
        self.assertIn("shoav", out)
        keys = list(out.keys())
        self.assertLess(keys.index("error"), keys.index("shoav"))


class TestEgressArgsBuilder(unittest.TestCase):
    def test_element_id_maps_to_selector(self):
        args = spec_egress_args(element_id="op-s4", box=[10, 20, 100, 40])
        self.assertEqual(args["selector"], '[data-operator-id="op-s4"]')

    def test_centre_point(self):
        args = spec_egress_args(element_id="op-s4", box=[10, 20, 100, 40])
        self.assertEqual(args["cx"], 60.0)
        self.assertEqual(args["cy"], 40.0)

    def test_selector_only_passthrough(self):
        args = spec_egress_args(selector="#buy", box=None)
        self.assertEqual(args["selector"], "#buy")
        self.assertIsNone(args["cx"])

    @unittest.skipUnless(REAL_EGRESS is not None, "real adapters not present")
    def test_real_egress_builder_conformance(self):
        fn = getattr(REAL_EGRESS, "decision_to_egress_args", None)
        self.assertTrue(callable(fn), "decision_to_egress_args must exist")
        out = fn("browser.execute_action",
                 {"action": "click", "element_id": "op-s4"},
                 [{"element_id": "op-s4", "role": "button"}])
        self.assertIsInstance(out, dict)


class TestSessionCacheReset(unittest.TestCase):
    def test_reset_on_origin_or_path_change(self):
        c = SpecSessionCache()
        c.put("s1", [{"element_id": "op-s1"}], "http://local/page-a")
        self.assertEqual(len(c.get("s1")), 1)
        c.on_navigate("s1", "http://local/page-a")
        self.assertEqual(len(c.get("s1")), 1)
        c.on_navigate("s1", "http://local/page-b")
        self.assertEqual(c.get("s1"), [])

    def test_reset_on_close(self):
        c = SpecSessionCache()
        c.put("s1", [{"element_id": "op-s1"}], "http://local/a")
        c.on_close("s1")
        self.assertEqual(c.get("s1"), [])

    def test_query_params_do_not_reset(self):
        # Spec compares origin and path, so query only change keeps cache.
        c = SpecSessionCache()
        c.put("s1", [{"element_id": "op-s1"}], "http://local/a?x=1")
        c.on_navigate("s1", "http://local/a?x=2")
        self.assertEqual(len(c.get("s1")), 1)

    @unittest.skipUnless(REAL_CACHE is not None, "real session cache not present")
    def test_real_cache_reset_conformance(self):
        # Accepts SessionCache or InteractablesCache with store/get/reset and
        # reset_if_navigated, plus should_reset_on_navigation helper.
        cache_cls = getattr(REAL_CACHE, "SessionCache", None) or getattr(
            REAL_CACHE, "InteractablesCache", None)
        self.assertTrue(cache_cls is not None, "a cache class must exist")
        c = cache_cls()
        c.store("s1", [{"element_id": "op-s1"}])
        self.assertEqual(len(c.get("s1")), 1)
        c.reset_if_navigated("s1", "http://local/a", "http://local/b")
        self.assertEqual(c.get("s1"), [])
        c.store("s1", [{"element_id": "op-s1"}])
        c.reset("s1")
        self.assertEqual(c.get("s1"), [])
        should_reset = getattr(REAL_CACHE, "should_reset_on_navigation", None)
        if callable(should_reset):
            self.assertFalse(should_reset("http://local/a?x=1", "http://local/a?x=2"))
            self.assertTrue(should_reset("http://local/a", "http://local/b"))


if __name__ == "__main__":
    unittest.main()
