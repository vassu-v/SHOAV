"""Payload normalizers for snapshot, find_elements, and get_html.

Pure dict-in/dict-out. No controller imports. Each function extracts the
scannable text from a raw handler result dict and returns a minimal
{"text": str} payload for the text-scan half of Target 1.
"""

from __future__ import annotations


def snapshot_to_payload(result_dict: dict) -> dict:
    """Extract scannable text from a browser.snapshot result.

    Snapshot results carry the readable text in "_mcp_text" (they omit
    structuredContent, so the rewrite must target that key).
    """
    result = result_dict if isinstance(result_dict, dict) else {}
    text = result.get("_mcp_text") or ""
    if not isinstance(text, str):
        text = str(text)
    return {"text": text, "text_excerpt": text}


def find_elements_to_payload(result_dict: dict) -> dict:
    """Extract scannable text from a browser.find_elements result.

    Concatenates each element's "text" and "context_text". Accepts three
    shapes: {"elements": [...]}, {"items": [...]}, and a flat
    {"text", "context_text"} dict. Missing keys become empty strings.
    """
    result = result_dict if isinstance(result_dict, dict) else {}
    elements = result.get("elements")
    if elements is None:
        elements = result.get("items")
    if isinstance(elements, list):
        parts: list[str] = []
        for el in elements:
            if not isinstance(el, dict):
                continue
            text = el.get("text") or ""
            context = el.get("context_text") or ""
            if text:
                parts.append(str(text))
            if context:
                parts.append(str(context))
        return {"text": "\n".join(parts), "text_excerpt": "\n".join(parts)}
    text = result.get("text") or ""
    context = result.get("context_text") or ""
    combined = "\n".join(p for p in (str(text), str(context)) if p)
    return {"text": combined, "text_excerpt": combined}


def get_html_to_payload(result_dict: dict) -> dict:
    """Extract scannable text from a browser.get_html result.

    Runs the text scan on "content".
    """
    result = result_dict if isinstance(result_dict, dict) else {}
    content = result.get("content") or ""
    if not isinstance(content, str):
        content = str(content)
    return {"text": content, "text_excerpt": content}
