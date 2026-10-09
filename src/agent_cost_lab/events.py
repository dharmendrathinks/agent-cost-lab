"""Version-aware Codex exec JSONL normalization.

The inspected Codex 0.157.1 and 0.160.0 `turn.completed.usage` are thread-total snapshots.
No unknown schema is silently interpreted as an additive turn delta.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from .records import Measurement, Usage, unknown_count

SUPPORTED_CODEX_VERSION = "0.160.0"
SUPPORTED_CODEX_VERSIONS = frozenset({"0.157.1", "0.160.0"})
FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)
REQUIRED_FIELDS = ("input_tokens", "output_tokens")
KNOWN_TYPES = {
    "thread.started", "turn.started", "turn.completed", "turn.failed", "error",
    "item.started", "item.updated", "item.completed",
}
KNOWN_ITEM_TYPES = {"agent_message", "reasoning", "command_execution", "file_change", "mcp_tool_call", "collab_tool_call", "web_search", "todo_list", "error"}


class UnsupportedEventSchema(ValueError):
    """A stream cannot be accounted for using an inspected schema."""


@dataclass(frozen=True)
class ParsedEvents:
    usage: Usage
    completed_turns: int
    failed_turns: int
    tool_events: int
    error_events: int
    malformed_lines: int
    partial_tail: bool
    thread_id_present: bool
    model_rerouted: bool = False


def _metric(value: int | None, status: str, field: str) -> Measurement:
    if value is None:
        return unknown_count()
    return Measurement(value, "tokens", "codex.exec.jsonl." + field, "thread_total", status)


def _snapshot(raw: object) -> dict[str, int]:
    if not isinstance(raw, dict):
        raise UnsupportedEventSchema("turn.completed.usage must be an object")
    unknown = set(raw) - set(FIELDS)
    if unknown:
        raise UnsupportedEventSchema("uninspected usage fields: " + ", ".join(sorted(unknown)))
    if not all(k in raw for k in REQUIRED_FIELDS):
        raise UnsupportedEventSchema("required usage fields missing")
    result: dict[str, int] = {}
    for key, value in raw.items():
        if type(value) is not int or value < 0:
            raise UnsupportedEventSchema("invalid " + key)
        result[key] = value
    if result.get("cached_input_tokens", 0) > result["input_tokens"]:
        raise UnsupportedEventSchema("cached input exceeds input")
    if result.get("reasoning_output_tokens", 0) > result["output_tokens"]:
        raise UnsupportedEventSchema("reasoning output exceeds output")
    return result


def parse_jsonl(lines: Iterable[str], *, codex_version: str) -> ParsedEvents:
    if codex_version not in SUPPORTED_CODEX_VERSIONS:
        raise UnsupportedEventSchema("Codex " + codex_version + " requires a reviewed usage adapter")
    snapshots: list[dict[str, int]] = []
    started = completed = failed = tools = errors = malformed = missing_usage_events = 0
    partial_tail = False
    thread_present = False
    model_rerouted = False
    completed_tool_ids: set[tuple[str, str]] = set()
    material = list(lines)
    for index, line in enumerate(material):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            if index == len(material) - 1 and not line.endswith("\n"):
                partial_tail = True
                continue
            malformed += 1
            raise UnsupportedEventSchema("malformed JSONL event") from exc
        if not isinstance(event, dict) or not isinstance(event.get("type"), str) or event["type"] not in KNOWN_TYPES:
            raise UnsupportedEventSchema("unknown event type or shape")
        kind = event["type"]
        if kind == "thread.started":
            thread_present = isinstance(event.get("thread_id"), str)
        elif kind == "turn.started":
            started += 1
        elif kind == "turn.completed":
            completed += 1
            if "usage" not in event:
                missing_usage_events += 1
            else:
                snapshots.append(_snapshot(event["usage"]))
        elif kind == "turn.failed":
            failed += 1
        elif kind == "error":
            errors += 1
        elif kind.startswith("item."):
            item = event.get("item")
            if not isinstance(item, dict) or not isinstance(item.get("type"), str) or item["type"] not in KNOWN_ITEM_TYPES:
                raise UnsupportedEventSchema("unknown item shape")
            if item["type"] == "error" and isinstance(item.get("message"), str) and item["message"].startswith("model rerouted:"):
                model_rerouted = True
            if item["type"] in {"command_execution", "file_change", "mcp_tool_call", "web_search"} and kind == "item.completed":
                item_id = item.get("id")
                if not isinstance(item_id, str):
                    raise UnsupportedEventSchema("completed tool event lacks an item ID")
                identity = item["type"], item_id
                if identity not in completed_tool_ids:
                    tools += 1
                    completed_tool_ids.add(identity)
    duplicates = 0
    distinct: list[dict[str, int]] = []
    for snap in snapshots:
        if distinct and snap == distinct[-1]:
            duplicates += 1
        else:
            distinct.append(snap)
    invalid = any(
        any(a[k] > b[k] for k in a.keys() & b.keys())
        for a, b in zip(distinct, distinct[1:])
    )
    if invalid:
        usage = Usage(observed_snapshots=tuple(snapshots), duplicate_events=duplicates, terminal_events=completed, status="invalid")
    elif not distinct:
        usage = Usage(duplicate_events=duplicates, terminal_events=completed, status="missing")
    else:
        final = distinct[-1]
        zero = all(value == 0 for value in final.values())
        status = "ambiguous" if zero else ("incomplete" if "cached_input_tokens" not in final else "complete")
        if failed or partial_tail or missing_usage_events or started > completed + failed:
            status = "incomplete"
        usage = Usage(
            **{k: _metric(final.get(k), status, k) for k in FIELDS},
            raw_snapshot=final,
            observed_snapshots=tuple(snapshots),
            duplicate_events=duplicates,
            terminal_events=completed,
            status=status,
        )
    return ParsedEvents(usage, completed, failed, tools, errors, malformed, partial_tail, thread_present, model_rerouted)
