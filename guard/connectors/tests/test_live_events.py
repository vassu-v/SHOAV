"""T-4 live event tests (spec only, fake live layer, no real controller).

Spec source: shoav-mcp/MCP/plan.md sections 5-6.
Contracts:
- Guard event shape with required keys; type override of tool default.
- End event carries a guard summary.
- Redaction passthrough: guard payloads go through existing redact and
  truncate helpers.
- GET /live-api/guard shape: mode, version, counters.

Tiny synthetic fixtures only. Stdlib unittest.
"""

import unittest


REQUIRED_GUARD_KEYS = (
    "type", "event", "call_id", "session_id", "seq", "ts",
    "stage", "tool", "verdict", "mode", "enforced", "reason",
    "findings", "target",
)

VERDICTS = ("ALLOW", "REWRITE", "BLOCK", "ESCALATE")
STAGES = ("ingress", "egress")
MODES = ("observe", "enforce")


def make_guard(seq=1, verdict="BLOCK", stage="egress", mode="enforce", enforced=True):
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
        "enforced": enforced,
        "reason": "overlay at target",
        "findings": [{"kind": "overlay", "detail": "top element differs"}],
        "target": {"element_id": "op-s4"},
    }


def validate_guard_event(ev):
    missing = [k for k in REQUIRED_GUARD_KEYS if k not in ev]
    if missing:
        return False, "missing keys: %s" % ",".join(missing)
    if ev["type"] != "guard":
        return False, "type must be guard"
    if ev["verdict"] not in VERDICTS:
        return False, "bad verdict"
    if ev["stage"] not in STAGES:
        return False, "bad stage"
    if ev["mode"] not in MODES:
        return False, "bad mode"
    if not isinstance(ev["enforced"], bool):
        return False, "enforced must be bool"
    if not isinstance(ev["findings"], list):
        return False, "findings must be list"
    return True, "ok"


# Fake live layer ------------------------------------------------------------

class FakeLiveCall:
    def __init__(self, session_id="sess-1", call_id="call-1"):
        self.session_id = session_id
        self.call_id = call_id
        self.events = []
        self._seq = 0

    def guard(self, stage, tool, verdict, mode, enforced, reason="",
              findings=None, target=None):
        self._seq += 1
        ev = {
            "type": "guard",
            "event": "verdict",
            "call_id": self.call_id,
            "session_id": self.session_id,
            "seq": self._seq,
            "ts": "2026-09-25T00:00:00Z",
            "stage": stage,
            "tool": tool,
            "verdict": verdict,
            "mode": mode,
            "enforced": enforced,
            "reason": reason,
            "findings": list(findings or []),
            "target": dict(target or {}),
        }
        self.events.append(ev)
        return ev

    def end(self, status="ok"):
        blocked = sum(1 for e in self.events if e["verdict"] == "BLOCK")
        rewritten = sum(1 for e in self.events if e["verdict"] == "REWRITE")
        escalated = sum(1 for e in self.events if e["verdict"] == "ESCALATE")
        return {
            "type": "tool",
            "event": "end",
            "call_id": self.call_id,
            "session_id": self.session_id,
            "status": status,
            "guard": {"blocked": blocked, "rewritten": rewritten,
                      "escalated": escalated, "total": len(self.events)},
        }


