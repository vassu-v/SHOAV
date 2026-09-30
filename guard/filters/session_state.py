"""Per-session memory for filter checks that need a T0 vs. T1 diff.

Ingress Target 3 (pre-checked form state) and egress Target 5 (cart
sneaking) are not decidable from a single observation — they need "what was
true when the page/cart first loaded" to diff against "what's true now".
The two design sketches in PLAN_AND_ROUGH_SKETCH.md and context.md treat
ingress/egress as stateless request->response filters and never say where
that T0 snapshot lives. This is that missing piece: an in-memory cache keyed
by session_id, since Auto Browser already hands us a session_id on every
call. No persistence, no eviction policy — a short-lived session
cache, not a production store.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SessionState:
    # Form control snapshot captured the first time ingress sees the page
    # (list of dicts: {"ref": str, "checked": bool, "type": str, "label": str}).
    initial_form_snapshot: list[dict] | None = None

    # Cart item ids seen at last observation, and which add-to-cart refs the
    # agent has actually clicked (for Target 5 cart-sneaking diff).
    last_cart_item_ids: set[str] = field(default_factory=set)
    clicked_add_to_cart_refs: set[str] = field(default_factory=set)

    # Refs the agent has explicitly interacted with (click/toggle), so a
    # pre-checked field the agent itself unchecked isn't re-flagged.
    touched_refs: set[str] = field(default_factory=set)

    def mark_touched(self, ref: str) -> None:
        self.touched_refs.add(ref)

    def reset_for_navigation(self) -> None:
        """Drop navigation-scoped guard memory (F-D, F-J egress half).

        Touched refs and the initial form snapshot belong to one page
        lifetime: after a navigation the old refs are meaningless, so both
        are cleared. Cart memory is deliberately left alone here; cart
        diffing spans navigations and is out of scope (Target 5).
        """
        self.touched_refs.clear()
        self.initial_form_snapshot = None


class SessionStateStore:
    """A plain dict-backed cache, one SessionState per session_id."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get_or_create(self, session_id: str) -> SessionState:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState()
        return self._sessions[session_id]

    def mark_touched(self, session_id: str, ref: str) -> None:
        self.get_or_create(session_id).mark_touched(ref)

    def reset(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def __len__(self) -> int:
        return len(self._sessions)
