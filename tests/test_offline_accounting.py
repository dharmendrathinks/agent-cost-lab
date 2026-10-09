"""Synthetic accounting edge cases; never authenticate or start a model/proxy."""

import copy
import json
import socket
import subprocess
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_cost_lab.accounting import model_identity, unique_records
from agent_cost_lab.cli import main, synthetic_demo
from agent_cost_lab.importing import import_sessions, parse_rollout
from agent_cost_lab.pricing import estimate, load_prices
from agent_cost_lab.reporting import comparison_verdict, read_records, render_markdown, write_records
from agent_cost_lab.summary import load_collection, render_summary, summarize

ROOT = Path(__file__).resolve().parents[1]


def event(kind, payload, timestamp="2026-10-05T01:00:00Z"):
    return {"timestamp": timestamp, "type": kind, "payload": payload}


def token_counts(inputs=100, cached=40, outputs=20):
    return {"input_tokens": inputs, "cached_input_tokens": cached, "cache_write_input_tokens": 0,
            "output_tokens": outputs, "reasoning_output_tokens": 5, "total_tokens": inputs + outputs}


def token_event(counts=None):
    return event("event_msg", {"type": "token_count", "info": {"total_token_usage": counts or token_counts()}})


def rollout_events():
    return [
        event("session_meta", {"id": "synthetic-session", "cli_version": "0.160.0", "model_provider": "openai",
                               "timestamp": "2026-10-05T01:00:00+05:30", "cwd": "/PRIVATE_WORKSPACE",
                               "creator_account_id": "PRIVATE_ACCOUNT", "base_instructions": "PRIVATE_INSTRUCTIONS"}),
        event("event_msg", {"type": "task_started", "turn_id": "turn-1"}),
        event("turn_context", {"model": "gpt-6-sol", "effort": "medium"}),
        event("response_item", {"type": "message", "content": "PRIVATE_PROMPT"}),
        token_event(), token_event(),
        event("event_msg", {"type": "task_complete", "turn_id": "turn-1", "duration_ms": 2000,
                            "last_agent_message": "PRIVATE_RESPONSE"}),
    ]


def encode(events):
    return ("\n".join(json.dumps(e) for e in events) + "\n").encode()


def priced_record():
    record = synthetic_demo()[0]
    record["model"] = "gpt-6-sol"
    return record


def test_rollout_cumulative_duplicate_snapshots_privacy_and_verification():
    record = parse_rollout(encode(rollout_events()))
    assert record["usage"]["input_tokens"]["value"] == 100
    assert record["usage"]["duplicate_events"] == 1
    assert record["usage"]["status"] == "complete"
    assert record["verification"]["passed"] is None
    assert record["billing_mode"] == "unknown"
    assert record["effective_model"] is None
    assert record["agent_seconds"] == 2
    assert record["started_at"].startswith("2026-10-04")
    assert "PRIVATE" not in json.dumps(record)
    assert "synthetic-session" not in json.dumps(record)


def test_per_response_thread_snapshots_are_not_added_to_token_counts():
    events = rollout_events()
    events.insert(4, event("token_usage_record", {"thread_id": "synthetic-session", "thread_token_usage": token_counts(),
                                               "usage": token_counts(), "response_id": "private-response-id"}))
    record = parse_rollout(encode(events))
    assert record["usage"]["input_tokens"]["value"] == 100
    assert record["usage"]["duplicate_events"] == 2


@pytest.mark.parametrize("mutation", ["partial", "unfinished", "failure", "missing", "decreasing", "zero"])
def test_rollout_incomplete_usage_never_becomes_complete(mutation):
    events = rollout_events()
    suffix = b""
    if mutation == "partial":
        suffix = b'{"type":'
    elif mutation == "unfinished":
        events.append(event("event_msg", {"type": "task_started", "turn_id": "turn-2"}))
    elif mutation == "failure":
        events[-1] = event("event_msg", {"type": "turn_aborted", "turn_id": "turn-1"})
    elif mutation == "missing":
        events = events[:4] + events[-1:]
    elif mutation == "decreasing":
        events.insert(-1, token_event(token_counts(90)))
    elif mutation == "zero":
        for index in (4, 5):
            events[index] = token_event({key: 0 for key in token_counts()})
    record = parse_rollout(encode(events) + suffix)
    assert record["usage"]["status"] != "complete"
    assert estimate(record, load_prices(ROOT / "configs/pricing.toml"))[0] is None


