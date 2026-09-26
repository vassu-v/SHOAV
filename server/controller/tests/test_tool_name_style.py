import re
import unittest

from pydantic import BaseModel

from app.tool_gateway.registry import ToolRegistry, ToolSpec

VALID_TOOL_NAME = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class _Empty(BaseModel):
    pass


async def _noop(_: BaseModel) -> dict:
    return {}


def _registry(style: str) -> ToolRegistry:
    registry = ToolRegistry(tool_profile="full", experimental_enabled=lambda _: True, name_style=style)
    for name in ("browser.observe", "browser.create_session", "harness.get_status"):
        registry.register(ToolSpec(name=name, description=name, input_model=_Empty, handler=_noop))
    return registry


class ToolNameStyleTests(unittest.TestCase):
    def test_dotted_is_the_default_advertised_style(self):
        names = {t["name"] for t in _registry("dotted").list_tools()}
        self.assertEqual(names, {"browser.observe", "browser.create_session", "harness.get_status"})

    def test_underscore_style_advertises_names_valid_for_gemini_clients(self):
        names = {t["name"] for t in _registry("underscore").list_tools()}
        self.assertEqual(names, {"browser_observe", "browser_create_session", "harness_get_status"})
        self.assertTrue(all(VALID_TOOL_NAME.match(n) for n in names))

    def test_both_spellings_resolve_in_either_style(self):
        for style in ("dotted", "underscore"):
            registry = _registry(style)
            for spelling in ("browser.observe", "browser_observe"):
                spec = registry.get(spelling)
                self.assertIsNotNone(spec, f"{style}: {spelling}")
                self.assertEqual(spec.name, "browser.observe")
            self.assertIsNone(registry.get("browser_missing"))

    def test_unregister_removes_the_alias(self):
        registry = _registry("underscore")
        registry.unregister("browser.observe")
        self.assertIsNone(registry.get("browser_observe"))
        self.assertIsNone(registry.get("browser.observe"))

    def test_unknown_style_falls_back_to_dotted(self):
        self.assertEqual(_registry("weird").name_style, "dotted")


if __name__ == "__main__":
    unittest.main()
