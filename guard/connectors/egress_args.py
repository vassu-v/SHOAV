"""Egress argument builder plus form-state probe script and runner.

Pure dict-in/dict-out. No controller imports. The page_evaluate callable
is injected by the guard layer, never imported here.

RECON unify e (FORMSTATE/normalizer single home): the JS probe home is
filters/ingress/scripts.py FORM_STATE_SCRIPT (imported above so the
window.__shoavSeq stamping stays shared); the Python normalizer home is
connectors.normalize_form_controls below. filters/ingress/engine.py keeps
a small inline normalization for its accessibility_outline fallback path
only; the FORM_STATE_SCRIPT path should delegate here on a future pass
(filters/ingress is outside this agent's ownership, so that half is filed
as pending and this file documents the decision).
Product rule: synthetic data only, no em dashes.
"""

from __future__ import annotations

try:
    # Single source of truth for the live probe (copy-regression fix):
    # the canonical FORM_STATE_SCRIPT lives in filters/ingress/scripts.py
    # so the ref stamping sequence stays shared with the interactables
    # script and mark_touched correlation keeps working.
    from filters.ingress.scripts import FORM_STATE_SCRIPT as _CANONICAL_FORM_STATE_SCRIPT

    FORM_STATE_SCRIPT = _CANONICAL_FORM_STATE_SCRIPT
except Exception:  # pragma: no cover - fail open to the embedded copy
    FORM_STATE_SCRIPT = """
(() => {
    window.__shoavSeq = window.__shoavSeq || 0;
    const out = [];
    const els = document.querySelectorAll('input, select, textarea, [role="checkbox"], [role="switch"]');
    const stampRef = (el) => {
        const existing = el.getAttribute('data-operator-id');
        if (existing) return existing;
        if (el.dataset && el.dataset.operatorId) return el.dataset.operatorId;
        window.__shoavSeq = (window.__shoavSeq || 0) + 1;
        const ref = 'op-s' + window.__shoavSeq.toString(36);
        try { el.dataset.operatorId = ref; } catch (e) {}
        return ref;
    };
    for (const el of els) {
        const isCheckbox = el.tagName === 'INPUT'
            ? (el.type === 'checkbox' || el.type === 'radio')
            : (el.getAttribute('role') === 'checkbox' || el.getAttribute('role') === 'switch');
        const ref = stampRef(el)
            || el.getAttribute('data-ref')
            || el.id
            || el.name
            || null;
        const labelEl = el.id ? document.querySelector('label[for="' + CSS.escape(el.id) + '"]') : null;
        const label = (labelEl && labelEl.innerText ? labelEl.innerText.trim() : '')
            || el.getAttribute('aria-label')
            || el.name
            || '';
        out.push({
            element_id: el.getAttribute('data-operator-id') || null,
            ref: ref,
            type: el.tagName === 'INPUT' ? (el.type || 'text') : (el.getAttribute('role') || el.tagName.toLowerCase()),
            checked: !!el.checked,
            label: label,
            is_checkbox_like: !!isCheckbox,
        });
    }
    return out;
})()
"""


def normalize_form_controls(raw: list[dict] | dict | None) -> list[dict]:
    """Normalize FORM_STATE_SCRIPT output to [{ref, type, checked, label}].

    Canonical Python normalizer home (RECON unify e). Prefers ref, then
    element_id, and coerces checked to bool. Extra keys (tag, name) are
    dropped so only guard-safe fields flow into the engine.
    """
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else [raw]
    controls: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        controls.append(
            {
                "ref": item.get("ref") or item.get("element_id"),
                "type": item.get("type"),
                "checked": bool(item.get("checked")),
                "label": item.get("label"),
            }
        )
    return controls


async def run_form_state_probe(page_evaluate_fn) -> list[dict]:
    """Run FORM_STATE_SCRIPT via an injected evaluate callable.

    page_evaluate_fn(script) may be sync (returns the raw list) or async
    (returns an awaitable). The raw output is normalized to
    [{ref, type, checked, label}]. Raises whatever the callable raises;
    the guard layer decides fail-open vs fail-closed.
    """
    raw = page_evaluate_fn(FORM_STATE_SCRIPT)
    if hasattr(raw, "__await__"):
        raw = await raw
    if isinstance(raw, dict) and "result" in raw:
        raw = raw["result"]
    return normalize_form_controls(raw if isinstance(raw, list) else [])


def _selector_for(element_id: str) -> str:
    return f'[data-operator-id="{element_id}"]'


def _looks_like_submit_control(element_id: str | None, cache: list[dict]) -> bool:
    """True when the cached interactable looks like a submit control (F-D).

    Matches the gateway submit-control check: type submit/button or a
    submit/place-order label. Pure function over the per-session
    interactables cache.
    """
    if not element_id:
        return False
    for node in cache:
        if not isinstance(node, dict):
            continue
        if node.get("element_id") != element_id:
            continue
        node_type = str(node.get("type") or "").lower()
        label = str(node.get("label") or node.get("name") or "").lower()
        if node_type in ("submit", "button"):
            return True
        if "submit" in label or "place order" in label:
            return True
        return False
    return False


def _center_of(bbox: dict | None) -> dict | None:
    if not isinstance(bbox, dict):
        return None
    try:
        x = float(bbox.get("x", 0))
        y = float(bbox.get("y", 0))
        w = float(bbox.get("width", 0))
        h = float(bbox.get("height", 0))
    except (TypeError, ValueError):
        return None
    return {"x": x + w / 2.0, "y": y + h / 2.0}


