"""Subscription-only Codex CLI runner; never handles bearer tokens directly."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from .events import FIELDS, SUPPORTED_CODEX_VERSIONS, ParsedEvents, UnsupportedEventSchema, parse_jsonl
from .processes import stop_owned_process
from .verifier import VerificationBoundaryError, sandbox_available

PERMISSION_PROFILE = "agent_cost_lab_restricted"
CONFLICTING_ENV = {"OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "OPENAI_ORG_ID", "OPENAI_PROJECT_ID"}


@dataclass(frozen=True)
class AgentRunResult:
    outcome: str
    elapsed_seconds: float
    parsed: ParsedEvents | None
    error_class: str | None


@dataclass(frozen=True)
class RunnerConfiguration:
    model: str
    reasoning: str
    timeout: int
    overrides: tuple[str, ...] = ()
    additional_read_paths: tuple[Path, ...] = ()
    additional_write_paths: tuple[Path, ...] = ()
    additional_read_files: tuple[Path, ...] = ()


class AgentRunner(Protocol):
    def run(self, task: str, workspace: Path, configuration: RunnerConfiguration) -> AgentRunResult: ...


def installed_version() -> str | None:
    if not shutil.which("codex"):
        return None
    try:
        result = subprocess.run(["codex", "--version"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    found = re.search(r"codex-cli\s+(\d+\.\d+\.\d+)", result.stdout)
    return found.group(1) if result.returncode == 0 and found else None


def auth_method() -> str:
    """Classify supported status output in memory; never return the raw text."""
    if CONFLICTING_ENV & set(os.environ):
        return "conflicting_environment"
    try:
        result = subprocess.run(["codex", "login", "status"], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    response = (result.stdout + result.stderr).lower()
    if result.returncode != 0:
        return "missing" if "not logged in" in response else "unknown"
    if "logged in using chatgpt" in response:
        return "subscription"
    if "api key" in response:
        return "api_key"
    return "unknown"


def _failure_class(stderr: str, returncode: int | None) -> str:
    """Keep only a diagnostic category; stderr may contain private content."""
    lower = stderr.lower()
    if "rate limit" in lower or "usage limit" in lower:
        return "rate_limit"
    if "certificate_verify_failed" in lower or "certificate verify failed" in lower:
        return "tls_verification"
    if "name or service not known" in lower or "nodename nor servname" in lower:
        return "dns"
    if "mcp" in lower and any(word in lower for word in ("failed", "timeout", "timed out")):
        return "mcp_startup"
    if "404" in lower and "not found" in lower:
        return "endpoint_not_found"
    if "stream disconnected" in lower or "error sending request" in lower:
        return "provider_transport"
    if any(term in lower for term in ("sandbox", "operation not permitted", "permission denied")):
        return "sandbox_denied"
    if any(term in lower for term in ("unrecognized option", "unexpected argument", "unknown argument")):
        return "cli_arguments"
    if any(term in lower for term in ("invalid configuration", "config.toml", "unknown config", "unknown field")):
        return "cli_configuration"
    if any(term in lower for term in ("model not found", "model is not available", "unsupported model")):
        return "model_unavailable"
    if any(term in lower for term in ("authentication", "not logged in", "login required", "unauthorized")):
        return "authentication"
    return "codex_exit_" + str(returncode) if returncode is not None else "codex_failure_unknown"


def _event_failure_class(stdout: str, returncode: int | None) -> str:
    """Classify known JSONL errors in memory; do not retain their messages."""
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict):
            continue
        message = event.get("message") if event.get("type") == "error" else None
        if event.get("type") == "turn.failed" and isinstance(event.get("error"), dict):
            message = event["error"].get("message")
        if isinstance(message, str):
            category = _failure_class(message, returncode)
            if not category.startswith("codex_exit_"):
                return category
    return "codex_exit_" + str(returncode)


def _permission_overrides(auth_dir: Path) -> tuple[str, ...]:
    """Local-command policy; the Codex client itself still uses saved auth."""
    auth_file = auth_dir / "auth.json"
    filesystem = (
        '{ ":root" = "deny", ":minimal" = "read", ":tmpdir" = "write", '
        '":workspace_roots" = { "." = "write", ".git" = "read", "**/*.env" = "deny" }, '
        + json.dumps(str(auth_file)) + ' = "deny" }'
    )
    return (
        "default_permissions=" + json.dumps(PERMISSION_PROFILE),
        "permissions." + PERMISSION_PROFILE + ".filesystem=" + filesystem,
        "permissions." + PERMISSION_PROFILE + ".network.enabled=false",
    )


def agent_tool_boundary_probe(workspace: Path, protected: Path, *, check_write: bool = False) -> None:
    """Exercise Codex's tool sandbox without starting a model task or reading secrets."""
    codex = shutil.which("codex")
    if not codex:
        raise VerificationBoundaryError("Codex CLI unavailable")
    auth_dir = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
    with tempfile.TemporaryDirectory(prefix="acl-tool-probe-") as td:
        environment = dict(os.environ)
        environment["CODEX_HOME"] = td
        for key in CONFLICTING_ENV:
            environment.pop(key, None)
        base = [str(codex), "sandbox", "-C", str(workspace), "-P", PERMISSION_PROFILE]
        for option in _permission_overrides(auth_dir):
            base.extend(["-c", option])
        def open_only(path: Path) -> int:
            result = subprocess.run(base + ["/bin/sh", "-c", 'exec 3< "$1"', "sh", str(path)], capture_output=True, timeout=10, cwd=workspace, env=environment)
            return result.returncode
        if open_only(workspace / "README.md") != 0:
            raise VerificationBoundaryError("Codex local-command profile cannot read the workspace")
        if open_only(protected) == 0:
            raise VerificationBoundaryError("Codex local-command profile can read the held-out verifier")
        if check_write:
            marker = workspace / ".acl-probe"
            try:
                result = subprocess.run(base + ["/bin/sh", "-c", 'printf x > "$1"', "sh", str(marker)], capture_output=True, timeout=10, cwd=workspace, env=environment)
                if result.returncode != 0 or not marker.is_file():
                    raise VerificationBoundaryError("Codex local-command profile cannot write the workspace")
            finally:
                marker.unlink(missing_ok=True)


