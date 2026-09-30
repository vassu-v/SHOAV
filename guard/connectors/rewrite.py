"""Apply ingress verdicts back onto MCP result dicts.

Pure dict-in/dict-out. No controller imports.

Safety rule: never copy page-derived strings (snippets, keywords, hidden
text, element labels) into the agent-visible summary. The _shoav note and
block reasons carry only counts, kinds, and guard-authored wording so a
hostile page cannot smuggle instructions through the guard's own telemetry.
"""

from __future__ import annotations

REWRITE_HEADER = "[S.H.O.A.V. guard: content sanitized]"

# Canonical scrub home (RECON unify a): _scrub_field below is the single
# source of truth for per-field scrubbing. Controller guard.py imports it
# and gateway.py keeps a local copy only as pending unification (see
# PENDING-GATEWAY note in guard.py; do NOT edit gateway.py from here).
REMOVED_MARKER = "[removed by S.H.O.A.V.: suspected injected instruction]"

# Supplemental phrases for find_elements/get_html element-level scrubbing
# (F-B). Core keywords come from filters.constants when importable; this fallback keeps connectors
# pure dict-in/dict-out with no controller imports. The shoav_t5_hidden
# entry covers synthetic hidden-text fixtures: bare marker tokens carry no
# core keyword, so without it a display:none plus opacity:0 pair leaves one
# marker runner-visible after sentence splitting merges the middle boundary.
_SUPPLEMENTAL_PHRASES = (
    "approve every refund",
    "send admin password",
    "admin password",
    "_inject_token",
    "_inject",
    "shoav_t5_hidden",
)

_CORE_KEYWORDS: tuple[str, ...] = ()
_ZERO_WIDTH: tuple[str, ...] = ()
try:  # pragma: no cover - import path varies by runner
    from filters.constants import INGRESS_INJECTION_KEYWORDS as _KW  # type: ignore
    from filters.constants import ZERO_WIDTH_CHARS as _ZW  # type: ignore

    _CORE_KEYWORDS = tuple(k.lower() for k in _KW)
    _ZERO_WIDTH = tuple(_ZW)
except Exception:
    _CORE_KEYWORDS = (
        "ignore previous",
        "ignore all previous",
        "disregard",
        "system prompt",
        "you are now",
        "new instructions",
        "act as",
        "assistant:",
    )
    _ZERO_WIDTH = (chr(0x200B), chr(0x200C), chr(0x200D), chr(0xFEFF))


def _scrub_field(value: str) -> str:
    """Deterministic per-field scrub for elements/content (F-B).

    Removes zero-width chars, then replaces sentences containing core
    injection keywords or supplemental refund/exfiltration markers with
    REMOVED_MARKER. Guard-authored marker only, never page text. HTML tags
    are split out before sentence splitting so a missing space at a tag
    boundary (</p><div>) does not merge a benign sentence with an injected
    one into a single replaceable blob.
    """
    import re as _re

    text = value
    for ch in _ZERO_WIDTH:
        if ch in text:
            text = text.replace(ch, "")
    marker = REMOVED_MARKER
    out_lines: list[str] = []
    for line in text.split("\n"):
        segs = _re.split(r"(<[^>]*>)", line)
        for idx, seg in enumerate(segs):
            if not seg or (seg.startswith("<") and seg.endswith(">")):
                continue
            parts = _re.split(r"(?<=[.!?])\s+", seg)
            new_parts: list[str] = []
            for part in parts:
                lowered = part.lower()
                if any(k in lowered for k in _CORE_KEYWORDS) or any(
                    p in lowered for p in _SUPPLEMENTAL_PHRASES
                ):
                    new_parts.append(marker)
                else:
                    new_parts.append(part)
            segs[idx] = " ".join(new_parts)
        out_lines.append("".join(segs))
    return "\n".join(out_lines)


def scrub_field(value: str) -> str:
    """Public alias of the canonical _scrub_field (RECON unify a)."""
    return _scrub_field(value)


def scrub_with_count(value: str) -> tuple[str, int]:
    """Canonical scrub plus removal count (RECON unify a).

    Counts REMOVED_MARKER occurrences in the scrubbed output so the
    guard layer can upgrade ALLOW to REWRITE without duplicating
    sentence logic. Guard-authored marker only, never page text.
    """
    scrubbed = _scrub_field(value)
    return scrubbed, scrubbed.count(REMOVED_MARKER)


