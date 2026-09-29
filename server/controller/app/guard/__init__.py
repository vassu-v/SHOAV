"""S.H.O.A.V. guard wiring for the Auto Browser controller (C-1).

Wiring only: config, loader, guard object, factory hookup. Behavior hooks
(C-3/C-4/C-5) live in tool_gateway/gateway.py and are owned by another agent.
"""

from .guard import ShoavGuard
from .session_cache import GuardSessionCache

__all__ = ["ShoavGuard", "GuardSessionCache"]
