"""Screencast hub and /live-api/sessions/{id}/stream, with fake CDP sessions."""

from __future__ import annotations

import asyncio
import base64
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from app.live import LiveViewService
from app.live.screencast import ScreencastHub, SessionNotLiveError, StreamLimitError
from app.routes.live_api import create_live_api_router, install_live_cors

SID = "a5af842a89e1"
ORIGIN = "http://127.0.0.1:3100"


class FakeCdp:
    def __init__(self):
        self.handlers = {}
        self.sent = []
        self.detached = False
        self.fail_start = False

    def on(self, event, handler):
        self.handlers[event] = handler

    async def send(self, method, params=None):
        self.sent.append((method, params))
        if method == "Page.startScreencast" and self.fail_start:
            raise RuntimeError("no target")

    async def detach(self):
        self.detached = True

    def emit(self, payload: bytes, n: int = 1):
        handler = self.handlers["Page.screencastFrame"]
        handler({"data": base64.b64encode(payload).decode(), "sessionId": n, "metadata": {}})

    def count(self, method):
        return sum(1 for m, _ in self.sent if m == method)


class FakePage:
    def __init__(self):
        self.closed = False
        self.listeners = {}

    def is_closed(self):
        return self.closed

    def on(self, event, cb):
        self.listeners[event] = cb


class FakeContext:
    def __init__(self):
        self.cdps: list[FakeCdp] = []

    async def new_cdp_session(self, page):
        cdp = FakeCdp()
        cdp.page = page
        self.cdps.append(cdp)
        return cdp


