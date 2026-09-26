"""T2 overlay block message regression: decoy details plus plain instruction.

Spec under test: the overlay block message must state which element
occluded the target (tag, opacity, z-index) and one plain instruction
("the click was aborted; call observe again, do not retry the same click,
or ask the user"); `error` key first; same text in content[0].text and
structuredContent.

Drives the gateway egress path (decide_click plus block response packer)
and the EgressFilter.verify_click engine with a synthetic hit-test payload
showing a transparent high-z decoy. No network or browser.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.tool_gateway import McpToolGateway

# Make shoav-mcp root importable so filters.egress.engine resolves
# without network or browser. Path insert only, no product change.
_SHOAV_ROOT = Path(__file__).resolve().parents[4]
if str(_SHOAV_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHOAV_ROOT))

REQUIRED_INSTRUCTION = (
    "the click was aborted; call observe again, "
    "do not retry the same click, or ask the user"
)


def _transparent_decoy_hit() -> dict:
    # Synthetic hit-test payload: transparent high-z decoy on top.
    return {
        "found": True,
        "inside_target": False,
        "tag": "DIV",
        "ref": "evil-overlay",
        "opacity": 0.0,
        "z_index": "999999",
        "pointer_events": "auto",
    }


def _gateway():
    manager = SimpleNamespace(
        settings=SimpleNamespace(mcp_tool_name_style="dotted")
    )
    return McpToolGateway(
        manager=manager,
        orchestrator=object(),
        job_queue=object(),
        guard=object(),
    )


class ShoavT2BlockMsgTests(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_block_states_occluder_and_instruction(self) -> None:
        gateway = _gateway()
        hit = _transparent_decoy_hit()
        verdict, reason = await gateway._shoav_decide_click(
            expected_ref=None, hit=hit, selector_only=True, coord_only=False
        )
        self.assertEqual(verdict, "BLOCK", "transparent high-z decoy must BLOCK")
        # Spec: message states which element occluded the target.
        self.assertIn("DIV", reason, "block message must state occluder tag")
        self.assertIn("0.0", str(reason), "block message must state occluder opacity")
        self.assertIn("999999", str(reason), "block message must state occluder z-index")
        # Spec: one plain instruction, exact text.
        self.assertIn(
            REQUIRED_INSTRUCTION,
            reason,
            "block message must carry the plain re-observe instruction",
        )

    def test_engine_verify_click_states_occluder_and_instruction(self) -> None:
        from filters.egress.engine import EgressFilter

        hit = _transparent_decoy_hit()
        outcome = EgressFilter().verify_click("op-s1", hit)
        verdict = str(outcome.get("verdict", ""))
        reason = str(outcome.get("reason", ""))
        self.assertIn("BLOCK", verdict, "transparent high-z decoy must BLOCK")
        self.assertIn("DIV", reason, "block message must state occluder tag")
        self.assertIn("0.0", reason, "block message must state occluder opacity")
        self.assertIn("999999", reason, "block message must state occluder z-index")
        self.assertIn(
            REQUIRED_INSTRUCTION,
            reason,
            "block message must carry the plain re-observe instruction",
        )

    async def test_gateway_block_response_error_first_and_same_text(self) -> None:
        gateway = _gateway()
        hit = _transparent_decoy_hit()
        verdict, reason = await gateway._shoav_decide_click(
            expected_ref=None, hit=hit, selector_only=True, coord_only=False
        )
        self.assertEqual(verdict, "BLOCK")
        full_reason = "%s %s" % (reason, REQUIRED_INSTRUCTION)
        response = gateway._shoav_block_response(
            full_reason,
            tool="browser.execute_action",
            stage="egress",
            verdict="BLOCK",
        )
        self.assertTrue(response.isError, "overlay block must be an error")
        # Spec: error key first in structuredContent.
        self.assertIsInstance(response.structuredContent, dict)
        keys = list(response.structuredContent.keys())
        self.assertGreater(len(keys), 0, "structuredContent must not be empty")
        self.assertEqual(keys[0], "error", "error key must be first")
        # Spec: error key first in content[0].text JSON as well.
        body_text = response.content[0].text
        parsed = json.loads(body_text)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(
            list(parsed.keys())[0], "error", "content JSON error key must be first"
        )
        # Spec: same text in content[0].text and structuredContent.
        self.assertEqual(
            parsed.get("error"),
            response.structuredContent.get("error"),
            "content and structuredContent must carry the same error text",
        )
        self.assertIn(
            response.structuredContent.get("error", ""),
            body_text,
            "content text must contain the structured error text",
        )
        # The packed message itself must still carry decoy details plus instruction.
        packed = str(response.structuredContent.get("error", ""))
        self.assertIn("DIV", packed)
        self.assertIn("999999", packed)
        self.assertIn(REQUIRED_INSTRUCTION, packed)


if __name__ == "__main__":
    unittest.main()
