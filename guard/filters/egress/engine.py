"""EgressFilter: orchestrates the pure egress rules by action type.

Like IngressFilter, this never touches a browser — a connector evaluates
the JS from scripts.py and hands this engine the plain-dict results.
"""

from __future__ import annotations

from ..session_state import SessionState
from ..types import Verdict
from . import rules


class EgressFilter:
    def verify_click(self, expected_ref: str, hit_result: dict) -> dict:
        verdict, reason = rules.evaluate_hit_test(hit_result, expected_ref)
        return {"verdict": verdict, "reason": reason}

    def verify_input(self, expected_ref: str, expected_value: str, focus_result: dict) -> dict:
        verdict, reason = rules.check_focus_integrity(expected_ref, expected_value, focus_result)
        return {"verdict": verdict, "reason": reason}

    def verify_submission(self, session_state: SessionState) -> dict:
        snapshot = session_state.initial_form_snapshot or []
        flags = rules.audit_form_state(snapshot, session_state.touched_refs)
        verdict = Verdict.ESCALATE if flags else Verdict.ALLOW
        reason = (
            f"{len(flags)} untouched pre-checked consent-like field(s) at submission."
            if flags else "No untouched pre-checked consent-like fields."
        )
        return {"verdict": verdict, "reason": reason, "flags": flags}

    def verify_cart(self, session_state: SessionState, current_item_ids: set[str]) -> dict:
        sneaked = rules.diff_cart_state(
            session_state.last_cart_item_ids,
            current_item_ids,
            session_state.clicked_add_to_cart_refs,
        )
        session_state.last_cart_item_ids = set(current_item_ids)
        verdict = Verdict.BLOCK if sneaked else Verdict.ALLOW
        reason = (
            f"Sneaked item(s) detected in cart without a logged add click: {sneaked}"
            if sneaked else "Cart contents match logged agent actions."
        )
        return {"verdict": verdict, "reason": reason, "sneaked_items": sneaked}
