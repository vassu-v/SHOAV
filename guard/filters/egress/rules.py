"""Pure egress decision rules — take already-evaluated JS output, return a
verdict. No browser, no I/O, fully unit-testable.
"""

from __future__ import annotations

from ..constants import (
    EGRESS_ABSURD_ZINDEX_THRESHOLD,
    EGRESS_OVERLAY_OPACITY_THRESHOLD,
    EGRESS_OVERLAY_ZINDEX_THRESHOLD,
    INGRESS_CONSENT_KEYWORDS,
)
from ..types import Verdict


def _looks_like_zindex_int(z_index: str) -> int:
    try:
        return int(z_index)
    except (TypeError, ValueError):
        return 0


def evaluate_hit_test(hit_result: dict, expected_ref: str) -> tuple[Verdict, str]:
    """Target 2: clickjacking / overlay hit-target mismatch.

    hit_result is elementFromPoint's report at the target's center point
    (build_hit_test_script's output shape). expected_ref is the ref the
    agent believes it's clicking.

    Design refinement vs. PLAN_AND_ROUGH_SKETCH.md's rough sketch: that
    version blocks a *matching* element too if its own opacity happens to
    be low (`safe = isMatch && !isTransparentOverlay`), which would
    false-positive on a legitimately semi-transparent/mid-animation target
    that is genuinely what the agent meant to click. Here, an exact match
    always ALLOWs; the overlay check only applies to a *different* topmost
    element, which is the actual clickjacking shape. A non-match that
    doesn't look like a decoy (an ordinary visible element — e.g. a cookie
    banner appeared) gets ESCALATE rather than a hard BLOCK, since it may
    just mean the page changed under the agent, not an attack.

    F-I modal policy: an opaque top element with a merely elevated z-index
    (above EGRESS_OVERLAY_ZINDEX_THRESHOLD but at or below
    EGRESS_ABSURD_ZINDEX_THRESHOLD) is a plausible modal, dialog, or cookie
    banner and ESCALATEs. Only near-zero-opacity top elements (with pointer
    events enabled) or absurd-z top elements BLOCK.
    """
    if not hit_result.get("found"):
        return Verdict.ESCALATE, "No element found at target coordinates — page may have changed."

    if hit_result.get("inside_target") is True or hit_result.get("ref") == expected_ref:
        return Verdict.ALLOW, "Target coordinate verified clean."

    opacity = hit_result.get("opacity", 1.0)
    z_index = _looks_like_zindex_int(hit_result.get("z_index", "0"))
    pointer_events = hit_result.get("pointer_events", "auto")

    try:
        opacity_value = float(opacity)
    except (TypeError, ValueError):
        opacity_value = 1.0
    is_transparent = (
        opacity_value < EGRESS_OVERLAY_OPACITY_THRESHOLD
        and pointer_events != "none"
    )
    is_absurd_z = z_index > EGRESS_ABSURD_ZINDEX_THRESHOLD

    if is_transparent or is_absurd_z:
        return (
            Verdict.BLOCK,
            f"Clickjacking overlay suspected: <{hit_result.get('tag')}> "
            f"(opacity={opacity}, z-index={hit_result.get('z_index')}) "
            f"occludes intended target {expected_ref!r}. "
            "the click was aborted; call observe again, "
            "do not retry the same click, or ask the user. "
            "Blocked overlay click. Re-observe before retrying, "
            "or request human takeover.",
        )

    if z_index > EGRESS_OVERLAY_ZINDEX_THRESHOLD:
        return (
            Verdict.ESCALATE,
            f"Target mismatch: expected {expected_ref!r}, topmost element is "
            f"<{hit_result.get('tag')}> ref={hit_result.get('ref')!r} "
            f"(opacity={opacity}, z-index={hit_result.get('z_index')}). "
            "Opaque top element with an elevated z-index looks like a "
            "plausible modal, not a transparent decoy, so this escalates "
            "for re-observation instead of blocking.",
        )

    return (
        Verdict.ESCALATE,
        f"Target mismatch: expected {expected_ref!r}, topmost element is "
        f"<{hit_result.get('tag')}> ref={hit_result.get('ref')!r}. Does not "
        "look like a decoy overlay — page state may have changed.",
    )


def audit_form_state(
    initial_snapshot: list[dict],
    touched_refs: set[str],
) -> list[dict]:
    """Target 3 at submission time: any consent-like toggle that was
    checked at load and the agent never touched. initial_snapshot entries:
    {"ref": str, "checked": bool, "label": str}.
    """
    flags: list[dict] = []
    for control in initial_snapshot:
        if not control.get("checked"):
            continue
        ref = control.get("ref")
        if ref in touched_refs:
            continue
        label = (control.get("label") or ref or "").lower()
        if any(keyword in label for keyword in INGRESS_CONSENT_KEYWORDS):
            flags.append({
                "ref": ref,
                "label": control.get("label"),
                "reason": "submitted_with_untouched_prechecked_default",
            })
    return flags


def check_focus_integrity(
    expected_ref: str,
    expected_value: str,
    focus_result: dict,
) -> tuple[Verdict, str]:
    """Anti-gaslighting check: did the type/fill action actually land where
    the agent intended, per document.activeElement + its value.
    """
    if not focus_result.get("found"):
        return Verdict.BLOCK, "No active element found after input action — focus was lost."

    ref_matches = focus_result.get("ref") == expected_ref
    value_matches = focus_result.get("value") == expected_value
    if focus_result.get("type") == "password":
        # password fields do not expose a comparable value; ref match suffices
        value_matches = True

    if ref_matches and value_matches:
        return Verdict.ALLOW, "Input focus and value verified intact."

    return (
        Verdict.BLOCK,
        f"Input focus deflection detected: expected active element "
        f"{expected_ref!r} with value {expected_value!r}, got "
        f"{focus_result.get('ref')!r} with value {focus_result.get('value')!r}.",
    )


def diff_cart_state(
    before_item_ids: set[str],
    after_item_ids: set[str],
    clicked_add_to_cart_refs: set[str],
) -> list[str]:
    """Target 5: items present now that weren't before, and weren't the
    result of a logged add-to-cart click.
    """
    new_items = after_item_ids - before_item_ids
    return sorted(item for item in new_items if item not in clicked_add_to_cart_refs)
