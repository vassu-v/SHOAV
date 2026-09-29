"""Per-session timeline recorder for Live View.

Every event gets a monotonic per-session `seq`, is appended to
`{artifact_root}/{session_id}/timeline.jsonl`, kept in a small in-memory tail for fast
reads, and pushed through the shared SSE bus (app/events.py). `summary.json` next to it
holds the session metadata. Nothing here may ever break a tool call: every public
coroutine swallows and logs its own failures.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import events as _events
from ..utils import UTC
from .banner import build_banner, colorize, live_url
from .phases import clean_text

logger = logging.getLogger(__name__)

# Same shape as the ids the controller mints (uuid hex prefix) but tolerant of test ids.
# No dots and no separators, so an id can never be a path traversal.
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
MAX_PERSISTED_EVENTS = 5000
TAIL_SIZE = 1000
DEFAULT_PAGE_LIMIT = 500
MAX_PAGE_LIMIT = 2000
MAX_PAGE_BYTES = 2_000_000
TIMELINE_FILE = "timeline.jsonl"
SUMMARY_FILE = "summary.json"


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def valid_session_id(session_id: Any) -> bool:
    return isinstance(session_id, str) and SESSION_ID_RE.fullmatch(session_id) is not None


@dataclass
class _State:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    loaded: bool = False
    seq: int = 0
    persisted: int = 0
    capped: bool = False
    tail: deque = field(default_factory=lambda: deque(maxlen=TAIL_SIZE))
    summary: dict[str, Any] | None = None


class LiveViewService:
    def __init__(self, settings: Any) -> None:
        self.settings = settings
        self._states: dict[str, _State] = {}

    # ── paths / links ───────────────────────────────────────────────────────

    @property
    def root(self) -> Path:
        return Path(self.settings.artifact_root)

    @property
    def base_url(self) -> str:
        return str(getattr(self.settings, "live_ui_base_url", "") or "http://127.0.0.1:3100")

    def live_url(self, session_id: str) -> str:
        return live_url(self.base_url, session_id)

    def banner(self, session_id: str) -> str:
        return build_banner(session_id, self.live_url(session_id))

    def live_view_block(self, session_id: str) -> dict[str, str]:
        return {"session_id": session_id, "url": self.live_url(session_id), "banner": self.banner(session_id)}

    def _dir(self, session_id: str) -> Path:
        return self.root / session_id

    # ── low-level sync IO (run in threads) ──────────────────────────────────

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        for _ in range(2):  # a concurrent atomic replace can transiently fail on Windows
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else None
            except FileNotFoundError:
                return None
            except (OSError, ValueError):
                continue
        return None

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(clean_text(json.dumps(data, ensure_ascii=False, indent=2)), encoding="utf-8")
        tmp.replace(path)

    def _read_events(self, session_id: str) -> list[dict[str, Any]]:
        path = self._dir(session_id) / TIMELINE_FILE
        events: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue  # torn write from a crash: skip
                    if isinstance(item, dict) and isinstance(item.get("seq"), int):
                        events.append(item)
        except FileNotFoundError:
            pass
        return events

    def _append_line(self, session_id: str, event: dict[str, Any]) -> None:
        path = self._dir(session_id) / TIMELINE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    # ── state ───────────────────────────────────────────────────────────────

    def _state(self, session_id: str) -> _State:
        state = self._states.get(session_id)
        if state is None:
            state = self._states[session_id] = _State()
        return state

    @asynccontextmanager
    async def _locked(self, session_id: str):
        """Yield the session's loaded state with its lock held.

        The state may be evicted (session closed) while we wait for the lock; then a
        new state object exists and holding the old lock guards nothing, so retry with
        the fresh one. Two live states for one session would hand out duplicate seqs.
        """
        while True:
            state = self._state(session_id)
            await state.lock.acquire()
            if self._states.get(session_id) is not state:
                state.lock.release()
                continue
            try:
                await self._ensure_loaded(session_id, state)
                yield state
            finally:
                state.lock.release()
            return

    async def _evict(self, session_id: str) -> None:
        state = self._states.get(session_id)
        if state is None:
            return
        async with state.lock:
            if self._states.get(session_id) is state:
                del self._states[session_id]

    async def _ensure_loaded(self, session_id: str, state: _State) -> None:
        """Must be called with state.lock held."""
        if state.loaded:
            return
        events = await asyncio.to_thread(self._read_events, session_id)
        state.seq = max((e["seq"] for e in events), default=0)
        state.persisted = len(events)
        state.capped = state.persisted >= MAX_PERSISTED_EVENTS
        state.tail.extend(events[-TAIL_SIZE:])
        state.summary = await asyncio.to_thread(self._read_json, self._dir(session_id) / SUMMARY_FILE)
        state.loaded = True

    @staticmethod
    def _default_summary(session_id: str) -> dict[str, Any]:
        return {
            "id": session_id,
            "name": None,
            "state": "live",
            "start_url": None,
            "current_url": None,
            "title": None,
            "created_at": now_iso(),
            "closed_at": None,
            "tool_calls": 0,
            "last_screenshot_url": None,
            "client": None,
        }

    async def _save_summary(self, session_id: str, state: _State) -> None:
        if state.summary is not None:
            await asyncio.to_thread(self._write_json, self._dir(session_id) / SUMMARY_FILE, state.summary)

    # ── public: recording ───────────────────────────────────────────────────

    async def register_session(
        self,
        session_id: str,
        *,
        name: str | None = None,
        start_url: str | None = None,
        current_url: str | None = None,
        title: str | None = None,
        created_at: str | None = None,
        client: str | None = None,
    ) -> bool:
        """Create the summary for a new session. True only the first time (banner trigger)."""
        if not valid_session_id(session_id):
            return False
        try:
            async with self._locked(session_id) as state:
                if state.summary is not None:
                    return False
                summary = self._default_summary(session_id)
                summary.update(
                    name=name,
                    start_url=start_url or current_url,
                    current_url=current_url or start_url,
                    title=title,
                    client=client,
                )
                if created_at:
                    summary["created_at"] = created_at
                state.summary = summary
                await self._save_summary(session_id, state)
            return True
        except Exception:
            logger.warning("live view: failed to register session %s", session_id, exc_info=True)
            return False

    def print_banner(self, session_id: str) -> None:
        """Print the banner to the controller console (ANSI colour only if enabled)."""
        try:
            text = self.banner(session_id)
            if getattr(self.settings, "live_banner_color", False):
                text = colorize(text)
            try:
                sys.stdout.write(text + "\n")
            except UnicodeEncodeError:
                # Legacy Windows code pages cannot draw box characters; degrade, don't drop.
                encoding = getattr(sys.stdout, "encoding", None) or "ascii"
                safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
                sys.stdout.write(safe + "\n")
            sys.stdout.flush()
        except Exception:
            logger.debug("live view: banner print failed", exc_info=True)

    async def record(self, session_id: str, event: dict[str, Any]) -> dict[str, Any] | None:
        """Stamp seq/ts/session_id, persist, and publish. Never raises."""
        if not valid_session_id(session_id):
            return None
        try:
            async with self._locked(session_id) as state:
                if not state.capped and state.persisted >= MAX_PERSISTED_EVENTS:
                    state.capped = True
                    state.seq += 1
                    note = {
                        "type": "note",
                        "event": "capped",
                        "session_id": session_id,
                        "seq": state.seq,
                        "ts": now_iso(),
                        "message": f"timeline capped at {MAX_PERSISTED_EVENTS} events; later events are live-only",
                    }
                    try:
                        await asyncio.to_thread(self._append_line, session_id, note)
                    except Exception:
                        logger.warning("live view: failed to write cap note for %s", session_id, exc_info=True)
                    state.tail.append(note)
                    _events.emit_raw(session_id, note)
                state.seq += 1
                full = {"type": "tool", **event, "session_id": session_id, "seq": state.seq, "ts": now_iso()}
                if not state.capped:
                    try:
                        await asyncio.to_thread(self._append_line, session_id, full)
                        state.persisted += 1
                    except Exception:
                        logger.warning("live view: failed to persist event for %s", session_id, exc_info=True)
                state.tail.append(full)
                _events.emit_raw(session_id, full)
                return full
        except Exception:
            logger.warning("live view: failed to record event for %s", session_id, exc_info=True)
            return None

    async def note_call(
        self,
        session_id: str,
        *,
        started: bool = False,
        url: str | None = None,
        title: str | None = None,
        screenshot_url: str | None = None,
        client: str | None = None,
    ) -> None:
        """Update summary counters/pointers; persists on every call (small file)."""
        if not valid_session_id(session_id):
            return
        try:
            async with self._locked(session_id) as state:
                summary = state.summary
                if summary is None or summary.get("state") == "archived":
                    return  # never resurrect or bump a closed/unknown session
                if started:
                    summary["tool_calls"] = int(summary.get("tool_calls") or 0) + 1
                if url:
                    summary["current_url"] = url
                    if not summary.get("start_url"):
                        summary["start_url"] = url
                if title:
                    summary["title"] = title
                if screenshot_url:
                    summary["last_screenshot_url"] = screenshot_url
                if client and not summary.get("client"):
                    summary["client"] = client
                await self._save_summary(session_id, state)
        except Exception:
            logger.warning("live view: failed to update summary for %s", session_id, exc_info=True)

    async def mark_closed(self, session_id: str) -> None:
        if not valid_session_id(session_id):
            return
        try:
            async with self._locked(session_id) as state:
                if state.summary is None:
                    return  # unknown session: do not create a phantom summary
                state.summary["state"] = "archived"
                state.summary["closed_at"] = state.summary.get("closed_at") or now_iso()
                await self._save_summary(session_id, state)
            # Free memory; later reads (and any late in-flight event) reload from disk.
            await self._evict(session_id)
        except Exception:
            logger.warning("live view: failed to close summary for %s", session_id, exc_info=True)

    # ── public: reading ─────────────────────────────────────────────────────

    async def get_summary(self, session_id: str) -> dict[str, Any] | None:
        if not valid_session_id(session_id):
            return None
        state = self._states.get(session_id)
        if state is not None and state.loaded and state.summary is not None:
            return dict(state.summary)
        return await asyncio.to_thread(self._read_json, self._dir(session_id) / SUMMARY_FILE)

    async def timeline(
        self,
        session_id: str,
        after_seq: int = 0,
        limit: int = DEFAULT_PAGE_LIMIT,
        max_bytes: int = MAX_PAGE_BYTES,
    ) -> tuple[list[dict[str, Any]], int, bool]:
        """(events with seq > after_seq oldest-first, last_seq, has_more).

        At most `limit` events and about `max_bytes` of serialised JSON (always at least one
        event). `last_seq` is the seq of the last returned event (or after_seq if none), so
        a client pages with `after_seq=last_seq` while `has_more` is true.
        """
        if not valid_session_id(session_id):
            return [], after_seq, False
        limit = max(1, min(int(limit), MAX_PAGE_LIMIT))
        candidates: list[dict[str, Any]] | None = None
        state = self._states.get(session_id)
        if state is not None and state.loaded:
            async with state.lock:
                tail = list(state.tail)
                persisted = state.persisted
            if not tail or tail[0]["seq"] <= after_seq + 1 or persisted <= len(tail):
                candidates = [e for e in tail if e["seq"] > after_seq]
        if candidates is None:
            candidates = await asyncio.to_thread(self._read_events_after, session_id, after_seq)
        picked: list[dict[str, Any]] = []
        used = 0
        for event in candidates:
            size = len(json.dumps(event, ensure_ascii=False))
            if picked and (len(picked) >= limit or used + size > max_bytes):
                break
            picked.append(event)
            used += size
        has_more = len(picked) < len(candidates)
        return picked, (picked[-1]["seq"] if picked else after_seq), has_more

    def _read_events_after(self, session_id: str, after_seq: int) -> list[dict[str, Any]]:
        return [e for e in self._read_events(session_id) if e["seq"] > after_seq]

    def _list_summaries_sync(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            children = list(self.root.iterdir())
        except OSError:
            return out
        for child in children:
            if not child.is_dir() or not valid_session_id(child.name):
                continue
            summary = self._read_json(child / SUMMARY_FILE)
            if summary and summary.get("id") == child.name:
                out.append(summary)
        return out

    async def list_summaries(self) -> list[dict[str, Any]]:
        summaries = await asyncio.to_thread(self._list_summaries_sync)
        for index, item in enumerate(summaries):  # prefer fresher in-memory copies
            state = self._states.get(item["id"])
            if state is not None and state.loaded and state.summary is not None:
                summaries[index] = dict(state.summary)
        summaries.sort(key=lambda s: (s.get("created_at") or "", s.get("id") or ""), reverse=True)
        return summaries

    async def archive_stale(self, live_ids: set[str]) -> int:
        """Startup: summaries still marked live with no live browser become archived."""
        count = 0
        for summary in await self.list_summaries():
            if summary.get("state") == "live" and summary["id"] not in live_ids:
                sid = summary["id"]
                await self.record(
                    sid,
                    {"type": "note", "event": "archived", "message": "controller restarted; session archived"},
                )
                await self.mark_closed(sid)
                count += 1
        return count

    async def reconcile(self, summary: dict[str, Any], live_ids: set[str] | frozenset[str]) -> dict[str, Any]:
        """Lazily archive sessions whose browser is gone (HTTP close, idle expiry, crash).

        Writes `state`/`closed_at` back to summary.json and evicts the in-memory state so
        the tail does not leak. Returns the up-to-date summary.
        """
        sid = str(summary.get("id"))
        if sid in live_ids or not valid_session_id(sid):
            return summary
        if summary.get("state") != "archived" or not summary.get("closed_at"):
            await self.mark_closed(sid)
            summary = await self.get_summary(sid) or summary
        await self._evict(sid)
        return summary

    def present(self, summary: dict[str, Any], live_ids: set[str] | frozenset[str]) -> dict[str, Any]:
        """Public SessionSummary: state derived from the live browser set, plus live_url."""
        sid = str(summary.get("id"))
        is_live = sid in live_ids
        return {
            "id": sid,
            "name": summary.get("name"),
            "state": "live" if is_live else "archived",
            "start_url": summary.get("start_url"),
            "current_url": summary.get("current_url"),
            "title": summary.get("title"),
            "created_at": summary.get("created_at") or "",
            "closed_at": None if is_live else summary.get("closed_at"),
            "tool_calls": int(summary.get("tool_calls") or 0),
            "last_screenshot_url": summary.get("last_screenshot_url"),
            "live_url": self.live_url(sid),
            "client": summary.get("client"),
        }