def make_settings(**kw):
    base = dict(
        live_stream_enabled=True,
        live_stream_fps=6,
        live_stream_quality=55,
        live_stream_max_width=1024,
        live_stream_max_viewers_per_session=2,
        live_stream_max_viewers=3,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def make_manager(*ids):
    context = FakeContext()
    sessions = {sid: SimpleNamespace(page=FakePage(), context=context) for sid in ids}
    return SimpleNamespace(sessions=sessions), context


async def until(pred, timeout=2.0):
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        if pred():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition not reached")


def hub_for(manager, **kw):
    return ScreencastHub(manager, make_settings(**kw), watch_interval=0.02)


async def test_lazy_start_and_stop_with_refcount():
    manager, ctx = make_manager(SID)
    hub = hub_for(manager)
    assert ctx.cdps == []  # nothing until a viewer connects
    v1 = hub.subscribe(SID)
    v2 = hub.subscribe(SID)
    await until(lambda: len(ctx.cdps) == 1 and hub.stats()["sessions"][SID]["screencast_active"])
    assert ctx.cdps[0].count("Page.startScreencast") == 1  # shared, not one per viewer
    params = ctx.cdps[0].sent[0][1]
    assert params["format"] == "jpeg" and params["quality"] == 55 and params["maxWidth"] == 1024
    assert params["everyNthFrame"] == 10  # 60 / 6 fps
    await v1.close()
    assert ctx.cdps[0].count("Page.stopScreencast") == 0  # one viewer left
    await v2.close()
    assert ctx.cdps[0].count("Page.stopScreencast") == 1
    assert ctx.cdps[0].detached
    assert hub.stats()["sessions"] == {}


async def test_fan_out_and_ack_every_frame():
    manager, ctx = make_manager(SID)
    hub = hub_for(manager)
    v1, v2 = hub.subscribe(SID), hub.subscribe(SID)
    await until(lambda: ctx.cdps and ctx.cdps[0].handlers)
    cdp = ctx.cdps[0]
    cdp.emit(b"one", 1)
    assert await v1.get(1) == b"one" and await v2.get(1) == b"one"
    cdp.emit(b"two", 2)
    await until(lambda: cdp.count("Page.screencastFrameAck") == 2)
    assert [p["sessionId"] for m, p in cdp.sent if m == "Page.screencastFrameAck"] == [1, 2]
    await v1.close()
    await v2.close()


async def test_slow_viewer_drops_frames_and_does_not_block_others():
    manager, ctx = make_manager(SID)
    hub = hub_for(manager)
    slow, fast = hub.subscribe(SID), hub.subscribe(SID)
    await until(lambda: ctx.cdps and ctx.cdps[0].handlers)
    cdp = ctx.cdps[0]
    got = []
    for i in range(50):
        cdp.emit(f"f{i}".encode(), i)
        got.append(await fast.get(1))
    assert got[-1] == b"f49" and len(got) == 50
    assert slow.dropped == 48  # queue of 2 kept only the newest frames
    assert await slow.get(1) == b"f48" and await slow.get(1) == b"f49"
    await slow.close()
    await fast.close()


async def test_late_joiner_gets_last_frame():
    manager, ctx = make_manager(SID)
    hub = hub_for(manager, live_stream_max_viewers_per_session=3)
    v1 = hub.subscribe(SID)
    await until(lambda: ctx.cdps and ctx.cdps[0].handlers)
    ctx.cdps[0].emit(b"pic")
    await v1.get(1)
    v2 = hub.subscribe(SID)
    assert await v2.get(1) == b"pic"
    await v1.close()
    await v2.close()


async def test_caps_per_session_and_total():
    manager, _ = make_manager(SID, "bbbbbbbbbbbb")
    hub = hub_for(manager)  # 2 per session, 3 total
    a1, a2 = hub.subscribe(SID), hub.subscribe(SID)
    with pytest.raises(StreamLimitError) as info:
        hub.subscribe(SID)
    assert info.value.scope == "per-session"
    b1 = hub.subscribe("bbbbbbbbbbbb")
    with pytest.raises(StreamLimitError) as info:
        hub.subscribe("bbbbbbbbbbbb")
    assert info.value.scope == "total"
    await a1.close()
    hub.subscribe(SID)  # a slot was freed
    for v in (a2, b1):
        await v.close()
    await hub.shutdown()


async def test_unknown_session_is_refused():
    manager, _ = make_manager()
    with pytest.raises(SessionNotLiveError):
        hub_for(manager).subscribe(SID)


async def test_session_close_ends_viewers_and_stops_screencast():
    manager, ctx = make_manager(SID)
    hub = hub_for(manager)
    v = hub.subscribe(SID)
    await until(lambda: ctx.cdps and ctx.cdps[0].handlers)
    ctx.cdps[0].emit(b"x")
    assert await v.get(1) == b"x"
    del manager.sessions[SID]
    assert await v.get(1) is None  # clean end
    assert await v.get(1) is None  # and stays ended
    assert ctx.cdps[0].count("Page.stopScreencast") == 1
    await v.close()


async def test_follows_active_page_switch_and_close():
    manager, ctx = make_manager(SID)
    hub = hub_for(manager)
    v = hub.subscribe(SID)
    await until(lambda: len(ctx.cdps) == 1 and ctx.cdps[0].handlers)
    first_page = manager.sessions[SID].page
    second = FakePage()
    manager.sessions[SID].page = second  # activate_tab / open_tab
    await until(lambda: len(ctx.cdps) == 2 and ctx.cdps[1].count("Page.startScreencast") == 1)
    assert ctx.cdps[0].detached and ctx.cdps[1].page is second
    ctx.cdps[1].emit(b"tab2")
    assert await v.get(1) == b"tab2"
    # the active page closes and another becomes active
    second.closed = True
    third = FakePage()
    manager.sessions[SID].page = third
    await until(lambda: len(ctx.cdps) == 3)
    assert ctx.cdps[2].page is third and first_page is not third
    await v.close()


async def test_crash_reattaches():
    manager, ctx = make_manager(SID)
    hub = hub_for(manager)
    v = hub.subscribe(SID)
    await until(lambda: len(ctx.cdps) == 1 and ctx.cdps[0].handlers)
    manager.sessions[SID].page.listeners["crash"]()
    await until(lambda: len(ctx.cdps) == 2)
    await v.close()


async def test_attach_failures_end_the_feed():
    manager, ctx = make_manager(SID)

    async def failing(page):
        cdp = FakeCdp()
        cdp.fail_start = True
        ctx.cdps.append(cdp)
        return cdp

    ctx.new_cdp_session = failing
    hub = hub_for(manager)
    v = hub.subscribe(SID)
    assert await v.get(3) is None
    assert len(ctx.cdps) == 5 and all(c.detached for c in ctx.cdps)
    await v.close()


async def test_resubscribe_after_feed_ended_starts_new_feed():
    manager, ctx = make_manager(SID)
    hub = hub_for(manager)
    v = hub.subscribe(SID)
    await until(lambda: ctx.cdps and ctx.cdps[0].handlers)
    await v.close()
    v2 = hub.subscribe(SID)
    await until(lambda: len(ctx.cdps) == 2 and ctx.cdps[1].handlers)
    await v2.close()


# ---- HTTP route ---------------------------------------------------------------------


class Env:
    def __init__(self, **settings_kw):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = make_settings(**settings_kw)
        self.settings.artifact_root = self.tmp.name
        self.settings.live_ui_base_url = ORIGIN
        self.settings.live_banner_color = False
        self.settings.live_ui_origin_list = [ORIGIN]
        self.svc = LiveViewService(self.settings)
        self.manager, self.ctx = make_manager(SID)
        self.manager.get_session_record = AsyncMock(side_effect=KeyError("x"))
        app = FastAPI()
        router = create_live_api_router(manager=self.manager, live_view=self.svc, tool_gateway=SimpleNamespace())
        app.include_router(router)
        install_live_cors(app, settings=self.settings)
        self.hub = router.screencast_hub
        self.hub.watch_interval = 0.02
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def env():
    e = Env()
    await e.svc.register_session(SID)
    yield e
    await e.hub.shutdown()
    await e.client.aclose()
    e.tmp.cleanup()


def parts(body: bytes) -> list[bytes]:
    out = []
    for chunk in body.split(b"--frame\r\n")[1:]:
        head, _, rest = chunk.partition(b"\r\n\r\n")
        length = int(head.split(b"Content-Length: ")[1].split(b"\r\n")[0])
        out.append(rest[:length])
    return out


async def test_route_streams_mjpeg_and_ends_on_session_close(env):
    task = asyncio.ensure_future(env.client.get(f"/live-api/sessions/{SID}/stream", headers={"origin": ORIGIN}))
    await until(lambda: env.ctx.cdps and env.ctx.cdps[0].handlers)
    for i in range(3):
        env.ctx.cdps[0].emit(f"jpeg{i}".encode())
        await asyncio.sleep(0.05)
    del env.manager.sessions[SID]
    response = await asyncio.wait_for(task, 5)
    assert response.status_code == 200
    assert response.headers["content-type"] == "multipart/x-mixed-replace; boundary=frame"
    assert response.headers["cache-control"].startswith("no-store")
    assert parts(response.content) == [b"jpeg0", b"jpeg1", b"jpeg2"]
    assert env.hub.stats()["sessions"] == {}  # viewer released, screencast stopped
    assert env.ctx.cdps[0].count("Page.stopScreencast") == 1


async def test_route_statuses(env):
    get = env.client.get
    assert (await get("/live-api/sessions/nope..x/stream")).status_code == 404  # bad id shape
    assert (await get("/live-api/sessions/..%2F..%2Fetc/stream")).status_code == 404
    assert (await get("/live-api/sessions/ffffffffffff/stream")).status_code == 404  # unknown
    assert (await get(f"/live-api/sessions/{SID}/stream", headers={"origin": "http://evil.example"})).status_code == 403
    cross = {"sec-fetch-site": "cross-site", "referer": "http://evil.example/page"}
    assert (await get(f"/live-api/sessions/{SID}/stream", headers=cross)).status_code == 403
    # an archived session answers with a small JSON body, never a hanging stream
    await env.svc.mark_closed(SID)
    del env.manager.sessions[SID]
    archived = await get(f"/live-api/sessions/{SID}/stream")
    assert archived.status_code == 409 and archived.json()["state"] == "archived"
    assert env.hub.stats()["sessions"] == {}


async def test_route_disabled_and_caps(env):
    env.settings.live_stream_enabled = False
    disabled = await env.client.get(f"/live-api/sessions/{SID}/stream")
    assert disabled.status_code == 503 and disabled.json()["state"] == "disabled"
    env.settings.live_stream_enabled = True
    held = [env.hub.subscribe(SID), env.hub.subscribe(SID)]  # per-session cap is 2
    limited = await env.client.get(f"/live-api/sessions/{SID}/stream")
    assert limited.status_code == 429 and limited.json()["scope"] == "per-session"
    assert limited.headers["retry-after"]
    for v in held:
        await v.close()


async def test_stream_stats_endpoint(env):
    v = env.hub.subscribe(SID)
    await until(lambda: env.hub.stats()["sessions"][SID]["screencast_active"])
    body = (await env.client.get("/live-api/stream-stats")).json()
    assert body["total_viewers"] == 1 and body["sessions"][SID]["screencast_active"] is True
    await v.close()
