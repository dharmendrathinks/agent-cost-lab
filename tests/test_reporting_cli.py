import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_cost_lab.cli import main, synthetic_demo
from agent_cost_lab.reporting import render_markdown, write_report, read_records


class ReportingTests(unittest.TestCase):
    def test_separate_real_pilots_are_not_implicitly_matched_by_pair_number(self):
        records = synthetic_demo()
        for record in records:
            record["source_kind"] = "real"
            record["environment_observations"]["trial_role"] = "baseline_pilot"
            record["environment_observations"]["campaign_id"] = "same-placeholder"
        self.assertIn("No complete, valid, comparable paired measurements.", render_markdown(records))
        for record, campaign in zip(records, ("campaign-a", "campaign-b")):
            record["environment_observations"]["trial_role"] = "matched_comparison"
            record["environment_observations"]["campaign_id"] = campaign
        self.assertIn("No complete, valid, comparable paired measurements.", render_markdown(records))

    def test_unmatched_controls_and_duplicate_pairs_withhold_differences(self):
        for mutation in ("model", "fixture_hash", "control_hash", "duplicate"):
            records = synthetic_demo()
            if mutation == "control_hash":
                records[1]["environment_observations"]["control_hash"] = "different"
            elif mutation == "duplicate":
                records += synthetic_demo()
            else:
                records[1][mutation] = "different"
            document = render_markdown(records)
            self.assertIn("No complete, valid, comparable paired measurements.", document)
            self.assertIn("resource differences are withheld", document)

    def test_synthetic_report_is_labeled_and_separates_money(self):
        document = render_markdown(synthetic_demo())
        self.assertIn("SYNTHETIC DEMO DATA", document)
        self.assertIn("Input tokens", document)
        self.assertIn("Cached input", document)
        self.assertIn("End-to-end runtime", document)
        self.assertIn("Not calculated for subscription runs", document)

    def test_record_roundtrip_and_zero_success(self):
        records = synthetic_demo()
        for record in records:
            record["verification"]["passed"] = False
            record["verification"]["status"] = "failed"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)
            write_report(path, records)
            self.assertEqual(len(read_records(path / "runs.jsonl")), 2)
            self.assertIn("0/1 (0.0%)", (path / "report.md").read_text())

    def test_missing_usage_is_unknown_in_aggregate(self):
        record = synthetic_demo()[0]
        for field in ("input_tokens", "cached_input_tokens", "output_tokens"):
            record["usage"][field]["value"] = None
            record["usage"][field]["completeness"] = "missing"
        record["usage"]["status"] = "missing"
        document = render_markdown([record])
        self.assertIn("Input tokens: baseline unknown (0/1 measured", document)
        self.assertIn("optimized not run (0/0 measured", document)

    def test_report_command_emits_markdown_and_csv_without_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_report(root / "source", synthetic_demo())
            with patch("agent_cost_lab.cli.execute") as execute:
                result = main(["report", str(root / "source"), "--out", str(root / "export.md")])
                execute.assert_not_called()
            self.assertEqual(result, 0)
            self.assertIn("SYNTHETIC DEMO DATA", (root / "export.md").read_text())
            self.assertTrue((root / "export.csv").is_file())

    def test_dry_run_never_calls_execute(self):
        with patch("agent_cost_lab.cli.execute") as execute, patch("agent_cost_lab.cli.declared_blockers", return_value=["synthetic blocker"]), contextlib.redirect_stdout(io.StringIO()):
            result = main(["optimize", "--task", "tasks/fix-midnight.toml", "--dry-run"])
        self.assertEqual(result, 0)
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
