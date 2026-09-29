from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from ...utils import UTC

if TYPE_CHECKING:
    from ...browser_manager import BrowserSession

logger = logging.getLogger(__name__)


class BrowserRemoteAccessService:
    """Encapsulates remote access metadata and takeover URL resolution."""

    def __init__(self, manager: Any) -> None:
        self.manager = manager

    def get_info(self, session_id: str | None = None) -> dict[str, Any]:
        if session_id:
            session = self.manager.sessions.get(session_id)
            if session is not None:
                return self.session_info(session)
        return self.global_info()

    def global_info(self) -> dict[str, Any]:
        info_path = Path(self.manager.settings.remote_access_info_path)
        payload: dict[str, Any] = {
            "active": False,
            "status": "inactive",
            "stale": False,
            "source": "static",
            "configured_takeover_url": self.manager.settings.takeover_url,
            "takeover_url": self.manager.settings.takeover_url,
            "api_url": None,
            "api_auth_enabled": bool(self.manager.settings.api_bearer_token),
            "info_path": str(info_path),
            "exists": info_path.exists(),
            "last_updated": None,
            "age_seconds": None,
            "stale_after_seconds": float(self.manager.settings.remote_access_stale_after_seconds),
            "tunnel": None,
            "error": None,
        }
        if not info_path.exists():
            return payload
        try:
            tunnel = json.loads(info_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("failed to read remote access info %s: %s", info_path, exc)
            payload["status"] = "error"
            payload["source"] = "metadata_file"
            payload["error"] = "remote_access_metadata_unreadable"
            return payload

        last_updated = self.parse_timestamp(tunnel.get("updated_at"))
        if last_updated is None:
            try:
                last_updated = datetime.fromtimestamp(info_path.stat().st_mtime, tz=UTC)
            except OSError:
                last_updated = None
        age_seconds = None
        if last_updated is not None:
            age_seconds = max(0.0, (datetime.now(UTC) - last_updated).total_seconds())
        stale_after_seconds = float(
            tunnel.get("stale_after_seconds") or self.manager.settings.remote_access_stale_after_seconds
        )
        raw_status = str(tunnel.get("status") or "active")
        stale = bool(age_seconds is not None and age_seconds > stale_after_seconds)
        active = raw_status == "active" and not stale
        takeover_url = tunnel.get("public_takeover_url") if active else self.manager.settings.takeover_url
        api_url = tunnel.get("public_api_url") if active else None
        payload.update(
            {
                "active": active,
                "status": "stale" if stale else raw_status,
                "stale": stale,
                "source": "metadata_file",
                "takeover_url": takeover_url,
                "api_url": api_url,
                "last_updated": (last_updated.isoformat().replace("+00:00", "Z") if last_updated is not None else None),
                "age_seconds": age_seconds,
                "stale_after_seconds": stale_after_seconds,
                "tunnel": tunnel,
            }
        )
        return payload

    def session_info(self, session: "BrowserSession") -> dict[str, Any]:
        # Native mode has a single shared browser node, so per-session isolated
        # runtimes do not exist. Every session shares the global takeover surface.
        return self.global_info()

    def current_takeover_url(self, session: "BrowserSession | None" = None) -> str:
        remote_access = self.global_info()
        if remote_access.get("active") and remote_access.get("takeover_url"):
            return str(remote_access["takeover_url"])
        if session is not None:
            return session.takeover_url
        return self.manager.settings.takeover_url

    @staticmethod
    def parse_timestamp(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def takeover_url_is_local_only(value: str) -> bool:
        host = (urlparse(value).hostname or "").strip().lower()
        return host in {"", "127.0.0.1", "localhost", "::1", "0.0.0.0"}
