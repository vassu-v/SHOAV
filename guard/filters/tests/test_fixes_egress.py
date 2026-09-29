"""F3 (hit test rules and script text) and F6 (password focus check)."""
import unittest

from ..egress import rules
from ..egress.scripts import build_hit_test_script
from ..types import Verdict
from . import fixtures as fx


class TestHitTestInsideTarget(unittest.TestCase):
    def test_inside_target_true_allows_despite_ref_mismatch(self):
        hit = {"found": True, "tag": "SPAN", "ref": "e-span", "opacity": 1.0,
               "z_index": "auto", "pointer_events": "auto", "inside_target": True}
        verdict, _ = rules.evaluate_hit_test(hit, "e1")
        self.assertEqual(verdict, Verdict.ALLOW)

    def test_ref_equal_still_allows(self):
        verdict, _ = rules.evaluate_hit_test(fx.hit_result_matching_target(), "e1")
        self.assertEqual(verdict, Verdict.ALLOW)

    def test_transparent_overlay_blocks_when_inside_target_false(self):
        hit = dict(fx.hit_result_clickjacking_overlay(), inside_target=False)
        verdict, _ = rules.evaluate_hit_test(hit, "e1")
        self.assertEqual(verdict, Verdict.BLOCK)

    def test_normal_different_element_escalates_when_inside_target_false(self):
        hit = dict(fx.hit_result_legit_different_element(), inside_target=False)
        verdict, _ = rules.evaluate_hit_test(hit, "e1")
        self.assertEqual(verdict, Verdict.ESCALATE)

    def test_not_found_escalates(self):
        verdict, _ = rules.evaluate_hit_test(fx.hit_result_nothing_found(), "e1")
        self.assertEqual(verdict, Verdict.ESCALATE)


class TestHitTestScriptText(unittest.TestCase):
    def test_returns_string_with_coordinates(self):
        js = build_hit_test_script(120, 340)
        self.assertIsInstance(js, str)
        self.assertIn("elementFromPoint", js)
        self.assertIn("120", js)
        self.assertIn("340", js)

    def test_with_expected_ref_mentions_inside_target_and_contains(self):
        js = build_hit_test_script(5, 6, expected_ref="e1")
        self.assertIn("inside_target", js)
        self.assertIn("contains", js)
        self.assertIn("e1", js)

    def test_expected_ref_is_optional(self):
        self.assertIsInstance(build_hit_test_script(1.5, 2.5, None), str)


class TestFocusIntegrityPassword(unittest.TestCase):
    def test_password_ref_match_allows_even_if_value_differs(self):
        fr = {"found": True, "tag": "INPUT", "ref": "e-pw", "value": "", "type": "password"}
        verdict, _ = rules.check_focus_integrity("e-pw", "hunter2", fr)
        self.assertEqual(verdict, Verdict.ALLOW)

    def test_password_ref_match_allows_with_masked_value(self):
        fr = {"found": True, "tag": "INPUT", "ref": "e-pw", "value": None, "type": "password"}
        verdict, _ = rules.check_focus_integrity("e-pw", "hunter2", fr)
        self.assertEqual(verdict, Verdict.ALLOW)

    def test_password_ref_mismatch_blocks(self):
        fr = {"found": True, "tag": "INPUT", "ref": "e-sniff", "value": "hunter2", "type": "password"}
        verdict, _ = rules.check_focus_integrity("e-pw", "hunter2", fr)
        self.assertEqual(verdict, Verdict.BLOCK)

    def test_text_type_value_mismatch_still_blocks(self):
        fr = {"found": True, "tag": "INPUT", "ref": "e-search", "value": "other", "type": "text"}
        verdict, _ = rules.check_focus_integrity("e-search", "wireless mouse", fr)
        self.assertEqual(verdict, Verdict.BLOCK)

    def test_text_type_exact_match_allows(self):
        fr = {"found": True, "tag": "INPUT", "ref": "e-search", "value": "wireless mouse", "type": "text"}
        verdict, _ = rules.check_focus_integrity("e-search", "wireless mouse", fr)
        self.assertEqual(verdict, Verdict.ALLOW)

    def test_missing_type_behaves_as_before(self):
        verdict, _ = rules.check_focus_integrity("e-search", "wireless mouse", fx.focus_result_matching())
        self.assertEqual(verdict, Verdict.ALLOW)
        verdict, _ = rules.check_focus_integrity("e-search", "wireless mouse", fx.focus_result_deflected())
        self.assertEqual(verdict, Verdict.BLOCK)

    def test_not_found_blocks_for_password_too(self):
        verdict, _ = rules.check_focus_integrity("e-pw", "x", {"found": False, "type": "password"})
        self.assertEqual(verdict, Verdict.BLOCK)


if __name__ == "__main__":
    unittest.main()
