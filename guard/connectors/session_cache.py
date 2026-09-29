"""Per-session interactables cache with navigation-aware reset.

Pure stdlib. No controller imports. The guard stores each session's latest
observe interactables here so egress can resolve an element_id to a
selector plus bounding box and centre point.
"""

from __future__ import annotations

from urllib.parse import urlsplit


class InteractablesCache:
    """One cached interactables list per session_id."""

    def __init__(self) -> None:
        self._store: dict[str, list[dict]] = {}
        self._urls: dict[str, str] = {}

    def store(self, session_id: str, interactables: list[dict]) -> None:
        """Cache a defensive copy of the session's interactables."""
        self._store[session_id] = list(interactables or [])

    def get(self, session_id: str) -> list[dict]:
        """Return the cached list (empty when unknown). A copy is returned
        so callers cannot mutate the cache by accident."""
        return list(self._store.get(session_id, []))

    def reset(self, session_id: str) -> None:
        """Drop all cached state for a session (navigation, close)."""
        self._store.pop(session_id, None)
        self._urls.pop(session_id, None)

    def reset_if_navigated(
        self, session_id: str, prev_url: str | None, curr_url: str | None
    ) -> bool:
        """Reset when origin or path changed between observations.

        Returns True when a reset happened. Records curr_url either way so
        the next comparison has a baseline.
        """
        if should_reset_on_navigation(prev_url, curr_url):
            self.reset(session_id)
            if curr_url:
                self._urls[session_id] = curr_url
            return True
        if curr_url:
            self._urls[session_id] = curr_url
        return False

    def last_url(self, session_id: str) -> str | None:
        """Last recorded URL for a session, if any."""
        return self._urls.get(session_id)


SessionCache = InteractablesCache


def _origin_and_path(url: str | None) -> tuple[str, str] | None:
    if not url or not isinstance(url, str):
        return None
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if not parts.scheme or not parts.hostname:
        return None
    port = f":{parts.port}" if parts.port else ""
    origin = f"{parts.scheme.lower()}://{parts.hostname.lower()}{port}"
    return (origin, parts.path or "/")


def should_reset_on_navigation(
    prev_url: str | None, curr_url: str | None
) -> bool:
    """True when origin (scheme+host+port) or path differs.

    Query strings and fragments are ignored: a same-page filter change
    keeps the cache, a real navigation drops it. Unparseable or missing
    URLs never trigger a reset on their own unless one side is known and
    the other is not.
    """
    if not prev_url and not curr_url:
        return False
    if not prev_url or not curr_url:
        return True
    prev = _origin_and_path(prev_url)
    curr = _origin_and_path(curr_url)
    if prev is None or curr is None:
        return prev_url != curr_url
    return prev != curr
