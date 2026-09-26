"""Option A sys.path bootstrap for the S.H.O.A.V. filter core.

Root resolution: SHOAV_FILTERS_PATH (Settings.shoav_filters_path) when set,
else parents[5] (shoav-mcp root) relative to this file. All import failures
degrade to (None, None) with a log line so the controller fails open.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def resolve_shoav_root(filters_path: str | None) -> Path:
    """Return the shoav-mcp repo root without touching sys.path."""
    if filters_path:
        candidate = Path(filters_path).expanduser().resolve()
        # Accept both the shoav-mcp root and the filters dir itself so a
        # SHOAV_FILTERS_PATH pointing at .../shoav-mcp/filters keeps working.
        if candidate.name == "filters" and (candidate / "ingress").is_dir():
            return candidate.parent.resolve()
        return candidate
    here = Path(__file__).resolve()
    # guard/loader.py -> parents[5] is the shoav-mcp root in the fresh copy
    # at shoav-mcp/MCP/auto-browser.
    return here.parents[5].resolve()


def _ensure_sys_path(root: Path) -> None:
    if not root.is_dir():
        return
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)


def load_filter_classes(settings: Any) -> tuple[Any | None, Any | None]:
    """Import IngressFilter/EgressFilter, fail open to (None, None) with a log.

    Also probes shoav-mcp/connectors (owned by another agent); a missing
    connectors package is tolerated and logged at info level.
    """
    filters_path = getattr(settings, "shoav_filters_path", None) or None
    explicit = filters_path is not None
    root = resolve_shoav_root(filters_path)
    if not root.is_dir():
        logger.warning("shoav root not found: %s (fail open)", root)
        return None, None
    if explicit and not (root / "filters").is_dir():
        logger.warning("shoav explicit root has no filters package: %s (fail open)", root)
        return None, None
    _ensure_sys_path(root)
    try:
        from filters.egress import EgressFilter
        from filters.ingress import IngressFilter
    except Exception as exc:
        logger.warning("shoav filter import failed from %s: %s (fail open)", root, exc)
        return None, None
    try:
        import importlib

        importlib.import_module("connectors")
    except Exception as exc:
        logger.info("shoav connectors not yet available: %s", exc)
    return IngressFilter, EgressFilter
