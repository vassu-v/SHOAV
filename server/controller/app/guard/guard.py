"""ShoavGuard: thin controller-side wrapper around the S.H.O.A.V. filter core.

Wiring only (C-1). The gateway behavior hooks (C-3/C-4/C-5) are owned by
another agent; this module exposes the guard object, its mode/counters, and
fail-open decide helpers with no gateway imports.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Canonical scrub home (RECON unify a): connectors.rewrite._scrub_field via
# scrub_with_count. This module keeps no sentence logic of its own.
# PENDING-GATEWAY: controller/app/tool_gateway/gateway.py lines 990-1040
# (_shoav_scrub_field) still carry a local copy; leave it untouched here
# (another agent owns gateway.py) and point it at connectors on their pass.
try:
    from connectors.rewrite import REMOVED_MARKER as _REMOVED_MARKER
    from connectors.rewrite import scrub_with_count as _canonical_scrub_with_count
except Exception:
    _REMOVED_MARKER = "[removed by S.H.O.A.V.: suspected injected instruction]"
    _canonical_scrub_with_count = None  # lazy import at call time

GUARD_MODES = ("off", "observe", "enforce")
GUARD_FAILS = ("open", "closed")

_COUNTER_KEYS = (
    "ingress_allow",
    "ingress_rewrite",
    "ingress_block",
    "ingress_escalate",
    "egress_allow",
    "egress_block",
    "egress_escalate",
    "errors",
    "fail_open",
)


def resolve_guard_fail(settings: Any = None, default: str = "open") -> str:
    """Canonical SHOAV_GUARD_FAIL reader (RECON unify c).

    Single source: Settings.shoav_guard_fail (controller/app/config.py
    line 115, alias SHOAV_GUARD_FAIL) wins when a settings object is
    supplied; otherwise the SHOAV_GUARD_FAIL env var is read. Unknown
    values warn and fall back to open. Returns "open" or "closed".
    PENDING-GATEWAY: controller/app/tool_gateway/gateway.py line 425
    (_shoav_fail_closed) reads os.getenv directly and ignores
    Settings/guard.fail; it should delegate here on the owning pass.
    """
    raw = None
    if settings is not None:
        raw = getattr(settings, "shoav_guard_fail", None)
    if raw is None:
        raw = os.getenv("SHOAV_GUARD_FAIL", default)
    fail = str(raw or default).strip().lower()
    if fail not in GUARD_FAILS:
        logger.warning("unknown SHOAV_GUARD_FAIL=%r, using open", raw)
        return "open"
    return fail


class ShoavGuard:
    """Owns filter instances plus mode, fail policy, and verdict counters."""

    def __init__(
        self,
        mode: str = "observe",
        fail: str = "open",
        ingress_filter: Any | None = None,
        egress_filter: Any | None = None,
    ) -> None:
        self.mode = mode if mode in GUARD_MODES else "observe"
        self.fail = fail if fail in GUARD_FAILS else "open"
        self.ingress_filter = ingress_filter
        self.egress_filter = egress_filter
        self.counters: dict[str, int] = {key: 0 for key in _COUNTER_KEYS}

    @classmethod
    def from_settings(cls, settings: Any) -> "ShoavGuard | None":
        """Build a guard from controller Settings, or None when off.

        Returns None when SHOAV_GUARD_MODE is off (zero overhead path) and
        when the filter core cannot be loaded (fail open with a log line).
        """
        raw_mode = getattr(settings, "shoav_guard_mode", "off") or "off"
        mode = str(raw_mode).strip().lower()
        if mode == "off":
            return None
        if mode not in GUARD_MODES:
            logger.warning("unknown SHOAV_GUARD_MODE=%r, guard disabled", raw_mode)
            return None
        fail = resolve_guard_fail(settings)

        from .loader import load_filter_classes

        ingress_cls, egress_cls = load_filter_classes(settings)
        if ingress_cls is None and egress_cls is None:
            logger.warning("shoav filters unavailable, guard disabled (fail open)")
            return None
        try:
            ingress = ingress_cls() if ingress_cls is not None else None
            egress = egress_cls() if egress_cls is not None else None
        except Exception:
            logger.warning("shoav filter init failed, guard disabled (fail open)", exc_info=True)
            return None
        return cls(mode=mode, fail=fail, ingress_filter=ingress, egress_filter=egress)

    def _fail_open_result(self, stage: str, reason: str) -> dict[str, Any]:
        self.counters["errors"] += 1
        if self.fail == "closed":
            key = "ingress_block" if stage == "ingress" else "egress_block"
            self.counters[key] += 1
            return {
                "verdict": "BLOCK",
                "enforced": True,
                "mode": self.mode,
                "reason": reason,
                "note": "shoav filter error, fail closed",
            }
        self.counters["fail_open"] += 1
        return {
            "verdict": "ALLOW",
            "enforced": False,
            "mode": self.mode,
            "reason": reason,
            "note": "shoav filter error, fail open",
        }

    @staticmethod
    def _supplemental_scrub(text: str) -> tuple[str, int]:
        """Canonical scrub delegate (RECON unify a).

        Uses connectors.rewrite.scrub_with_count so sentence logic lives
        in one place. Lazy import keeps module importable when the
        connectors package is not yet on sys.path; failure degrades to
        no upgrade (fail open) rather than raising.
        """
        fn = _canonical_scrub_with_count
        if fn is None:
            try:
                from connectors.rewrite import scrub_with_count as _lazy
            except Exception:
                return text, 0
            fn = _lazy
        try:
            return fn(text)
        except Exception:
            logger.warning("canonical scrub failed, skipping supplemental upgrade", exc_info=True)
            return text, 0

    def decide_ingress(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Run the ingress filter over an observation-shaped payload.

        ONE ingress contract (F-A/F-B/F-C): accepts observe-shaped payloads
        (interactables, text_excerpt, accessibility_outline, style_facts,
        form_controls) plus snapshot/find_elements/get_html shapes
        (tool plus text, with optional elements/items/content). The text
        half always runs on text_excerpt, falling back to text when
        text_excerpt is missing. style_facts from STYLE_PROBE_SCRIPT
        (gathered live via session.page.evaluate) are forwarded so
        display:none, opacity:0, font-size:0, off-screen, ancestor-hidden,
        and zero-width stripping work through IngressFilter.process.

        Returns {verdict, sanitized:{text_excerpt, interactables}, reason,
        findings, enforced, mode, payload (alias of sanitized), result}.
        Gateway reads sanitized (primary) with payload fallback, same keys.

        Never raises: filter exceptions degrade to ALLOW with a guard note,
        unless fail policy is closed (then BLOCK). In observe mode the
        returned verdict is advisory and enforced is always False.
        """
        payload = dict(payload or {})
        text_excerpt = payload.get("text_excerpt")
        if not isinstance(text_excerpt, str) or not text_excerpt:
            text_val = payload.get("text")
            if isinstance(text_val, str):
                text_excerpt = text_val
            elif text_val is not None:
                text_excerpt = str(text_val)
            else:
                text_excerpt = ""
        if not isinstance(text_excerpt, str):
            text_excerpt = str(text_excerpt)
        interactables = payload.get("interactables")
        if interactables is None:
            interactables = []
        if not isinstance(interactables, list):
            interactables = []
        accessibility_outline = payload.get("accessibility_outline") or {}
        if not isinstance(accessibility_outline, dict):
            accessibility_outline = {}
        style_facts = payload.get("style_facts")
        form_controls = payload.get("form_controls")
        session_state = payload.get("session_state")
        mutation_rate = payload.get("mutation_rate")
        if self.ingress_filter is None:
            sanitized_empty = {
                "text_excerpt": text_excerpt,
                "interactables": list(interactables),
                "text": text_excerpt,
            }
            return {
                "verdict": "ALLOW",
                "enforced": False,
                "mode": self.mode,
                "reason": "ingress filter unavailable",
                "note": "fail open",
                "findings": {},
                "sanitized": sanitized_empty,
                "payload": dict(sanitized_empty),
            }
        try:
            engine_payload = {
                **payload,
                "text_excerpt": text_excerpt,
                "interactables": list(interactables),
                "accessibility_outline": accessibility_outline,
            }
            kwargs: dict[str, Any] = {}
            if style_facts is not None:
                kwargs["style_facts"] = style_facts
            if form_controls is not None:
                kwargs["form_controls"] = form_controls
            if session_state is not None:
                kwargs["session_state"] = session_state
            if mutation_rate is not None:
                kwargs["mutation_rate"] = mutation_rate
            result = self.ingress_filter.process(engine_payload, **kwargs)
        except Exception as exc:
            logger.warning("shoav ingress filter failed: %s", exc, exc_info=True)
            return self._fail_open_result("ingress", f"ingress filter error: {exc}")
        verdict = str(result.get("verdict", "ALLOW")).upper()
        telemetry = result.get("telemetry", "") or ""
        findings = result.get("findings", {}) or {}
        filter_payload = result.get("payload")
        if isinstance(filter_payload, dict):
            clean_text = filter_payload.get("text_excerpt", text_excerpt)
            clean_inter = filter_payload.get("interactables", interactables)
            if not isinstance(clean_text, str):
                clean_text = str(clean_text)
            if not isinstance(clean_inter, list):
                clean_inter = list(interactables)
        else:
            clean_text = text_excerpt
            clean_inter = list(interactables)
        # F-B supplemental: upgrade ALLOW with refund/exfiltration markers.
        if verdict == "ALLOW":
            scrubbed, removed = self._supplemental_scrub(clean_text)
            if removed:
                verdict = "REWRITE"
                clean_text = scrubbed
                telemetry = (
                    (telemetry + "\n" if telemetry else "")
                    + "status: rewritten\n"
                    + f"- supplemental injection sentences removed: {removed}"
                )
                if isinstance(findings, dict):
                    findings = {
                        **findings,
                        "supplemental_injections": [
                            {"reason": "supplemental_instruction_pattern", "count": removed}
                        ],
                    }
                else:
                    findings = {
                        "supplemental_injections": [
                            {"reason": "supplemental_instruction_pattern", "count": removed}
                        ]
                    }
        key = f"ingress_{verdict.lower()}"
        if key in self.counters:
            self.counters[key] += 1
        enforced = self.mode == "enforce" and verdict in ("REWRITE", "BLOCK", "ESCALATE")
        sanitized = {
            "text_excerpt": clean_text,
            "interactables": list(clean_inter),
            "text": clean_text,
        }
        return {
            "verdict": verdict,
            "enforced": enforced,
            "mode": self.mode,
            "reason": telemetry,
            "findings": findings,
            "sanitized": sanitized,
            "payload": dict(sanitized),
            "result": result,
        }

    def decide_egress(self, args: dict[str, Any]) -> dict[str, Any]:
        """Run the egress filter over click, input, and submission checks.

        Click expects {"expected_ref": str, "hit_result": dict}. Submission
        expects {"check": "submission", "snapshot": [...], "touched": [...]},
        input expects {"check": "input", ...}. Missing keys or a missing
        filter degrade to ALLOW with a note. Never raises.
        """
        args = dict(args or {})
        if self.egress_filter is None:
            return {
                "verdict": "ALLOW",
                "enforced": False,
                "mode": self.mode,
                "reason": "egress filter unavailable",
                "note": "fail open",
            }
        check = args.get("check")
        if check == "submission":
            snapshot = args.get("snapshot") or []
            touched = args.get("touched") or []
            if not isinstance(snapshot, list):
                snapshot = []
            touched_set = set(touched) if isinstance(touched, list) else set()
            try:
                from filters.session_state import SessionState as _SessionState

                fake = _SessionState(
                    initial_form_snapshot=snapshot, touched_refs=set(touched_set)
                )
                result = self.egress_filter.verify_submission(fake)
            except Exception as exc:
                logger.warning("shoav egress filter failed: %s", exc, exc_info=True)
                return self._fail_open_result("egress", f"egress filter error: {exc}")
            verdict = str(result.get("verdict", "ALLOW")).upper()
            key = f"egress_{verdict.lower()}"
            if key in self.counters:
                self.counters[key] += 1
            enforced = self.mode == "enforce" and verdict in ("BLOCK", "ESCALATE")
            out: dict[str, Any] = {
                "verdict": verdict,
                "enforced": enforced,
                "mode": self.mode,
                "reason": result.get("reason", ""),
                "result": result,
            }
            if isinstance(result.get("flags"), list):
                out["flags"] = result["flags"]
            return out
        if check == "input":
            expected_ref = args.get("expected_ref")
            expected_value = args.get("expected_value", "")
            focus_result = args.get("focus_result")
            if not expected_ref or not isinstance(focus_result, dict):
                return {
                    "verdict": "ALLOW",
                    "enforced": False,
                    "mode": self.mode,
                    "reason": "egress check skipped: missing expected_ref or hit_result",
                    "note": "fail open",
                }
            try:
                result = self.egress_filter.verify_input(
                    expected_ref, expected_value, focus_result
                )
            except Exception as exc:
                logger.warning("shoav egress filter failed: %s", exc, exc_info=True)
                return self._fail_open_result("egress", f"egress filter error: {exc}")
            verdict = str(result.get("verdict", "ALLOW")).upper()
            key = f"egress_{verdict.lower()}"
            if key in self.counters:
                self.counters[key] += 1
            enforced = self.mode == "enforce" and verdict in ("BLOCK", "ESCALATE")
            return {
                "verdict": verdict,
                "enforced": enforced,
                "mode": self.mode,
                "reason": result.get("reason", ""),
                "result": result,
            }
        expected_ref = args.get("expected_ref")
        hit_result = args.get("hit_result")
        if not expected_ref or not isinstance(hit_result, dict):
            return {
                "verdict": "ALLOW",
                "enforced": False,
                "mode": self.mode,
                "reason": "egress check skipped: missing expected_ref or hit_result",
                "note": "fail open",
            }
        try:
            result = self.egress_filter.verify_click(expected_ref, hit_result)
        except Exception as exc:
            logger.warning("shoav egress filter failed: %s", exc, exc_info=True)
            return self._fail_open_result("egress", f"egress filter error: {exc}")
        verdict = str(result.get("verdict", "ALLOW")).upper()
        key = f"egress_{verdict.lower()}"
        if key in self.counters:
            self.counters[key] += 1
        enforced = self.mode == "enforce" and verdict in ("BLOCK", "ESCALATE")
        return {
            "verdict": verdict,
            "enforced": enforced,
            "mode": self.mode,
            "reason": result.get("reason", ""),
            "result": result,
        }

    def snapshot(self) -> dict[str, Any]:
        """Status shape for the future GET /live-api/guard route (C-2)."""
        return {
            "mode": self.mode,
            "fail": self.fail,
            "counters": dict(self.counters),
            "ingress_available": self.ingress_filter is not None,
            "egress_available": self.egress_filter is not None,
        }