def agent_boundary_probe(workspace: Path, protected: Path, *, additional_read_paths: tuple[Path, ...] = (), additional_write_paths: tuple[Path, ...] = (), additional_read_files: tuple[Path, ...] = (), tool_path: Path | None = None, mcp_profile: Path | None = None) -> None:
    """Validate native Codex tool restrictions, not a nested client sandbox.

    The supported client handles authentication on the host. Codex applies its
    own permission profile to model commands and filesystem operations. A
    second Seatbelt profile around that client prevents those sandboxes from
    starting on macOS and must not be mistaken for a usable agent boundary.
    """
    if not sandbox_available():
        raise VerificationBoundaryError("macOS sandbox-exec unavailable")
    path = shutil.which("codex")
    if not path:
        raise VerificationBoundaryError("Codex CLI unavailable")
    auth_dir = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
    command = [path, "exec", "--json", "-C", str(workspace), "--ephemeral", "--ignore-user-config", "--ignore-rules", "--strict-config", "--color", "never"]
    for option in _permission_overrides(auth_dir):
        command.extend(["-c", option])
    # Help validates flags without accepting a task or making a model request.
    result = subprocess.run(command + ["--help"], capture_output=True, timeout=10, cwd=workspace)
    if result.returncode != 0:
        raise VerificationBoundaryError("Codex exec option check failed")
    agent_tool_boundary_probe(workspace, protected)
    if tool_path is not None:
        if mcp_profile is None:
            raise VerificationBoundaryError("retrieval requires its own restricted profile")
        state = mcp_profile.parent.resolve()
        environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(state), "TMPDIR": str(state), "HEADROOM_CONFIG_DIR": str(state), "HEADROOM_WORKSPACE_DIR": str(state), "HEADROOM_MCP_READ": "off", "HF_HUB_OFFLINE": "1"}
        result = subprocess.run(["sandbox-exec", "-f", str(mcp_profile), str(tool_path), "--version"], capture_output=True, timeout=10, cwd=state, env=environment)
        if result.returncode != 0:
            raise VerificationBoundaryError("retrieval tool cannot execute in its restricted boundary")


