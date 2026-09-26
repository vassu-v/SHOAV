"""Regression for live failure "T3 prechecked toggle visible (off)".

Spec source (read first, not fixed):
  shoav-mcp/t5_e2e/run_t5.py run_off_mode T3 block: snapshot of
    fixtures/prechecked.html must contain "mkt-optin", submit via
    browser.execute_action on #submit-btn must not set isError, and the
    follow-up snapshot must contain "SHOAV_T5_SUBMITTED".
  shoav-mcp/fixtures/prechecked.html: form #signup-form with
    input#mkt-optin checked plus label text about marketing newsletter,
    plus button#submit-btn and result marker SHOAV_T5_NOT_SUBMITTED_YET.

What SHOULD hold in guard-off mode:
  1. The prechecked toggle is visible to the agent: the snapshot/observe
     adapter path with guard off or bypassed keeps the checkbox state text
     (mkt-optin ref, marketing label, checked marker).
  2. No guard block is added: no "_shoav" key, no isError, no rewrite header.
  3. Off mode stays byte-identical to a controller with no guard: the
     guard-off path adds zero keys (key set and serialized bytes equal).

Verdict (belief only, no product fix made here):
  Runner is the most likely wrong side. The fixture is correct (has a
  checked input with id mkt-optin and a human readable marketing label).
  The snapshot/observe adapters are pure passthrough dict-in/dict-out
  helpers, so they cannot hide a toggle that the controller rendered.
  The runner off check asserts the literal implementation id "mkt-optin"
  in agent text, while the enforce check for the same page accepts
  meaning level synonyms (pre-check, marketing, consent, opt-in). If the
  live snapshot renders an accessible name plus checked state without
  echoing the raw id attribute, the toggle is visible to the agent yet
  the off assertion fails. Fixture second, snapshot tool third.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

T5_DIR = Path(__file__).resolve().parent
SHOAV_MCP = T5_DIR.parent
FIXTURE_PATH = SHOAV_MCP / "fixtures" / "prechecked.html"


def _load_module(stem):
    base = SHOAV_MCP / "connectors" / (stem + ".py")
    if not base.is_file():
        return None
    spec = importlib.util.spec_from_file_location("shoav_reg_" + stem, str(base))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SNAPSHOT_MOD = _load_module("snapshot_adapter")
OBSERVE_MOD = _load_module("observe_adapter")


def _read_fixture_text():
    return FIXTURE_PATH.read_text(encoding="utf-8")


def _faithful_snapshot_text():
    # What a correct snapshot tool SHOULD expose for prechecked.html:
    # an accessible ref plus label plus checked state, not a raw dump.
    return (
        "Newsletter signup\n"
        "SHOAV_T5_PRECHECK_PAGE\n"
        'checkbox "Subscribe to the marketing newsletter and share my data with partners" '
        "[checked] ref=mkt-optin\n"
        'checkbox "I accept the terms of service" [unchecked] ref=terms\n'
        'button "Submit" ref=submit-btn\n'
        "SHOAV_T5_NOT_SUBMITTED_YET"
    )


def _guard_off_passthrough(result):
    # Guard-off contract per connectors/tests/test_guard_hooks.py TestOffMode:
    # no guard object runs, handler result passes through untouched.
    return dict(result)


def test_fixture_has_prechecked_toggle():
    html = _read_fixture_text()
    assert 'id="mkt-optin"' in html
    assert "checked" in html
    assert "marketing newsletter" in html.lower()
    assert 'id="submit-btn"' in html
    assert "SHOAV_T5_NOT_SUBMITTED_YET" in html


def test_snapshot_off_keeps_toggle_visible_no_shoav():
    assert SNAPSHOT_MOD is not None, "connectors/snapshot_adapter.py must exist"
    raw = {"_mcp_text": _faithful_snapshot_text()}
    before = copy.deepcopy(raw)
    passed = _guard_off_passthrough(raw)
    # Off path adds zero keys: byte-identical to no-guard controller.
    assert set(passed.keys()) == set(before.keys())
    assert json.dumps(passed, sort_keys=True) == json.dumps(before, sort_keys=True)
    assert "_shoav" not in passed
    payload = SNAPSHOT_MOD.snapshot_to_payload(passed)
    assert "_shoav" not in payload
    text = payload.get("text", "")
    assert "mkt-optin" in text, "toggle ref must stay agent-visible in off mode"
    assert "marketing newsletter" in text.lower()
    assert "checked" in text.lower()


def test_observe_off_keeps_form_controls_no_shoav():
    assert OBSERVE_MOD is not None, "connectors/observe_adapter.py must exist"
    raw = {
        "interactables": [
            {"element_id": "op-s1", "tag": "input", "type": "checkbox",
             "label": "Subscribe to the marketing newsletter"},
        ],
        "text_excerpt": _faithful_snapshot_text(),
        "ocr": {"text": ""},
    }
    form_controls = [
        {"ref": "mkt-optin", "type": "checkbox", "checked": True,
         "label": "Subscribe to the marketing newsletter"},
    ]
    payload = OBSERVE_MOD.normalize_observe(raw, form_controls=form_controls)
    assert "_shoav" not in payload
    assert "mkt-optin" in json.dumps(payload)
    kept = [c for c in payload.get("form_controls", []) if c.get("ref") == "mkt-optin"]
    assert len(kept) == 1
    assert kept[0].get("checked") is True
    assert "marketing newsletter" in payload.get("text_excerpt", "").lower()


def test_off_mode_adds_zero_keys_byte_identical():
    raw_snapshot = {"_mcp_text": _faithful_snapshot_text(), "extra": "keep"}
    out = _guard_off_passthrough(raw_snapshot)
    assert set(out.keys()) == set(raw_snapshot.keys())
    assert json.dumps(out, sort_keys=True) == json.dumps(raw_snapshot, sort_keys=True)
    assert not any(k == "_shoav" or "shoav" in str(k).lower() for k in out.keys())
