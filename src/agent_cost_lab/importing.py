"""Read selected Codex rollout logs into a content-free, idempotent local ledger."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from .accounting import unique_records, utc_timestamp
from .events import FIELDS, _snapshot
from .records import Measurement, RunRecord, Usage, VerificationResult
from .reporting import read_records

SUPPORTED_ROLLOUT_VERSIONS = frozenset({"0.160.0"})
ADAPTER = "codex-rollout-0.160.0-v1"
ROLLOUT_TYPES = frozenset({"session_meta", "turn_context", "event_msg", "response_item",
                           "token_usage_record", "compacted", "world_state"})


def _label(value: object) -> str:
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", value) else "unknown"


def _usage_snapshot(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise ValueError("unsupported rollout usage shape")
    counts = _snapshot({k: v for k, v in raw.items() if k != "total_tokens"})
    total = raw.get("total_tokens")
    if total is not None and (type(total) is not int or total != counts["input_tokens"] + counts["output_tokens"]):
        raise ValueError("inconsistent rollout total_tokens")
    if counts.get("cached_input_tokens", 0) + counts.get("cache_write_input_tokens", 0) > counts["input_tokens"]:
        raise ValueError("invalid rollout cache subsets")
    return counts


def parse_rollout(data: bytes, *, task_label: str = "codex-session") -> dict:
    """One cumulative snapshot per session; never sum repeated token_count events."""
    if _label(task_label) != task_label:
        raise ValueError("task label must be a short identifier without spaces")
    meta = None
    models: set[str] = set()
    efforts: set[str] = set()
    active_turns: set[str] = set()
    completed_turns: dict[str, int | None] = {}
    failed_turns: set[str] = set()
    snapshots: list[dict[str, int]] = []
    partial = partial_tail = invalid = rerouted = False
    started_at = ended_at = None
    last_start = last_usage = -1
    duplicates = 0
    lines = data.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (ValueError, UnicodeDecodeError) as exc:
            if index == len(lines) - 1 and not line.endswith(b"\n"):
                partial = True
                partial_tail = True
                break
            raise ValueError("malformed rollout JSONL; no raw content copied") from exc
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ValueError("unsupported rollout event shape")
        kind, payload = event["type"], event.get("payload")
        if kind not in ROLLOUT_TYPES:
            raise ValueError("unsupported rollout event type")
        if not isinstance(payload, dict):
            raise ValueError("unsupported rollout payload shape")
        if kind == "session_meta":
            if meta is not None:
                raise ValueError("multiple session metadata records are unsupported")
            if payload.get("cli_version") not in SUPPORTED_ROLLOUT_VERSIONS:
                raise ValueError("unsupported rollout version; supported: " + ", ".join(sorted(SUPPORTED_ROLLOUT_VERSIONS)))
            if payload.get("model_provider") != "openai":
                raise ValueError("unsupported rollout provider")
            if not isinstance(payload.get("id"), str) or not payload["id"]:
                raise ValueError("rollout lacks a stable session identity")
            if payload.get("forked_from_id") or payload.get("forked_from"):
                raise ValueError("forked history cannot be safely attributed by this adapter")
            meta = {k: payload.get(k) for k in ("id", "cli_version")}
            started_at = utc_timestamp(payload.get("timestamp")) or utc_timestamp(event.get("timestamp"))
        elif meta is None:
            raise ValueError("rollout must start with session_meta")
        elif kind == "turn_context":
            models.add(_label(payload.get("model")))
            efforts.add(_label(payload.get("effort")))
        elif kind == "token_usage_record":
            if payload.get("thread_id") != meta["id"]:
                raise ValueError("usage from another thread or inherited history is unsupported")
            # A persisted per-response record also includes a cumulative thread snapshot.
            snap = _usage_snapshot(payload.get("thread_token_usage"))
            snapshots.append(snap)
            last_usage = index
        elif kind == "event_msg":
            event_type = payload.get("type")
            if not isinstance(event_type, str):
                raise ValueError("unsupported rollout event message")
            if event_type != "token_count" and ("token" in event_type or "usage" in event_type):
                raise ValueError("uninspected rollout accounting event")
            turn_id = payload.get("turn_id")
            if event_type in {"thread_rolled_back", "rollback"}:
                raise ValueError("rolled-back history cannot be safely attributed by this adapter")
            if event_type == "token_count":
                info = payload.get("info")
                if info is not None:
                    if not isinstance(info, dict):
                        raise ValueError("unsupported token_count info")
                    snapshots.append(_usage_snapshot(info.get("total_token_usage")))
                    last_usage = index
            elif event_type == "task_started":
                if not isinstance(turn_id, str):
                    raise ValueError("task_started lacks turn identity")
                active_turns.add(turn_id)
                last_start = index
            elif event_type == "task_complete":
                if not isinstance(turn_id, str):
                    raise ValueError("task_complete lacks turn identity")
                if turn_id not in active_turns and turn_id not in completed_turns:
                    partial = True
                active_turns.discard(turn_id)
                duration = payload.get("duration_ms")
                completed_turns[turn_id] = duration if type(duration) is int and duration >= 0 else None
                ended_at = utc_timestamp(event.get("timestamp"))
            elif event_type in {"turn_aborted", "task_failed", "error"}:
                failed_turns.add(turn_id if isinstance(turn_id, str) else "unknown")
                active_turns.discard(turn_id)
            elif event_type == "model_rerouted":
                rerouted = True
    if meta is None:
        raise ValueError("no supported rollout session metadata")
    for previous, following in zip(snapshots, snapshots[1:]):
        if previous == following:
            duplicates += 1
        if any(previous[k] > following[k] for k in previous.keys() & following.keys()):
            invalid = True
    final = snapshots[-1] if snapshots and not invalid else None
    status = "invalid" if invalid else "missing"
    if final is not None:
        status = "complete"
        if not any(final.values()):
            status = "ambiguous"
        if partial or active_turns or failed_turns or not completed_turns or last_usage < last_start or "cached_input_tokens" not in final:
            status = "incomplete"
    # Keep only final counts and safe counters, never prompts/tool output/user identifiers.
    usage = Usage(
        **{field: Measurement((final or {}).get(field), "tokens", "codex.rollout." + field,
                              "thread_total", status if field in (final or {}) else "missing") for field in FIELDS},
        raw_snapshot=final, duplicate_events=duplicates, terminal_events=len(completed_turns), status=status,
    )
    model = next(iter(models)) if len(models) == 1 else ("mixed" if models else "unknown")
    identity = "rerouted" if rerouted else ("mixed" if len(models) > 1 else "unconfirmed")
    complete = bool(completed_turns) and not active_turns and not failed_turns and not partial
    durations = list(completed_turns.values())
    runtime = sum(durations) / 1000 if complete and all(d is not None for d in durations) else None
    session_key = hashlib.sha256(meta["id"].encode()).hexdigest()
    record = RunRecord(
        task_id=task_label, run_id="session-" + session_key, attempt_id="session-" + session_key,
        pair_id="unpaired", configuration="codex_session", fixture_hash="unknown", fixture_commit="unknown",
        task_hash="unknown", verifier_hash="unknown", config_hash="unknown", agent_version=meta["cli_version"],
        model=model, requested_model=model, reasoning=next(iter(efforts)) if len(efforts) == 1 else "unknown",
        billing_mode="unknown", outcome="completed" if complete else ("failed" if failed_turns else "incomplete"),
        agent_seconds=runtime, end_to_end_seconds=None, usage=usage,
        verification=VerificationResult(None, "not_verified"), source_kind="imported",
        started_at=started_at, ended_at=ended_at if complete else None, model_identity_status=identity,
        environment_observations={"import_adapter": ADAPTER, "requested_models": sorted(models),
                                  "snapshot_count": len(snapshots), "completed_turns": len(completed_turns),
                                  "failed_turns": len(failed_turns), "partial_tail": partial_tail,
                                  "model_rerouted": rerouted, "usage_scope": "thread_only"},
    ).to_dict()
    record["import_metadata"] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "adapter": ADAPTER}
    return record


def import_sessions(paths: list[Path], ledger: Path, *, task_label: str = "codex-session") -> dict[str, int]:
    sources: set[Path] = set()
    for path in paths:
        if path.is_dir():
            sources.update(p.resolve() for p in path.rglob("rollout-*.jsonl") if p.is_file())
        else:
            sources.add(path.resolve())
    if not sources:
        raise ValueError("no rollout JSONL files found")
    if ledger.resolve() in sources:
        raise ValueError("import destination cannot overwrite a source log")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    result = {"added": 0, "updated": 0, "unchanged": 0, "older_copy_skipped": 0}
    # Serialize read/merge/atomic replace so two local imports cannot lose updates.
    with ledger.with_suffix(ledger.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        existing, _ = unique_records(read_records(ledger) if ledger.exists() else [])
        indexed = {r["run_id"]: r for r in existing}
        for path in sorted(sources):
            data = path.read_bytes()
            record = parse_rollout(data, task_label=task_label)
            previous = indexed.get(record["run_id"])
            if previous:
                old = previous.get("import_metadata", {})
                current = record["import_metadata"]
                if previous.get("task_id") != task_label:
                    raise ValueError("session already imported with a different task label")
                if old.get("sha256") == current["sha256"]:
                    result["unchanged"] += 1
                    continue
                old_size = old.get("bytes")
                if type(old_size) is not int:
                    raise ValueError("existing session lacks import provenance")
                if len(data) < old_size:
                    result["older_copy_skipped"] += 1
                    continue
                if hashlib.sha256(data[:old_size]).hexdigest() != old.get("sha256"):
                    raise ValueError("session history changed; refusing to replace conflicting usage")
                result["updated"] += 1
            else:
                result["added"] += 1
            indexed[record["run_id"]] = record
        # Do not rewrite the ledger for an exact repeated import.
        if result["added"] or result["updated"]:
            temp_name = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=ledger.parent, delete=False) as stream:
                    temp_name = stream.name
                    for record in indexed.values():
                        stream.write(json.dumps(record, sort_keys=True) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_name, ledger)
            finally:
                if temp_name and os.path.exists(temp_name):
                    os.unlink(temp_name)
    return result
