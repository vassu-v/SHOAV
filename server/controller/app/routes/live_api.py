"""/live-api: read side of Live View (session list, timelines, tool catalogue, restart).

Auth is not special-cased: the controller's global bearer-token middleware protects these
paths exactly like the rest of the API. CORS is limited to LIVE_UI_ORIGINS and to the few
paths the live-ui needs (this router and the per-session SSE stream); credentials are
never allowed, so a controller that requires a bearer token cannot be read cross-origin
by the UI without a proxy - that is intentional.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from ..live import LiveViewService, classify_phase, valid_session_id
from ..live.recorder import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT
from ..live.screencast import ScreencastHub, SessionNotLiveError, StreamLimitError
from ..mcp_transport import MCP_INSTRUCTIONS

logger = logging.getLogger(__name__)

_LIVE_CORS_PATH = re.compile(r"^(/live-api(/|$)|/sessions/[^/]+/events$)")
_CORS_METHODS = "GET, POST, OPTIONS"
_BOUNDARY = "frame"
_HEARTBEAT_S = 10.0
_GUARD_VERSION = "1"
_GUARD_COUNTER_KEYS = ("allow", "rewrite", "block", "escalate")
# RECON unify d: errors and fail_open are first-class guard counters
# (ShoavGuard._COUNTER_KEYS) but were dropped by this route. They are
# exposed as optional top-level fields plus a per-stage split so existing
# {"allow","rewrite","block","escalate"} assertions keep passing.
_GUARD_EXTRA_KEYS = ("errors", "fail_open")

try:
    from connectors.rewrite import findings_to_summary as _canonical_findings_summary
except Exception:
    _canonical_findings_summary = None  # type: ignore[assignment]


def _guard_counter_value(raw: dict[str, Any], key: str) -> int:
    """Aggregate one verdict total from a guard counters dict.

    The ShoavGuard snapshot uses per-stage keys (ingress_allow, egress_block,
    ...) while simpler guards may expose plain allow/rewrite/block/escalate.
    Sum every matching shape so the route reports real totals, not zeros.
    """
    total = 0
    candidates = (
        key,
        key.upper(),
        f"ingress_{key}",
        f"ingress_{key}".upper(),
        f"INGRESS_{key.upper()}",
        f"egress_{key}",
        f"egress_{key}".upper(),
        f"EGRESS_{key.upper()}",
    )
    seen: set[str] = set()
    for name in candidates:
        if name in seen:
            continue
        seen.add(name)
        try:
            value = raw.get(name, 0) or 0
        except AttributeError:
            value = 0
        try:
            total += int(value)
        except (TypeError, ValueError):
            continue
    return total


def _aggregate_guard_counters(raw: Any) -> dict[str, int]:
    if not isinstance(raw, dict):
        return dict.fromkeys(_GUARD_COUNTER_KEYS, 0)
    return {key: _guard_counter_value(raw, key) for key in _GUARD_COUNTER_KEYS}


def _guard_int_value(raw: Any, *names: str) -> int | None:
    """Read the first present int counter among names, else None."""
    if not isinstance(raw, dict):
        return None
    for name in names:
        if name in raw:
            try:
                return int(raw.get(name) or 0)
            except (TypeError, ValueError):
                continue
    return None


def _guard_extra_fields(raw: Any) -> dict[str, Any]:
    """Optional errors/fail_open plus per-stage split (RECON unify d).

    Returns {} when the raw counters carry none of these so guard-off
    and simple-guard shapes stay byte-identical for existing tests.
    """
    if not isinstance(raw, dict):
        return {}
    extra: dict[str, Any] = {}
    for key in _GUARD_EXTRA_KEYS:
        value = _guard_int_value(raw, key, key.upper())
        if value is not None:
            extra[key] = value
    stages: dict[str, Any] = {}
    for stage in ("ingress", "egress"):
        stage_counters: dict[str, int] = {}
        present = False
        for verdict in _GUARD_COUNTER_KEYS:
            for name in (f"{stage}_{verdict}", f"{stage}_{verdict}".upper(), f"{stage.upper()}_{verdict.upper()}"):
                if name in raw:
                    present = True
                    try:
                        stage_counters[verdict] = stage_counters.get(verdict, 0) + int(raw.get(name) or 0)
                    except (TypeError, ValueError):
                        continue
        if present:
            stages[stage] = stage_counters
    if stages:
        extra["stages"] = stages
    return extra


def _guard_findings_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Optional canonical findings summary for guard status (RECON unify b)."""
    findings = data.get("findings")
    if findings is None:
        return {}
    if _canonical_findings_summary is not None:
        try:
            return {"findings": _canonical_findings_summary(findings)}
        except Exception:
            return {}
    return {}


