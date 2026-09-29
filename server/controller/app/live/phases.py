"""Pure helpers for Live View: tool phase, redaction, truncation, result summaries.

No I/O and no imports from the rest of the app, so everything here is unit-testable.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

PHASES = ("session", "screenshot", "read", "act", "other")

SESSION_TOOLS = frozenset(
    {
        "browser.create_session",
        "browser.close_session",
        "browser.fork_session",
        "browser.list_sessions",
        "browser.get_session",
        "browser.list_tabs",
        "browser.activate_tab",
        "browser.close_tab",
    }
)
SCREENSHOT_TOOLS = frozenset({"browser.screenshot"})
READ_TOOLS = frozenset(
    {
        "browser.get_html",
        "browser.snapshot",
        "browser.find_elements",
        "browser.get_console",
        "browser.get_page_errors",
        "browser.get_request_failures",
        "browser.get_network_log",
        "browser.wait_for_selector",
        "browser.list_downloads",
    }
)
ACT_TOOLS = frozenset(
    {
        "browser.execute_action",
        "browser.drag_drop",
        "browser.eval_js",
        "browser.set_viewport",
        "browser.request_human_takeover",
    }
)
# observe is split by preset in classify_phase().
OBSERVE_TOOL = "browser.observe"


def classify_phase(tool: str, args: dict[str, Any] | None = None) -> str:
    """Map a tool call to exactly one of PHASES. Unknown tools are `other`."""
    if tool == OBSERVE_TOOL:
        preset = (args or {}).get("preset")
        return "read" if preset == "text" else "screenshot"
    if tool in SESSION_TOOLS:
        return "session"
    if tool in SCREENSHOT_TOOLS:
        return "screenshot"
    if tool in READ_TOOLS:
        return "read"
    if tool in ACT_TOOLS:
        return "act"
    return "other"


# ── redaction / truncation ──────────────────────────────────────────────────

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD_SPLIT_RE = re.compile(r"[^a-z0-9]+")
_SENSITIVE_WORDS = frozenset(
    {"pass", "pwd", "passwd", "password", "passwords", "passphrase", "secrets", "cookies", "auth", "totp"}
)
_SENSITIVE_SUFFIXES = (
    "password",
    "passwd",
    "passphrase",
    "secret",
    "token",
    "cookie",
    "apikey",
    "totp",
    "authorization",
)
_HEADER_AUTH_RE = re.compile(r"^x[_-]?auth", re.IGNORECASE)


def is_sensitive_key(key: Any) -> bool:
    """Word-boundary version of the contract regex, so `passed`, `bypass`, `compass`,
    `max_tokens` and `tokens_used` are kept, while `proxy_password`, `apiKey`,
    `Set-Cookie`, `X-Auth-Token` and `Authorization` are hidden."""
    text = str(key)
    if _HEADER_AUTH_RE.match(text):
        return True
    words = [w for w in _WORD_SPLIT_RE.split(_CAMEL_RE.sub(" ", text).lower()) if w]
    if "apikey" in "".join(words):
        return True
    for word in words:
        if word in _SENSITIVE_WORDS or word.endswith(_SENSITIVE_SUFFIXES):
            # a lone `auth` word is only sensitive for header-like keys handled above
            if word == "auth":
                continue
            return True
    return False


REDACTED = "[redacted]"
TRUNCATED_MARKER = "...[truncated]"
MAX_STRING = 500
MAX_TOTAL = 4000
_MAX_DEPTH = 8

# Whole-value redaction for tools whose output is credential-like by nature.
_REDACT_RESULT_TOOLS = frozenset({"browser.get_cookies", "browser.get_local_storage"})
# Noise / internals that add nothing to a timeline card (dropped at any depth).
_DROP_RESULT_KEYS = frozenset(
    {"remote_access", "isolation", "witness_remote", "auth_state", "takeover_url", "artifact_dir", "trace_path"}
)
# Only dropped at the top level of a result: nested `before`/`downloads` can be real data.
_DROP_TOP_LEVEL_KEYS = frozenset({"downloads", "before"})


def clean_text(text: str) -> str:
    """Replace lone surrogates etc. so the string always encodes to UTF-8."""
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        return text.encode("utf-8", errors="replace").decode("utf-8")


def scrub_url(text: str) -> str:
    """Blank the values of sensitive-named query/fragment params in URL-like strings."""
    if not isinstance(text, str) or "?" not in text and "#" not in text:
        return text
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", text):
        return text
    try:
        parts = urlsplit(text)
        changed = False

        def fix(raw: str) -> str:
            nonlocal changed
            if not raw or "=" not in raw:
                return raw
            pairs = parse_qsl(raw, keep_blank_values=True)
            if not any(is_sensitive_key(k) for k, _ in pairs):
                return raw
            changed = True
            return urlencode([(k, REDACTED if is_sensitive_key(k) else v) for k, v in pairs], safe="[]")

        query, fragment = fix(parts.query), fix(parts.fragment)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, fragment)) if changed else text
    except ValueError:
        return text


def _sanitize(value: Any, depth: int = 0) -> Any:
    """Turn anything into JSON-safe primitives (bytes, sets, models, cycles, odd types)."""
    if isinstance(value, str):
        return clean_text(value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else str(value)
    if depth >= _MAX_DEPTH:
        return "[max depth]"
    if isinstance(value, dict):
        return {clean_text(str(k)): _sanitize(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize(v, depth + 1) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return f"[{len(value)} bytes]"
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return _sanitize(dump(mode="json"), depth + 1)
        except Exception:
            pass
    try:
        return str(value)
    except Exception:
        return "[unprintable]"


_BASE64_RE = re.compile(r"[A-Za-z0-9+/=\s]+")
_DATA_URL_RE = re.compile(r"^data:([\w.+-]+/[\w.+-]+);base64,")
_BASE64_MIN_CHARS = 1500


def looks_like_base64_blob(text: str) -> bool:
    """True for a long base64 payload or a base64 data URL (an image the model was sent)."""
    if len(text) < _BASE64_MIN_CHARS:
        return False
    return bool(_DATA_URL_RE.match(text)) or _BASE64_RE.fullmatch(text) is not None


def blob_placeholder(text: str, mime: str | None = None) -> str:
    """Short stand-in such as "[image 61 KB jpeg]" for a base64 payload."""
    match = _DATA_URL_RE.match(text)
    if match:
        mime = mime or match.group(1)
        text = text[match.end() :]
    kb = max(1, round(len(text) * 3 / 4 / 1024))
    if mime:
        return f"[image {kb} KB {mime.split('/')[-1]}]"
    return f"[base64 {kb} KB]"


_PASSWORD_TARGET_RE = re.compile(r"pass|pwd", re.IGNORECASE)


def _is_password_action(action: dict[str, Any]) -> bool:
    """A `type` into something that looks like a password field (by selector/label hints)."""
    return any(
        isinstance(action.get(key), str) and _PASSWORD_TARGET_RE.search(action[key])
        for key in ("selector", "label", "element_id", "username")
    )


def _redact(
    value: Any, *, drop: frozenset[str] = frozenset(), top_drop: frozenset[str] = frozenset(), top: bool = True
) -> Any:
    if isinstance(value, dict):
        # An MCP image block that leaked into a result: never store or stream its base64.
        if value.get("type") == "image" and isinstance(value.get("data"), str):
            mime = value.get("mimeType") or "image"
            return {"type": "image", "mimeType": mime, "data": blob_placeholder(value["data"], mime)}
        hide_text = value.get("sensitive") is True or (
            isinstance(value.get("action"), str) and value["action"] in ("type", "fill") and _is_password_action(value)
        )
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in drop or (top and key in top_drop):
                continue
            if is_sensitive_key(key):
                out[key] = REDACTED
            elif hide_text and key in ("text", "value") and isinstance(item, str):
                out[key] = REDACTED
            else:
                out[key] = _redact(item, drop=drop, top=False)
        return out
    if isinstance(value, list):
        return [_redact(item, drop=drop, top=False) for item in value]
    if isinstance(value, str):
        if looks_like_base64_blob(value):
            return blob_placeholder(value)
        return scrub_url(value)
    return value


def _shrink(value: Any, max_str: int, max_items: int | None) -> Any:
    if isinstance(value, str):
        return value if len(value) <= max_str else value[:max_str] + TRUNCATED_MARKER
    if isinstance(value, dict):
        return {k: _shrink(v, max_str, max_items) for k, v in value.items()}
    if isinstance(value, list):
        items = value if max_items is None or len(value) <= max_items else value[:max_items]
        shrunk = [_shrink(v, max_str, max_items) for v in items]
        if max_items is not None and len(value) > max_items:
            shrunk.append(f"...[{len(value) - max_items} more]")
        return shrunk
    return value


def truncate_value(value: Any, *, max_string: int = MAX_STRING, max_total: int = MAX_TOTAL) -> Any:
    """Cut every string at max_string and the serialised whole at max_total chars.

    Progressively shrinks strings/lists so the result stays a valid JSON value; only
    falls back to a `{"_truncated": "<preview>...[truncated]"}` wrapper as a last resort.
    """
    value = _sanitize(value)
    current = _shrink(value, max_string, None)
    for limit_str, limit_items in ((200, 20), (80, 5)):
        if len(json.dumps(current, ensure_ascii=False)) <= max_total:
            return current
        current = _shrink(current, limit_str, limit_items)
    text = json.dumps(current, ensure_ascii=False)
    if len(text) <= max_total:
        return current
    return {"_truncated": text[:max_total] + TRUNCATED_MARKER}


def redact_args(tool: str, args: dict[str, Any] | None) -> Any:
    """Redacted + truncated copy of tool arguments, safe to persist and stream."""
    args = dict(args or {})
    session_id = args.get("session_id")
    lead = {"session_id": session_id} if session_id else {}
    if tool == "browser.eval_js":
        expression = args.get("expression")
        return {**lead, "redacted": True, "expression_length": len(expression) if isinstance(expression, str) else 0}
    if tool == "browser.set_cookies":
        cookies = args.get("cookies")
        return {**lead, "redacted": True, "keys": len(cookies) if isinstance(cookies, list) else 0}
    if tool == "browser.set_local_storage":
        return {**lead, "redacted": True, "keys": 1}
    return truncate_value(_redact(_sanitize(args)))


def redact_result(tool: str, result: Any) -> Any:
    """Redacted + truncated copy of a tool result."""
    if tool in _REDACT_RESULT_TOOLS:
        return {"redacted": True}
    if tool == "browser.eval_js":
        inner = result.get("result") if isinstance(result, dict) else result
        try:
            length = len(json.dumps(inner, default=str))
        except (TypeError, ValueError):
            length = 0
        return {"redacted": True, "result_length": length}
    return truncate_value(_redact(_sanitize(result), drop=_DROP_RESULT_KEYS, top_drop=_DROP_TOP_LEVEL_KEYS))


# ── guard payload redaction ───────────────────────────────────────────────

GUARD_VERDICTS = frozenset({"ALLOW", "REWRITE", "BLOCK", "ESCALATE"})
GUARD_STAGES = frozenset({"ingress", "egress"})


def redact_guard_reason(reason: Any) -> Any:
    """Redacted + truncated guard reason string (None stays None)."""
    if reason is None:
        return None
    return truncate_value(_redact(_sanitize(reason)))


def redact_guard_findings(findings: Any) -> list[dict[str, Any]]:
    """Redacted + truncated guard findings list in [{kind, detail}] shape.

    Canonical shape (RECON unify b): connectors.rewrite.findings_to_list
    normalizes grouped dicts ({kind: [...]}) and plain counts to the
    [{kind, detail}] list before redaction. Falls back to local handling
    when connectors is not importable.
    PENDING-GATEWAY: gateway _shoav_findings (count/groups shape) should
    round trip through findings_to_summary/findings_to_list; do NOT edit
    gateway.py here.
    """
    if findings is None:
        return []
    try:
        from connectors.rewrite import findings_to_list as _to_list
    except Exception:
        _to_list = None  # type: ignore[assignment]
    if _to_list is not None:
        try:
            items = _to_list(findings)
        except Exception:
            items = findings if isinstance(findings, list) else [findings]
    else:
        items = findings if isinstance(findings, list) else [findings]
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            kind = item.get("kind")
            detail = item.get("detail", item.get("message"))
            kind_text = clean_text(str(kind)) if kind is not None else "finding"
            out.append(
                {
                    "kind": truncate_value(kind_text),
                    "detail": truncate_value(_redact(_sanitize(detail))) if detail is not None else None,
                }
            )
        else:
            out.append({"kind": "finding", "detail": truncate_value(_redact(_sanitize(item)))})
    return truncate_value(out)


# ── result inspection ───────────────────────────────────────────────────────


def find_screenshot_url(result: Any, _depth: int = 0) -> str | None:
    """Latest `screenshot_url` in a (possibly nested) result, or None."""
    if _depth > 4:
        return None
    if isinstance(result, dict):
        for key in ("after", "session"):
            if key in result:
                nested = find_screenshot_url(result[key], _depth + 1)
                if nested:
                    return nested
        url = result.get("screenshot_url")
        if isinstance(url, str) and url.startswith("/"):
            return url
        for value in result.values():
            if isinstance(value, dict):
                nested = find_screenshot_url(value, _depth + 1)
                if nested:
                    return nested
    return None


def find_page_state(result: Any) -> tuple[str | None, str | None]:
    """(url, title) the call reports, if any."""
    if not isinstance(result, dict):
        return None, None
    candidates = [result]
    for key in ("after", "session"):
        nested = result.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)
    url = title = None
    for item in candidates:
        url = item.get("current_url") or item.get("url") or url
        title = item.get("title") or title
    url = scrub_url(url) if isinstance(url, str) and url else None
    title = title if isinstance(title, str) and title else None
    return url, title


def summarize_result(tool: str, args: dict[str, Any] | None, result: Any, *, is_error: bool, error: str | None) -> str:
    if is_error:
        return (error or "error")[:500]
    url, title = find_page_state(result)
    where = f" at {url}" if url else ""
    if tool == "browser.execute_action" and isinstance(result, dict):
        return f"{result.get('action', 'action')} ok, now{where}" if url else f"{result.get('action', 'action')} ok"
    if tool == "browser.observe":
        return f"observed {title or url or 'page'}" + (f" ({url})" if url and title else "")
    if tool == "browser.create_session":
        return f"session created{where}"
    if tool == "browser.close_session":
        return "session closed"
    if tool == "browser.screenshot":
        image = result.get("image") if isinstance(result, dict) else None
        return f"screenshot{where}" + (f" {image}" if isinstance(image, str) and image.startswith("[image") else "")
    if tool == "browser.snapshot" and isinstance(result, dict):
        return f"snapshot: {result.get('nodes', 0)} nodes, {result.get('interactive', 0)} interactive{where}"
    if isinstance(result, list):
        return f"{len(result)} item(s)"
    return f"ok{where}"[:500]


def error_message(response_structured: Any, response_text: str) -> str:
    if isinstance(response_structured, dict):
        for key in ("error", "message", "detail"):
            value = response_structured.get(key)
            if isinstance(value, str) and value:
                return value
    return response_text
