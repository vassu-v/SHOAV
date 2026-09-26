"""F-E spec tests: context flood BLOCK vs benign ALLOW (Target 4).

Spec sources: shoav-mcp/MCP/plan.md section 5 (ingress BLOCK on flood:
isError true, error key first, then shoav detail) and
shoav-mcp/DETERMINISTIC_TARGETS.md Target 4 plus filters/constants.py
thresholds (node trigger 150 with gross-flood floor at 4x, raw element
floor 500, raw text floor 16000 chars, mutation threshold 50/sec).

Covered here, from spec only:
- 720 filler interactables (fixtures/flood.html shape) BLOCKs.
- Raw element count past 500 BLOCKs even with few interactables.
- Raw text chars past the token budget floor BLOCKs.
- High mutation rate BLOCKs via mutation_rate and via mutation dict.
- Benign pages (few nodes, small text, low rate, unmeasured signals)
  stay ALLOW, which is the fail-open direction.

Synthetic data only. No network. stdlib unittest. Target 5 not touched.
"""

import unittest

from ..constants import (
    INGRESS_MUTATION_RATE_THRESHOLD,
    INGRESS_NODE_BUDGET_TRIGGER,
    INGRESS_RAW_ELEMENT_COUNT_THRESHOLD,
    INGRESS_RAW_TEXT_CHARS_THRESHOLD,
)
from ..ingress import rules
from ..ingress.engine import IngressFilter
from ..types import Verdict
from . import fixtures as fx


def _payload_with_fillers(count):
    payload = fx.clean_observation_payload()
    payload["interactables"] = fx.flooded_interactables(count)
    return payload


class TestFeNodeCountFlood(unittest.TestCase):
    def test_720_filler_nodes_block(self):
        res = IngressFilter().process(_payload_with_fillers(720))
        self.assertEqual(res["verdict"], Verdict.BLOCK)
        self.assertIsNone(res["payload"])

    def test_gross_floor_is_four_times_trigger(self):
        over = _payload_with_fillers(INGRESS_NODE_BUDGET_TRIGGER * 4 + 1)
        self.assertEqual(IngressFilter().process(over)["verdict"], Verdict.BLOCK)
        under = _payload_with_fillers(INGRESS_NODE_BUDGET_TRIGGER + 10)
        self.assertNotEqual(
            IngressFilter().process(under)["verdict"], Verdict.BLOCK)

    def test_benign_node_count_allows(self):
        res = IngressFilter().process(_payload_with_fillers(10))
        self.assertEqual(res["verdict"], Verdict.ALLOW)


class TestFeRawProbeFlood(unittest.TestCase):
    def test_raw_element_count_blocks(self):
        res = IngressFilter().process(
            fx.clean_observation_payload(),
            raw_element_count=INGRESS_RAW_ELEMENT_COUNT_THRESHOLD + 220)
        self.assertEqual(res["verdict"], Verdict.BLOCK)
        self.assertIsNone(res["payload"])

    def test_720_raw_count_blocks(self):
        res = IngressFilter().process(
            fx.clean_observation_payload(), raw_element_count=720)
        self.assertEqual(res["verdict"], Verdict.BLOCK)

    def test_raw_text_chars_block(self):
        res = IngressFilter().process(
            fx.clean_observation_payload(),
            raw_text_chars=INGRESS_RAW_TEXT_CHARS_THRESHOLD + 1000)
        self.assertEqual(res["verdict"], Verdict.BLOCK)

    def test_raw_signal_rule_single_trigger(self):
        flooded, reason = rules.evaluate_flood_signal(raw_element_count=720)
        self.assertTrue(flooded)
        self.assertIn("720", reason or "")
        flooded, _ = rules.evaluate_flood_signal(
            raw_text_chars=INGRESS_RAW_TEXT_CHARS_THRESHOLD + 1)
        self.assertTrue(flooded)
        calm, reason = rules.evaluate_flood_signal(
            raw_element_count=40, raw_text_chars=500,
            mutations_per_second=5.0)
        self.assertFalse(calm)
        self.assertIsNone(reason)

    def test_unmeasured_signals_skip_fail_open(self):
        flooded, reason = rules.evaluate_flood_signal()
        self.assertFalse(flooded)
        self.assertIsNone(reason)


class TestFeMutationRateFlood(unittest.TestCase):
    def test_high_mutation_rate_blocks(self):
        res = IngressFilter().process(
            fx.clean_observation_payload(),
            mutation_rate=INGRESS_MUTATION_RATE_THRESHOLD + 70.0)
        self.assertEqual(res["verdict"], Verdict.BLOCK)

    def test_mutation_dict_blocks(self):
        res = IngressFilter().process(
            fx.clean_observation_payload(),
            mutation={"count": 400, "seconds": 2.0, "rate": 200.0})
        self.assertEqual(res["verdict"], Verdict.BLOCK)

    def test_mutation_dict_count_over_seconds_blocks(self):
        res = IngressFilter().process(
            fx.clean_observation_payload(),
            mutation={"count": 300, "seconds": 2.0})
        self.assertEqual(res["verdict"], Verdict.BLOCK)

    def test_low_mutation_rate_allows(self):
        res = IngressFilter().process(
            fx.clean_observation_payload(), mutation_rate=5.0)
        self.assertEqual(res["verdict"], Verdict.ALLOW)

    def test_zero_second_mutation_window_allows(self):
        self.assertEqual(
            rules.evaluate_mutation_rate_verdict(100, 0.0), Verdict.ALLOW)


class TestFeBenignAllow(unittest.TestCase):
    def test_small_page_allows(self):
        res = IngressFilter().process(
            fx.clean_observation_payload(),
            raw_element_count=40, raw_text_chars=800,
            mutation_rate=2.0)
        self.assertEqual(res["verdict"], Verdict.ALLOW)

    def test_no_probe_signals_allows(self):
        res = IngressFilter().process(fx.clean_observation_payload())
        self.assertEqual(res["verdict"], Verdict.ALLOW)


if __name__ == "__main__":
    unittest.main()
