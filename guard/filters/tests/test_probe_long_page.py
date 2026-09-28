"""Real Chromium: a long, fully visible page must not be stripped by the off-screen rule."""
import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from ..ingress import rules as ingress_rules
from ..ingress.scripts import STYLE_PROBE_SCRIPT


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


def _paragraphs(n=60):
    return "".join(f"<p style='margin:0;height:50px'>Long page paragraph number {i:03d} text</p>"
                   for i in range(n))


LONG = "<html><body style='margin:0'>" + _paragraphs() + "%s</body></html>"
LEFT = "<p style='position:absolute;left:-9999px;top:100px'>HIDDEN_LEFT_PAYLOAD</p>"
TOP = "<p style='position:absolute;top:-9999px;left:10px'>HIDDEN_TOP_PAYLOAD</p>"


def _probe(page, html, scroll_y=0):
    page.set_content(html)
    if scroll_y:
        page.evaluate(f"window.scrollTo(0,{scroll_y})")
    return page.evaluate(STYLE_PROBE_SCRIPT)


def _text(result):
    return " ".join(e.get("text", "") for e in result["stripped"])


def test_long_visible_page_strips_nothing(page):
    facts = _probe(page, LONG % "")
    assert any("number 059" in f["text_snippet"] for f in facts)
    assert ingress_rules.find_hidden_textful_nodes(facts)["stripped"] == []


def test_only_offscreen_paragraphs_stripped(page):
    facts = _probe(page, LONG % (LEFT + TOP))
    result = ingress_rules.find_hidden_textful_nodes(facts)
    text = _text(result)
    assert "HIDDEN_LEFT_PAYLOAD" in text and "HIDDEN_TOP_PAYLOAD" in text
    assert "Long page paragraph" not in text
    assert len(result["stripped"]) == 2


def test_scrolled_window_still_strips_nothing_visible(page):
    facts = _probe(page, LONG % "", scroll_y=1500)
    assert any(f["rect"]["top"] < 0 for f in facts)
    assert ingress_rules.find_hidden_textful_nodes(facts)["stripped"] == []


def test_scrolled_window_still_strips_hidden(page):
    facts = _probe(page, LONG % (LEFT + TOP), scroll_y=1500)
    result = ingress_rules.find_hidden_textful_nodes(facts)
    assert len(result["stripped"]) == 2
    assert "Long page paragraph" not in _text(result)


def test_probe_facts_have_scroll_and_doc(page):
    facts = _probe(page, LONG % "", scroll_y=1500)
    assert facts
    for f in facts:
        assert "scroll" in f and "doc" in f
    f = facts[0]
    assert f["scroll"]["y"] == 1500 and f["scroll"]["x"] == 0
    assert f["doc"]["height"] >= 3000
    assert 1 <= f["doc"]["width"] <= 1100