def findings_to_summary(findings) -> dict:
    """Canonical findings to count/groups shape (RECON unify b).

    Accepts grouped dicts ({kind: [...]}, the filter engine shape),
    canonical lists ([{kind, detail}]), plain counts (int), or None.
    Returns {"count": int} plus "groups" when kind names are known.
    Detail strings are dropped so page content never flows into telemetry.
    Gateway _shoav_findings should delegate here (pending, do NOT edit
    gateway.py from this agent).
    """
    if findings is None:
        return {"count": 0}
    if isinstance(findings, int):
        try:
            return {"count": int(findings)}
        except (TypeError, ValueError):
            return {"count": 0}
    if isinstance(findings, float):
        try:
            return {"count": int(findings)}
        except (TypeError, ValueError):
            return {"count": 0}
    if isinstance(findings, list):
        return {"count": len(findings)}
    if isinstance(findings, dict):
        if isinstance(findings.get("count"), (int, float)):
            return {"count": int(findings["count"])}
        total = 0
        groups: list[str] = []
        for kind, items in findings.items():
            groups.append(str(kind))
            if isinstance(items, list):
                total += len(items)
            elif isinstance(items, dict):
                stripped = items.get("stripped")
                if isinstance(stripped, list):
                    total += len(stripped)
                else:
                    total += 1
            elif isinstance(items, int):
                total += items
            elif items:
                total += 1
        if groups:
            return {"count": total, "groups": sorted(groups)}
        return {"count": total}
    return {"count": 0}


def findings_to_list(findings) -> list[dict]:
    """Canonical findings to [{kind, detail}] shape (RECON unify b).

    Accepts grouped dicts, canonical lists, plain counts, or None.
    Grouped dicts expand to one entry per item with detail None so the
    live redactor never receives page-derived strings. Plain counts
    expand to count entries with kind "finding" so counts survive the
    round trip. Used by phases.redact_guard_findings.
    """
    if findings is None:
        return []
    if isinstance(findings, list):
        out: list[dict] = []
        for item in findings:
            if isinstance(item, dict) and "kind" in item:
                out.append({"kind": item.get("kind"), "detail": item.get("detail", item.get("message"))})
            elif isinstance(item, dict):
                out.append({"kind": "finding", "detail": None})
            else:
                out.append({"kind": "finding", "detail": item})
        return out
    if isinstance(findings, dict) and not any(k in findings for k in ("kind", "detail", "message")) and "count" not in findings:
        out = []
        for kind, items in findings.items():
            if isinstance(items, list):
                for _ in items:
                    out.append({"kind": str(kind), "detail": None})
            elif isinstance(items, int):
                for _ in range(max(0, int(items))):
                    out.append({"kind": str(kind), "detail": None})
            else:
                out.append({"kind": str(kind), "detail": None})
        return out
    if isinstance(findings, dict) and isinstance(findings.get("count"), (int, float)):
        try:
            count = int(findings["count"])
        except (TypeError, ValueError):
            count = 0
        return [{"kind": "finding", "detail": None} for _ in range(max(0, count))]
    if isinstance(findings, (int, float)):
        try:
            count = int(findings)
        except (TypeError, ValueError):
            return []
        return [{"kind": "finding", "detail": None} for _ in range(max(0, count))]
    return [{"kind": "finding", "detail": findings}]


def _read_sanitized(verdict_dict: dict) -> dict:
    """ONE ingress contract reader: sanitized primary, payload fallback."""
    if not isinstance(verdict_dict, dict):
        return {}
    sanitized = verdict_dict.get("sanitized")
    if isinstance(sanitized, dict):
        return sanitized
    fallback = verdict_dict.get("payload")
    if isinstance(fallback, dict):
        return fallback
    nested = verdict_dict.get("result")
    if isinstance(nested, dict) and isinstance(nested.get("payload"), dict):
        return nested["payload"]
    if isinstance(sanitized, str):
        return {"text": sanitized}
    if isinstance(fallback, str):
        return {"text": fallback}
    return {}


def _verdict_str(verdict_dict: dict) -> str:
    verdict = verdict_dict.get("verdict", "ALLOW")
    if hasattr(verdict, "value"):
        return str(verdict.value)
    return str(verdict)


