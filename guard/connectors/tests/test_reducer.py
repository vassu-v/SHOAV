"""T-3 reducer and UI contract tests (spec only).

Spec source: shoav-mcp/MCP/plan.md section 6.
Contracts:
- Guard badge on each tool row: ALLOW quiet, REWRITE amber, ESCALATE
  orange, BLOCK red.
- Expanded row: reason, findings list (kind, short detail), target element
  id, mode, whether enforced.
- Header chip: Guard mode plus blocked and rewritten counts.
- Guard filter next to timeline filters, with a count (countGuard).
- Reducer attaches guard events by call_id and creates stub rows for
  unknown call ids. Unknown event types are ignored so an old UI stays safe.

These tests use a tiny python mirror of the reducer so the UI agent can
port the assertions to vitest. They test contracts, not UI internals.
"""

import unittest


VERDICTS = ("ALLOW", "REWRITE", "ESCALATE", "BLOCK")

BADGE = {
    "ALLOW": {"tone": "quiet", "color": "gray"},
    "REWRITE": {"tone": "amber", "color": "amber"},
    "ESCALATE": {"tone": "orange", "color": "orange"},
    "BLOCK": {"tone": "red", "color": "red"},
}


def badge_for_verdict(verdict):
    return BADGE.get(verdict, BADGE["ALLOW"])


def reduce_timeline(state, event):
    """Spec mirror: attach guard event by call_id, stub unknown rows."""
    etype = event.get("type")
    if etype != "guard":
        return state
    call_id = event.get("call_id")
    if not call_id:
        return state
    rows = dict(state.get("rows", {}))
    row = dict(rows.get(call_id, {"call_id": call_id, "tool": event.get("tool", ""), "stub": True}))
    guards = list(row.get("guards", []))
    guards.append(event)
    row["guards"] = guards
    row["verdict"] = event.get("verdict", row.get("verdict", "ALLOW"))
    rows[call_id] = row
    return {"rows": rows}


def count_guard(events):
    return sum(1 for e in events if e.get("type") == "guard")


def header_chip(mode, events):
    blocked = sum(1 for e in events if e.get("verdict") == "BLOCK")
    rewritten = sum(1 for e in events if e.get("verdict") == "REWRITE")
    return "Guard: %s, %d blocked, %d rewritten" % (mode, blocked, rewritten)


def guard_event(call_id="c1", verdict="BLOCK", tool="browser.execute_action"):
    return {
        "type": "guard",
        "event": "verdict",
        "call_id": call_id,
        "session_id": "s1",
        "seq": 1,
        "ts": "2026-09-25T00:00:00Z",
        "stage": "egress",
        "tool": tool,
        "verdict": verdict,
        "mode": "enforce",
        "enforced": True,
        "reason": "overlay",
        "findings": [{"kind": "overlay", "detail": "top element differs"}],
        "target": {"element_id": "op-s4"},
    }


class TestBadgeMapping(unittest.TestCase):
    def test_allow_quiet(self):
        self.assertEqual(badge_for_verdict("ALLOW")["tone"], "quiet")

    def test_rewrite_amber(self):
        self.assertEqual(badge_for_verdict("REWRITE")["tone"], "amber")

    def test_escalate_orange(self):
        self.assertEqual(badge_for_verdict("ESCALATE")["tone"], "orange")

    def test_block_red(self):
        self.assertEqual(badge_for_verdict("BLOCK")["tone"], "red")

    def test_unknown_verdict_falls_back_to_allow(self):
        self.assertEqual(badge_for_verdict("NOPE")["tone"], "quiet")


class TestReducerAttach(unittest.TestCase):
    def test_attach_by_call_id(self):
        state = {"rows": {"c1": {"call_id": "c1", "tool": "browser.execute_action"}}}
        out = reduce_timeline(state, guard_event(call_id="c1", verdict="BLOCK"))
        self.assertEqual(out["rows"]["c1"]["verdict"], "BLOCK")
        self.assertEqual(len(out["rows"]["c1"]["guards"]), 1)

    def test_stub_row_for_unknown_call_id(self):
        out = reduce_timeline({"rows": {}}, guard_event(call_id="new1"))
        self.assertIn("new1", out["rows"])
        self.assertTrue(out["rows"]["new1"].get("stub"))

    def test_unknown_types_ignored(self):
        state = {"rows": {}}
        out = reduce_timeline(state, {"type": "future-thing", "call_id": "c9"})
        self.assertEqual(out, state)

    def test_missing_call_id_ignored(self):
        ev = guard_event()
        del ev["call_id"]
        out = reduce_timeline({"rows": {}}, ev)
        self.assertEqual(out, {"rows": {}})

    def test_multiple_guards_accumulate(self):
        state = {"rows": {}}
        state = reduce_timeline(state, guard_event(call_id="c1", verdict="REWRITE"))
        state = reduce_timeline(state, guard_event(call_id="c1", verdict="BLOCK"))
        self.assertEqual(len(state["rows"]["c1"]["guards"]), 2)
        self.assertEqual(state["rows"]["c1"]["verdict"], "BLOCK")


class TestCountGuard(unittest.TestCase):
    def test_counts_only_guard(self):
        events = [guard_event("a", "BLOCK"), {"type": "tool", "call_id": "b"},
                  guard_event("c", "ALLOW")]
        self.assertEqual(count_guard(events), 2)

    def test_empty(self):
        self.assertEqual(count_guard([]), 0)


class TestExpandedRowFields(unittest.TestCase):
    def test_required_display_fields(self):
        ev = guard_event()
        for key in ("reason", "findings", "target", "mode", "enforced"):
            self.assertIn(key, ev)

    def test_findings_shape(self):
        ev = guard_event()
        for f in ev["findings"]:
            self.assertIn("kind", f)
            self.assertIn("detail", f)

    def test_target_element_id(self):
        ev = guard_event()
        self.assertEqual(ev["target"]["element_id"], "op-s4")


class TestHeaderChip(unittest.TestCase):
    def test_chip_text(self):
        events = [guard_event("a", "BLOCK"), guard_event("b", "BLOCK"),
                  guard_event("c", "REWRITE")]
        chip = header_chip("enforce", events)
        self.assertIn("enforce", chip)
        self.assertIn("2 blocked", chip)
        self.assertIn("1 rewritten", chip)


if __name__ == "__main__":
    unittest.main()
