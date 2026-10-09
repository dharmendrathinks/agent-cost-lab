import json
import unittest
from pathlib import Path

from agent_cost_lab.events import SUPPORTED_CODEX_VERSIONS, UnsupportedEventSchema, parse_jsonl


VERSION = "0.157.1"
FIXTURE = Path(__file__).parent / "event_fixtures" / "cumulative.jsonl"


def event_line(value):
    return json.dumps(value) + "\n"


class EventAccountingTests(unittest.TestCase):
    def test_missing_later_subset_is_not_a_zero_or_a_decrease(self):
        first = event_line({"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 30, "output_tokens": 10}})
        final = event_line({"type": "turn.completed", "usage": {"input_tokens": 150, "output_tokens": 20}})
        usage = parse_jsonl([first, final], codex_version="0.160.0").usage
        self.assertEqual(usage.status, "incomplete")
        self.assertIsNone(usage.cached_input_tokens.value)
        self.assertEqual(usage.input_tokens.value, 150)
        self.assertEqual(len(usage.observed_snapshots), 2)

    def test_decreasing_cumulative_usage_retains_observations(self):
        lines = [event_line({"type": "turn.completed", "usage": {"input_tokens": value, "cached_input_tokens": 0, "output_tokens": 10}}) for value in (100, 90)]
        usage = parse_jsonl(lines, codex_version="0.160.0").usage
        self.assertEqual(usage.status, "invalid")
        self.assertIsNone(usage.input_tokens.value)
        self.assertEqual([s["input_tokens"] for s in usage.observed_snapshots], [100, 90])

    def test_unknown_item_schema_and_observed_model_rerouting(self):
        with self.assertRaises(UnsupportedEventSchema):
            parse_jsonl([event_line({"type": "item.completed", "item": {"type": "future_tool"}})], codex_version="0.160.0")
        reroute = {"type": "item.completed", "item": {"id": "synthetic-error", "type": "error", "message": "model rerouted: synthetic-a -> synthetic-b (test)"}}
        self.assertTrue(parse_jsonl([event_line(reroute)], codex_version="0.160.0").model_rerouted)

    def test_duplicate_completed_tool_is_counted_once(self):
        line = event_line({"type": "item.completed", "item": {"id": "synthetic-command", "type": "command_execution"}})
        self.assertEqual(parse_jsonl([line, line], codex_version="0.160.0").tool_events, 1)

    def test_reviewed_versions_share_the_cumulative_contract(self):
        for version in SUPPORTED_CODEX_VERSIONS:
            with self.subTest(version=version):
                parsed = parse_jsonl(FIXTURE.read_text().splitlines(keepends=True), codex_version=version)
                self.assertEqual(parsed.usage.input_tokens.value, 150)
                self.assertEqual(parsed.usage.reasoning_output_tokens.value, 9)

    def test_last_cumulative_snapshot_and_subsets(self):
        parsed = parse_jsonl(FIXTURE.read_text().splitlines(keepends=True), codex_version=VERSION)
        self.assertEqual(parsed.usage.input_tokens.value, 150)
        self.assertEqual(parsed.usage.cached_input_tokens.value, 30)
        self.assertEqual(parsed.usage.output_tokens.value, 40)
        self.assertEqual(parsed.usage.reasoning_output_tokens.value, 9)
        self.assertEqual(parsed.tool_events, 1)

    def test_duplicate_terminal_does_not_add_usage(self):
        lines = FIXTURE.read_text().splitlines(keepends=True)
        parsed = parse_jsonl(lines + [lines[-1]], codex_version=VERSION)
        self.assertEqual(parsed.usage.input_tokens.value, 150)
        self.assertEqual(parsed.usage.duplicate_events, 1)

    def test_missing_and_zero_have_distinct_states(self):
        missing = parse_jsonl([event_line({"type": "turn.failed"})], codex_version=VERSION)
        self.assertIsNone(missing.usage.input_tokens.value)
        self.assertEqual(missing.usage.status, "missing")
        omitted = parse_jsonl([event_line({"type": "turn.completed"})], codex_version=VERSION)
        self.assertEqual(omitted.usage.status, "missing")
        zero = parse_jsonl([event_line({"type": "turn.completed", "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}})], codex_version=VERSION)
        self.assertEqual(zero.usage.status, "ambiguous")
        self.assertEqual(zero.usage.input_tokens.value, 0)
        partial_categories = parse_jsonl([event_line({"type": "turn.completed", "usage": {"input_tokens": 7, "output_tokens": 2}})], codex_version=VERSION)
        self.assertEqual(partial_categories.usage.input_tokens.value, 7)
        self.assertIsNone(partial_categories.usage.cached_input_tokens.value)
        self.assertEqual(partial_categories.usage.status, "incomplete")

    def test_decrease_and_conflict_invalidate(self):
        lines = FIXTURE.read_text().splitlines(keepends=True)
        smaller = event_line({"type": "turn.completed", "usage": {"input_tokens": 149, "cached_input_tokens": 30, "output_tokens": 40}})
        parsed = parse_jsonl(lines + [smaller], codex_version=VERSION)
        self.assertEqual(parsed.usage.status, "invalid")
        self.assertIsNone(parsed.usage.input_tokens.value)

    def test_partial_tail_is_incomplete(self):
        parsed = parse_jsonl(FIXTURE.read_text().splitlines(keepends=True) + ['{"type":"turn'], codex_version=VERSION)
        self.assertEqual(parsed.usage.status, "incomplete")
        self.assertTrue(parsed.partial_tail)

    def test_started_turn_without_terminal_is_incomplete(self):
        lines = FIXTURE.read_text().splitlines(keepends=True) + [event_line({"type": "turn.started"})]
        parsed = parse_jsonl(lines, codex_version=VERSION)
        self.assertEqual(parsed.usage.status, "incomplete")

    def test_malformed_middle_event_fails_explicitly(self):
        with self.assertRaises(UnsupportedEventSchema):
            parse_jsonl(['not json\n', event_line({"type": "turn.started"})], codex_version=VERSION)

    def test_unknown_version_or_shape_fails(self):
        with self.assertRaises(UnsupportedEventSchema):
            parse_jsonl([], codex_version="0.158.0")
        with self.assertRaises(UnsupportedEventSchema):
            parse_jsonl([event_line({"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1, "cached_input_tokens": 0, "new_total": 5}})], codex_version=VERSION)
        with self.assertRaises(UnsupportedEventSchema):
            parse_jsonl([event_line({"type": "future.event"})], codex_version=VERSION)


if __name__ == "__main__":
    unittest.main()
