from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .utils import UTC


class SessionArtifactService:
    def __init__(self, artifact_root: str | Path) -> None:
        self.artifact_root = Path(artifact_root)

    def prepare_session_dir(self, session_id: str) -> Path:
        artifact_dir = self.artifact_root / session_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "downloads").mkdir(parents=True, exist_ok=True)
        return artifact_dir

    async def capture_screenshot(
        self, session: Any, label: str, *, full_page: bool = False, selector: str | None = None
    ) -> dict[str, str]:
        safe_label = self._safe_label(label)
        filename = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')}Z-{safe_label}.png"
        path = session.artifact_dir / filename
        if not (selector or full_page):
            await session.page.screenshot(path=str(path), full_page=False)
        else:
            try:
                # Playwright's own timeout is not always honoured when Chromium stalls
                # rendering beyond the viewport, so bound the whole call.
                await asyncio.wait_for(self._capture_region(session.page, path, full_page, selector), 25)
            except Exception as exc:
                if "Timeout" not in type(exc).__name__:
                    raise
                if selector:
                    raise RuntimeError(
                        f"screenshot of selector {selector!r} timed out: not found, hidden, or too heavy to "
                        "render beyond the viewport (try a smaller selector or scroll it into view)"
                    ) from exc
                raise RuntimeError(
                    "full_page screenshot timed out (the page is probably too tall); "
                    "use selector, or a viewport screenshot after scrolling"
                ) from exc
        return {"path": str(path), "url": f"/artifacts/{session.id}/{filename}"}

    @staticmethod
    async def _capture_region(page: Any, path: Path, full_page: bool, selector: str | None) -> None:
        if not selector:
            await page.screenshot(path=str(path), full_page=full_page, timeout=15_000)
            return
        # Clip capture instead of Locator.screenshot(): the locator path scrolls and waits for
        # stability and hung on tall elements (a table, an infobox) in headless Chromium.
        box = await page.locator(selector).first.bounding_box(timeout=10_000)
        if not box or box["width"] < 1 or box["height"] < 1:
            raise RuntimeError(f"screenshot of selector {selector!r}: element has no visible area")
        scroll_x, scroll_y, view_w, view_h = await page.evaluate(
            "() => [window.scrollX, window.scrollY, window.innerWidth, window.innerHeight]"
        )
        height = min(box["height"], 16000.0)
        inside = box["x"] >= 0 and box["y"] >= 0 and box["x"] + box["width"] <= view_w and box["y"] + height <= view_h
        if inside:
            # Fully inside the viewport: a plain clip. The beyond-viewport path stalls on some
            # heavy pages, so only use it when it is needed.
            clip = {"x": box["x"], "y": box["y"], "width": box["width"], "height": height}
            await page.screenshot(path=str(path), clip=clip, timeout=15_000)
            return
        clip = {
            "x": max(0.0, box["x"] + scroll_x),
            "y": max(0.0, box["y"] + scroll_y),
            "width": box["width"],
            "height": height,
        }
        await page.screenshot(path=str(path), clip=clip, full_page=True, timeout=15_000)

    @staticmethod
    def trace_payload(session: Any) -> dict[str, Any]:
        return {
            "trace_path": str(session.trace_path),
            "trace_url": f"/artifacts/{session.id}/{session.trace_path.name}",
            "trace_exists": session.trace_path.exists(),
            "trace_recording": session.trace_recording,
        }

    async def append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False)
        await asyncio.to_thread(self.append_text, path, line + "\n")

    @staticmethod
    def append_text(path: Path, text: str) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text)

    @staticmethod
    def _safe_label(label: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", label).strip(".-")
        return safe[:120] or "screenshot"