class CodexCliRunner:
    def run(self, task: str, workspace: Path, configuration: RunnerConfiguration) -> AgentRunResult:
        version = installed_version()
        if version not in SUPPORTED_CODEX_VERSIONS:
            raise RuntimeError("unsupported Codex version; inspect events and permissions before use")
        if auth_method() != "subscription":
            raise RuntimeError("subscription authentication is required; API-key fallback is forbidden")
        if not workspace.is_dir() or not (workspace / ".git").is_dir():
            raise RuntimeError("Codex requires a prepared Git workspace")
        codex = Path(shutil.which("codex") or "").resolve()
        auth_dir = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
        with tempfile.TemporaryDirectory(prefix="acl-agent-") as td:
            scratch = Path(td).resolve()
            command = [
                str(codex), "exec", "--json", "-C", str(workspace),
                "-m", configuration.model, "-c", "model_reasoning_effort=" + json.dumps(configuration.reasoning),
                "-c", 'approval_policy="never"', "-c", 'forced_login_method="chatgpt"',
                "--ephemeral", "--ignore-user-config", "--ignore-rules",
                "--strict-config", "--color", "never", *sum((["-c", option] for option in configuration.overrides), []),
            ]
            # Keep runtime state and transient logs out of the user's setup.
            for option in (
                "sqlite_home=" + json.dumps(str(scratch / "state")),
                "log_dir=" + json.dumps(str(scratch / "logs")),
                "analytics.enabled=false",
                "features.plugins=false", "features.remote_plugin=false",
                "features.memories=false", "features.multi_agent=false",
                'web_search="disabled"', "allow_login_shell=false",
                'shell_environment_policy.inherit="none"',
            ):
                command.extend(["-c", option])
            for option in _permission_overrides(auth_dir):
                command.extend(["-c", option])
            command.append("-")
            env = dict(os.environ)
            for key in CONFLICTING_ENV:
                env.pop(key, None)
            env["TMPDIR"] = str(scratch)
            start = time.monotonic()
            process = subprocess.Popen(command, cwd=workspace, env=env, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                stdout, stderr = process.communicate(task, timeout=configuration.timeout)
                elapsed = time.monotonic() - start
            except subprocess.TimeoutExpired:
                stop_owned_process(process)
                stdout, stderr = process.communicate()
                elapsed = time.monotonic() - start
                outcome = "timeout"
            except KeyboardInterrupt:
                stop_owned_process(process)
                stdout, stderr = process.communicate()
                elapsed = time.monotonic() - start
                outcome = "cancelled"
            except BaseException:
                stop_owned_process(process)
                raise
            else:
                outcome = "completed" if process.returncode == 0 else "failed"
            finally:
                stop_owned_process(process)
            # Raw text can contain task/code/private output. Keep it in memory only.
            error_class = _failure_class(stderr, process.returncode) if outcome == "failed" else None
            if error_class and error_class.startswith("codex_exit_"):
                error_class = _event_failure_class(stdout, process.returncode)
            try:
                parsed = parse_jsonl(stdout.splitlines(keepends=True), codex_version=version)
            except UnsupportedEventSchema:
                parsed = None
                outcome = "unsupported_events"
                error_class = "schema"
            if parsed is not None and outcome in {"timeout", "cancelled"} and parsed.usage.status in {"complete", "ambiguous"}:
                usage = replace(parsed.usage, status="incomplete", **{field: replace(getattr(parsed.usage, field), completeness="incomplete") for field in FIELDS if getattr(parsed.usage, field).value is not None})
                parsed = replace(parsed, usage=usage)
            if parsed is not None and parsed.failed_turns and outcome == "completed":
                outcome = "failed_turn"
            if parsed is not None and parsed.model_rerouted:
                outcome = "model_rerouted"
                error_class = "model_rerouted"
            if outcome == "failed" and not stdout.strip():
                outcome = "startup_failed"
            elif outcome == "completed" and not stdout.strip():
                outcome = "unsupported_events"
                error_class = "missing_events"
            return AgentRunResult(outcome, elapsed, parsed, error_class)
