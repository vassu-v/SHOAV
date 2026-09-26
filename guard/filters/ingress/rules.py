"""Pure ingress detection rules.

Every function here takes and returns plain dicts/lists — no browser, no
network, no I/O — so each is directly unit-testable with fixture data.
Two of these (find_hidden_textful_nodes, flag_prechecked_toggles) work on
data Auto Browser's *existing* payload can already supply; the others need
the new STYLE_PROBE_SCRIPT capability from scripts.py wired in later.
"""

from __future__ import annotations

import re

from ..constants import (
    INGRESS_BENIGN_HIDDEN_MARKERS,
    INGRESS_CHARS_PER_TOKEN_ESTIMATE,
    INGRESS_CONSENT_KEYWORDS,
    INGRESS_FLAGGABLE_TOGGLE_TYPES,
    INGRESS_INJECTION_KEYWORDS,
    INGRESS_MIN_FONT_SIZE_PX,
    INGRESS_MUTATION_RATE_THRESHOLD,
    INGRESS_NODE_BUDGET_TARGET,
    INGRESS_NODE_PRIORITY,
    INGRESS_OFFSCREEN_LEFT_PX,
    INGRESS_OPACITY_THRESHOLD,
    INGRESS_RAW_ELEMENT_COUNT_THRESHOLD,
    INGRESS_RAW_TEXT_CHARS_THRESHOLD,
    INGRESS_TOKEN_BUDGET_TRIGGER,
    ZERO_WIDTH_CHARS,
)
from ..types import Verdict


def _is_offscreen(rect: dict, viewport: dict) -> bool:
    right = rect.get("right", 0)
    bottom = rect.get("bottom", 0)
    left = rect.get("left", 0)
    top = rect.get("top", 0)
    width = viewport.get("width", 0)
    height = viewport.get("height", 0)
    fully_outside = right < 0 or bottom < 0 or left > width or top > height
    return fully_outside or left < INGRESS_OFFSCREEN_LEFT_PX


def _is_benign_hidden(node: dict) -> bool:
    class_name = (node.get("class_name") or "").lower()
    return any(marker in class_name for marker in INGRESS_BENIGN_HIDDEN_MARKERS)


def find_hidden_textful_nodes(style_facts: list[dict]) -> dict:
    """Target 1: hidden-but-textful nodes, from STYLE_PROBE_SCRIPT output.

    Returns {"stripped": [...], "skipped_benign": [...]} — both lists are
    kept so telemetry can be honest about what was left alone and why.
    Non-rendered head tags (TITLE, META, HEAD, LINK, BASE, STYLE, SCRIPT)
    are never stripped: their text never reaches agent-visible snapshot
    text, so flagging them would turn every benign page into REWRITE.
    """
    _NON_RENDERED = {"HTML", "HEAD", "TITLE", "META", "LINK", "BASE", "STYLE", "SCRIPT", "NOSCRIPT", "TEMPLATE"}
    stripped: list[dict] = []
    skipped_benign: list[dict] = []

    for node in style_facts:
        tag = str(node.get("tag") or "").upper()
        if tag in _NON_RENDERED:
            continue
        rect = node.get("rect", {})
        viewport = node.get("viewport", {})
        hidden = (
            node.get("display") == "none"
            or node.get("visibility") == "hidden"
            or node.get("opacity", 1.0) < INGRESS_OPACITY_THRESHOLD
            or node.get("font_size", 1.0) <= INGRESS_MIN_FONT_SIZE_PX
            or _is_offscreen(rect, viewport)
        )
        if not hidden:
            continue

        entry = {
            "ref": node.get("ref"),
            "tag": node.get("tag"),
            "snippet": (node.get("text_snippet") or "")[:50],
            "text": node.get("text_snippet") or "",
            "reason": "computed_style_hidden",
        }
        if _is_benign_hidden(node):
            skipped_benign.append(entry)
        else:
            stripped.append(entry)

    return {"stripped": stripped, "skipped_benign": skipped_benign}


REMOVED_MARKER = "[removed by S.H.O.A.V.: suspected injected instruction]"

