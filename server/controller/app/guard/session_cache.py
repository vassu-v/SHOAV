"""Per-session state cache for the S.H.O.A.V. guard (C-1 wiring).

Single session-cache home for Task 6c: touched refs, initial form
snapshot, cached interactables, and last origin plus path. The gateway
delegates its touched and interactables memory here instead of keeping
a local dict, so navigation resets and submit checks share one store.
Filter-core SessionStateStore stays untouched; this cache mirrors its
touched and snapshot semantics for controller-side use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GuardSessionEntry:
    session_id: str
    touched_refs: set[str] = field(default_factory=set)
    initial_form_snapshot: list[dict] | None = None
    last_cart_item_ids: set[str] = field(default_factory=set)
    # Task 6c merge: interactables cache plus navigation baseline live
    # here so the gateway has one session cache instead of a local dict.
    interactables: list[dict] = field(default_factory=list)
    last_origin_path: str | None = None

    def mark_touched(self, ref: str) -> None:
        self.touched_refs.add(ref)

    # Dict-compatible view for gateway code and legacy tests that use
    # state["touched"], state["interactables"], state["form_snapshot"],
    # and state["last_origin_path"]. Reads return live objects so
    # set.add and list assignment patterns keep working.
    _LEGACY_KEYS = ("touched", "interactables", "form_snapshot", "last_origin_path")

    def __getitem__(self, key: str) -> Any:
        if key == "touched":
            return self.touched_refs
        if key == "interactables":
            return self.interactables
        if key == "form_snapshot":
            return self.initial_form_snapshot
        if key == "last_origin_path":
            return self.last_origin_path
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        if key == "touched":
            self.touched_refs = set(value) if not isinstance(value, set) else value
        elif key == "interactables":
            self.interactables = list(value) if isinstance(value, list) else value
        elif key == "form_snapshot":
            self.initial_form_snapshot = value
        elif key == "last_origin_path":
            self.last_origin_path = value
        else:
            raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def __contains__(self, key: object) -> bool:
        return key in self._LEGACY_KEYS


class GuardSessionCache:
    """In-memory cache of GuardSessionEntry, keyed by session_id."""

    def __init__(self) -> None:
        self._sessions: dict[str, GuardSessionEntry] = {}

    def get_or_create(self, session_id: str) -> GuardSessionEntry:
        entry = self._sessions.get(session_id)
        if entry is None:
            entry = GuardSessionEntry(session_id=session_id)
            self._sessions[session_id] = entry
        return entry

    def mark_touched(self, session_id: str, ref: str) -> None:
        self.get_or_create(session_id).mark_touched(ref)

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def __len__(self) -> int:
        return len(self._sessions)


__all__ = ["GuardSessionCache", "GuardSessionEntry"]