def fake_redact(obj):
    """Spec mirror: redact secrets but preserve guard shape."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k.lower() in ("password", "token", "secret", "cookie"):
                out[k] = "[redacted]"
            else:
                out[k] = fake_redact(v)
        return out
    if isinstance(obj, list):
        return [fake_redact(x) for x in obj]
    if isinstance(obj, str) and len(obj) > 2000:
        return obj[:2000] + "...[truncated]"
    return obj


def fake_guard_status(mode="enforce", version="1", counters=None):
    return {"mode": mode, "version": version,
            "counters": dict(counters or {"blocked": 0, "rewritten": 0})}


# Tests ----------------------------------------------------------------------

class TestGuardEventShape(unittest.TestCase):
    def test_required_keys(self):
        ok, msg = validate_guard_event(make_guard())
        self.assertTrue(ok, msg)

    def test_missing_key_fails(self):
        ev = make_guard()
        del ev["reason"]
        ok, _ = validate_guard_event(ev)
        self.assertFalse(ok)

    def test_verdict_enum(self):
        for v in VERDICTS:
            ok, msg = validate_guard_event(make_guard(verdict=v))
            self.assertTrue(ok, msg)
        ok, _ = validate_guard_event(make_guard(verdict="NOPE"))
        self.assertFalse(ok)

    def test_stage_enum(self):
        for s in STAGES:
            ok, _ = validate_guard_event(make_guard(stage=s))
            self.assertTrue(ok)
        ok, _ = validate_guard_event(make_guard(stage="network"))
        self.assertFalse(ok)

    def test_mode_enum(self):
        for m in MODES:
            ok, _ = validate_guard_event(make_guard(mode=m))
            self.assertTrue(ok)

    def test_observe_never_enforced(self):
        ev = make_guard(mode="observe", enforced=False, verdict="REWRITE")
        ok, _ = validate_guard_event(ev)
        self.assertTrue(ok)
        self.assertFalse(ev["enforced"])

    def test_live_call_guard_shape(self):
        call = FakeLiveCall()
        ev = call.guard(stage="egress", tool="browser.execute_action",
                        verdict="BLOCK", mode="enforce", enforced=True,
                        reason="overlay", findings=[{"kind": "overlay", "detail": "x"}],
                        target={"element_id": "op-s4"})
        ok, msg = validate_guard_event(ev)
        self.assertTrue(ok, msg)


class TestEndEventSummary(unittest.TestCase):
    def test_end_carries_guard_summary(self):
        call = FakeLiveCall()
        call.guard(stage="egress", tool="t", verdict="BLOCK",
                   mode="enforce", enforced=True)
        call.guard(stage="ingress", tool="t", verdict="REWRITE",
                   mode="enforce", enforced=True)
        end = call.end()
        self.assertIn("guard", end)
        self.assertEqual(end["guard"]["blocked"], 1)
        self.assertEqual(end["guard"]["rewritten"], 1)
        self.assertEqual(end["guard"]["total"], 2)

    def test_end_with_no_guards(self):
        end = FakeLiveCall().end()
        self.assertEqual(end["guard"]["total"], 0)


class TestRedactionPassthrough(unittest.TestCase):
    def test_shape_preserved(self):
        ev = make_guard()
        out = fake_redact(ev)
        ok, msg = validate_guard_event(out)
        self.assertTrue(ok, msg)

    def test_secrets_masked(self):
        payload = {"password": "hunter2", "reason": "ok"}
        out = fake_redact(payload)
        self.assertEqual(out["password"], "[redacted]")
        self.assertEqual(out["reason"], "ok")

    def test_long_strings_truncated(self):
        out = fake_redact("x" * 5000)
        self.assertTrue(out.endswith("...[truncated]"))
        self.assertLessEqual(len(out), 2015)


class TestGuardStatusRoute(unittest.TestCase):
    def test_status_shape(self):
        body = fake_guard_status(mode="enforce", version="filters-1",
                                 counters={"blocked": 2, "rewritten": 3})
        self.assertIn("mode", body)
        self.assertIn("version", body)
        self.assertIn("counters", body)
        self.assertIn(body["mode"], ("off", "observe", "enforce"))
        self.assertIsInstance(body["counters"], dict)

    def test_counters_round_trip(self):
        body = fake_guard_status(counters={"blocked": 2, "rewritten": 3,
                                           "escalated": 1})
        self.assertEqual(body["counters"]["blocked"], 2)


if __name__ == "__main__":
    unittest.main()