def _guard_status(tool_gateway: Any) -> dict[str, Any]:
    """Guard mode/version/counters for GET /live-api/guard.

    Reads the guard object attached by app wiring (if any) without importing it,
    so this route works with guard off (no object) and with any guard object
    exposing mode/version/counters or a status()/snapshot() dict.
    """
    guard = None
    for attr in ("guard", "shoav_guard", "shoav"):
        candidate = getattr(tool_gateway, attr, None)
        if candidate is not None:
            guard = candidate
            break
    if guard is None:
        return {"mode": "off", "version": _GUARD_VERSION, "counters": dict.fromkeys(_GUARD_COUNTER_KEYS, 0)}
    for method in ("status", "snapshot", "describe"):
        fn = getattr(guard, method, None)
        if callable(fn):
            try:
                data = fn()
            except Exception:
                continue
            if isinstance(data, dict) and isinstance(data.get("counters"), dict):
                raw = data["counters"]
                counters = _aggregate_guard_counters(raw)
                status: dict[str, Any] = {
                    "mode": str(data.get("mode", "off") or "off").lower(),
                    "version": str(data.get("version", _GUARD_VERSION) or _GUARD_VERSION),
                    "counters": counters,
                }
                status.update(_guard_extra_fields(raw))
                status.update(_guard_findings_summary(data))
                return status
    raw_counters = getattr(guard, "counters", None)
    if callable(raw_counters):
        try:
            raw_counters = raw_counters()
        except Exception:
            raw_counters = {}
    if not isinstance(raw_counters, dict):
        raw_counters = {}
    counters = _aggregate_guard_counters(raw_counters)
    status = {
        "mode": str(getattr(guard, "mode", "off") or "off").lower(),
        "version": str(getattr(guard, "version", _GUARD_VERSION) or _GUARD_VERSION),
        "counters": counters,
    }
    status.update(_guard_extra_fields(raw_counters))
    return status


def _part(frame: bytes) -> bytes:
    """One multipart/x-mixed-replace part carrying a JPEG."""
    crlf = bytes([13, 10])
    lines = (f"--{_BOUNDARY}", "Content-Type: image/jpeg", f"Content-Length: {len(frame)}", "", "")
    return crlf.join(line.encode() for line in lines) + frame + crlf


