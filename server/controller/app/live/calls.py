"""Tracks one MCP tool call for Live View: start/end events, summary upkeep, banner.

Used by McpToolGateway. Every method swallows its own failures; a recorder problem must
never change the outcome of a tool call.
"""

from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

from ..models import McpToolCallContent, McpToolCallResponse
from .phases import (
    GUARD_STAGES,
    GUARD_VERDICTS,
    classify_phase,
    error_message,
    find_page_state,
    find_screenshot_url,
    redact_args,
    redact_guard_findings,
    redact_guard_reason,
    redact_result,
    scrub_url,
    summarize_result,
)
from .recorder import LiveViewService, valid_session_id

logger = logging.getLogger(__name__)

# Name of the MCP client (clientInfo.name) for the call in flight. Set by the HTTP
# transport around tool_gateway.call_tool; a ContextVar keeps the gateway signature
# unchanged and stays correct when several clients call concurrently.
current_mcp_client: ContextVar[str | None] = ContextVar("current_mcp_client", default=None)

LIVE_NOTICE = (
    "The user is watching this session live. Before your next tool call, tell the user the session id "
    "and watch link by pasting live_view.banner as-is in a code block in your reply, then continue the task."
)
_CREATES_SESSION = frozenset({"browser.create_session", "browser.fork_session"})
_BLANK_URLS = frozenset({"", "about:blank"})


def _clean_url(url: Any) -> str | None:
    return scrub_url(url) if isinstance(url, str) and url not in _BLANK_URLS else None


