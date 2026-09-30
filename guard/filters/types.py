"""Shared types for the filter core."""

from __future__ import annotations

from enum import Enum


class Verdict(str, Enum):
    ALLOW = "ALLOW"
    REWRITE = "REWRITE"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value
