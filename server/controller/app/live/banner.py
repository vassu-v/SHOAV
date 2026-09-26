"""The live-view banner shown to the user when a session is created.

Fixed format (see live-ui/CONTRACT.md): 60 columns wide, Unicode box drawing, no ANSI.
A line whose text does not fit (a very long watch URL) is emitted without the right
border and overflows it, so the link stays on one unbroken line and copy-pastes
cleanly. Widening only that row would misalign the border and, worse, get the URL
wrapped or cut by narrow terminals; overflowing keeps the URL byte-exact.
"""

from __future__ import annotations

WIDTH = 60
_INNER = WIDTH - 2  # between the two vertical borders
_TEXT = _INNER - 2  # one space of padding on each side


def live_url(base_url: str, session_id: str) -> str:
    return f"{(base_url or '').strip().rstrip('/')}/s/{session_id}"


def _row(text: str) -> str:
    if len(text) <= _TEXT:
        return f"│ {text.ljust(_TEXT)} │"
    return f"│ {text}"


def build_banner(session_id: str, url: str) -> str:
    lines = [
        "┌" + "─" * _INNER + "┐",
        _row("AUTO BROWSER  live view"),
        _row(f"session  {session_id}"),
        _row(f"watch    {url}"),
        "└" + "─" * _INNER + "┘",
    ]
    return "\n".join(lines)


def colorize(banner: str) -> str:
    """ANSI cyan, for the controller's own console only (never sent to agents)."""
    return f"\x1b[36m{banner}\x1b[0m"
