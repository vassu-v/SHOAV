"""Live MJPEG feed of a session's active page, built on CDP ``Page.startScreencast``.

One CDP screencast per session is shared by every viewer (fan-out). It starts when the
first viewer subscribes and stops when the last one leaves, so an unwatched session pays
nothing. Each viewer has a tiny bounded queue and the oldest frame is dropped when it is
full, so a slow client never blocks the browser or the other viewers.

The screencast is read-only: it does not resize the viewport, focus a window or touch page
state, and it uses its own CDP session, so ``page.screenshot`` keeps working beside it.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

WATCH_INTERVAL_S = 0.4
MAX_ATTACH_FAILURES = 5


class StreamLimitError(Exception):
    """Too many viewers (per session or in total)."""

    def __init__(self, scope: str, limit: int):
        super().__init__(f"Too many live viewers ({scope} limit {limit})")
        self.scope = scope
        self.limit = limit


class SessionNotLiveError(Exception):
    """The session is not in the live set."""


class Viewer:
    """One connected client. ``get()`` returns JPEG bytes, or None once the feed ended."""

    def __init__(self, feed: _Feed, queue_size: int = 2):
        self._feed = feed
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=queue_size)
        self.dropped = 0
        self.received = 0
        self.ended = False
        self._closed = False

    def push(self, frame: bytes) -> None:
        if self.ended:
            return
        if self._queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
            self.dropped += 1
        self._queue.put_nowait(frame)

    def end(self) -> None:
        """Signal a clean end. Pending frames are discarded, the sentinel always fits."""
        if self.ended:
            return
        self.ended = True
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._queue.put_nowait(None)

    async def get(self, timeout: float | None = None) -> bytes | None:
        if timeout is None:
            frame = await self._queue.get()
        else:
            frame = await asyncio.wait_for(self._queue.get(), timeout)
        if frame is None:
            # keep the sentinel so later get() calls also see the end
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(None)
        else:
            self.received += 1
        return frame

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._feed.hub._release(self._feed, self)


class _Feed:
    def __init__(self, hub: ScreencastHub, session_id: str):
        self.hub = hub
        self.session_id = session_id
        self.viewers: set[Viewer] = set()
        self.last_frame: bytes | None = None
        self.task: asyncio.Task | None = None
        self.active = False  # a CDP screencast is running right now
        self.frames = 0
        self.bytes = 0
        self.started_at = time.monotonic()
        self.attach_failures = 0

    def publish(self, frame: bytes) -> None:
        self.last_frame = frame
        self.frames += 1
        self.bytes += len(frame)
        for viewer in tuple(self.viewers):
            viewer.push(frame)

    def end_viewers(self) -> None:
        for viewer in tuple(self.viewers):
            viewer.end()

    async def run(self) -> None:
        manager = self.hub.manager
        page: Any = None
        cdp: Any = None
        crashed = False

        def on_crash() -> None:
            nonlocal crashed
            crashed = True

        try:
            while True:
                session = manager.sessions.get(self.session_id)
                if session is None:
                    break  # session closed: end cleanly
                current = session.page
                closed = bool(current.is_closed()) if hasattr(current, "is_closed") else False
                if current is not page or crashed or (cdp is None and not closed):
                    await self._detach(cdp)
                    cdp = None
                    crashed = False
                    page = current
                    if not closed:
                        try:
                            cdp = await self._attach(session, page, on_crash)
                            self.attach_failures = 0
                        except Exception as exc:
                            self.attach_failures += 1
                            logger.info("screencast %s: attach failed (%s)", self.session_id, exc)
                            page = None  # retry against the current page next tick
                            if self.attach_failures >= MAX_ATTACH_FAILURES:
                                break
                elif closed and cdp is not None:
                    await self._detach(cdp)
                    cdp = None
                await asyncio.sleep(self.hub.watch_interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("screencast %s: feed crashed", self.session_id)
        finally:
            with contextlib.suppress(Exception):
                await asyncio.shield(self._detach(cdp))
            self.end_viewers()

    async def _attach(self, session: Any, page: Any, on_crash: Any) -> Any:
        settings = self.hub.settings
        cdp = await session.context.new_cdp_session(page)

        def on_frame(params: dict[str, Any]) -> None:
            # Ack first and always: without the ack Chromium stops sending frames.
            asyncio.ensure_future(self._ack(cdp, params.get("sessionId")))
            data = params.get("data")
            if not data or not self.viewers:
                return
            try:
                self.publish(base64.b64decode(data))
            except Exception:
                logger.debug("screencast %s: bad frame", self.session_id, exc_info=True)

        cdp.on("Page.screencastFrame", on_frame)
        with contextlib.suppress(Exception):
            page.on("crash", lambda *_: on_crash())
        every_nth = max(1, round(60 / max(1, settings.live_stream_fps)))
        try:
            await cdp.send(
                "Page.startScreencast",
                {
                    "format": "jpeg",
                    "quality": int(settings.live_stream_quality),
                    "maxWidth": int(settings.live_stream_max_width),
                    "everyNthFrame": every_nth,
                },
            )
        except Exception:
            with contextlib.suppress(Exception):
                await cdp.detach()
            raise
        self.active = True
        logger.info("screencast start session=%s every_nth=%d", self.session_id, every_nth)
        return cdp

    @staticmethod
    async def _ack(cdp: Any, frame_session_id: Any) -> None:
        with contextlib.suppress(Exception):
            await cdp.send("Page.screencastFrameAck", {"sessionId": frame_session_id})

    async def _detach(self, cdp: Any) -> None:
        if cdp is None:
            return
        self.active = False
        with contextlib.suppress(Exception):
            await cdp.send("Page.stopScreencast")
        with contextlib.suppress(Exception):
            await cdp.detach()
        logger.info(
            "screencast stop session=%s frames=%d bytes=%d",
            self.session_id,
            self.frames,
            self.bytes,
        )


class ScreencastHub:
    def __init__(self, manager: Any, settings: Any, *, watch_interval: float = WATCH_INTERVAL_S):
        self.manager = manager
        self.settings = settings
        self.watch_interval = watch_interval
        self._feeds: dict[str, _Feed] = {}

    @property
    def total_viewers(self) -> int:
        return sum(len(feed.viewers) for feed in self._feeds.values())

    def stats(self) -> dict[str, Any]:
        return {
            "total_viewers": self.total_viewers,
            "sessions": {
                sid: {
                    "viewers": len(feed.viewers),
                    "screencast_active": feed.active,
                    "frames": feed.frames,
                    "bytes": feed.bytes,
                }
                for sid, feed in self._feeds.items()
            },
        }

    def subscribe(self, session_id: str) -> Viewer:
        """Register a viewer and start the shared screencast if needed (no awaits: atomic)."""
        if session_id not in self.manager.sessions:
            raise SessionNotLiveError(session_id)
        feed = self._feeds.get(session_id)
        per_session = int(self.settings.live_stream_max_viewers_per_session)
        total = int(self.settings.live_stream_max_viewers)
        if feed is not None and len(feed.viewers) >= per_session:
            raise StreamLimitError("per-session", per_session)
        if self.total_viewers >= total:
            raise StreamLimitError("total", total)
        if feed is None or feed.task is None or feed.task.done():
            feed = _Feed(self, session_id)
            self._feeds[session_id] = feed
            feed.task = asyncio.ensure_future(feed.run())
        viewer = Viewer(feed)
        feed.viewers.add(viewer)
        if feed.last_frame is not None:
            viewer.push(feed.last_frame)  # late joiner sees the current picture at once
        return viewer

    async def _release(self, feed: _Feed, viewer: Viewer) -> None:
        feed.viewers.discard(viewer)
        if feed.viewers:
            return
        if self._feeds.get(feed.session_id) is feed:
            del self._feeds[feed.session_id]
        task = feed.task
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    async def shutdown(self) -> None:
        feeds = list(self._feeds.values())
        self._feeds.clear()
        for feed in feeds:
            if feed.task is not None and not feed.task.done():
                feed.task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await feed.task
            feed.end_viewers()
