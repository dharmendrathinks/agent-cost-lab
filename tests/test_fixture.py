import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_cost_lab.tasks import load_task
from agent_cost_lab.workspace import commit_hash, prepare_workspace, validate_candidate
from agent_cost_lab.verifier import VerificationBoundaryError, boundary_probe
from agent_cost_lab.verifier import fixture_execution_probe
from agent_cost_lab.verifier import _sandbox_run
from agent_cost_lab.records import VerificationResult


ROOT = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FixtureTests(unittest.TestCase):
    def test_verifier_canonicalizes_paths_before_restricted_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            candidate = root / "candidate"
            candidate.mkdir()
            scratch = root / "scratch"
            scratch.mkdir()
            alias = root / "alias"
            alias.symlink_to(candidate, target_is_directory=True)
            profile = scratch / "candidate.sb"
            profile.write_text("synthetic profile")
            with patch("agent_cost_lab.verifier.sandbox_available", return_value=True), \
                 patch("agent_cost_lab.verifier.subprocess.Popen") as popen, \
                 patch("agent_cost_lab.verifier.stop_owned_process"):
                popen.return_value.communicate.return_value = ("sandbox-ok", "")
                popen.return_value.returncode = 0
                result = _sandbox_run(alias, profile, "print('sandbox-ok')", {}, 1, scratch)
            args, kwargs = popen.call_args
            self.assertEqual(args[0][-1], str(candidate.resolve()))
            self.assertEqual(kwargs["cwd"], candidate.resolve())
            self.assertEqual(kwargs["env"]["TMPDIR"], str(scratch.resolve()))
            self.assertEqual(result.returncode, 0)

    def test_doctor_rejects_a_broken_restricted_verifier(self):
        task = load_task(ROOT / "tasks/fix-midnight.toml", ROOT)
        starting = VerificationResult(False, "failed", 6, 1, ("cross_midnight",))
        with patch("agent_cost_lab.verifier.verify", side_effect=[starting, VerificationResult(False, "failed", 6, 0)]):
            with self.assertRaisesRegex(VerificationBoundaryError, "trusted reference"):
                fixture_execution_probe(task)
        with patch("agent_cost_lab.verifier.verify", return_value=VerificationResult(True, "passed", 6, 6)):
            with self.assertRaisesRegex(VerificationBoundaryError, "starting fixture"):
                fixture_execution_probe(task)

    def test_starting_fixture_fails_each_target_and_reference_passes(self):
        buggy = load(ROOT / "fixtures/timeledger/timeledger/ledger.py", "buggy").summarize
        reference = load(ROOT / "verification/reference_ledger.py", "reference").summarize
        for manifest in ROOT.glob("tasks/*.toml"):
            task = load_task(manifest, ROOT)
            cases = load(task.verifier, "cases_" + task.id.replace("-", "_")).CASES
            misses = 0
            for _, payload, expected in cases:
                def invoke(fn):
                    try:
                        if isinstance(payload, dict):
                            return fn(payload["rows"], group_by=payload.get("group_by", "project"))
                        return fn(payload)
                    except ValueError as exc:
                        return {"error": "ValueError", "message": str(exc)}
                    except (TypeError, KeyError):
                        return None
                actual = invoke(reference)
                if isinstance(expected, dict):
                    self.assertEqual(actual.get("error"), expected["error"])
                    self.assertIn(expected["contains"], actual["message"])
                else:
                    self.assertEqual(actual, expected)
                baseline = invoke(buggy)
                if isinstance(expected, dict):
                    misses += not (isinstance(baseline, dict) and baseline.get("error") == expected["error"] and expected["contains"] in baseline.get("message", ""))
                else:
                    misses += baseline != expected
            self.assertGreater(misses, 0, task.id)

    def test_candidate_cannot_change_trusted_fixture_material(self):
        task = load_task(ROOT / "tasks/fix-midnight.toml", ROOT)
        with tempfile.TemporaryDirectory() as td:
            candidate = Path(td) / "candidate"
            prepare_workspace(task, candidate, git=False)
            validate_candidate(task, candidate)
            (candidate / "tests/test_public.py").write_text("assert True")
            with self.assertRaises(ValueError):
                validate_candidate(task, candidate)

    def test_workspace_resets_are_independent(self):
        task = load_task(ROOT / "tasks/fix-midnight.toml", ROOT)
        with tempfile.TemporaryDirectory() as td:
            first, second = Path(td) / "first", Path(td) / "second"
            self.assertEqual(prepare_workspace(task, first, git=False), prepare_workspace(task, second, git=False))
            (first / task.allowed_source).write_text("# candidate edit\n")
            self.assertNotEqual((first / task.allowed_source).read_bytes(), (second / task.allowed_source).read_bytes())
            validate_candidate(task, second)

    def test_fixture_git_snapshot_is_reproducible(self):
        task = load_task(ROOT / "tasks/fix-midnight.toml", ROOT)
        with tempfile.TemporaryDirectory() as td:
            first, second = Path(td) / "first", Path(td) / "second"
            self.assertEqual(prepare_workspace(task, first, git=True), prepare_workspace(task, second, git=True))
            self.assertEqual(commit_hash(first), commit_hash(second))

    def test_verifier_boundary_fails_closed(self):
        task = load_task(ROOT / "tasks/fix-midnight.toml", ROOT)
        with tempfile.TemporaryDirectory() as td, patch("agent_cost_lab.verifier.sandbox_available", return_value=False):
            with self.assertRaises(VerificationBoundaryError):
                boundary_probe(Path(td), task.verifier)


if __name__ == "__main__":
    unittest.main()
