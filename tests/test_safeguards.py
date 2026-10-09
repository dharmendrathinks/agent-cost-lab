import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_cost_lab.codex import CodexCliRunner, RunnerConfiguration, _failure_class, _event_failure_class, auth_method, stop_owned_process
from agent_cost_lab.controller import classify_treatment, declared_blockers
from agent_cost_lab.headroom import compatibility_blockers


class SafeguardTests(unittest.TestCase):
    def test_interrupted_runner_keeps_partial_usage_and_marks_it_incomplete(self):
        for interrupted, expected in ((subprocess.TimeoutExpired("synthetic", 1), "timeout"), (KeyboardInterrupt(), "cancelled")):
            class PartialProcess:
                returncode = -2
                calls = 0

                def communicate(self, _task=None, timeout=None):
                    self.calls += 1
                    if self.calls == 1:
                        raise interrupted
                    return '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":1,"output_tokens":2}}\n', ""

            with tempfile.TemporaryDirectory() as td:
                workspace = Path(td)
                (workspace / ".git").mkdir()
                with patch("agent_cost_lab.codex.installed_version", return_value="0.160.0"), \
                     patch("agent_cost_lab.codex.auth_method", return_value="subscription"), \
                     patch("agent_cost_lab.codex.stop_owned_process"), \
                     patch("agent_cost_lab.codex.subprocess.Popen", return_value=PartialProcess()):
                    result = CodexCliRunner().run("synthetic task", workspace, RunnerConfiguration("synthetic-model", "medium", 1))
            self.assertEqual(result.outcome, expected)
            self.assertEqual(result.parsed.usage.input_tokens.value, 10)
            self.assertEqual(result.parsed.usage.input_tokens.completeness, "incomplete")
            self.assertEqual(result.parsed.usage.status, "incomplete")

    def test_runner_classifies_empty_event_startup_failure_without_retaining_stderr(self):
        class FailedProcess:
            returncode = 2

            def communicate(self, _task=None, timeout=None):
                return "", "error: unknown field in private@example.invalid"

        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".git").mkdir()
            with patch("agent_cost_lab.codex.installed_version", return_value="0.157.1"), \
                 patch("agent_cost_lab.codex.auth_method", return_value="subscription"), \
                 patch("agent_cost_lab.codex.stop_owned_process"), \
                 patch("agent_cost_lab.codex.subprocess.Popen", return_value=FailedProcess()):
                result = CodexCliRunner().run("synthetic task", workspace, RunnerConfiguration("synthetic-model", "medium", 5))
        self.assertEqual(result.outcome, "startup_failed")
        self.assertEqual(result.error_class, "cli_configuration")
        self.assertNotIn("private@example.invalid", str(result))

    def test_trusted_client_uses_native_restrictions_and_owned_runtime_state(self):
        class EmptyProcess:
            returncode = 1

            def communicate(self, *_args, **_kwargs):
                return "", "synthetic failure"

        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            (workspace / ".git").mkdir()
            with patch("agent_cost_lab.codex.installed_version", return_value="0.160.0"), \
                 patch("agent_cost_lab.codex.auth_method", return_value="subscription"), \
                 patch("agent_cost_lab.codex.stop_owned_process"), \
                 patch("agent_cost_lab.codex.subprocess.Popen", return_value=EmptyProcess()) as launch:
                CodexCliRunner().run("synthetic", workspace, RunnerConfiguration("synthetic-model", "medium", 1))
        command = launch.call_args.args[0]
        self.assertEqual(command[1], "exec")
        self.assertNotIn("sandbox-exec", command)
        self.assertIn('--ignore-rules', command)
        settings = [command[index + 1] for index, item in enumerate(command[:-1]) if item == "-c"]
        self.assertIn('approval_policy="never"', settings)
        self.assertIn('permissions.agent_cost_lab_restricted.network.enabled=false', settings)
        self.assertTrue(any(item.startswith("sqlite_home=") for item in settings))
        self.assertTrue(any(item.startswith("permissions.agent_cost_lab_restricted.filesystem=") and '":root" = "deny"' in item for item in settings))
        self.assertFalse(any("bypass" in item or "danger-full-access" in item for item in command))

    def test_cli_failure_diagnostics_discard_private_text(self):
        self.assertEqual(_failure_class("unknown field near private@example.invalid", 2), "cli_configuration")
        self.assertEqual(_failure_class("some private output", 7), "codex_exit_7")
        self.assertEqual(_event_failure_class('{"type":"turn.failed","error":{"message":"stream disconnected from private@example.invalid"}}', 1), "provider_transport")
        self.assertEqual(_event_failure_class('{"type":"agent_message","message":"certificate verify failed"}', 1), "codex_exit_1")

    def test_subscription_classifier_never_returns_status_text(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "do-not-print-this"}), patch("agent_cost_lab.codex.subprocess.run") as run:
            self.assertEqual(auth_method(), "conflicting_environment")
            run.assert_not_called()
        with patch.dict(os.environ, {}, clear=True), patch("agent_cost_lab.codex.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "Logged in using API key: sk-secret", "")):
            self.assertEqual(auth_method(), "api_key")
        with patch.dict(os.environ, {}, clear=True), patch("agent_cost_lab.codex.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "Logged in using ChatGPT", "")):
            self.assertEqual(auth_method(), "subscription")

    def test_treatment_requires_proxy_evidence(self):
        self.assertEqual(classify_treatment({"proxy_total_requests": 0}), "unexpected_bypass")
        self.assertEqual(classify_treatment({"proxy_total_requests": 1, "proxy_tokens_saved_estimate": 0}), "unknown_or_no_eligible_content")
        self.assertEqual(classify_treatment({"proxy_total_requests": 1, "proxy_tokens_saved_estimate": 10}), "active_proxy_estimate")

    def test_headroom_absent_blocks_optimization(self):
        with tempfile.TemporaryDirectory() as td:
            blockers = compatibility_blockers(Path(td))
        self.assertIn("project-local Headroom is not installed", blockers)

    def test_owned_timeout_cleanup(self):
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        try:
            stop_owned_process(process)
            self.assertIsNotNone(process.poll())
        finally:
            if process.poll() is None:
                process.kill()

    def test_cleanup_reaches_descendants_after_the_leader_exits(self):
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / "child-stopped"
            child = (
                "import signal,time,sys; from pathlib import Path; "
                "signal.signal(signal.SIGINT, lambda *_: (Path(sys.argv[1]).write_text('stopped'), sys.exit(0))); "
                "print('ready',flush=True); time.sleep(30)"
            )
            leader = "import subprocess,sys; p=subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]],stdout=subprocess.PIPE,text=True); print(p.stdout.readline(),end='',flush=True)"
            process = subprocess.Popen([sys.executable, "-c", leader, child, str(marker)],
                                       stdout=subprocess.PIPE, text=True, start_new_session=True)
            try:
                self.assertEqual(process.stdout.readline().strip(), "ready")
                process.wait(timeout=5)
                stop_owned_process(process)
                deadline = time.monotonic() + 2
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(marker.exists())
            finally:
                stop_owned_process(process)
                process.stdout.close()


if __name__ == "__main__":
    unittest.main()