def create_live_api_router(*, manager: Any, live_view: LiveViewService, tool_gateway: Any) -> APIRouter:
    router = APIRouter(prefix="/live-api")
    hub = ScreencastHub(manager, live_view.settings)
    router.screencast_hub = hub  # type: ignore[attr-defined]

    def _require_id(session_id: str) -> str:
        if not valid_session_id(session_id):
            raise HTTPException(status_code=404, detail=f"Not found: {session_id}")
        return session_id

    async def _adopt_live_sessions() -> None:
        """Sessions opened outside MCP (HTTP API) have no summary yet; create one."""
        for sid in list(manager.sessions.keys()):
            if not valid_session_id(sid) or await live_view.get_summary(sid) is not None:
                continue
            try:
                record = await manager.get_session_record(sid)
                await live_view.register_session(
                    sid,
                    name=record.get("name"),
                    current_url=record.get("current_url") or None,
                    title=record.get("title") or None,
                    created_at=record.get("created_at"),
                )
            except Exception:
                logger.debug("live-api: could not adopt live session %s", sid, exc_info=True)

    def _live_ids() -> set[str]:
        return set(manager.sessions.keys())

    @router.get("/sessions")
    async def list_sessions() -> dict[str, Any]:
        await _adopt_live_sessions()
        live_ids = _live_ids()
        summaries = await live_view.list_summaries()
        fresh = [await live_view.reconcile(item, live_ids) for item in summaries]
        return {"sessions": [live_view.present(item, live_ids) for item in fresh]}

    @router.get("/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        _require_id(session_id)
        await _adopt_live_sessions()
        summary = await live_view.get_summary(session_id)
        if summary is None:
            raise HTTPException(status_code=404, detail=f"Not found: {session_id}")
        summary = await live_view.reconcile(summary, _live_ids())
        return live_view.present(summary, _live_ids())

    @router.get("/sessions/{session_id}/timeline")
    async def get_timeline(
        session_id: str,
        after_seq: int = Query(0, ge=0),
        limit: int = Query(DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    ) -> dict[str, Any]:
        _require_id(session_id)
        await _adopt_live_sessions()
        summary = await live_view.get_summary(session_id)
        if summary is None:
            raise HTTPException(status_code=404, detail=f"Not found: {session_id}")
        summary = await live_view.reconcile(summary, _live_ids())
        events, last_seq, has_more = await live_view.timeline(session_id, after_seq, limit)
        return {
            "session": live_view.present(summary, _live_ids()),
            "events": events,
            "last_seq": last_seq,
            "has_more": has_more,
        }

    @router.post("/sessions/{session_id}/restart")
    async def restart_session(session_id: str, request: Request) -> dict[str, Any]:
        # CSRF: a browser page on another origin must not be able to open sessions.
        origin = request.headers.get("origin")
        allowed = {o.rstrip("/") for o in getattr(live_view.settings, "live_ui_origin_list", [])}
        if origin is not None and origin.rstrip("/") not in allowed:
            raise HTTPException(status_code=403, detail="Origin not allowed")
        if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
            raise HTTPException(status_code=403, detail="Cross-site request refused")
        _require_id(session_id)
        summary = await live_view.get_summary(session_id)
        if summary is None:
            raise HTTPException(status_code=404, detail=f"Not found: {session_id}")
        if session_id in manager.sessions:
            raise HTTPException(status_code=409, detail=f"Session {session_id} is still live")
        try:
            created = await manager.create_session(start_url=summary.get("start_url") or None)
        except RuntimeError as exc:  # session limit etc.
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except ValueError as exc:  # start_url no longer allowed
            raise HTTPException(status_code=400, detail=str(exc)) from None
        new_id = created["id"]
        is_new = await live_view.register_session(
            new_id,
            name=created.get("name"),
            start_url=summary.get("start_url"),
            current_url=created.get("current_url") or None,
            title=created.get("title") or None,
            created_at=created.get("created_at"),
        )
        if is_new:
            live_view.print_banner(new_id)
        fresh = await live_view.get_summary(new_id) or {"id": new_id}
        return {"session": live_view.present(fresh, _live_ids())}

    def _stream_origin_ok(request: Request) -> bool:
        """An <img> sends no Origin, so judge by Sec-Fetch-Site and Referer instead."""
        allowed = {o.rstrip("/") for o in getattr(live_view.settings, "live_ui_origin_list", [])}
        origin = request.headers.get("origin")
        if origin is not None and origin.rstrip("/") not in allowed:
            return False
        if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
            referer = request.headers.get("referer", "")
            match = re.match(r"^(https?://[^/]+)", referer)
            return bool(match and match.group(1).rstrip("/") in allowed)
        return True

    @router.get("/sessions/{session_id}/stream")
    async def stream_session(session_id: str, request: Request) -> Response:
        """MJPEG feed (multipart/x-mixed-replace) of the session's active page."""
        _require_id(session_id)
        if not getattr(live_view.settings, "live_stream_enabled", True):
            return JSONResponse({"detail": "Live stream is disabled", "state": "disabled"}, status_code=503)
        if not _stream_origin_ok(request):
            raise HTTPException(status_code=403, detail="Origin not allowed")
        if session_id not in manager.sessions:
            await _adopt_live_sessions()
            if await live_view.get_summary(session_id) is None:
                raise HTTPException(status_code=404, detail=f"Not found: {session_id}")
            return JSONResponse(
                {"detail": f"Session {session_id} is archived; no live feed", "state": "archived"},
                status_code=409,
            )
        try:
            viewer = hub.subscribe(session_id)
        except SessionNotLiveError:
            return JSONResponse({"detail": "Session is not live", "state": "archived"}, status_code=409)
        except StreamLimitError as exc:
            return JSONResponse(
                {"detail": str(exc), "state": "limit", "scope": exc.scope, "limit": exc.limit},
                status_code=429,
                headers={"Retry-After": "5"},
            )

        async def frames():
            last: bytes | None = None
            idle = 0.0
            try:
                while True:
                    try:
                        frame = await viewer.get(timeout=1.0)
                    except asyncio.TimeoutError:
                        if await request.is_disconnected():
                            return
                        idle += 1.0
                        if last is None or idle < _HEARTBEAT_S:
                            continue
                        frame = last  # keep-alive so a dead client is noticed by a failed write
                    if frame is None:
                        return  # feed ended: session closed
                    last, idle = frame, 0.0
                    yield _part(frame)
            finally:
                await asyncio.shield(viewer.close())

        return StreamingResponse(
            frames(),
            media_type=f"multipart/x-mixed-replace; boundary={_BOUNDARY}",
            headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
        )

    @router.get("/stream-stats")
    async def stream_stats() -> dict[str, Any]:
        """Viewer and screencast counters (debug aid, no page content)."""
        return hub.stats()

    @router.get("/guard")
    async def guard_status() -> dict[str, Any]:
        """Guard mode, version and verdict counters (debug aid, no page content)."""
        return _guard_status(tool_gateway)

    @router.get("/tools")
    async def list_tools() -> dict[str, Any]:
        tools = []
        for descriptor in tool_gateway.list_tools():
            name = descriptor.get("name", "")
            schema = descriptor.get("inputSchema") or {}
            tools.append(
                {
                    "name": name,
                    "description": descriptor.get("description", ""),
                    "phase": classify_phase(name),
                    "read_only": bool((descriptor.get("annotations") or {}).get("readOnlyHint", False)),
                    "required": list(schema.get("required") or []),
                }
            )
        return {"tools": tools, "instructions": MCP_INSTRUCTIONS}

    return router


def install_live_cors(application: FastAPI, *, settings: Any) -> None:
    """CORS for the live-ui origins, on live-ui paths only; GET/POST, no credentials.

    Install it after the other HTTP middleware so it is outermost: preflights are then
    answered before the auth/rate-limit layers, which cannot satisfy a preflight.
    """
    allowed = {origin.rstrip("/") for origin in settings.live_ui_origin_list}

    @application.middleware("http")
    async def live_ui_cors(request: Request, call_next):
        origin = request.headers.get("origin")
        path = str(request.scope.get("path") or "")
        if not origin or origin.rstrip("/") not in allowed or not _LIVE_CORS_PATH.match(path):
            return await call_next(request)
        headers = {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
        if request.method == "OPTIONS" and request.headers.get("access-control-request-method"):
            headers["Access-Control-Allow-Methods"] = _CORS_METHODS
            headers["Access-Control-Allow-Headers"] = request.headers.get(
                "access-control-request-headers", "Content-Type"
            )
            headers["Access-Control-Max-Age"] = "600"
            return Response(status_code=204, headers=headers)
        response = await call_next(request)
        for key, value in headers.items():
            response.headers[key] = value
        return response