@pytest.mark.parametrize("mutation", ["version", "foreign_thread", "fork", "unknown_usage", "malformed", "rollback", "unknown_event", "new_usage_event"])
def test_unsupported_or_ambiguous_rollouts_fail_explicitly(mutation):
    events = rollout_events()
    if mutation == "version":
        events[0]["payload"]["cli_version"] = "99.0.0"
    elif mutation == "foreign_thread":
        events.insert(-1, event("token_usage_record", {"thread_id": "parent", "thread_token_usage": token_counts()}))
    elif mutation == "fork":
        events[0]["payload"]["forked_from_id"] = "parent"
    elif mutation == "unknown_usage":
        events[4]["payload"]["info"]["total_token_usage"]["new_tokens"] = 9
    elif mutation == "rollback":
        events.append(event("event_msg", {"type": "thread_rolled_back"}))
    elif mutation == "unknown_event":
        events.append(event("new_accounting_type", {}))
    elif mutation == "new_usage_event":
        events.append(event("event_msg", {"type": "new_token_usage"}))
    data = encode(events)
    if mutation == "malformed":
        data = b"BAD JSON\n" + data
    with pytest.raises(ValueError):
        parse_rollout(data)


def test_import_upserts_growing_session_skips_copies_and_preserves_on_error(tmp_path):
    path = tmp_path / "rollout-example.jsonl"
    ledger = tmp_path / "ledger.jsonl"
    initial = encode(rollout_events())
    path.write_bytes(initial)
    assert import_sessions([path], ledger)["added"] == 1
    saved = ledger.read_bytes()
    assert import_sessions([path], ledger)["unchanged"] == 1
    assert saved == ledger.read_bytes()
    events = [event("event_msg", {"type": "task_started", "turn_id": "turn-2"}),
              token_event(token_counts(200, 60, 30)),
              event("event_msg", {"type": "task_complete", "turn_id": "turn-2", "duration_ms": 3000})]
    path.write_bytes(initial + encode(events))
    assert import_sessions([path], ledger)["updated"] == 1
    records = read_records(ledger)
    assert len(records) == 1
    assert records[0]["usage"]["input_tokens"]["value"] == 200
    assert records[0]["agent_seconds"] == 5
    old = tmp_path / "older.jsonl"
    old.write_bytes(initial)
    assert import_sessions([old], ledger)["older_copy_skipped"] == 1
    saved = ledger.read_bytes()
    path.write_bytes(initial.replace(b'"gpt-6-sol"', b'"other-model"') + encode(events))
    with pytest.raises(ValueError, match="history changed"):
        import_sessions([path], ledger)
    assert saved == ledger.read_bytes()


def test_import_batch_is_atomic_and_source_cannot_be_overwritten(tmp_path):
    good = tmp_path / "a.jsonl"
    bad = tmp_path / "b.jsonl"
    ledger = tmp_path / "ledger.jsonl"
    good.write_bytes(encode(rollout_events()))
    bad.write_text("INVALID\n")
    with pytest.raises(ValueError):
        import_sessions([good, bad], ledger)
    assert not ledger.exists()
    with pytest.raises(ValueError, match="overwrite"):
        import_sessions([good], good)


def test_model_switch_is_visible_and_unpriced():
    events = rollout_events()
    events.insert(-1, event("turn_context", {"model": "gpt-6-astra"}))
    record = parse_rollout(encode(events))
    assert record["model_identity_status"] == "mixed"
    assert estimate(record, load_prices(ROOT / "configs/pricing.toml"))[0] is None
    assert "mixed" in render_summary([record], summarize([record], ["model"]))


def test_prices_count_cached_and_reasoning_subsets_once():
    table = load_prices(ROOT / "configs/pricing.toml")
    record = parse_rollout(encode(rollout_events()))
    amount, basis = estimate(record, table)
    assert amount == Decimal("0.000328")  # 60*2 + 40*.2 + 20*10, per million
    assert "unconfirmed" in basis
    assert estimate(record, table, "long")[0] == Decimal("0.000556")
    record["usage"]["cache_write_input_tokens"]["value"] = 10
    assert estimate(record, table)[0] == Decimal("0.000333")
    record["usage"]["cache_write_input_tokens"]["value"] = 90
    assert estimate(record, table)[0] is None


@pytest.mark.parametrize("change", ["unknown_model", "missing_cache", "incomplete", "rerouted"])
def test_unpriceable_records_are_unknown_not_zero(change):
    record = priced_record()
    if change == "unknown_model":
        record["model"] = "gpt-6-sol-unlisted"
    elif change == "missing_cache":
        record["usage"]["cached_input_tokens"]["value"] = None
    elif change == "incomplete":
        record["usage"]["status"] = "incomplete"
    else:
        record["environment_observations"]["model_rerouted"] = True
    assert estimate(record, load_prices(ROOT / "configs/pricing.toml"))[0] is None


