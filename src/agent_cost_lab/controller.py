"""Bounded task execution and matched comparison controller."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .codex import CodexCliRunner, RunnerConfiguration, agent_boundary_probe, agent_tool_boundary_probe, auth_method, installed_version
from .events import SUPPORTED_CODEX_VERSIONS
from .headroom import DECLARED_SETTINGS, ManagedHeadroom, compatibility_blockers, local_executable
from .records import RunRecord, Usage, VerificationResult
from .reporting import write_report
from .tasks import Task, load_task
from .verifier import VerificationBoundaryError, boundary_probe, fixture_execution_probe, verify
from .workspace import commit_hash, file_hash, prepare_workspace, tree_hash


def declared_blockers(project_root: Path, *, optimized: bool, validation_probe: bool = False) -> list[str]:
    blockers = []
    version = installed_version()
    if version not in SUPPORTED_CODEX_VERSIONS:
        blockers.append("Codex event/permission adapter requires a reviewed version: " + ", ".join(sorted(SUPPORTED_CODEX_VERSIONS)))
    if auth_method() != "subscription":
        blockers.append("subscription authentication has not been positively established")
    probe_workspace = project_root / "fixtures/timeledger"
    probe_verifier = project_root / "verification/midnight_cases.py"
    try:
        boundary_probe(probe_workspace, probe_verifier)
        fixture_execution_probe(load_task(project_root / "tasks/fix-midnight.toml", project_root))
        agent_boundary_probe(probe_workspace, probe_verifier)
        agent_tool_boundary_probe(probe_workspace, probe_verifier)
    except (VerificationBoundaryError, OSError) as exc:
        blockers.append("restricted execution boundary not validated: " + str(exc))
    if optimized:
        backend_blockers = compatibility_blockers(project_root)
        if validation_probe:
            backend_blockers = [blocker for blocker in backend_blockers if not blocker.startswith("Headroom live gate pending:")]
        blockers.extend(backend_blockers)
    return blockers


def _hash_config(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def classify_treatment(observations: dict) -> str:
    requests = observations.get("proxy_total_requests")
    saved = observations.get("proxy_tokens_saved_estimate")
    if requests == 0:
        return "unexpected_bypass"
    if isinstance(requests, int) and requests > 0 and isinstance(saved, int) and saved > 0:
        return "active_proxy_estimate"
    return "unknown_or_no_eligible_content"


def _run_one(task: Task, project_root: Path, pair_dir: Path, config: str, model: str, reasoning: str, timeout: int, verifier_timeout: int, pair_id: str, *, validation_probe: bool = False) -> RunRecord:
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.monotonic()
    workspace = pair_dir / config
    fixture_hash = tree_hash(task.fixture)
    fixture_commit = "unknown"
    agent_version = installed_version() or "unknown"
    runner = CodexCliRunner()
    optimizer_observations = {"declared_settings": DECLARED_SETTINGS, "effective_settings": None} if config == "codex_headroom" else {}
    treatment_status = "not_applicable" if config == "codex_baseline" else "unknown"
    result = None
    outcome = "setup_failed"
    verification = VerificationResult(None, "not_run")
    try:
        prepared_hash = prepare_workspace(task, workspace, git=True)
        if prepared_hash != fixture_hash:
            raise RuntimeError("fixture snapshot changed during preparation")
        fixture_commit = commit_hash(workspace)
        boundary_probe(workspace, task.verifier)
        agent_boundary_probe(workspace, task.verifier)
        agent_tool_boundary_probe(workspace, task.verifier, check_write=True)
        if config == "codex_headroom":
            with ManagedHeadroom(project_root, pair_dir / "headroom-state", validation_probe=validation_probe) as backend:
                tool = local_executable(project_root)
                if tool is None:
                    raise RuntimeError("project-local retrieval executable disappeared")
                mcp_state = pair_dir / "mcp-state"
                mcp_state.mkdir(exist_ok=False)
                try:
                    mcp_profile = backend.prepare_mcp_profile(mcp_state)
                    agent_boundary_probe(workspace, task.verifier, additional_read_paths=(project_root / ".venv", mcp_state), additional_write_paths=(mcp_state,), additional_read_files=(mcp_profile,), tool_path=tool, mcp_profile=mcp_profile)
                    result = runner.run(task.requirements, workspace, RunnerConfiguration(model, reasoning, timeout, backend.codex_overrides(mcp_state, mcp_profile), (project_root / ".venv", mcp_state), (mcp_state,), (mcp_profile,)))
                finally:
                    shutil.rmtree(mcp_state)
                optimizer_observations = backend.observations()
                treatment_status = classify_treatment(optimizer_observations)
        else:
            result = runner.run(task.requirements, workspace, RunnerConfiguration(model, reasoning, timeout))
        outcome = result.outcome
        if outcome == "startup_failed":
            verification = VerificationResult(None, "not_run_agent_startup")
        else:
            try:
                verification = verify(task, workspace, timeout=verifier_timeout)
            except ValueError:
                verification = VerificationResult(False, "invalid_candidate")
            except VerificationBoundaryError:
                verification = VerificationResult(None, "verifier_boundary_failed")
                outcome = "verifier_boundary_failed"
    except KeyboardInterrupt:
        outcome = "cancelled"
        if config == "codex_headroom":
            treatment_status = "integration_failure"
    except Exception:
        outcome = "integration_failure" if config == "codex_headroom" else "setup_failed"
        if config == "codex_headroom":
            treatment_status = "integration_failure"
    elapsed = time.monotonic() - start
    parsed = result.parsed if result else None
    effective = {
        "config": config, "model": model, "reasoning": reasoning,
        "agent_version": agent_version,
        "timeout": timeout, "verifier_timeout": verifier_timeout,
        "codex_sandbox": "permission-profile:agent_cost_lab_restricted", "approval_policy": "never",
        "auth_mode": "subscription", "ignore_user_config": True,
        "ignore_user_project_rules": True, "client_runtime_state": "owned_temporary_directory",
        "unrelated_features": "plugins,remote_plugin,memories,multi_agent,web_search_disabled",
        "shell_environment_inherit": "none", "allow_login_shell": False,
        "client_boundary": "trusted_supported_client_on_host",
        "agent_boundary": "native_codex_command_and_filesystem_sandbox",
        "optimizer_engine": "Headroom 0.39.1" if config == "codex_headroom" else None,
        "optimizer_declared_settings": DECLARED_SETTINGS if config == "codex_headroom" else None,
        "retrieval_mcp": config == "codex_headroom",
    }
    return RunRecord(
        task_id=task.id, run_id=uuid.uuid4().hex, pair_id=pair_id, attempt_id=uuid.uuid4().hex,
        configuration=config, fixture_hash=fixture_hash, fixture_commit=fixture_commit, task_hash=task.manifest_hash,
        verifier_hash=file_hash(task.verifier), config_hash=_hash_config(effective),
        agent_version=agent_version, model=model, reasoning=reasoning,
        billing_mode="subscription", outcome=outcome, agent_seconds=result.elapsed_seconds if result else None,
        end_to_end_seconds=elapsed, usage=parsed.usage if parsed else Usage(), verification=verification,
        error_class=result.error_class if result else (outcome if outcome != "completed" else None),
        treatment_status=treatment_status, optimizer_engine="Headroom" if config == "codex_headroom" else None,
        optimizer_version="0.39.1" if config == "codex_headroom" else None,
        optimizer_observations=optimizer_observations,
        environment_observations={
            "control_hash": _hash_config({key: value for key, value in effective.items() if key not in {"config", "optimizer_engine", "optimizer_declared_settings", "retrieval_mcp"}}),
            "ignore_user_config": True,
            "ignore_user_project_rules": True,
            "client_runtime_state": "owned_temporary_directory",
            "client_boundary": "trusted_supported_client_on_host",
            "agent_boundary": "native_codex_command_and_filesystem_sandbox",
            "additional_mcp": "headroom_retrieval" if config == "codex_headroom" else None,
            "inherited_skills": None,
            "inherited_memory": None,
            "agent_compaction": None,
            "service_tier": None,
            "model_rerouted": parsed.model_rerouted if parsed else None,
        },
        observable_tool_events=parsed.tool_events if parsed else 0,
        observable_error_events=parsed.error_events if parsed else 0,
        started_at=started_at, ended_at=datetime.now(timezone.utc).isoformat(),
        requested_model=model,
        model_identity_status="rerouted" if parsed and parsed.model_rerouted else "unconfirmed",
    )


def execute(task: Task, project_root: Path, *, optimized: bool, model: str, reasoning: str, max_runs: int, timeout: int, verifier_timeout: int, max_total_seconds: int, artifacts_root: Path, validation_probe: bool = False) -> Path:
    if not model or max_runs < 1 or timeout < 1 or verifier_timeout < 1 or max_total_seconds < 1:
        raise ValueError("positive limits and an explicit model are required")
    if validation_probe and (not optimized or max_runs != 1):
        raise ValueError("Headroom validation check requires exactly one optimized attempt")
    if optimized and not validation_probe and (max_runs < 2 or max_runs % 2):
        raise ValueError("optimize requires an even max-runs of at least two")
    blockers = declared_blockers(project_root, optimized=optimized, validation_probe=validation_probe)
    if blockers:
        raise RuntimeError("execution blocked: " + "; ".join(blockers))
    campaign = artifacts_root / ("campaign-" + uuid.uuid4().hex[:12])
    campaign.mkdir(parents=True, exist_ok=False)
    records: list[dict] = []
    deadline = time.monotonic() + max_total_seconds
    try:
        count = max_runs // 2 if optimized and not validation_probe else max_runs
        for pair_index in range(count):
            if time.monotonic() >= deadline:
                break
            pair_id = f"pair-{pair_index + 1:03d}"
            pair_dir = campaign / pair_id
            pair_dir.mkdir()
            order = ("codex_baseline", "codex_headroom") if pair_index % 2 == 0 else ("codex_headroom", "codex_baseline")
            for config in (("codex_headroom",) if validation_probe else (order if optimized else ("codex_baseline",))):
                if time.monotonic() + timeout + verifier_timeout > deadline:
                    raise RuntimeError("remaining campaign deadline cannot cover next bounded attempt")
                record = _run_one(task, project_root, pair_dir, config, model, reasoning, timeout, verifier_timeout, pair_id, validation_probe=validation_probe)
                record.environment_observations["campaign_id"] = campaign.name
                record.environment_observations["trial_role"] = (
                    "compatibility_probe" if validation_probe else
                    "matched_comparison" if optimized else "baseline_pilot"
                )
                records.append(record.to_dict())
                write_report(campaign, records)
                if record.outcome != "completed" or record.treatment_status == "unexpected_bypass":
                    detail = "; " + record.error_class if record.error_class else ""
                    raise RuntimeError("attempt stopped campaign: " + record.outcome + "/" + record.treatment_status + detail + "; report: " + str(campaign / "report.md"))
    finally:
        if records:
            write_report(campaign, records)
    return campaign
