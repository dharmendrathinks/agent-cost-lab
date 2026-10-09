"""Secret-free normalized records. Provider counts and optimizer estimates stay separate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

RECORD_SCHEMA_VERSION = 1
UsageState = Literal["complete", "ambiguous", "missing", "invalid", "incomplete"]


@dataclass(frozen=True)
class Measurement:
    value: int | float | None
    unit: str
    source: str
    granularity: str
    completeness: UsageState


def unknown_count(source: str = "codex.exec.jsonl") -> Measurement:
    return Measurement(None, "tokens", source, "thread_total", "missing")


@dataclass(frozen=True)
class Usage:
    input_tokens: Measurement = field(default_factory=unknown_count)
    cached_input_tokens: Measurement = field(default_factory=unknown_count)
    cache_write_input_tokens: Measurement = field(default_factory=unknown_count)
    output_tokens: Measurement = field(default_factory=unknown_count)
    reasoning_output_tokens: Measurement = field(default_factory=unknown_count)
    raw_snapshot: dict[str, int] | None = None
    observed_snapshots: tuple[dict[str, int], ...] = ()
    duplicate_events: int = 0
    terminal_events: int = 0
    status: UsageState = "missing"


@dataclass(frozen=True)
class VerificationResult:
    passed: bool | None
    status: str
    case_count: int = 0
    passed_cases: int = 0
    failure_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunRecord:
    task_id: str
    run_id: str
    pair_id: str
    attempt_id: str
    configuration: str
    fixture_hash: str
    fixture_commit: str
    task_hash: str
    verifier_hash: str
    config_hash: str
    agent_version: str
    model: str
    reasoning: str
    billing_mode: str
    outcome: str
    agent_seconds: float | None
    end_to_end_seconds: float | None
    usage: Usage
    verification: VerificationResult
    error_class: str | None = None
    treatment_status: str = "not_applicable"
    optimizer_engine: str | None = None
    optimizer_version: str | None = None
    optimizer_observations: dict[str, Any] = field(default_factory=dict)
    environment_observations: dict[str, Any] = field(default_factory=dict)
    observable_tool_events: int = 0
    observable_error_events: int = 0
    source_kind: str = "real"
    record_schema_version: int = RECORD_SCHEMA_VERSION
    started_at: str | None = None
    ended_at: str | None = None
    requested_model: str | None = None
    effective_model: str | None = None
    model_identity_status: str = "unconfirmed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
