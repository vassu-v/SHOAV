"""JS snippets the egress engine needs evaluated in-page.

Same split as ingress/scripts.py: these strings are for a future connector
to execute (via browser.eval_js today, or a direct session.page.evaluate()
once wired into Auto Browser internals). rules.py consumes only their
already-evaluated output shape, so it never needs a browser to test.
"""

from __future__ import annotations

import json


def build_hit_test_script(cx: float, cy: float, expected_ref: str | None = None) -> str:
    """Target 2: what's actually topmost at the target's center point.

    When expected_ref is given, the result also carries inside_target: whether
    the topmost element is the target or one of its descendants.
    """
    ref_js = json.dumps(expected_ref) if expected_ref is not None else "null"
    return f"""
    (() => {{
        const topEl = document.elementFromPoint({cx}, {cy});
        if (!topEl) return {{ found: false }};
        const style = window.getComputedStyle(topEl);
        const expectedRef = {ref_js};
        let insideTarget = null;
        if (expectedRef !== null) {{
            const target = Array.from(document.querySelectorAll('[data-operator-id]'))
                .find(e => e.getAttribute('data-operator-id') === expectedRef);
            insideTarget = target ? target.contains(topEl) : false;
        }}
        return {{
            found: true,
            inside_target: insideTarget,
            tag: topEl.tagName,
            ref: topEl.getAttribute('data-operator-id'),
            opacity: parseFloat(style.opacity),
            z_index: style.zIndex,
            pointer_events: style.pointerEvents,
        }};
    }})()
    """


FOCUS_CHECK_SCRIPT = """
(() => {
    const el = document.activeElement;
    if (!el) return { found: false };
    return {
        found: true,
        tag: el.tagName,
        ref: el.getAttribute('data-operator-id'),
        type: el.type || null,
        value: el.value !== undefined ? el.value : null,
    };
})()
"""