NL = chr(10)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def sanitize_text(text: str, hidden_texts: list[str] | None = None) -> tuple[str, int]:
    """Actually remove dangerous content from a text blob.

    Order: delete zero-width chars, delete every occurrence of hidden-node
    text, then replace each sentence/line containing an injection keyword
    with REMOVED_MARKER. Returns (clean_text, removed_count), where
    removed_count counts zero-width chars, hidden-text occurrences and
    replaced sentences.
    """
    removed = 0
    for ch in ZERO_WIDTH_CHARS:
        n = text.count(ch)
        if n:
            removed += n
            text = text.replace(ch, "")

    for hidden in sorted({h for h in (hidden_texts or []) if h}, key=len, reverse=True):
        variants = []
        for cand in (hidden, hidden.strip()):
            cand = "".join(c for c in cand if c not in ZERO_WIDTH_CHARS)
            if cand and cand not in variants:
                variants.append(cand)
        for cand in variants:
            n = text.count(cand)
            if n:
                removed += n
                text = text.replace(cand, "")

    out_lines = []
    for line in text.split(NL):
        parts = _SENTENCE_SPLIT.split(line)
        new_parts = []
        for part in parts:
            lowered = part.lower()
            if any(kw in lowered for kw in INGRESS_INJECTION_KEYWORDS):
                removed += 1
                new_parts.append(REMOVED_MARKER)
            else:
                new_parts.append(part)
        out_lines.append(" ".join(new_parts))
    return NL.join(out_lines), removed


def find_text_injections(text_blob: str) -> list[dict]:
    """Target 1 (text half): zero-width Unicode + suspicious HTML comments.

    Works on plain text/HTML Auto Browser already returns today
    (text_excerpt / get_html) — needs no new capability.
    """
    findings: list[dict] = []

    for ch in ZERO_WIDTH_CHARS:
        count = text_blob.count(ch)
        if count:
            findings.append({
                "reason": "zero_width_unicode",
                "char": f"U+{ord(ch):04X}",
                "count": count,
            })

    lowered = text_blob.lower()
    for keyword in INGRESS_INJECTION_KEYWORDS:
        if keyword in lowered:
            idx = lowered.index(keyword)
            findings.append({
                "reason": "suspicious_instruction_keyword",
                "keyword": keyword,
                "snippet": text_blob[max(0, idx - 20): idx + len(keyword) + 20],
            })

    return findings


def compact_node_budget(
    nodes: list[dict],
    max_nodes: int = INGRESS_NODE_BUDGET_TARGET,
) -> tuple[list[dict], bool]:
    """Target 4: bound the interactive-node count, prioritizing real controls.

    nodes are expected in Auto Browser's real interactables shape:
    {element_id, tag, type, role, label, bbox, ...}. Returns
    (possibly-truncated list, whether truncation happened).
    """
    if len(nodes) <= max_nodes:
        return list(nodes), False

    def priority(node: dict) -> int:
        tag = (node.get("tag") or "").lower()
        try:
            return INGRESS_NODE_PRIORITY.index(tag)
        except ValueError:
            return len(INGRESS_NODE_PRIORITY)

    ordered = sorted(enumerate(nodes), key=lambda pair: (priority(pair[1]), pair[0]))
    kept_indices = sorted(idx for idx, _ in ordered[:max_nodes])
    return [nodes[i] for i in kept_indices], True


def estimate_tokens(text: str) -> int:
    """Rough token estimate for the token half of Target 4's budget trigger.

    Deliberately crude (chars / 4) — good enough to decide "is this page's
    text volume worth compacting", not meant to match any real tokenizer.
    """
    return len(text) // INGRESS_CHARS_PER_TOKEN_ESTIMATE


def truncate_text_excerpt(text: str, token_trigger: int = INGRESS_TOKEN_BUDGET_TRIGGER) -> tuple[str, bool]:
    """Target 4 (token half): cap text_excerpt when it blows the token budget.

    This was a genuine gap in the first pass — INGRESS_TOKEN_BUDGET_TRIGGER
    was defined but nothing ever read it. compact_node_budget only bounds
    the *interactables* list; text_excerpt is a separate bloat source (a
    flooding page can pad plain text without adding interactive nodes at
    all) and needed its own check.
    """
    max_chars = token_trigger * INGRESS_CHARS_PER_TOKEN_ESTIMATE
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars] + " …[truncated by S.H.O.A.V. token budget]", True


