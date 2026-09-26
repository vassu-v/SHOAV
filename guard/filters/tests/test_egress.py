import unittest

from ..egress.engine import EgressFilter
from ..egress import rules as egress_rules
from ..session_state import SessionState
from ..types import Verdict
from . import fixtures as fx


class TestEgressRules(unittest.TestCase):
    def test_hit_test_matching_target_allows(self):
        verdict, _reason = egress_rules.evaluate_hit_test(fx.hit_result_matching_target(), "e1")
        self.assertEqual(verdict, Verdict.ALLOW)

    def test_hit_test_clickjacking_overlay_blocks(self):
        verdict, reason = egress_rules.evaluate_hit_test(fx.hit_result_clickjacking_overlay(), "e1")
        self.assertEqual(verdict, Verdict.BLOCK)
        self.assertIn("overlay", reason.lower())

    def test_hit_test_legit_different_element_escalates_not_blocks(self):
        verdict, _reason = egress_rules.evaluate_hit_test(fx.hit_result_legit_different_element(), "e1")
        self.assertEqual(verdict, Verdict.ESCALATE)

    def test_hit_test_nothing_found_escalates(self):
        verdict, _reason = egress_rules.evaluate_hit_test(fx.hit_result_nothing_found(), "e1")
        self.assertEqual(verdict, Verdict.ESCALATE)

    def test_focus_integrity_matching_allows(self):
        verdict, _reason = egress_rules.check_focus_integrity(
            "e-search", "wireless mouse", fx.focus_result_matching()
        )
        self.assertEqual(verdict, Verdict.ALLOW)

    def test_focus_integrity_deflected_blocks(self):
        verdict, reason = egress_rules.check_focus_integrity(
            "e-search", "wireless mouse", fx.focus_result_deflected()
        )
        self.assertEqual(verdict, Verdict.BLOCK)
        self.assertIn("deflection", reason.lower())

    def test_audit_form_state_flags_untouched_prechecked(self):
        snapshot = [
            {"ref": "c2", "checked": True, "label": "Share my data with partners"},
            {"ref": "c1", "checked": True, "label": "Remember me"},
        ]
        flags = egress_rules.audit_form_state(snapshot, touched_refs=set())
        self.assertEqual({f["ref"] for f in flags}, {"c2"})

    def test_audit_form_state_allows_when_touched(self):
        snapshot = [{"ref": "c2", "checked": True, "label": "Share my data with partners"}]
        flags = egress_rules.audit_form_state(snapshot, touched_refs={"c2"})
        self.assertEqual(flags, [])

    def test_diff_cart_state_detects_sneaked_item(self):
        sneaked = egress_rules.diff_cart_state(
            before_item_ids={"item-1001"},
            after_item_ids={"item-1001", "item-warranty-9"},
            clicked_add_to_cart_refs={"item-1001"},
        )
        self.assertEqual(sneaked, ["item-warranty-9"])

    def test_diff_cart_state_allows_logged_add(self):
        sneaked = egress_rules.diff_cart_state(
            before_item_ids={"item-1001"},
            after_item_ids={"item-1001", "item-1002"},
            clicked_add_to_cart_refs={"item-1001", "item-1002"},
        )
        self.assertEqual(sneaked, [])


class TestEgressEngine(unittest.TestCase):
    def setUp(self):
        self.engine = EgressFilter()

    def test_verify_click_matching(self):
        result = self.engine.verify_click("e1", fx.hit_result_matching_target())
        self.assertEqual(result["verdict"], Verdict.ALLOW)

    def test_verify_click_overlay(self):
        result = self.engine.verify_click("e1", fx.hit_result_clickjacking_overlay())
        self.assertEqual(result["verdict"], Verdict.BLOCK)

    def test_verify_input_deflected(self):
        result = self.engine.verify_input("e-search", "wireless mouse", fx.focus_result_deflected())
        self.assertEqual(result["verdict"], Verdict.BLOCK)

    def test_verify_submission_escalates_on_untouched_prechecked(self):
        state = SessionState()
        state.initial_form_snapshot = [
            {"ref": "c2", "checked": True, "label": "Share my data with marketing partners"},
        ]
        result = self.engine.verify_submission(state)
        self.assertEqual(result["verdict"], Verdict.ESCALATE)
        self.assertEqual(len(result["flags"]), 1)

    def test_verify_submission_allows_clean(self):
        state = SessionState()
        state.initial_form_snapshot = [
            {"ref": "c1", "checked": True, "label": "Remember me"},
        ]
        result = self.engine.verify_submission(state)
        self.assertEqual(result["verdict"], Verdict.ALLOW)

    def test_verify_cart_blocks_sneaked_item(self):
        state = SessionState()
        state.last_cart_item_ids = {"item-1001"}
        state.clicked_add_to_cart_refs = {"item-1001"}
        result = self.engine.verify_cart(state, current_item_ids={"item-1001", "item-warranty-9"})
        self.assertEqual(result["verdict"], Verdict.BLOCK)
        self.assertEqual(result["sneaked_items"], ["item-warranty-9"])
        # state should now track the new snapshot for the next diff
        self.assertEqual(state.last_cart_item_ids, {"item-1001", "item-warranty-9"})


if __name__ == "__main__":
    unittest.main()
