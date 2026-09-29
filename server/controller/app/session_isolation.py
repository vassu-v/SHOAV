from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MANAGED_LABEL = "auto-browser.managed"

_UNSUPPORTED_MESSAGE = (
    "docker_ephemeral session isolation is not supported in this native-mode build; "
    "use SESSION_ISOLATION_MODE=shared_browser_node (native headed Chromium)."
)


@dataclass
class IsolatedBrowserRuntime:
    session_id: str
    container_id: str
    container_name: str
    network_name: str
    browser_node_name: str
    profile_dir: Path
    downloads_dir: Path
    ws_endpoint_file: Path
    ws_endpoint: str
    takeover_url: str
    novnc_port: int | None
    vnc_port: int | None
    tunnel_local_host: str = "127.0.0.1"
    tunnel_local_port: int = 6080


@dataclass
class PendingBrowserProvision:
    session_id: str
    container: Any
    container_name: str
    network_name: str
    browser_node_name: str
    local_profile_dir: Path
    local_downloads_dir: Path
    ws_endpoint_file: Path


class DockerBrowserNodeProvisioner:
    """Native-mode stub: per-session Docker browser nodes are unsupported.

    Kept under its historic name so imports and the tool catalogue stay
    stable. All Docker-backed provisioning paths raise a clear error naming
    the supported native mode (``shared_browser_node``).
    """

    def __init__(self, settings, *, client: Any | None = None):
        self.settings = settings
        self._client = client
        self._host_data_root: Path | None = None
        self._network_name: str | None = None

    async def startup(self) -> None:
        if self.settings.session_isolation_mode == "docker_ephemeral":
            raise RuntimeError(_UNSUPPORTED_MESSAGE)
        return None

    def _reap_orphaned_containers(self) -> None:
        return None

    async def provision(self, session_id: str) -> IsolatedBrowserRuntime:
        raise RuntimeError(_UNSUPPORTED_MESSAGE)

    async def release(self, runtime: IsolatedBrowserRuntime) -> None:
        self._release_sync(runtime)

    def _provision_container_sync(self, session_id: str) -> PendingBrowserProvision:
        raise RuntimeError(_UNSUPPORTED_MESSAGE)

    def _release_sync(self, runtime: IsolatedBrowserRuntime) -> None:
        self._remove_runtime_dirs(runtime.session_id)

    def _remove_runtime_dirs(self, session_id: str) -> None:
        """Delete the per-session profile and downloads tree.

        Only the container was ever removed on release. Each isolated session
        leaves behind a full Chromium profile — tens to hundreds of megabytes —
        and nothing cleaned it: MaintenanceService sweeps only the artifact,
        upload and auth roots. On a long-lived host that is unbounded growth
        with no signal until the volume fills mid-session.
        """
        runtime_root = self._local_runtime_root(session_id)
        try:
            resolved = runtime_root.resolve()
            base = self._local_runtime_root("").resolve()
            # Never delete outside the managed runtime root, whatever a
            # malformed session id might resolve to.
            if base not in resolved.parents:
                logger.warning("Refusing to remove %s: outside the session runtime root", resolved)
                return
            shutil.rmtree(resolved, ignore_errors=True)
            logger.debug("Removed isolated session runtime dir %s", resolved)
        except Exception as exc:
            logger.warning("Could not remove runtime dir for session %s: %s", session_id, exc)

    def _ensure_context(self):
        raise RuntimeError(_UNSUPPORTED_MESSAGE)

    def _discover_host_data_root(self, client) -> Path:
        raise RuntimeError(_UNSUPPORTED_MESSAGE)

    def _discover_network_name(self, client) -> str:
        raise RuntimeError(_UNSUPPORTED_MESSAGE)

    def _get_controller_container(self, client):
        raise RuntimeError(_UNSUPPORTED_MESSAGE)

    async def _wait_for_ws_endpoint(self, container, endpoint_file: Path) -> str:
        raise RuntimeError(_UNSUPPORTED_MESSAGE)

    def _cleanup_pending_container(self, pending: PendingBrowserProvision) -> None:
        raise RuntimeError(_UNSUPPORTED_MESSAGE)

    @staticmethod
    def _container_logs(container) -> str:
        raise RuntimeError(_UNSUPPORTED_MESSAGE)

    @staticmethod
    def _extract_host_port(ports: dict[str, Any], key: str) -> int | None:
        raise RuntimeError(_UNSUPPORTED_MESSAGE)

    def _build_takeover_url(self, novnc_port: int | None) -> str:
        raise RuntimeError(_UNSUPPORTED_MESSAGE)

    def _local_runtime_root(self, session_id: str) -> Path:
        return Path(self.settings.artifact_root).resolve().parent / "browser-sessions" / session_id