def evaluate_mutation_rate(
    mutations_per_second: float,
    threshold: float = INGRESS_MUTATION_RATE_THRESHOLD,
) -> tuple[bool, str]:
    """Target 4 (mutation-rate half): rapid dummy-DOM-diff flooding.

    This cannot be decided from a single snapshot — it needs a live
    MutationObserver count from the connector layer, sampled over a window
    (see scripts.py for why no JS snippet for this exists yet: a per-second
    rate isn't a single page.evaluate() call, it's a subscription). This
    function is the decision half only; the observation half is still an
    open connector-layer task, documented as such.
    """
    if mutations_per_second > threshold:
        return True, f"{mutations_per_second}/sec exceeds the {threshold}/sec flood threshold"
    return False, "mutation rate within normal range"


def evaluate_mutation_rate_verdict(
    count: int,
    seconds: float,
    threshold: float = INGRESS_MUTATION_RATE_THRESHOLD,
) -> Verdict:
    """Verdict form of the mutation-rate decision for observer read output.

    count and seconds come from MUTATION_OBSERVER_READ_SCRIPT. Returns
    Verdict.BLOCK when count / seconds exceeds threshold (default 50/sec),
    else Verdict.ALLOW. Zero or negative windows return ALLOW (no rate can
    be computed, so there is no evidence of flooding). Pure function.
    """
    if seconds <= 0:
        return Verdict.ALLOW
    rate = count / seconds
    if rate > threshold:
        return Verdict.BLOCK
    return Verdict.ALLOW


def evaluate_flood_signal(
    raw_element_count: int | None = None,
    raw_text_chars: int | None = None,
    mutations_per_second: float | None = None,
    *,
    element_threshold: int = INGRESS_RAW_ELEMENT_COUNT_THRESHOLD,
    text_chars_threshold: int = INGRESS_RAW_TEXT_CHARS_THRESHOLD,
    mutation_threshold: float = INGRESS_MUTATION_RATE_THRESHOLD,
) -> tuple[bool, str | None]:
    """Target 4 (F-E): raw pre-cap flood signal.

    Inputs come from FLOOD_PROBE_SCRIPT output (element_count, text_chars,
    both measured BEFORE compaction/truncation) plus the mutation-rate feed
    from MUTATION_OBSERVER_READ_SCRIPT. Any single signal past its threshold
    floods. None means that signal was not measured, so it is skipped
    (fail-open per signal). Pure function.
    """
    if raw_element_count is not None and raw_element_count > element_threshold:
        return True, (
            f"raw element count {raw_element_count} exceeds {element_threshold}"
        )
    if raw_text_chars is not None and raw_text_chars > text_chars_threshold:
        return True, (
            f"raw text volume {raw_text_chars} chars exceeds {text_chars_threshold}"
        )
    if mutations_per_second is not None and mutations_per_second > mutation_threshold:
        return True, (
            f"{mutations_per_second}/sec exceeds the {mutation_threshold}/sec flood threshold"
        )
    return False, None


def flag_prechecked_toggles(form_controls: list[dict]) -> list[dict]:
    """Target 3: pre-checked consent/marketing/add-on toggles.

    form_controls: [{"ref": str, "type": str, "checked": bool, "label": str}].
    Works today from Auto Browser's accessibility_outline, whose AX nodes
    already carry a `checked` field — no new capability required.
    Only checkbox/toggle/switch types are eligible (never radio/select),
    and only when the label/name matches a consent-ish keyword — see
    constants.py for the documented false-negative limitation this implies.
    """
    flagged: list[dict] = []
    for control in form_controls:
        control_type = (control.get("type") or "").lower()
        if control_type not in INGRESS_FLAGGABLE_TOGGLE_TYPES:
            continue
        if not control.get("checked"):
            continue
        label = (control.get("label") or control.get("ref") or "").lower()
        if any(keyword in label for keyword in INGRESS_CONSENT_KEYWORDS):
            flagged.append({
                "ref": control.get("ref"),
                "label": control.get("label"),
                "reason": "prechecked_consent_like_default",
            })
    return flagged
