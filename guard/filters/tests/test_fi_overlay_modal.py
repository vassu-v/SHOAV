"""F-I spec tests: overlay policy with modal tuning (Target 2).

Spec sources: shoav-mcp/MCP/plan.md section 5 egress points 1-4 and
shoav-mcp/DETERMINISTIC_TARGETS.md Target 2 plus the F-I modal policy in
filters/egress/rules.py (opaque top element with merely elevated z-index
escalates as a plausible modal; near-zero-opacity top element or absurd z
blocks; ordinary mismatch escalates; exact match or inside_target allows).

Covered here, from spec only:
- Opaque top element with elevated z (above 9000, at or below 100000)
  returns ESCALATE, not BLOCK.
- Transparent top element (opacity below 0.1 with pointer events) BLOCKs.
- Absurd z (above 100000) BLOCKs even when opaque.
- Cookie banner shape (opaque, low z, different ref) never BLOCKs: it
  ESCALATEs on mismatch and ALLOWs on match or inside_target.

Synthetic dicts only. No network. stdlib unittest. Target 5 not touched.
"""

import unittest

from ..egress import rules
from ..egress.engine import EgressFilter
from ..types import Verdict


def _hit(**over):
    hit = {"found": True, "tag": "DIV", "ref": "e-top",
           "opacity": 1.0, "z_index": "10", "pointer_events": "auto",
           "inside_target": False}
    hit.update(over)
    return hit


class TestFiOpaqueElevatedEscalates(unittest.TestCase):
    def test_opaque_z_9500_escalates(self):
        verdict, _ = rules.evaluate_hit_test(_hit(z_index="9500"), "op-s4")
        self.assertEqual(verdict, Verdict.ESCALATE)

    def test_opaque_z_50000_escalates(self):
        verdict, _ = rules.evaluate_hit_test(_hit(z_index="50000"), "op-s4")
        self.assertEqual(verdict, Verdict.ESCALATE)

    def test_engine_verify_click_matches_rule(self):
        out = EgressFilter().verify_click("op-s4", _hit(z_index="9500"))
        self.assertEqual(out["verdict"], Verdict.ESCALATE)


class TestFiTransparentOrAbsurdBlocks(unittest.TestCase):
    def test_transparent_overlay_blocks(self):
        verdict, _ = rules.evaluate_hit_test(
            _hit(opacity=0.0, z_index="99999"), "op-s4")
        self.assertEqual(verdict, Verdict.BLOCK)

    def test_transparent_low_z_blocks(self):
        verdict, _ = rules.evaluate_hit_test(
            _hit(opacity=0.0, z_index="5"), "op-s4")
        self.assertEqual(verdict, Verdict.BLOCK)

    def test_absurd_z_blocks_when_opaque(self):
        verdict, _ = rules.evaluate_hit_test(
            _hit(opacity=1.0, z_index="200000"), "op-s4")
        self.assertEqual(verdict, Verdict.BLOCK)

    def test_pointer_events_none_not_transparent_decoy(self):
        verdict, _ = rules.evaluate_hit_test(
            _hit(opacity=0.0, z_index="5", pointer_events="none"), "op-s4")
        self.assertEqual(verdict, Verdict.ESCALATE)


class TestFiCookieBannerNeverBlocks(unittest.TestCase):
    def test_banner_mismatch_escalates(self):
        verdict, _ = rules.evaluate_hit_test(
            _hit(tag="DIV", ref="e-cookie-banner", opacity=1.0,
                 z_index="10", inside_target=False),
            "op-s4")
        self.assertEqual(verdict, Verdict.ESCALATE)

    def test_banner_inside_target_allows(self):
        verdict, _ = rules.evaluate_hit_test(
            _hit(tag="BUTTON", ref="e-cookie-banner", opacity=1.0,
                 z_index="10", inside_target=True),
            "op-s4")
        self.assertEqual(verdict, Verdict.ALLOW)

    def test_exact_match_allows(self):
        verdict, _ = rules.evaluate_hit_test(
            _hit(tag="BUTTON", ref="op-s4", opacity=1.0,
                 z_index="10", inside_target=False),
            "op-s4")
        self.assertEqual(verdict, Verdict.ALLOW)

    def test_missing_element_escalates_fail_open(self):
        verdict, _ = rules.evaluate_hit_test({"found": False}, "op-s4")
        self.assertEqual(verdict, Verdict.ESCALATE)


if __name__ == "__main__":
    unittest.main()
