"""Shared offline accounting; unknown observations never become zero totals."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def safe_text(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")


def csv_cell(value: Any) -> Any:
    """Prevent user-controlled labels from becoming spreadsheet formulas."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def utc_timestamp(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def model_identity(record: dict) -> tuple[str, str, str]:
    requested = record.get("requested_model") or record.get("model") or "unknown"
    status = record.get("model_identity_status", "unconfirmed")
    if record.get("environment_observations", {}).get("model_rerouted") is True:
        status = "rerouted"
    effective = record.get("effective_model")
    if status != "confirmed" or not effective:
        effective = "unknown"
    return str(requested), str(effective), str(status)


def metric(record: dict, field: str) -> tuple[int | float | None, str]:
    if field in {"agent_seconds", "end_to_end_seconds"}:
        value = record.get(field)
        if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
            return None, "missing"
        return value, "complete"
    observation = record.get("usage", {}).get(field, {})
    value, state = observation.get("value"), observation.get("completeness", "missing")
    if type(value) is not int or value < 0:
        return None, "missing"
    return value, state


def complete_tokens(record: dict) -> tuple[int, int, int] | None:
    values = [metric(record, field) for field in ("input_tokens", "cached_input_tokens", "output_tokens")]
    if record.get("usage", {}).get("status") != "complete" or any(v is None or state != "complete" for v, state in values):
        return None
    inputs, cached, outputs = (v for v, _ in values)
    if cached > inputs:
        return None
    return inputs, cached, outputs


def unique_records(records: list[dict]) -> tuple[list[dict], int]:
    """Deduplicate copied ledgers, but never silently pick conflicting observations."""
    unique: dict[tuple[str, str], dict] = {}
    duplicates = 0
    for record in records:
        identity = record.get("run_id")
        if not isinstance(identity, str) or not identity:
            raise ValueError("record is missing a stable run_id")
        key = str(record.get("source_kind", "real")), identity
        if key in unique:
            if unique[key] != record:
                raise ValueError("conflicting copies of a run; select one ledger or re-import into the same ledger")
            duplicates += 1
        else:
            unique[key] = record
    return list(unique.values()), duplicates
