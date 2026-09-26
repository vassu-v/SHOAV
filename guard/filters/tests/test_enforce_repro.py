"""Enforce-failure reproduction: decision-function level (items 3, 4, 5).

Spec source: shoav-mcp/MCP/plan.md section 5 plus public decision
signatures only: EgressFilter.verify_click(expected_ref, hit_result),
IngressFilter.process(payload, ...) with form_controls, and
EgressFilter.verify_submission(session_state). No controller reads, no
network, no browsers. Synthetic inline data mirroring
shoav-mcp/fixtures/overlay.html, prechecked.html and flood.html.
"""

import unittest

from ..egress.engine import EgressFilter
from ..ingress.engine import IngressFilter
from ..session_state import SessionState
from ..types import Verdict
from .fixtures import (
    clean_observation_payload,
    flooded_interactables,
    hit_result_clickjacking_overlay,
)


def _checkout_payload():
    return {
        "url": "https://example-shop.test/checkout",
        "title": "Checkout",
        "text_excerpt": "Checkout. Review your order. Press submit to continue.",
        "interactables": [
            {"element_id": "op-s1", "tag": "button", "type": "submit",
             "role": "button", "label": "Submit order"},
        ],
        "accessibility_outline": {"nodes": []},
    }


def _consent_control(**over):
    control = {
        "element_id": "op-s9",
        "ref": "op-s9",
        "tag": "INPUT",
        "type": "checkbox",
        "checked": True,
        "label": "Share my data with marketing partners",
        "name": "marketing-optin",
    }
    control.update(over)
    return control


class TestReproOverlayBlock(unittest.TestCase):
    """Item 3: transparent overlay over the target center must BLOCK."""

    def test_overlay_hit_test_blocks(self):
        hit = hit_result_clickjacking_overlay()
        # Fixture shape: transparent overlay top element over target center.
        self.assertLess(float(hit["opacity"]), 0.1)
        result = EgressFilter().verify_click("e1", hit)
        self.assertEqual(
            result["verdict"], Verdict.BLOCK,
            "overlay hit-test must BLOCK, got %r" % (result.get("verdict"),),
        )


class TestReproPrecheckedToggle(unittest.TestCase):
    """Item 4: prechecked consent flagged at ingress, submit escalated."""

    def test_prechecked_consent_flagged_rewrite(self):
        res = IngressFilter().process(
            _checkout_payload(), form_controls=[_consent_control()])
        self.assertEqual(
            res["verdict"], Verdict.REWRITE,
            "prechecked consent must yield REWRITE, got %r" % (res.get("verdict"),),
        )
        flagged = res["findings"]["prechecked_toggles"]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["ref"], "op-s9")

    def test_untouched_submit_escalates(self):
        state = SessionState()
        IngressFilter().process(
            _checkout_payload(), form_controls=[_consent_control()],
            session_state=state)
        out = EgressFilter().verify_submission(state)
        self.assertEqual(
            out["verdict"], Verdict.ESCALATE,
            "untouched prechecked submit must ESCALATE, got %r" % (out.get("verdict"),),
        )
        self.assertEqual(len(out["flags"]), 1)
        self.assertEqual(out["flags"][0]["ref"], "op-s9")


class TestReproFloodBlock(unittest.TestCase):
    """Item 5: flood-shaped payload (720 fillers / raw counts) must BLOCK."""

    def test_720_filler_nodes_block(self):
        payload = clean_observation_payload()
        payload["interactables"] = flooded_interactables(720)
        res = IngressFilter().process(payload)
        self.assertEqual(
            res["verdict"], Verdict.BLOCK,
            "720 filler nodes must BLOCK, got %r" % (res.get("verdict"),),
        )
        self.assertIsNone(res["payload"])

    def test_720_raw_element_count_blocks(self):
        res = IngressFilter().process(
            clean_observation_payload(), raw_element_count=720)
        self.assertEqual(
            res["verdict"], Verdict.BLOCK,
            "720 raw elements must BLOCK, got %r" % (res.get("verdict"),),
        )


if __name__ == "__main__":
    unittest.main()
