"""SHOAV user visible identity: MCP serverInfo, live banner, live UI strings.

Upstream attribution (LICENSE, CHANGELOG, credit lines, upstream docs) is
allowed to keep the "Auto Browser" name; runtime identity is not.
"""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path

from app.live.banner import build_banner

_SERVER = Path(__file__).resolve().parents[2]
_LIVE_UI = _SERVER / "live-ui"
_PATTERN = re.compile(r"auto[\s_-]?browser", re.IGNORECASE)
# Lines that may name the upstream project (credit lines only).
_ALLOWED_LINE = re.compile(r"based on auto browser|lvcidpsyche|reworked auto browser", re.IGNORECASE)


def _offending_lines(path: Path) -> list[str]:
    hits = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if _PATTERN.search(line) and not _ALLOWED_LINE.search(line):
            hits.append(f"{path.relative_to(_SERVER)}:{number}: {line.strip()}")
    return hits


class ShoavBrandingTests(unittest.TestCase):
    def test_initialize_server_info_name_is_shoav(self) -> None:
        # The production transport is built in app_factory; read its keyword
        # arguments without constructing services (which would touch data dirs).
        source = (_SERVER / "controller" / "app" / "app_factory.py").read_text(encoding="utf-8")
        calls = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "McpHttpTransport"
        ]
        self.assertEqual(len(calls), 1)
        kwargs = {kw.arg: kw.value for kw in calls[0].keywords}
        self.assertEqual(ast.literal_eval(kwargs["server_name"]), "shoav")
        self.assertNotRegex(ast.literal_eval(kwargs["server_title"]), _PATTERN)
        self.assertIn("server_version", kwargs)

    def test_live_banner_says_shoav(self) -> None:
        banner = build_banner("abc123", "http://127.0.0.1:3200/s/abc123")
        self.assertIn("SHOAV  live view", banner)
        self.assertNotRegex(banner, _PATTERN)

    def test_live_ui_source_has_no_auto_browser(self) -> None:
        roots = [_LIVE_UI / "app", _LIVE_UI / "components"]
        files = [
            p
            for root in roots
            if root.is_dir()
            for p in root.rglob("*")
            if p.is_file() and p.suffix in {".ts", ".tsx", ".js", ".jsx", ".css", ".json", ".html"}
        ]
        if not files:
            self.skipTest("live-ui sources not present")
        hits = [hit for p in files for hit in _offending_lines(p)]
        self.assertEqual(hits, [], "user visible 'Auto Browser' in live-ui:\n" + "\n".join(hits))

    def test_live_ui_layout_title_is_shoav(self) -> None:
        layout = _LIVE_UI / "app" / "layout.tsx"
        if not layout.is_file():
            self.skipTest("live-ui layout not present")
        self.assertIn("SHOAV", layout.read_text(encoding="utf-8"))

    def test_controller_banner_source_has_no_auto_browser(self) -> None:
        banner_src = _SERVER / "controller" / "app" / "live" / "banner.py"
        self.assertEqual(_offending_lines(banner_src), [])


if __name__ == "__main__":
    unittest.main()
