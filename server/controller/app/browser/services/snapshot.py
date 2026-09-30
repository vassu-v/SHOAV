from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..snapshot_script import SNAPSHOT_SCRIPT

if TYPE_CHECKING:
    from ...browser_manager import BrowserSession

HARD_MAX_CHARS = 30000


def paginate(lines: list[str], *, offset: int, max_chars: int) -> tuple[str, int, int, bool]:
    """Cut `lines` (joined with newlines) at a line boundary.

    Returns (body, start, end, truncated) where start and end are character offsets into the
    full body. `offset` is rounded down to the start of the line that contains it, so no
    text is skipped when a caller passes an arbitrary number.
    """
    max_chars = min(max_chars, HARD_MAX_CHARS)
    starts: list[int] = []
    pos = 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1
    total = max(0, pos - 1)
    first = 0
    for index, start in enumerate(starts):
        if start <= offset:
            first = index
        else:
            break
    chosen: list[str] = []
    used = 0
    for line in lines[first:]:
        cost = len(line) + (1 if chosen else 0)
        if chosen and used + cost > max_chars:
            break
        if not chosen and len(line) > max_chars:
            line = line[: max_chars - 1] + "…"
            cost = len(line)
        chosen.append(line)
        used += cost
    start_char = starts[first] if starts else 0
    end_char = start_char + used
    truncated = first + len(chosen) < len(lines)
    if not truncated:
        end_char = total
    return "\n".join(chosen), start_char, end_char, truncated


def build_snapshot_text(
    raw: dict[str, Any], *, offset: int, max_chars: int, depth: int, include: str
) -> tuple[str, dict[str, Any]]:
    """Render header + body for one in-page result. Returns (text, metadata)."""
    lines: list[str] = raw["lines"]
    stats = raw["stats"]
    body, start, end, truncated = paginate(lines, offset=offset, max_chars=max_chars)
    total = max(0, sum(len(line) + 1 for line in lines) - 1)
    skipped = f"hidden_skipped={stats['hidden']}"
    if stats.get("outside_viewport"):
        skipped += f" outside_viewport={stats['outside_viewport']}"
    counts = f"nodes={stats['nodes']} interactive={stats['interactive']} tables={stats['tables']} {skipped}"
    if stats.get("deeper_omitted"):
        counts += f" deeper_omitted={stats['deeper_omitted']}"
    returned = len(body)
    header = (
        f"snapshot {raw.get('url', '')} | {raw.get('title', '')!r}\n"
        f"{counts} | chars={returned} of {total} (from {start}) | truncated={'true' if truncated else 'false'}"
        f" | include={include} depth={depth}\n"
        "refs (op-...) work as element_id in browser.execute_action; inline form is [text|ref]"
    )
    text = header + "\n" + body if body else header + "\n(empty: nothing visible in scope)"
    if stats.get("tables", 0) > 0 and total < 60:
        text += '\n(hint: tables present but almost no text; retry scoped with selector e.g. "table.infobox" or include="all")'
    meta = {
        "url": raw.get("url"),
        "title": raw.get("title"),
        "nodes": stats["nodes"],
        "interactive": stats["interactive"],
        "tables": stats["tables"],
        "hidden_skipped": stats["hidden"],
        "outside_viewport": stats.get("outside_viewport", 0),
        "chars_returned": returned,
        "chars_total": total,
        "offset": start,
        "truncated": truncated,
    }
    if truncated:
        meta["next_offset"] = end + 1
        text += (
            f"\n... truncated: {total - end - 1} more chars. Continue with offset={end + 1}, "
            'or narrow with selector (for example "main"), or lower depth.'
        )
    return text, meta


class BrowserSnapshotService:
    """browser.snapshot: compact, ref-tagged text tree of the page or a scoped part of it."""

    def __init__(self, manager: Any) -> None:
        self.manager = manager

    async def snapshot(
        self,
        session_id: str | None,
        *,
        selector: str | None = None,
        depth: int = 8,
        max_chars: int = 8000,
        offset: int = 0,
        viewport_only: bool = False,
        include: str = "interactive",
    ) -> dict[str, Any]:
        session = await self.manager.get_session(session_id)
        async with session.lock:
            return await self.snapshot_session(
                session,
                selector=selector,
                depth=depth,
                max_chars=max_chars,
                offset=offset,
                viewport_only=viewport_only,
                include=include,
            )

    async def snapshot_session(
        self,
        session: "BrowserSession",
        *,
        selector: str | None,
        depth: int,
        max_chars: int,
        offset: int,
        viewport_only: bool,
        include: str,
    ) -> dict[str, Any]:
        raw = await session.page.evaluate(
            SNAPSHOT_SCRIPT,
            {"selector": selector, "depth": depth, "viewportOnly": viewport_only, "include": include},
        )
        if raw.get("error"):
            raise ValueError(f"browser.snapshot: {raw['error']}")
        text, meta = build_snapshot_text(raw, offset=offset, max_chars=max_chars, depth=depth, include=include)
        return {"session_id": session.id, **meta, "_mcp_text": text}