class LiveCall:
    def __init__(self, service: LiveViewService, manager: Any, tool: str, raw_args: dict[str, Any] | None) -> None:
        self.service = service
        self.manager = manager
        self.tool = tool
        self.raw_args = dict(raw_args or {})
        self.call_id = uuid4().hex[:16]
        self.started = time.perf_counter()
        self.client = current_mcp_client.get()
        raw_sid = self.raw_args.get("session_id")
        self.session_id: str | None = raw_sid if valid_session_id(raw_sid) else None
        self.created: dict[str, Any] | None = None  # session created on demand by the gateway
        self.new_session_ids: list[str] = []
        self._start_emitted = False
        self._known: bool | None = None
        self._phase = classify_phase(tool, self.raw_args)
        self._guards: list[dict[str, Any]] = []

    # ── helpers ─────────────────────────────────────────────────────────────

    async def _register(self, summary: dict[str, Any], *, start_url: str | None = None) -> None:
        sid = summary.get("id")
        if not valid_session_id(sid):
            return
        try:
            is_new = await self.service.register_session(
                sid,
                name=summary.get("name"),
                start_url=_clean_url(start_url),
                current_url=_clean_url(summary.get("current_url")),
                title=summary.get("title") or None,
                created_at=summary.get("created_at"),
                client=self.client,
            )
            if is_new:
                self.new_session_ids.append(sid)
                self.service.print_banner(sid)
        except Exception:
            logger.warning("live view: register failed for %s", sid, exc_info=True)

    async def _ensure_known(self, session_id: str) -> bool:
        """True if the session has a summary; adopts sessions created outside MCP.

        Calls naming a session that does not exist (typo, stale id) are not recorded,
        so a wrong id never creates a phantom timeline directory.
        """
        if self._known is not None:
            return self._known
        if session_id in self.new_session_ids:
            self._known = True
            return True
        # Only a session with a live browser and a live summary gets events. Calls naming
        # a closed/archived id (or an id the manager no longer has) must not write to it.
        live = getattr(self.manager, "sessions", None)
        if live is not None and session_id not in live:
            self._known = False
            return False
        summary = await self.service.get_summary(session_id)
        if summary is not None and summary.get("state") == "archived":
            self._known = False
            return False
        known = summary is not None
        if not known:
            try:
                record = await self.manager.get_session_record(session_id)
                if isinstance(record, dict) and record.get("id") == session_id:
                    await self._register(record)
                    known = await self.service.get_summary(session_id) is not None
            except Exception:
                logger.debug("live view: unknown session %s, not recording", session_id, exc_info=True)
        self._known = known
        return known

    async def _emit_start(self) -> None:
        if self._start_emitted or not self.session_id:
            return
        self._start_emitted = True
        if not await self._ensure_known(self.session_id):
            return
        try:
            event: dict[str, Any] = {
                "event": "start",
                "call_id": self.call_id,
                "tool": self.tool,
                "phase": self._phase,
                "args": redact_args(self.tool, self.raw_args),
            }
            if self.client:
                event["client"] = self.client
            await self.service.record(self.session_id, event)
            await self.service.note_call(self.session_id, started=True, client=self.client)
        except Exception:
            logger.warning("live view: start event failed", exc_info=True)

    # ── guard ───────────────────────────────────────────────────────────────

    async def guard(
        self,
        stage: str,
        verdict: str,
        mode: str,
        enforced: bool,
        reason: Any | None = None,
        findings: Any | None = None,
        element_id: str | None = None,
    ) -> None:
        """Emit one guard verdict event (type override of the tool default).

        Never raises; a recorder problem must not change the tool call outcome.
        The verdict is also remembered so finish() can add a guard summary.
        """
        try:
            sid = self.session_id
            if not valid_session_id(sid):
                return
            assert sid is not None
            if not await self._ensure_known(sid):
                return
            norm_stage = str(stage).lower() if stage is not None else ""
            norm_verdict = str(verdict).upper() if verdict is not None else ""
            norm_mode = str(mode).lower() if mode is not None else ""
            if norm_stage not in GUARD_STAGES or norm_verdict not in GUARD_VERDICTS:
                logger.warning("live view: guard event with unexpected stage/verdict %r/%r", stage, verdict)
            event: dict[str, Any] = {
                "type": "guard",
                "event": "verdict",
                "call_id": self.call_id,
                "tool": self.tool,
                "stage": norm_stage,
                "verdict": norm_verdict,
                "mode": norm_mode,
                "enforced": bool(enforced),
                "reason": redact_guard_reason(reason),
                "findings": redact_guard_findings(findings),
            }
            if element_id is not None:
                event["target"] = {"element_id": str(element_id)}
            if self.client:
                event["client"] = self.client
            await self.service.record(sid, event)
            self._guards.append(
                {"stage": norm_stage, "verdict": norm_verdict, "mode": norm_mode, "enforced": bool(enforced)}
            )
        except Exception:
            logger.warning("live view: guard event failed", exc_info=True)

    # ── lifecycle ───────────────────────────────────────────────────────────

    async def begin(self, session_id: str | None) -> None:
        """Called once the session is resolved, right before the handler runs."""
        try:
            if self.created is not None:
                await self._register(self.created)
                session_id = self.created.get("id") or session_id
            if not valid_session_id(session_id):
                return
            self.session_id = session_id
            await self._emit_start()
        except Exception:
            logger.warning("live view: begin failed", exc_info=True)

    async def finish(self, response: McpToolCallResponse, *, error: str | None = None) -> McpToolCallResponse:
        """Emit the end event and, for new sessions, attach the live_view block + banner."""
        try:
            structured = response.structuredContent
            is_error = response.isError or error is not None
            if not is_error and self.tool in _CREATES_SESSION and isinstance(structured, dict):
                new_id = structured.get("id")
                if isinstance(new_id, str):
                    await self._register(structured, start_url=self.raw_args.get("start_url"))
                    if self.tool == "browser.create_session":
                        self.session_id = new_id if valid_session_id(new_id) else self.session_id
            sid = self.session_id
            if sid and self.session_id in self.new_session_ids:
                self._known = True
            if sid:
                await self._emit_start()
            if sid and self._known:
                text = response.content[0].text if response.content else ""
                message = error or (error_message(structured, text) if is_error else None)
                url, title = find_page_state(structured)
                shot = find_screenshot_url(structured) if not is_error else None
                event: dict[str, Any] = {
                    "event": "end",
                    "call_id": self.call_id,
                    "tool": self.tool,
                    "phase": self._phase,
                    "status": "error" if is_error else "ok",
                    "duration_ms": int((time.perf_counter() - self.started) * 1000),
                    "result_summary": summarize_result(
                        self.tool, self.raw_args, structured, is_error=is_error, error=message
                    ),
                }
                if not is_error:
                    event["result"] = redact_result(self.tool, structured)
                else:
                    event["result"] = redact_result(self.tool, structured) if structured is not None else None
                if shot:
                    event["screenshot_url"] = shot
                if self.client:
                    event["client"] = self.client
                if self._guards:
                    last = self._guards[-1]
                    event["guard"] = {
                        "verdict": last["verdict"],
                        "mode": last["mode"],
                        "enforced": any(item["enforced"] for item in self._guards),
                        "count": len(self._guards),
                        "verdicts": [item["verdict"] for item in self._guards],
                    }
                await self.service.record(sid, event)
                if not is_error:
                    await self.service.note_call(sid, url=_clean_url(url), title=title, screenshot_url=shot)
                    if self.tool == "browser.close_session":
                        await self.service.mark_closed(sid)
            self._attach_banner(response)
        except Exception:
            logger.warning("live view: finish failed", exc_info=True)
        return response

    def _attach_banner(self, response: McpToolCallResponse) -> None:
        if not self.new_session_ids:
            return
        sid = self.new_session_ids[-1]
        block = self.service.live_view_block(sid)
        structured = response.structuredContent
        if isinstance(structured, dict):
            # live_view first, so it is the first thing in content[0].text: some MCP clients
            # only surface the first block (or only its text), never structuredContent.
            merged = {"_notice": LIVE_NOTICE, "live_view": block, **structured}
            response.structuredContent = merged
            if response.content:
                response.content = [
                    McpToolCallContent(text=json.dumps(merged, ensure_ascii=False)),
                    *response.content[1:],
                ]
        elif structured is None:
            response.structuredContent = {"live_view": block}
        response.content = [*response.content, McpToolCallContent(text=block["banner"])]