def decision_to_egress_args(
    tool: str | dict,
    arguments: dict | None = None,
    interactables: list[dict] | None = None,
) -> dict:
    """Normalize an egress tool call into guard-actionable args.

    Args:
      tool: "execute_action" or "drag_drop" (other names yield kind "skip").
      arguments: raw tool arguments. For execute_action the inner action
        may be nested under arguments["action"] as a dict or a flat
        action/type/disposition. Supported action names: click,
        select_option, type, fill, press.
      interactables: cached per-session interactables for element_id
        resolution ([{element_id, ..., bbox}]).

    Returns a dict with at least {"kind", "element_id", "selector",
    "bbox", "center", "expected_ref", "needs_hit_test",
    "needs_focus_check", "needs_submit_check"}. kind is one of
    "click", "drag", "type", "submit", "skip".

    Single-dict shorthand: decision_to_egress_args({"element_id": ...,
    "box": [x, y, w, h]}) resolves the element against interactables and
    returns click-style args with selector and center.
    """
    if isinstance(tool, dict) and arguments is None:
        shorthand = tool
        element_id = shorthand.get("element_id")
        box = shorthand.get("box") or shorthand.get("bbox")
        bbox = None
        if isinstance(box, (list, tuple)) and len(box) == 4:
            try:
                x, y, w, h = (float(v) for v in box)
                bbox = {"x": x, "y": y, "width": w, "height": h}
            except (TypeError, ValueError):
                bbox = None
        if interactables and element_id and bbox is None:
            for node in interactables:
                if isinstance(node, dict) and node.get("element_id") == element_id:
                    bbox = node.get("bbox") if isinstance(node.get("bbox"), dict) else None
                    break
        return {
            "kind": "click",
            "element_id": element_id,
            "selector": _selector_for(element_id) if element_id else None,
            "bbox": bbox,
            "center": _center_of(bbox),
            "expected_ref": element_id,
            "needs_hit_test": True,
            "needs_focus_check": False,
            "needs_submit_check": False,
        }
    args = arguments if isinstance(arguments, dict) else {}
    cache = list(interactables) if interactables else []

    def resolve(element_id: str | None) -> dict:
        bbox = None
        if element_id:
            for node in cache:
                if isinstance(node, dict) and node.get("element_id") == element_id:
                    bbox = node.get("bbox")
                    break
        return {
            "element_id": element_id,
            "selector": _selector_for(element_id) if element_id else None,
            "bbox": bbox,
            "center": _center_of(bbox),
            "expected_ref": element_id,
        }

    if tool == "drag_drop":
        return {
            "kind": "drag",
            "needs_hit_test": True,
            "needs_focus_check": False,
            "needs_submit_check": False,
            "start": args.get("start") or args.get("from"),
            "end": args.get("end") or args.get("to"),
            "element_id": args.get("element_id"),
            "selector": _selector_for(args["element_id"]) if args.get("element_id") else None,
            "bbox": None,
            "center": None,
            "expected_ref": None,
            "note": "coordinate-only drag: decoy check only, no target containment",
        }

    if tool != "execute_action":
        return {
            "kind": "skip",
            "reason": f"tool {tool!r} is not gated in v1",
            "element_id": None,
            "selector": None,
            "bbox": None,
            "center": None,
            "expected_ref": None,
            "needs_hit_test": False,
            "needs_focus_check": False,
            "needs_submit_check": False,
        }

    inner = args.get("action")
    action: dict = dict(inner) if isinstance(inner, dict) else dict(args)
    name = str(action.get("action") or action.get("type") or action.get("name") or "").lower()
    element_id = action.get("element_id") or action.get("ref") or args.get("element_id")

    if name in ("click", "select_option", "select"):
        resolved = resolve(element_id)
        key = (action.get("key") or "").lower() if isinstance(action.get("key"), str) else ""
        submit_hint = (
            name == "select_option"
            or key in ("enter", "return")
            or bool(action.get("submit"))
            or _looks_like_submit_control(element_id, cache)
        )
        return {
            "kind": "click",
            **resolved,
            "needs_hit_test": True,
            "needs_focus_check": False,
            "needs_submit_check": submit_hint,
        }

    if name in ("type", "fill", "input"):
        resolved = resolve(element_id)
        value = action.get("text", action.get("value", action.get("input")))
        return {
            "kind": "type",
            **resolved,
            "text": value if isinstance(value, str) else "",
            "sensitive": bool(action.get("sensitive")),
            "needs_hit_test": False,
            "needs_focus_check": True,
            "needs_submit_check": False,
        }

    if name in ("press", "keydown"):
        key = action.get("key", action.get("text", ""))
        resolved = resolve(element_id)
        wants_submit = isinstance(key, str) and key.lower() in ("enter", "return")
        return {
            "kind": "submit" if wants_submit else "skip",
            **resolved,
            "key": key,
            "needs_hit_test": False,
            "needs_focus_check": False,
            "needs_submit_check": wants_submit,
            **({} if wants_submit else {"reason": f"action {name!r} is not gated in v1"}),
        }

    return {
        "kind": "skip",
        "reason": f"action {name!r} is not gated in v1",
        "element_id": element_id,
        "selector": _selector_for(element_id) if element_id else None,
        "bbox": None,
        "center": None,
        "expected_ref": element_id,
        "needs_hit_test": False,
        "needs_focus_check": False,
        "needs_submit_check": False,
    }
