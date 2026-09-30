"""Browser-run checks of STYLE_PROBE_SCRIPT (F2) and the hit-test script (F3).

Uses tiny inline synthetic snippets via page.set_content: no network, no
external URLs. Skipped when playwright or a launchable chromium is missing.
"""
import unittest

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from ..egress import rules as egress_rules
from ..egress.scripts import build_hit_test_script
from ..ingress import rules as ingress_rules
from ..ingress.scripts import STYLE_PROBE_SCRIPT
from ..types import Verdict

PROBE_KEYS = {"ref", "tag", "class_name", "text_snippet", "display", "visibility",
              "opacity", "font_size", "rect", "viewport"}

PROBE_HTML = """
<html><head><style>
.sr-only{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}
body{margin:0}
</style></head><body>
<p>Visible paragraph text here</p>
<div>Display none payload ALPHA</div>
<div style="display:none">Display none payload BRAVO</div>
<div style="opacity:0">Opacity zero payload CHARLIE</div>
<span style="font-size:0">Font zero payload DELTA</span>
<div style="position:absolute;left:-9999px;top:0">Offscreen payload ECHO</div>
<div style="display:none"><div><span>Ancestor hidden payload FOXTROT</span></div></div>
<span class="sr-only">Skip to main content</span>
</body></html>
"""


@pytest.fixture(scope="module")
def page():
    try:
        pw = sync_api.sync_playwright().start()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"playwright not startable: {exc}")
    try:
        browser = pw.chromium.launch()
    except Exception as exc:
        pw.stop()
        pytest.skip(f"chromium not launchable: {exc}")
    pg = browser.new_page(viewport={"width": 1000, "height": 700})
    yield pg
    browser.close()
    pw.stop()


def _probe(page, html):
    page.set_content(html)
    return page.evaluate(STYLE_PROBE_SCRIPT)


def _by_text(facts, needle):
    matches = [f for f in facts if needle in f["text_snippet"]]
    assert matches, f"no probe entry containing {needle!r}"
    # most specific (innermost) entry has the shortest snippet
    return min(matches, key=lambda f: len(f["text_snippet"]))


def _stripped_text(result):
    return " ".join(e.get("snippet", "") for e in result["stripped"])


def test_probe_returns_expected_keys(page):
    facts = _probe(page, PROBE_HTML)
    assert facts
    for f in facts:
        assert PROBE_KEYS <= set(f.keys())
    for k in ("width", "height"):
        assert k in facts[0]["viewport"]
    for k in ("left", "top", "right", "bottom"):
        assert k in facts[0]["rect"]


def test_probe_finds_plain_div_not_only_stamped(page):
    facts = _probe(page, PROBE_HTML)
    f = _by_text(facts, "BRAVO")
    assert f["display"] == "none"


def test_probe_opacity_zero(page):
    f = _by_text(_probe(page, PROBE_HTML), "CHARLIE")
    assert f["opacity"] == 0


def test_probe_font_size_zero(page):
    f = _by_text(_probe(page, PROBE_HTML), "DELTA")
    assert f["font_size"] == 0


def test_probe_offscreen_rect(page):
    f = _by_text(_probe(page, PROBE_HTML), "ECHO")
    assert f["rect"]["right"] < 0 or f["rect"]["left"] < -500


def test_probe_ancestor_hidden_reports_display_none(page):
    f = _by_text(_probe(page, PROBE_HTML), "FOXTROT")
    assert f["display"] == "none"


def test_probe_opacity_is_product_up_the_chain(page):
    html = ('<div style="opacity:0.2"><div style="opacity:0.5">'
            '<span>Chain payload GOLF</span></div></div>')
    f = _by_text(_probe(page, html), "GOLF")
    assert abs(f["opacity"] - 0.1) < 1e-6


def test_probe_output_feeds_hidden_node_rule(page):
    facts = _probe(page, PROBE_HTML)
    result = ingress_rules.find_hidden_textful_nodes(facts)
    stripped = _stripped_text(result)
    for token in ("BRAVO", "CHARLIE", "DELTA", "ECHO", "FOXTROT"):
        assert token in stripped, token
    assert "Visible paragraph" not in stripped
    assert "Skip to main content" not in stripped
    benign = " ".join(e.get("snippet", "") for e in result["skipped_benign"])
    assert "Skip to main content" in benign


def test_visible_only_page_strips_nothing(page):
    facts = _probe(page, "<body style='margin:0'><p>Just visible text</p><div>More visible</div></body>")
    assert ingress_rules.find_hidden_textful_nodes(facts)["stripped"] == []


HIT_HTML = """
<html><body style="margin:0">
<button id="b" data-operator-id="btn" style="position:absolute;left:100px;top:100px;width:200px;height:60px;padding:0">
  <span id="s" style="display:block;width:200px;height:60px">Pay now</span>
</button>
<div id="other" data-operator-id="other" style="position:absolute;left:500px;top:100px;width:100px;height:60px;background:#ccc">Other</div>
%s
</body></html>
"""
OVERLAY = ('<div data-operator-id="decoy" style="position:absolute;left:90px;top:90px;'
           'width:250px;height:100px;opacity:0;z-index:99999"></div>')


def _hit(page, html, selector, expected_ref="btn"):
    page.set_content(html)
    box = page.evaluate(
        "(s) => { const r = document.querySelector(s).getBoundingClientRect();"
        " return [r.left + r.width/2, r.top + r.height/2]; }", selector)
    return page.evaluate(build_hit_test_script(box[0], box[1], expected_ref=expected_ref))


def test_hit_child_span_inside_button_allows(page):
    hit = _hit(page, HIT_HTML % "", "#s")
    assert hit["inside_target"] is True
    verdict, _ = egress_rules.evaluate_hit_test(hit, "btn")
    assert verdict == Verdict.ALLOW


def test_hit_button_itself_allows(page):
    hit = _hit(page, HIT_HTML.replace('<span id="s"', '<span id="s" hidden'), "#b")
    verdict, _ = egress_rules.evaluate_hit_test(hit, "btn")
    assert verdict == Verdict.ALLOW


def test_hit_transparent_overlay_blocks(page):
    hit = _hit(page, HIT_HTML % OVERLAY, "#b")
    assert hit["inside_target"] is False
    verdict, _ = egress_rules.evaluate_hit_test(hit, "btn")
    assert verdict == Verdict.BLOCK


def test_hit_different_visible_element_escalates(page):
    # point at the other element while claiming the button was the target
    page.set_content(HIT_HTML % "")
    box = page.evaluate(
        "() => { const r = document.querySelector('#other').getBoundingClientRect();"
        " return [r.left + r.width/2, r.top + r.height/2]; }")
    hit = page.evaluate(build_hit_test_script(box[0], box[1], expected_ref="btn"))
    assert hit["inside_target"] is False
    verdict, _ = egress_rules.evaluate_hit_test(hit, "btn")
    assert verdict == Verdict.ESCALATE
