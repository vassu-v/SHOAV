"""Tests for the tiny shoav CLI (stdlib unittest, faked HTTP)."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from . import cli


class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _guard_event(seq=3, verdict="BLOCK", stage="egress", mode="enforce"):
    return {
        "type": "guard",
        "event": "verdict",
        "call_id": "call-1",
        "session_id": "sess-1",
        "seq": seq,
        "ts": "2026-09-25T00:00:00Z",
        "stage": stage,
        "tool": "browser.execute_action",
        "verdict": verdict,
        "mode": mode,
        "enforced": True,
        "reason": "overlay at target",
        "findings": [],
        "target": {"element_id": "op-s1"},
    }


def _tool_event(seq=1):
    return {"type": "tool", "event": "end", "call_id": "call-1", "seq": seq, "status": "ok"}


class TestGuardPredicates(unittest.TestCase):
    def test_guard_type_detected(self):
        self.assertTrue(cli.is_guard_event(_guard_event()))

    def test_tool_event_not_guard(self):
        self.assertFalse(cli.is_guard_event(_tool_event()))

    def test_verdict_shape_without_type_still_guard(self):
        event = {"event": "verdict", "verdict": "REWRITE", "stage": "ingress"}
        self.assertTrue(cli.is_guard_event(event))

    def test_non_dict_not_guard(self):
        self.assertFalse(cli.is_guard_event("nope"))

    def test_filter_by_verdict_and_stage(self):
        events = [
            _guard_event(seq=1, verdict="BLOCK", stage="egress"),
            _guard_event(seq=2, verdict="REWRITE", stage="ingress"),
        ]
        self.assertEqual(len(cli.filter_guard_events(events)), 2)
        blocked = cli.filter_guard_events(events, verdict="block")
        self.assertEqual([e["seq"] for e in blocked], [1])
        ingress = cli.filter_guard_events(events, stage="INGRESS")
        self.assertEqual([e["seq"] for e in ingress], [2])

    def test_filter_by_mode(self):
        events = [_guard_event(seq=1, mode="enforce"), _guard_event(seq=2, mode="observe")]
        self.assertEqual(len(cli.filter_guard_events(events, mode="observe")), 1)


class TestStatusCommand(unittest.TestCase):
    def test_status_json_output(self):
        payload = {"mode": "enforce", "version": "1", "counters": {"block": 2}}
        with patch.object(cli.urllib.request, "urlopen", return_value=_FakeResponse(payload)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["status", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buf.getvalue())["mode"], "enforce")

    def test_status_human_output(self):
        payload = {"mode": "observe", "version": "1", "counters": {"allow": 5}}
        with patch.object(cli.urllib.request, "urlopen", return_value=_FakeResponse(payload)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["status"])
        self.assertEqual(code, 0)
        self.assertIn("mode: observe", buf.getvalue())

    def test_status_hits_guard_path(self):
        seen = {}

        def fake_open(req, timeout=15):
            seen["url"] = req.full_url
            return _FakeResponse({"mode": "off", "version": "1", "counters": {}})

        with patch.object(cli.urllib.request, "urlopen", side_effect=fake_open):
            cli.main(["--controller", "http://127.0.0.1:18501/", "status"])
        self.assertTrue(seen["url"].endswith("/live-api/guard"))

    def test_status_http_error_exits_nonzero(self):
        with patch.object(cli.urllib.request, "urlopen", side_effect=OSError("down")):
            code = cli.main(["status"])
        self.assertEqual(code, 1)


class TestEventsCommand(unittest.TestCase):
    def test_events_filters_to_guard_only(self):
        payload = {"events": [_tool_event(1), _guard_event(2), _guard_event(3, verdict="REWRITE")]}
        with patch.object(cli.urllib.request, "urlopen", return_value=_FakeResponse(payload)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["events", "sess-1", "--json"])
        self.assertEqual(code, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out["session_id"], "sess-1")
        self.assertEqual(len(out["guard_events"]), 2)

    def test_events_verdict_filter(self):
        payload = {"events": [_guard_event(2, verdict="BLOCK"), _guard_event(3, verdict="REWRITE")]}
        with patch.object(cli.urllib.request, "urlopen", return_value=_FakeResponse(payload)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["events", "sess-1", "--json", "--verdict", "REWRITE"])
        self.assertEqual(code, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual([e["seq"] for e in out["guard_events"]], [3])

    def test_events_timeline_path_and_query(self):
        seen = {}

        def fake_open(req, timeout=15):
            seen["url"] = req.full_url
            return _FakeResponse({"events": []})

        with patch.object(cli.urllib.request, "urlopen", side_effect=fake_open):
            cli.main(["events", "sess-9", "--after-seq", "5", "--limit", "7"])
        self.assertIn("/live-api/sessions/sess-9/timeline", seen["url"])
        self.assertIn("after_seq=5", seen["url"])
        self.assertIn("limit=7", seen["url"])

    def test_events_empty_human_message(self):
        with patch.object(cli.urllib.request, "urlopen", return_value=_FakeResponse({"events": []})):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["events", "sess-1"])
        self.assertEqual(code, 0)
        self.assertIn("no guard events", buf.getvalue())


def _real_create_session_response(sid="08f6f408427d"):
    merged = {
        "_notice": "live session",
        "live_view": {
            "session_id": sid,
            "url": "http://127.0.0.1:3200/s/" + sid,
            "banner": "session " + sid,
        },
        "id": sid,
        "name": "session-" + sid,
        "status": "active",
        "current_url": "http://127.0.0.1:18634/flood.html",
    }
    return {
        "content": [
            {"type": "text", "text": json.dumps(merged)},
            {"type": "text", "text": "session " + sid},
        ],
        "structuredContent": merged,
        "isError": False,
    }


class TestSessionIdParsing(unittest.TestCase):
    def test_real_gateway_shape_prefers_id(self):
        resp = _real_create_session_response("08f6f408427d")
        self.assertEqual(cli.session_id_of(resp), "08f6f408427d")

    def test_live_view_only_shape(self):
        resp = {
            "content": [{"type": "text", "text": "banner"}],
            "structuredContent": {"live_view": {"session_id": "abc123def456"}},
        }
        self.assertEqual(cli.session_id_of(resp), "abc123def456")

    def test_text_fallback_when_structured_missing(self):
        inner = {"id": "08f6f408427d", "name": "session-08f6f408427d"}
        resp = {"content": [{"type": "text", "text": json.dumps(inner)}], "isError": False}
        self.assertEqual(cli.session_id_of(resp), "08f6f408427d")

    def test_id_only_structured_shape(self):
        resp = {"structuredContent": {"id": "sid-9"}, "content": []}
        self.assertEqual(cli.session_id_of(resp), "sid-9")

    def test_empty_response_yields_none(self):
        self.assertIsNone(cli.session_id_of({"content": [], "structuredContent": {}}))
        self.assertIsNone(cli.session_id_of({}))

    def test_create_session_helper_posts_tool_and_parses_sid(self):
        seen = {}

        def fake_open(req, timeout=15):
            seen["url"] = req.full_url
            seen["body"] = json.loads(req.data.decode())
            return _FakeResponse(_real_create_session_response("08f6f408427d"))

        with patch.object(cli.urllib.request, "urlopen", side_effect=fake_open):
            sid, raw = cli.create_session("http://127.0.0.1:18501", start_url="http://x/y")
        self.assertEqual(sid, "08f6f408427d")
        self.assertTrue(seen["url"].endswith("/mcp/tools/call"))
        self.assertEqual(seen["body"]["name"], "browser.create_session")

    def test_create_session_cli_json_output(self):
        with patch.object(
            cli.urllib.request, "urlopen", return_value=_FakeResponse(_real_create_session_response("08f6f408427d"))
        ):
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = cli.main(["create-session", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(buf.getvalue())["session_id"], "08f6f408427d")


if __name__ == "__main__":
    unittest.main()
