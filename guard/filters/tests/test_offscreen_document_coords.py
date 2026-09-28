"""Off-screen is judged in document coordinates, not viewport coordinates."""
from ..ingress.rules import find_hidden_textful_nodes

VIEWPORT = {"width": 1280, "height": 800}


def _fact(ref, top, bottom, left=10, right=400, scroll=None, doc=None, text="Visible text"):
    fact = {
        "ref": ref, "tag": "P", "class_name": "", "text_snippet": text,
        "display": "block", "visibility": "visible", "opacity": 1.0,
        "font_size": 16.0,
        "rect": {"left": left, "top": top, "right": right, "bottom": bottom},
        "viewport": VIEWPORT,
    }
    if scroll is not None:
        fact["scroll"] = scroll
    if doc is not None:
        fact["doc"] = doc
    return fact


def _stripped(facts):
    return find_hidden_textful_nodes(facts)["stripped"]


def test_below_fold_with_doc_facts_not_stripped():
    f = _fact("a", 2500, 2540, scroll={"x": 0, "y": 0}, doc={"width": 1280, "height": 4000})
    assert _stripped([f]) == []


def test_below_fold_without_doc_facts_not_stripped():
    assert _stripped([_fact("a", 2500, 2540)]) == []


def test_scrolled_far_down_not_stripped():
    # viewport top is negative, document top is positive
    f = _fact("a", -1200, -1160, scroll={"x": 0, "y": 3000}, doc={"width": 1280, "height": 6000})
    assert _stripped([f]) == []


def test_left_minus_9999_stripped():
    f = _fact("a", 10, 30, left=-9999, right=-9000, scroll={"x": 0, "y": 0},
              doc={"width": 1280, "height": 4000})
    assert len(_stripped([f])) == 1


def test_left_minus_9999_stripped_without_doc():
    assert len(_stripped([_fact("a", 10, 30, left=-9999, right=-9000)])) == 1


def test_above_page_origin_stripped():
    f = _fact("a", -9999, -9960, scroll={"x": 0, "y": 0}, doc={"width": 1280, "height": 4000})
    assert len(_stripped([f])) == 1


def test_above_page_origin_when_scrolled_stripped():
    # viewport top -5000 with scroll 100 gives document top -4900
    f = _fact("a", -5000, -4960, scroll={"x": 0, "y": 100}, doc={"width": 1280, "height": 4000})
    assert len(_stripped([f])) == 1


def test_beyond_document_height_stripped():
    f = _fact("a", 20000, 20040, scroll={"x": 0, "y": 0}, doc={"width": 1280, "height": 4000})
    assert len(_stripped([f])) == 1


def test_far_right_beyond_document_width_stripped():
    f = _fact("a", 10, 30, left=9000, right=9400, scroll={"x": 0, "y": 0},
              doc={"width": 1280, "height": 4000})
    assert len(_stripped([f])) == 1


def test_sixty_visible_paragraphs_zero_stripped():
    facts = [_fact(f"p{i}", i * 60, i * 60 + 40, scroll={"x": 0, "y": 0},
                   doc={"width": 1280, "height": 3700}, text=f"Paragraph {i}")
             for i in range(60)]
    assert _stripped(facts) == []


def test_sixty_visible_paragraphs_zero_stripped_old_probe():
    facts = [_fact(f"p{i}", i * 60, i * 60 + 40, text=f"Paragraph {i}") for i in range(60)]
    assert _stripped(facts) == []
