"""Offline summaries of saved attempts and imported sessions."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from .accounting import complete_tokens, csv_cell, metric, model_identity, safe_text, unique_records, utc_timestamp
from .pricing import PriceTable, estimate, pricing_lines
from .reporting import read_records


def load_collection(paths: list[Path]) -> tuple[list[dict], int]:
    files: set[Path] = set()
    for path in paths:
        if path.is_dir():
            files.update(p.resolve() for p in path.rglob("runs.jsonl") if p.is_file())
        else:
            files.add(path.resolve())
    records = [record for path in sorted(files) for record in read_records(path)]
    records, duplicates = unique_records(records)
    if not records:
        raise ValueError("no saved records found; directories are searched for runs.jsonl")
    if any(r.get("source_kind") == "synthetic" for r in records) and not all(r.get("source_kind") == "synthetic" for r in records):
        raise ValueError("cannot mix synthetic and real records in a summary")
    return records, duplicates


def _group(record: dict, dimension: str) -> str:
    if dimension == "model":
        requested, effective, status = model_identity(record)
        return effective + " (confirmed)" if status == "confirmed" else requested + " (" + status + ")"
    if dimension == "task":
        return str(record.get("task_id") or "unknown")
    if dimension == "day":
        stamp = utc_timestamp(record.get("started_at"))
        return stamp[:10] if stamp else "unknown"
    raise ValueError("unsupported summary group")


def _row(records: list[dict], dimension: str, label: str, prices: PriceTable | None, context: str) -> dict:
    count = len(records)
    verification = [r.get("verification", {}).get("passed") for r in records]
    passed = sum(v is True for v in verification)
    outcomes = Counter(r.get("outcome", "unknown") for r in records)
    completed = sum(outcomes[key] for key in ("completed", "synthetic_completed"))
    unfinished = sum(outcomes[key] for key in ("incomplete", "unknown", "cancelled"))
    row = {"dimension": dimension, "group": label, "records": count, "completed": completed,
           "failed": count - completed - unfinished, "incomplete": unfinished,
           "verified_successes": passed, "verified_failures": sum(v is False for v in verification),
           "unverified": sum(v is not True and v is not False for v in verification)}
    for field in ("input_tokens", "cached_input_tokens", "output_tokens", "agent_seconds", "end_to_end_seconds"):
        values = [value for r in records for value, state in [metric(r, field)] if value is not None and state == "complete"]
        row[field] = sum(values) if values else None
        row[field + "_coverage"] = f"{len(values)}/{count}"
    tokens = [complete_tokens(r) for r in records]
    row["tokens_per_verified_success"] = (
        sum(t[0] + t[2] for t in tokens) / passed
        if passed and not row["unverified"] and all(t is not None for t in tokens) else None
    )
    row["api_equivalent_usd"] = None
    row["priced_coverage"] = "disabled"
    if prices:
        priced = [amount for r in records for amount, _ in [estimate(r, prices, context)] if amount is not None]
        row["api_equivalent_usd"] = str(sum(priced)) if priced else None
        row["priced_coverage"] = f"{len(priced)}/{count}"
    return row


def summarize(records: list[dict], groups: list[str], *, prices: PriceTable | None = None, context: str = "short") -> list[dict]:
    rows = [_row(records, "total", "All records", prices, context)]
    for dimension in groups:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for record in records:
            grouped[_group(record, dimension)].append(record)
        rows.extend(_row(members, dimension, label, prices, context) for label, members in sorted(grouped.items()))
    return rows


def _display(row: dict, field: str) -> str:
    value = row[field]
    if value is None:
        return "unknown"
    coverage = row.get(field + "_coverage")
    suffix = f" ({coverage})" if coverage else ""
    return f"{value:g}" + suffix


def render_summary(records: list[dict], rows: list[dict], *, duplicates: int = 0, prices: PriceTable | None = None, context: str = "short") -> str:
    total = rows[0]
    lines = ["# AGENT COST LAB — Saved usage summary", ""]
    if all(r.get("source_kind") == "synthetic" for r in records):
        lines.extend(["**SYNTHETIC DEMO DATA — not measured usage.**", ""])
    lines.extend([f"**{len(records)} unique records**; {duplicates} duplicate copies excluded. No agent or API calls were made.", "",
                  f"Execution: {total['completed']} completed, {total['failed']} failed, {total['incomplete']} incomplete/cancelled. "
                  f"Independent verification: {total['verified_successes']} passed, {total['verified_failures']} failed, {total['unverified']} unverified.", "",
                  "Counts in parentheses are measurement coverage (known/records). Partial coverage is a **known subtotal**, not a complete total. "
                  "Failed attempts remain included where their usage is known. Cached input is a subset of input; reasoning is a subset of output.", "",
                  "Day groups use the **UTC start date** of the run/session, not the dates individual tokens were consumed. "
                  "Older records without timestamps remain in unknown. Imported sessions are unverified, cover their own thread only, "
                  "and may span multiple days or models. Their runtime is summed completed-turn duration when fully available; idle gaps are excluded.", ""])
    for dimension in dict.fromkeys(row["dimension"] for row in rows):
        label = {"total": "Overall", "model": "By model", "task": "By task", "day": "By UTC start day"}[dimension]
        lines.extend(["## " + label, "", "| Group | Records | Input | Cached input | Output | Agent seconds | Tokens / verified success |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
        group_rows = [r for r in rows if r["dimension"] == dimension]
        for row in group_rows:
            values = [_display(row, field) for field in ("input_tokens", "cached_input_tokens", "output_tokens", "agent_seconds", "tokens_per_verified_success")]
            lines.append(f"| {safe_text(row['group'])} | {row['records']} | " + " | ".join(values) + " |")
        lines.extend(["", "| Group | Completed | Failed | Incomplete | Verified pass / fail / unknown |", "| --- | ---: | ---: | ---: | --- |"])
        for row in group_rows:
            lines.append(f"| {safe_text(row['group'])} | {row['completed']} | {row['failed']} | {row['incomplete']} | {row['verified_successes']} / {row['verified_failures']} / {row['unverified']} |")
        if prices:
            lines.extend(["", "| Group | API-equivalent USD | Priced records |", "| --- | ---: | ---: |"])
            for row in group_rows:
                amount = row["api_equivalent_usd"]
                lines.append(f"| {safe_text(row['group'])} | {'unknown' if amount is None else '$' + amount} | {row['priced_coverage']} |")
        lines.append("")
    lines.extend(["## Model identity", "", "| Requested model | Confirmed effective model | Status | Records |", "| --- | --- | --- | ---: |"])
    for (requested, effective, status), count in sorted(Counter(model_identity(r) for r in records).items()):
        lines.append(f"| {safe_text(requested)} | {safe_text(effective)} | {safe_text(status)} | {count} |")
    lines.extend(["", "A configured model or absence of rerouting is not independent confirmation of the serving model. "
                  "Tokens per verified success includes all measured attempts, including failures, and is withheld when usage or verification coverage is incomplete. "
                  "This inventory does not establish an optimization effect across unrelated tasks or campaigns.", "",
                  "Actual monetary cost and subscription allowance consumed: **not measured**.", ""])
    if prices:
        lines.extend(pricing_lines(records, prices, context))
    return "\n".join(lines)


def write_summary_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows({key: csv_cell(value) for key, value in row.items()} for row in rows)