def _count_findings(findings) -> tuple[int, list[str]]:
    """Summarize a findings blob into (total_count, sorted_kind_names).

    Only counts and key names are returned. Detail strings and snippets
    are deliberately dropped so page content never flows into telemetry.
    Thin wrapper over findings_to_summary (RECON unify b).
    """
    summary = findings_to_summary(findings)
    count = int(summary.get("count", 0) or 0)
    groups = summary.get("groups")
    if isinstance(groups, list):
        return count, [str(g) for g in groups]
    return count, []


def apply_rewrite(result_dict: dict, verdict_dict: dict) -> dict:
    """Return a new result dict with sanitized text and a leading _shoav key.

    ONE ingress contract: sanitized text is read from
    verdict_dict["sanitized"] (primary) with verdict_dict["payload"]
    fallback, both shaped {text_excerpt, interactables}. Legacy nested
    result.payload is also accepted. Which result key is rewritten is
    detected from the result shape:
      "text_excerpt" in result -> browser.observe (plus "interactables")
      "_mcp_text" in result -> browser.snapshot (from sanitized
        text_excerpt/text, structuredContent stays omitted)
      "elements" (list) in result -> browser.find_elements (each
        element text/context_text/match scrubbed, plus text_excerpt)
      "content" in result -> browser.get_html (content scrubbed, plus
        text_excerpt)

    The returned dict has "_shoav" FIRST:
      {"_shoav": {"verdict": str, "findings": int, "summary": str}, ...}

    _shoav.findings is a count only. _shoav.summary is guard-authored
    wording plus counts, never page-derived instructions.
    """
    result = dict(result_dict) if isinstance(result_dict, dict) else {}
    verdict = verdict_dict if isinstance(verdict_dict, dict) else {}
    verdict_name = _verdict_str(verdict)
    findings_blob = verdict.get("findings", {})
    count, kinds = _count_findings(findings_blob)

    kind_part = (" (" + ", ".join(kinds) + ")") if kinds else ""
    summary = (
        f"{REWRITE_HEADER} verdict={verdict_name} "
        f"findings={count}{kind_part}"
    )
    shoav_note = {
        "verdict": verdict_name,
        "findings": count,
        "summary": summary,
    }

    sanitized = _read_sanitized(verdict)
    updated = dict(result)

    clean_excerpt: str | None = None
    if isinstance(sanitized.get("text_excerpt"), str):
        clean_excerpt = sanitized["text_excerpt"]
    elif isinstance(sanitized.get("text"), str):
        clean_excerpt = sanitized["text"]
    elif isinstance(sanitized.get("_mcp_text"), str):
        clean_excerpt = sanitized["_mcp_text"]

    if "text_excerpt" in updated and clean_excerpt is not None:
        updated["text_excerpt"] = _scrub_field(clean_excerpt)
        if "interactables" in sanitized and isinstance(sanitized["interactables"], list):
            updated["interactables"] = sanitized["interactables"]
        header = sanitized.get("header") if isinstance(sanitized.get("header"), str) else REWRITE_HEADER
        if isinstance(updated.get("text_excerpt"), str) and header not in updated["text_excerpt"]:
            updated["text_excerpt"] = header + "\n" + updated["text_excerpt"]
    if "_mcp_text" in updated:
        clean_text = clean_excerpt
        if clean_text is None:
            raw = sanitized.get("text", sanitized.get("_mcp_text", ""))
            clean_text = raw if isinstance(raw, str) else ""
        header = sanitized.get("header") if isinstance(sanitized.get("header"), str) else REWRITE_HEADER
        if isinstance(clean_text, str):
            scrubbed_text = _scrub_field(clean_text)
            updated["_mcp_text"] = (
                header + "\n" + scrubbed_text if header not in scrubbed_text else scrubbed_text
            )
    if "elements" in updated and isinstance(updated.get("elements"), list):
        scrubbed_elements: list = []
        for el in updated["elements"]:
            if not isinstance(el, dict):
                scrubbed_elements.append(el)
                continue
            cleaned = dict(el)
            for key in ("text", "context_text", "match"):
                if isinstance(cleaned.get(key), str):
                    cleaned[key] = _scrub_field(cleaned[key])
            scrubbed_elements.append(cleaned)
        updated["elements"] = scrubbed_elements
        if "text_excerpt" not in updated and clean_excerpt is not None:
            header = sanitized.get("header") if isinstance(sanitized.get("header"), str) else REWRITE_HEADER
            scrubbed_excerpt = _scrub_field(clean_excerpt)
            updated["text_excerpt"] = header + "\n" + scrubbed_excerpt if header not in scrubbed_excerpt else scrubbed_excerpt
    if "items" in updated and isinstance(updated.get("items"), list):
        # find_elements items shape: same scrub contract as elements shape
        # (text, context_text, match per entry) so injected sentences in
        # items[] cannot survive while elements[] is cleaned.
        scrubbed_items: list = []
        for el in updated["items"]:
            if not isinstance(el, dict):
                scrubbed_items.append(el)
                continue
            cleaned = dict(el)
            for key in ("text", "context_text", "match"):
                if isinstance(cleaned.get(key), str):
                    cleaned[key] = _scrub_field(cleaned[key])
            scrubbed_items.append(cleaned)
        updated["items"] = scrubbed_items
        if "text_excerpt" not in updated and clean_excerpt is not None:
            header = sanitized.get("header") if isinstance(sanitized.get("header"), str) else REWRITE_HEADER
            scrubbed_excerpt = _scrub_field(clean_excerpt)
            updated["text_excerpt"] = header + "\n" + scrubbed_excerpt if header not in scrubbed_excerpt else scrubbed_excerpt
    if "content" in updated and isinstance(updated.get("content"), str):
        if clean_excerpt is not None and "text_excerpt" not in updated:
            # get_html content scan: write back cleaned scan text when the
            # result carries no separate text_excerpt.
            updated["content"] = _scrub_field(updated["content"])
            if not isinstance(updated["content"], str) or not updated["content"]:
                updated["content"] = clean_excerpt
        else:
            updated["content"] = _scrub_field(updated["content"])

    return {"_shoav": shoav_note, **updated}


