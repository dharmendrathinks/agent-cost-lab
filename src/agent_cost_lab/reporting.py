"""Secret-free JSONL, Markdown and CSV reporting."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from .accounting import csv_cell, metric, model_identity, safe_text
from .pricing import PriceTable, estimate, pricing_lines


def write_records(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def read_records(path: Path) -> list[dict[str, Any]]:
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    if not all(isinstance(record, dict) and type(record.get("record_schema_version")) is int and record["record_schema_version"] == 1 for record in records):
        raise ValueError("unsupported normalized record schema")
    return records


def _metric(record: dict[str, Any], name: str) -> tuple[int | float | None, str]:
    return metric(record, name)


def _display(record: dict[str, Any] | None, name: str) -> str:
    if record is None:
        return "—"
    if name == "verification":
        result = record.get("verification", {})
        return result.get("status", "unknown")
    if name == "telemetry":
        return record.get("usage", {}).get("status", "missing")
    value, status = _metric(record, name)
    return "unknown" if value is None else f"{value:g}" + (" (ambiguous)" if status == "ambiguous" else "")


def _success(records: list[dict[str, Any]]) -> str:
    if not records:
        return "0/0 (undefined)"
    count = sum(record.get("verification", {}).get("passed") is True for record in records)
    return f"{count}/{len(records)} ({100 * count / len(records):.1f}%)"


def _aggregate(records: list[dict[str, Any]], field: str) -> tuple[float, int, int]:
    known = [value for record in records for value, state in [_metric(record, field)] if value is not None and state == "complete"]
    return float(sum(known)), len(known), len(records)


def _comparable_pairs(baseline: list[dict[str, Any]], optimized: list[dict[str, Any]]) -> bool:
    if not baseline or len(baseline) != len(optimized):
        return False
    left = {r["pair_id"]: r for r in baseline}
    right = {r["pair_id"]: r for r in optimized}
    if len(left) != len(baseline) or len(right) != len(optimized) or left.keys() != right.keys():
        return False
    fields = ("task_id", "fixture_hash", "fixture_commit", "task_hash", "verifier_hash", "agent_version", "model", "reasoning", "billing_mode")
    for pair_id, a in left.items():
        b = right[pair_id]
        if any(r.get("source_kind") != "synthetic" for r in (a, b)):
            environments = [r.get("environment_observations", {}) for r in (a, b)]
            if any(e.get("trial_role") != "matched_comparison" for e in environments):
                return False
            if not environments[0].get("campaign_id") or environments[0].get("campaign_id") != environments[1].get("campaign_id"):
                return False
        if any(r.get("outcome") == "model_rerouted" or r.get("environment_observations", {}).get("model_rerouted") is True for r in (a, b)):
            return False
        if any(a.get(key) is None or a.get(key) != b.get(key) for key in fields):
            return False
        if model_identity(a) != model_identity(b):
            return False
        control = a.get("environment_observations", {}).get("control_hash")
        if not control or control != b.get("environment_observations", {}).get("control_hash"):
            return False
    return True


def comparison_verdict(baseline: list[dict], optimized: list[dict]) -> str:
    if not baseline or not optimized:
        return "Insufficient evidence — no matched baseline/optimized pair."
    if not _comparable_pairs(baseline, optimized) or any(r.get("treatment_status") != "active_proxy_estimate" for r in optimized):
        return "Insufficient evidence — comparable pairs or valid optimization evidence are missing."
    if any(r.get("verification", {}).get("passed") is not True for r in baseline + optimized):
        return "Insufficient evidence of improvement — task verification failed or is incomplete."
    totals = []
    for arm in (baseline, optimized):
        total = 0
        for field in ("input_tokens", "output_tokens"):
            subtotal, covered, count = _aggregate(arm, field)
            if covered != count or any(r.get("usage", {}).get("status") != "complete" for r in arm):
                return "Insufficient evidence — token accounting is incomplete."
            total += subtotal
        totals.append(total)
    before, after = totals
    direction = "Used more tokens" if after > before else ("Used fewer tokens" if after < before else "Used the same number of tokens")
    difference = f" ({100 * (after - before) / before:+.1f}%)" if before else ""
    return f"{direction}{difference}; both arms passed the specified checks. Input + output, with cached input counted once. Observed pairs only; no general savings claim."


def render_markdown(records: list[dict[str, Any]], *, prices: PriceTable | None = None, context: str = "short") -> str:
    if not records:
        raise ValueError("no records")
    tasks = {record["task_id"] for record in records}
    if len(tasks) != 1:
        raise ValueError("report requires one task")
    synthetic = all(record.get("source_kind") == "synthetic" for record in records)
    mixed = any(record.get("source_kind") == "synthetic" for record in records) and not synthetic
    if mixed:
        raise ValueError("cannot mix synthetic and real records")
    if any(r.get("billing_mode") != "subscription" for r in records):
        raise ValueError("this report supports subscription records only")
    if any(r.get("configuration") not in {"codex_baseline", "codex_headroom"} for r in records):
        raise ValueError("unsupported experiment configuration")
    baseline = [r for r in records if r["configuration"] == "codex_baseline"]
    optimized = [r for r in records if r["configuration"] == "codex_headroom"]
    if not baseline and not optimized:
        raise ValueError("no supported configurations")
    pair = baseline[-1] if baseline else None, optimized[-1] if optimized else None
    lines = ["# AGENT COST LAB", ""]
    if synthetic:
        lines.extend(["**SYNTHETIC DEMO DATA — not captured Codex runs or measured savings.**", ""])
    lines.extend(["**Result: " + comparison_verdict(baseline, optimized) + "**", ""])
    lines.extend([
        f"Task: {safe_text(next(iter(tasks)))}  ",
        "Optimization: Context optimization (Headroom)  " if optimized else "Optimization: not run (baseline pilot)  ",
        "Execution: Codex subscription", "",
        "| Configuration | Requested model | Confirmed effective model | Identity status |",
        "| --- | --- | --- | --- |",
    ])
    for configuration, arm in (("Baseline", baseline), ("Optimized", optimized)):
        for requested, effective, status in sorted({model_identity(r) for r in arm}):
            lines.append(f"| {configuration} | {safe_text(requested)} | {safe_text(effective)} | {safe_text(status)} |")
    lines.extend(["", "Configured/requested model is not confirmation of the model served. Absence of a reroute event does not confirm it.", "",
        "| Measure | Baseline | Optimized |", "| --- | ---: | ---: |",
    ])
    for label, field in (
        ("Input tokens", "input_tokens"),
        ("Cached input", "cached_input_tokens"),
        ("Output tokens", "output_tokens"),
        ("Agent runtime (s)", "agent_seconds"),
        ("End-to-end runtime (s)", "end_to_end_seconds"),
        ("Independent verification", "verification"),
        ("Telemetry completeness", "telemetry"),
    ):
        lines.append(f"| {label} | {_display(pair[0], field)} | {_display(pair[1], field)} |")
    lines.extend(["", "Success rate: baseline " + _success(baseline) + "; optimized " + _success(optimized) + ".", ""])
    lines.append(f"Started attempts: baseline {len(baseline)}; optimized {len(optimized)}. Failed attempts remain in resource totals.")
    for record in records:
        if record.get("outcome") not in ("completed", "synthetic_completed") or record.get("verification", {}).get("passed") is not True:
            failure = f", diagnostic {record['error_class']}" if record.get("error_class") else ""
            lines.append(f"- Attempt {record.get('attempt_id', 'unknown')}: {record.get('configuration', 'unknown')}, outcome {record.get('outcome', 'unknown')}{failure}, verification {record.get('verification', {}).get('status', 'unknown')}.")
    lines.extend(["", "The table shows the latest attempt in each configuration. Aggregate accounting includes every started attempt.", "", "## Aggregate resource accounting", ""])
    for label, field in (("Input tokens", "input_tokens"), ("Cached input", "cached_input_tokens"), ("Output tokens", "output_tokens"), ("Agent runtime (s)", "agent_seconds"), ("End-to-end runtime (s)", "end_to_end_seconds")):
        parts = []
        for name, arm in (("baseline", baseline), ("optimized", optimized)):
            subtotal, covered, total = _aggregate(arm, field)
            successes = sum(record.get("verification", {}).get("passed") is True for record in arm)
            if total == 0:
                parts.append(f"{name} not run (0/0 measured; per success not applicable)")
                continue
            if covered == 0:
                per_success = "undefined (zero successes)" if not successes else "unknown (incomplete coverage)"
                parts.append(f"{name} unknown (0/{total} measured; per success {per_success})")
                continue
            suffix = "complete total" if total and covered == total else "known subtotal"
            per_success = f"; {subtotal / successes:g} per verified success" if successes and total and covered == total else ("; per success undefined (zero successes)" if not successes else "; per success unknown (incomplete coverage)")
            parts.append(f"{name} {subtotal:g} ({covered}/{total} measured, {suffix}{per_success})")
        lines.append(f"- {label}: " + "; ".join(parts) + ".")
    lines.extend(["", "## Illustrative differences (synthetic)" if synthetic else "## Measured differences", ""])
    any_diff = False
    comparable_pairs = _comparable_pairs(baseline, optimized)
    valid_treatment = all(r.get("treatment_status") == "active_proxy_estimate" for r in optimized)
    for label, field in (("Input tokens", "input_tokens"), ("Cached input", "cached_input_tokens"), ("Output tokens", "output_tokens"), ("Agent runtime", "agent_seconds"), ("End-to-end runtime", "end_to_end_seconds")):
        a, ac, at = _aggregate(baseline, field)
        b, bc, bt = _aggregate(optimized, field)
        if comparable_pairs and valid_treatment and ac == at and bc == bt:
            diff = b - a
            pct = f" ({100 * diff / a:+.1f}%)" if a else " (percentage undefined: zero baseline)"
            lines.append(f"- {label}: {diff:+g}{pct} optimized versus baseline across all started attempts.")
            any_diff = True
    if not any_diff:
        lines.append("No complete, valid, comparable paired measurements.")
    lines.extend(["", "## Limitations", "", "This report covers only the specified acceptance tests and available telemetry. Provider cache state is uncontrolled. Live attempts may consume subscription allowance; allowance use is not measured here."])
    if any(r.get("usage", {}).get("status") != "complete" for r in records):
        lines.append("Some token telemetry is missing, ambiguous, invalid, or incomplete.")
    if any(r.get("outcome") not in ("completed", "synthetic_completed") and r.get("usage", {}).get("status") == "missing" for r in records):
        lines.append("A failed attempt has no usage events; agent work cannot be established from that attempt. Verification of its candidate does not attribute the failure to the agent.")
    if len(baseline) < 3 or len(optimized) < 3:
        lines.append("The sample is too small for a general quality-preservation claim.")
    if baseline and optimized and not comparable_pairs:
        lines.append("Pair identities or shared controls differ or are missing; resource differences are withheld.")
    if any(any(value is None for key, value in r.get("environment_observations", {}).items() if key in {"inherited_skills", "inherited_memory", "agent_compaction", "service_tier"}) for r in records):
        lines.append("Some inherited agent settings and compaction behavior were not observable.")
    lines.extend(["", "## Implementation details", ""])
    if optimized:
        r = optimized[-1]
        lines.append("Engine: Headroom " + str(r.get("optimizer_version") or "unknown"))
        lines.append("Treatment status: " + str(r.get("treatment_status") or "unknown"))
        observations = r.get("optimizer_observations", {})
        if isinstance(observations, dict):
            def observed_count(value):
                return str(value) if type(value) is int and value >= 0 else "unknown"
            lines.append("Headroom proxy requests observed: " + observed_count(observations.get("proxy_total_requests")) + " (not an inferred internal provider-call count).")
            lines.append("Headroom proxy compression estimate (tokens): " + observed_count(observations.get("proxy_tokens_saved_estimate")) + " (supplementary, not provider usage or billed savings).")
            ws = observations.get("codex_ws", {})
            if isinstance(ws, dict):
                lines.append("Headroom context units observed / modified: " + observed_count(ws.get("units_total")) + " / " + observed_count(ws.get("units_modified_total")) + ".")
                lines.append("Headroom frames attempted / compressed / failed: " + " / ".join(observed_count(ws.get(key)) for key in ("frames_attempted_total", "frames_compressed_total", "frames_failed_total")) + ".")
        observations = r.get("optimizer_observations", {})
        lines.append("Declared strategy/settings: " + str(observations.get("declared_settings", "unknown")))
        lines.append("Effective strategy/settings: " + str(observations.get("effective_settings") or "unverified"))
    else:
        lines.append("Engine: not run")
    lines.extend(["", "Monetary savings: **Not calculated for subscription runs.**", ""])
    if prices:
        lines.extend(pricing_lines(records, prices, context))
    return "\n".join(lines)


def write_csv(path: Path, records: list[dict[str, Any]], *, prices: PriceTable | None = None, context: str = "short") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["task_id", "run_id", "pair_id", "configuration", "source_kind", "outcome", "error_class", "verification", "input_tokens", "cached_input_tokens", "output_tokens", "agent_seconds", "end_to_end_seconds", "telemetry_completeness", "treatment_status"]
    fields += ["requested_model", "effective_model", "model_identity_status", "started_at", "ended_at", "api_equivalent_usd", "pricing_basis", "pricing_as_of", "pricing_context"]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            requested, effective, identity = model_identity(record)
            amount, basis = estimate(record, prices, context) if prices else (None, "disabled")
            row = {
                **{k: record.get(k) for k in ("task_id", "run_id", "pair_id", "configuration", "source_kind", "outcome", "error_class", "agent_seconds", "end_to_end_seconds", "treatment_status")},
                "verification": record.get("verification", {}).get("status"),
                **{k: _metric(record, k)[0] for k in ("input_tokens", "cached_input_tokens", "output_tokens")},
                "telemetry_completeness": record.get("usage", {}).get("status"),
                "requested_model": requested, "effective_model": effective, "model_identity_status": identity,
                "started_at": record.get("started_at"), "ended_at": record.get("ended_at"),
                "api_equivalent_usd": str(amount) if amount is not None else None,
                "pricing_basis": basis, "pricing_as_of": prices.as_of if prices else None,
                "pricing_context": context if prices else None,
            }
            writer.writerow({key: csv_cell(value) for key, value in row.items()})


def write_report(directory: Path, records: list[dict[str, Any]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    write_records(directory / "runs.jsonl", records)
    (directory / "report.md").write_text(render_markdown(records), encoding="utf-8")
    write_csv(directory / "runs.csv", records)
