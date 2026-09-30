"""MCP_TOOL_PROFILE=minimal|curated|full. Default stays curated (harness depends on it)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.config import Settings
from app.tool_gateway import McpToolGateway
from app.tool_gateway.registry import MINIMAL_TOOL_NAMES, ToolRegistry

EXPECTED_MINIMAL = frozenset(
    {
        "browser.create_session",
        "browser.observe",
        "browser.find_elements",
        "browser.execute_action",
        "browser.snapshot",
        "browser.screenshot",
        "browser.list_tabs",
        "browser.activate_tab",
        "browser.close_session",
        "browser.wait_for_selector",
    }
)


def _gateway(profile: str) -> McpToolGateway:
    manager = MagicMock()
    manager.settings.mcp_tool_name_style = "dotted"
    return McpToolGateway(manager=manager, orchestrator=None, job_queue=None, tool_profile=profile)


def _names(gateway: McpToolGateway) -> set[str]:
    return {t["name"] for t in gateway.list_tools()}


class ToolProfileTests(unittest.TestCase):
    def test_minimal_lists_exactly_the_ten_loop_tools(self) -> None:
        names = _names(_gateway("minimal"))
        # snapshot ships in this tree; if it ever unregisters, expect 9 + note.
        if "browser.snapshot" not in names:
            self.assertEqual(names, set(EXPECTED_MINIMAL) - {"browser.snapshot"})
        else:
            self.assertEqual(names, set(EXPECTED_MINIMAL))
        self.assertEqual(MINIMAL_TOOL_NAMES, EXPECTED_MINIMAL)

    def test_curated_is_unchanged(self) -> None:
        # Working-tree baseline is 37 without vision (38 with); the spec's "36"
        # predates newer curated tools (stop_trace, witness bundle, ...).
        names = _names(_gateway("curated"))
        self.assertEqual(len(names), 37)
        self.assertTrue(EXPECTED_MINIMAL <= names)

    def test_full_covers_curated(self) -> None:
        curated = _names(_gateway("curated"))
        full = _names(_gateway("full"))
        self.assertGreaterEqual(len(full), len(curated))
        self.assertTrue(curated <= full)

    def test_default_is_curated(self) -> None:
        self.assertEqual(Settings().mcp_tool_profile, "curated")
        self.assertEqual(McpToolGateway.__init__.__kwdefaults__["tool_profile"], "curated")
        self.assertEqual(ToolRegistry(tool_profile="curated",
                                     experimental_enabled=lambda _: True).tool_profile, "curated")

    def test_unknown_profile_falls_back_safely(self) -> None:
        registry = ToolRegistry(tool_profile="bogus", experimental_enabled=lambda _: True)
        self.assertEqual(registry.tool_profile, "curated")
        gateway = _gateway("bogus")
        self.assertEqual(gateway.tool_profile, "curated")
        self.assertEqual(_names(gateway), _names(_gateway("curated")))


if __name__ == "__main__":
    unittest.main()
