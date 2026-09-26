"""F-D spec tests: form_controls flag plus submission audit (Target 3).

Spec sources: shoav-mcp/MCP/plan.md section 5 points 6-8 and
shoav-mcp/filters/plan.md tasks F-1/F-3.

Covered here, from spec only:
- IngressFilter.process accepts form_controls directly (FORM_STATE_SCRIPT
  shape: element_id/ref/tag/type/checked/label) and flags a pre-checked
  consent-like toggle.
- EgressFilter.verify_submission returns ESCALATE before the agent touches
  the toggle and ALLOW after mark_touched.
- Navigation reset clears touched refs and the initial snapshot so the next
  page starts clean.
- Benign login submit stays ALLOW.

Synthetic data only. No network. stdlib unittest. Target 5 not touched.
"""

import unittest

from ..egress.engine import EgressFilter
from ..ingress.engine import IngressFilter
from ..session_state import SessionState
from ..types import Verdict


def _clean_payload():
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


class TestFdFormControlsFlag(unittest.TestCase):
    def test_prechecked_consent_flagged_rewrite(self):
        res = IngressFilter().process(
            _clean_payload(), form_controls=[_consent_control()])
        self.assertEqual(res["verdict"], Verdict.REWRITE)
        flagged = res["findings"]["prechecked_toggles"]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["ref"], "op-s9")

    def test_element_id_used_when_ref_missing(self):
        control = _consent_control()
        del control["ref"]
        res = IngressFilter().process(_clean_payload(), form_controls=[control])
        flagged = res["findings"]["prechecked_toggles"]
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["ref"], "op-s9")

    def test_unchecked_consent_not_flagged(self):
        res = IngressFilter().process(
            _clean_payload(), form_controls=[_consent_control(checked=False)])
        self.assertEqual(res["findings"]["prechecked_toggles"], [])
        self.assertEqual(res["verdict"], Verdict.ALLOW)

    def test_radio_default_never_flagged(self):
        control = _consent_control(type="radio", label="Standard shipping data plan")
        res = IngressFilter().process(_clean_payload(), form_controls=[control])
        self.assertEqual(res["findings"]["prechecked_toggles"], [])

    def test_non_consent_checkbox_not_flagged(self):
        control = _consent_control(label="Remember me on this device")
        res = IngressFilter().process(_clean_payload(), form_controls=[control])
        self.assertEqual(res["findings"]["prechecked_toggles"], [])

    def test_missing_form_controls_fails_open(self):
        res = IngressFilter().process(_clean_payload(), form_controls=None)
        self.assertEqual(res["verdict"], Verdict.ALLOW)


class TestFdVerifySubmission(unittest.TestCase):
    def _observed_state(self):
        state = SessionState()
        IngressFilter().process(
            _clean_payload(), form_controls=[_consent_control()],
            session_state=state)
        return state

    def test_untouched_prechecked_escalates(self):
        out = EgressFilter().verify_submission(self._observed_state())
        self.assertEqual(out["verdict"], Verdict.ESCALATE)
        self.assertEqual(len(out["flags"]), 1)
        self.assertEqual(out["flags"][0]["ref"], "op-s9")

    def test_touched_prechecked_allows(self):
        state = self._observed_state()
        state.mark_touched("op-s9")
        out = EgressFilter().verify_submission(state)
        self.assertEqual(out["verdict"], Verdict.ALLOW)
        self.assertEqual(out["flags"], [])

    def test_clean_login_submit_allows(self):
        state = SessionState()
        IngressFilter().process(_clean_payload(), form_controls=[
            {"element_id": "op-s2", "ref": "op-s2", "tag": "INPUT",
             "type": "checkbox", "checked": False,
             "label": "Subscribe to newsletter", "name": "news"},
        ], session_state=state)
        out = EgressFilter().verify_submission(state)
        self.assertEqual(out["verdict"], Verdict.ALLOW)

    def test_empty_snapshot_allows(self):
        out = EgressFilter().verify_submission(SessionState())
        self.assertEqual(out["verdict"], Verdict.ALLOW)


class TestFdNavigationReset(unittest.TestCase):
    def test_reset_clears_touched_and_snapshot(self):
        state = SessionState()
        IngressFilter().process(
            _clean_payload(), form_controls=[_consent_control()],
            session_state=state)
        state.mark_touched("op-s9")
        self.assertEqual(
            EgressFilter().verify_submission(state)["verdict"], Verdict.ALLOW)
        state.reset_for_navigation()
        self.assertEqual(state.touched_refs, set())
        self.assertIsNone(state.initial_form_snapshot)
        IngressFilter().process(
            _clean_payload(), form_controls=[_consent_control()],
            session_state=state)
        out = EgressFilter().verify_submission(state)
        self.assertEqual(out["verdict"], Verdict.ESCALATE)


if __name__ == "__main__":
    unittest.main()
