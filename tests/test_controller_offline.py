import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_cost_lab.codex import AgentRunResult
from agent_cost_lab.controller import execute
from agent_cost_lab.events import parse_jsonl
from agent_cost_lab.records import VerificationResult
from agent_cost_lab.reporting import read_records
from agent_cost_lab.tasks import load_task


ROOT = Path(__file__).resolve().parents[1]


class FakeRunner:
    def run(self, *_args, **_kwargs):
        parsed = parse_jsonl(['{"type":"turn.started"}\n', '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":1,"output_tokens":2}}\n'], codex_version="0.157.1")
        return AgentRunResult("completed", 0.01, parsed, None)


class StartupFailedRunner:
    def run(self, *_args, **_kwargs):
        parsed = parse_jsonl([], codex_version="0.157.1")
        return AgentRunResult("startup_failed", 0.01, parsed, "cli_configuration")


class FakeHeadroom:
    def __init__(self, *_args, **_kwargs):
        self.state = Path(_args[1])

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def prepare_mcp_profile(self, _mcp_state):
        return self.state / "mcp.sb"

    def codex_overrides(self, _mcp_state, _mcp_profile):
        return ("synthetic-testing-override",)

    def observations(self):
        return {"declared_settings": "synthetic test", "effective_settings": None, "proxy_total_requests": 1, "proxy_tokens_saved_estimate": 2}


class FailingHeadroom(FakeHeadroom):
    def __enter__(self):
        raise RuntimeError("synthetic startup failure")


class ControllerOfflineTests(unittest.TestCase):
    def test_startup_failure_stops_without_reporting_fixture_as_test_failure(self):
        task = load_task(ROOT / "tasks/fix-midnight.toml", ROOT)
        with tempfile.TemporaryDirectory() as td, \
             patch("agent_cost_lab.controller.declared_blockers", return_value=[]), \
             patch("agent_cost_lab.controller.boundary_probe"), \
             patch("agent_cost_lab.controller.agent_boundary_probe"), \
             patch("agent_cost_lab.controller.agent_tool_boundary_probe"), \
             patch("agent_cost_lab.controller.CodexCliRunner", StartupFailedRunner), \
             patch("agent_cost_lab.controller.verify") as verifier:
            with self.assertRaisesRegex(RuntimeError, "startup_failed/not_applicable; cli_configuration"):
                execute(task, ROOT, optimized=False, model="synthetic-model", reasoning="medium",
                        max_runs=1, timeout=1, verifier_timeout=1, max_total_seconds=30,
                        artifacts_root=Path(td))
            verifier.assert_not_called()
            campaign = next(Path(td).glob("campaign-*"))
            record = read_records(campaign / "runs.jsonl")[0]
            self.assertEqual(record["verification"]["status"], "not_run_agent_startup")
            self.assertEqual(record["usage"]["status"], "missing")

    def test_two_pairs_counterbalance_and_keep_candidates_separate(self):
        task = load_task(ROOT / "tasks/fix-midnight.toml", ROOT)
        with tempfile.TemporaryDirectory() as td, \
             patch("agent_cost_lab.controller.declared_blockers", return_value=[]), \
             patch("agent_cost_lab.controller.boundary_probe"), \
             patch("agent_cost_lab.controller.agent_boundary_probe"), \
             patch("agent_cost_lab.controller.agent_tool_boundary_probe"), \
             patch("agent_cost_lab.controller.CodexCliRunner", FakeRunner), \
             patch("agent_cost_lab.controller.ManagedHeadroom", FakeHeadroom), \
             patch("agent_cost_lab.controller.local_executable", return_value=Path("/usr/bin/true")), \
             patch("agent_cost_lab.controller.verify", return_value=VerificationResult(True, "passed", 6, 6)):
            campaign = execute(task, ROOT, optimized=True, model="synthetic-model", reasoning="medium",
                               max_runs=4, timeout=1, verifier_timeout=1, max_total_seconds=30,
                               artifacts_root=Path(td))
            records = read_records(campaign / "runs.jsonl")
            self.assertEqual([r["configuration"] for r in records], ["codex_baseline", "codex_headroom", "codex_headroom", "codex_baseline"])
            self.assertEqual(len({r["fixture_hash"] for r in records}), 1)
            self.assertEqual(len({r["fixture_commit"] for r in records}), 1)
            self.assertEqual(len({r["run_id"] for r in records}), 4)
            self.assertTrue((campaign / "report.md").is_file())
            self.assertTrue((campaign / "runs.csv").is_file())
            self.assertTrue((campaign / "pair-001/codex_baseline/timeledger/ledger.py").is_file())
            self.assertTrue((campaign / "pair-001/codex_headroom/timeledger/ledger.py").is_file())

    def test_integration_failure_keeps_partial_attempt_record(self):
        task = load_task(ROOT / "tasks/fix-midnight.toml", ROOT)
        with tempfile.TemporaryDirectory() as td, \
             patch("agent_cost_lab.controller.declared_blockers", return_value=[]), \
             patch("agent_cost_lab.controller.boundary_probe"), \
             patch("agent_cost_lab.controller.agent_boundary_probe"), \
             patch("agent_cost_lab.controller.agent_tool_boundary_probe"), \
             patch("agent_cost_lab.controller.CodexCliRunner", FakeRunner), \
             patch("agent_cost_lab.controller.ManagedHeadroom", FailingHeadroom), \
             patch("agent_cost_lab.controller.local_executable", return_value=Path("/usr/bin/true")), \
             patch("agent_cost_lab.controller.verify", return_value=VerificationResult(True, "passed", 6, 6)):
            with self.assertRaises(RuntimeError):
                execute(task, ROOT, optimized=True, model="synthetic-model", reasoning="medium",
                        max_runs=2, timeout=1, verifier_timeout=1, max_total_seconds=30,
                        artifacts_root=Path(td))
            campaign = next(Path(td).glob("campaign-*"))
            records = read_records(campaign / "runs.jsonl")
            self.assertEqual(len(records), 2)
            self.assertEqual(records[-1]["outcome"], "integration_failure")
            self.assertIsNone(records[-1]["usage"]["input_tokens"]["value"])
            self.assertEqual(records[-1]["verification"]["status"], "not_run")


if __name__ == "__main__":
    unittest.main()
