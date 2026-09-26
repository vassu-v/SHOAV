"""Normalize browser.observe results into filter-ready payloads.

Pure dict-in/dict-out. No controller imports.
"""

from __future__ import annotations


def normalize_observe(
    result_dict: dict,
    style_facts: list[dict] | None = None,
    form_controls: list[dict] | None = None,
) -> dict:
    """Build an ingress payload from a raw browser.observe result dict.

    Reads (all optional, missing keys become empty):
      result_dict["interactables"]: list of
        {element_id, tag, type, role, label, bbox}
      result_dict["text_excerpt"]: str
      result_dict["ocr"]["text"]: str (also accepts result_dict["ocr_text"])

    Args:
      result_dict: raw handler result dict. Never mutated.
      style_facts: STYLE_PROBE_SCRIPT output (list of style fact dicts),
        gathered by the guard via session.page.evaluate. None means the
        style half of Target 1 is skipped.
      form_controls: FORM_STATE_SCRIPT output normalized to
        [{ref, type, checked, label}]. None means Target 3 runs on
        whatever the result already carries, if anything.

    Returns:
      {"interactables": [...], "text_excerpt": str, "ocr_text": str,
       "style_facts": [...], "form_controls": [...]}
    """
    result = result_dict if isinstance(result_dict, dict) else {}
    interactables = result.get("interactables") or []
    text_excerpt = result.get("text_excerpt") or ""
    ocr_text = ""
    ocr = result.get("ocr")
    if isinstance(ocr, dict):
        ocr_text = ocr.get("text") or ""
    if not ocr_text and isinstance(result.get("ocr_text"), str):
        ocr_text = result.get("ocr_text") or ""

    return {
        "interactables": list(interactables),
        "text_excerpt": text_excerpt if isinstance(text_excerpt, str) else "",
        "ocr_text": ocr_text if isinstance(ocr_text, str) else "",
        "style_facts": list(style_facts) if style_facts is not None else [],
        "form_controls": list(form_controls) if form_controls is not None else [],
    }