def test_price_table_requires_date_source_and_finite_rates(tmp_path):
    source = (ROOT / "configs/pricing.toml").read_text()
    for old, new in [('as_of = "2026-10-05"', 'as_of = "invalid"'), ('input = "2.00"', 'input = "NaN"'),
                     ('input = "2.00"', 'input = "-1"'), ('currency = "USD"', 'currency = "INR"')]:
        table = tmp_path / "prices.toml"
        table.write_text(source.replace(old, new, 1))
        with pytest.raises(ValueError):
            load_prices(table)


def test_summary_retains_failures_coverage_unknown_days_and_denominator():
    first, second = synthetic_demo()
    second["verification"]["passed"] = False
    second["outcome"] = "failed"
    first["started_at"] = "2026-10-05T01:00:00+05:30"
    rows = summarize([first, second], ["model", "task", "day"])
    total = rows[0]
    assert total["tokens_per_verified_success"] == 493
    assert total["failed"] == 1
    assert {r["group"] for r in rows if r["dimension"] == "day"} == {"2026-10-04", "unknown"}
    second["usage"]["input_tokens"]["value"] = None
    rows = summarize([first, second], ["model"])
    assert rows[0]["input_tokens"] == 200
    assert rows[0]["input_tokens_coverage"] == "1/2"
    assert rows[0]["tokens_per_verified_success"] is None
    second["verification"]["passed"] = None
    assert summarize([first, second], [])[0]["unverified"] == 1


def test_duplicate_collection_and_conflicts(tmp_path):
    records = synthetic_demo()
    write_records(tmp_path / "one/runs.jsonl", records)
    write_records(tmp_path / "two/runs.jsonl", records)
    unique, duplicate_count = load_collection([tmp_path])
    assert len(unique) == 2 and duplicate_count == 2
    altered = copy.deepcopy(records[0])
    altered["model"] = "other"
    with pytest.raises(ValueError, match="conflicting"):
        unique_records([records[0], altered])


def test_verdict_does_not_turn_compression_into_savings():
    a, b = synthetic_demo()
    b["usage"]["input_tokens"]["value"] = 400
    assert "Used more tokens" in comparison_verdict([a], [b])
    b["verification"]["passed"] = False
    assert "verification failed" in comparison_verdict([a], [b])
    b["verification"]["passed"] = True
    b["environment_observations"]["control_hash"] = "different"
    assert "Insufficient evidence" in comparison_verdict([a], [b])


def test_model_identity_and_price_assumptions_are_in_report():
    record = priced_record()
    assert model_identity(record) == ("gpt-6-sol", "unknown", "unconfirmed")
    document = render_markdown([record], prices=load_prices(ROOT / "configs/pricing.toml"))
    assert "Confirmed effective model" in document
    assert "not the Codex bill" in document
    assert "cache writes assumed zero" in document
    assert "2026-10-05" in document
    record["effective_model"] = "gpt-6-luna"
    record["model_identity_status"] = "confirmed"
    assert model_identity(record)[1] == "gpt-6-luna"


def test_all_offline_commands_never_spawn_process_or_network(tmp_path):
    path = tmp_path / "rollout-example.jsonl"
    path.write_bytes(encode(rollout_events()))
    ledger = tmp_path / "imported/runs.jsonl"
    records = tmp_path / "synthetic/runs.jsonl"
    write_records(records, synthetic_demo())
    out = tmp_path / "summary.md"
    with patch("agent_cost_lab.cli.execute", side_effect=AssertionError("agent execution")), \
         patch.object(subprocess, "Popen", side_effect=AssertionError("subprocess")), \
         patch.object(socket, "socket", side_effect=AssertionError("network")):
        assert main(["import-codex", str(path), "--ledger", str(ledger)]) == 0
        assert main(["summary", str(ledger), "--prices", str(ROOT / "configs/pricing.toml"), "--out", str(out)]) == 0
        assert main(["report", str(records), "--prices", str(ROOT / "configs/pricing.toml"), "--out", str(tmp_path / "report.md")]) == 0
        assert main(["compare", str(records), str(records), "--out", str(tmp_path / "compare.md")]) == 0
    assert out.with_suffix(".csv").exists()
    assert "unknown" in out.read_text()  # imported task success is unverified