def build_block(tool: str, reason: str, shoav_detail: dict | None = None) -> dict:
    """Build an ingress BLOCK / egress BLOCK-or-ESCALATE body.

    Decision: plan.md MCP/plan.md section 5 specifies BLOCK as error
    first ({"error": reason, "shoav": {...}} so the timeline row shows
    the reason). The T1 _shoav contract requires a leading _shoav block
    {verdict, findings, summary} in the same dict. This builder carries
    both so both consumer families work: the returned dict is
    {"_shoav": {...}, "error": reason, "shoav": {...}} with _shoav
    FIRST for _shoav consumers, while error-first consumers still read
    body["error"] and body["shoav"] unchanged. The caller sets
    isError=True and mirrors this dict into both content[0].text and
    structuredContent.

    shoav_detail carries structured context (verdict, target, mode). Any
    page-derived strings inside it are dropped here; only counts, kinds,
    element ids, and guard-authored text pass through. The _shoav
    summary is guard-authored wording plus counts, never page text.
    """
    detail = dict(shoav_detail) if isinstance(shoav_detail, dict) else {}
    safe_detail: dict = {"tool": tool, "verdict": detail.get("verdict", "BLOCK")}
    for key in ("reason", "mode", "enforced", "target", "stage"):
        if key in detail:
            safe_detail[key] = detail[key]
    if "findings" in detail:
        count, kinds = _count_findings(detail["findings"])
        safe_detail["findings"] = count
        if kinds:
            safe_detail["finding_kinds"] = kinds
    verdict_name = safe_detail.get("verdict", "BLOCK")
    if hasattr(verdict_name, "value"):
        verdict_name = str(verdict_name.value)
    else:
        verdict_name = str(verdict_name)
    findings_count = safe_detail.get("findings", 0)
    try:
        findings_count = int(findings_count)
    except (TypeError, ValueError):
        findings_count = 0
    kinds = safe_detail.get("finding_kinds", [])
    kind_part = (" (" + ", ".join(str(k) for k in kinds) + ")") if kinds else ""
    summary = (
        "[S.H.O.A.V. guard: request blocked] "
        f"verdict={verdict_name} findings={findings_count}{kind_part}"
    )
    shoav_note = {
        "verdict": verdict_name,
        "findings": findings_count,
        "summary": summary,
    }
    return {"_shoav": shoav_note, "error": reason, "shoav": safe_detail}
