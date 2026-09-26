"""F4: touched refs suppress pre-checked toggle flags."""
import unittest

from ..egress.engine import EgressFilter
from ..ingress.engine import IngressFilter
from ..session_state import SessionState, SessionStateStore
from ..types import Verdict
from . import fixtures as fx


def _payload_with_toggle(**node_extra):
    p = fx.clean_observation_payload()
    p["accessibility_outline"]["nodes"] = [
        dict({"role": "checkbox", "name": "Share my data with marketing partners",
              "checked": True}, **node_extra)
    ]
    return p


class TestMarkTouched(unittest.TestCase):
    def test_state_mark_touched(self):
        s = SessionState()
        s.mark_touched("c1")
        self.assertIn("c1", s.touched_refs)

    def test_store_mark_touched_creates_and_persists(self):
        store = SessionStateStore()
        store.mark_touched("sess", "c1")
        self.assertIn("c1", store.get_or_create("sess").touched_refs)

    def test_store_mark_touched_isolated_per_session(self):
        store = SessionStateStore()
        store.mark_touched("a", "c1")
        self.assertNotIn("c1", store.get_or_create("b").touched_refs)


class TestTouchedSuppression(unittest.TestCase):
    def test_untouched_toggle_flagged_by_ingress(self):
        st = SessionState()
        res = IngressFilter().process(_payload_with_toggle(ref="c-mkt"), session_state=st)
        self.assertEqual(len(res["findings"]["prechecked_toggles"]), 1)

    def test_touched_toggle_not_flagged_by_ingress(self):
        st = SessionState()
        st.mark_touched("c-mkt")
        res = IngressFilter().process(_payload_with_toggle(ref="c-mkt"), session_state=st)
        self.assertEqual(res["findings"]["prechecked_toggles"], [])
        self.assertEqual(res["verdict"], Verdict.ALLOW)

    def test_ref_key_preferred_over_name(self):
        st = SessionState()
        res = IngressFilter().process(_payload_with_toggle(ref="c-mkt"), session_state=st)
        self.assertEqual(res["findings"]["prechecked_toggles"][0]["ref"], "c-mkt")

    def test_element_id_used_as_ref(self):
        st = SessionState()
        res = IngressFilter().process(_payload_with_toggle(element_id="e42"), session_state=st)
        self.assertEqual(res["findings"]["prechecked_toggles"][0]["ref"], "e42")

    def test_ref_beats_element_id(self):
        st = SessionState()
        res = IngressFilter().process(
            _payload_with_toggle(ref="r1", element_id="e42"), session_state=st)
        self.assertEqual(res["findings"]["prechecked_toggles"][0]["ref"], "r1")

    def test_touched_by_element_id_not_flagged(self):
        st = SessionState()
        st.mark_touched("e42")
        res = IngressFilter().process(_payload_with_toggle(element_id="e42"), session_state=st)
        self.assertEqual(res["findings"]["prechecked_toggles"], [])

    def test_egress_submission_escalates_when_untouched(self):
        st = SessionState()
        IngressFilter().process(_payload_with_toggle(ref="c-mkt"), session_state=st)
        out = EgressFilter().verify_submission(st)
        self.assertEqual(out["verdict"], Verdict.ESCALATE)

    def test_egress_submission_allows_when_touched(self):
        st = SessionState()
        IngressFilter().process(_payload_with_toggle(ref="c-mkt"), session_state=st)
        st.mark_touched("c-mkt")
        out = EgressFilter().verify_submission(st)
        self.assertEqual(out["verdict"], Verdict.ALLOW)
        self.assertEqual(out["flags"], [])

    def test_touched_before_first_ingress_also_allows_at_submission(self):
        st = SessionState()
        st.mark_touched("c-mkt")
        IngressFilter().process(_payload_with_toggle(ref="c-mkt"), session_state=st)
        self.assertEqual(EgressFilter().verify_submission(st)["verdict"], Verdict.ALLOW)


if __name__ == "__main__":
    unittest.main()
