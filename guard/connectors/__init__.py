"""S.H.O.A.V. connectors package (adapter layer).

Adapters are dict in, dict out, no controller imports, no network.
See shoav-mcp/MCP/plan.md sections 4-5 and shoav-mcp/filters/README.md.
"""

from .egress_args import (
    FORM_STATE_SCRIPT,
    decision_to_egress_args,
    normalize_form_controls,
    run_form_state_probe,
)
from .observe_adapter import normalize_observe
from .rewrite import apply_rewrite, build_block, findings_to_list, findings_to_summary, scrub_field, scrub_with_count
from .session_cache import InteractablesCache, SessionCache, should_reset_on_navigation
from .snapshot_adapter import (
    find_elements_to_payload,
    get_html_to_payload,
    snapshot_to_payload,
)

__all__ = [
    "FORM_STATE_SCRIPT",
    "InteractablesCache",
    "SessionCache",
    "apply_rewrite",
    "build_block",
    "decision_to_egress_args",
    "find_elements_to_payload",
    "findings_to_list",
    "findings_to_summary",
    "get_html_to_payload",
    "normalize_form_controls",
    "normalize_observe",
    "run_form_state_probe",
    "scrub_field",
    "scrub_with_count",
    "should_reset_on_navigation",
    "snapshot_to_payload",
]
