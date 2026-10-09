"""Small CLI; dry-run and CI never start agents or proxies."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from .codex import auth_method, installed_version as codex_version
from .controller import declared_blockers, execute
from .headroom import installed_version as headroom_version
from .records import Measurement, RunRecord, Usage, VerificationResult
from .reporting import read_records, render_markdown, write_csv
from .pricing import load_prices
from .importing import import_sessions
from .summary import load_collection, render_summary, summarize, write_summary_csv
from .tasks import load_task
from .verifier import sandbox_available

def project_root() -> Path:
    """A source checkout owns live fixtures; an installed CLI uses the current directory."""
    source = Path(__file__).resolve().parents[2]
    return source if (source / "pyproject.toml").is_file() and (source / "tasks").is_dir() else Path.cwd()


ROOT = project_root()


def require_checkout() -> None:
    if not all((ROOT / name).is_dir() for name in ("tasks", "fixtures/timeledger", "verification", "configs")):
        raise ValueError("live commands and doctor require the source checkout; run from its root or use ./agent-cost-lab")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent-cost-lab")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Inspect installed capabilities without running an agent")
    for name in ("optimize", "run", "headroom-check"):
        sub = commands.add_parser(name)
        sub.add_argument("--task", type=Path)
        if name == "run":
            sub.add_argument("--config", type=Path, help="Optional TOML with task and execution defaults")
        if name == "headroom-check":
            sub.add_argument("--baseline-records", type=Path, help="Real verified baseline pilot JSONL")
        sub.add_argument("--model")
        sub.add_argument("--reasoning", default="medium")
        sub.add_argument("--max-runs", type=int, default=2 if name == "optimize" else 1)
        sub.add_argument("--timeout", type=int, default=600)
        sub.add_argument("--verifier-timeout", type=int, default=60)
        sub.add_argument("--max-total-seconds", type=int, default=1800 if name == "optimize" else 900)
        sub.add_argument("--dry-run", action="store_true")
        sub.add_argument("--artifacts", type=Path, default=ROOT / "artifacts")
    report = commands.add_parser("report")
    report.add_argument("path", type=Path)
    report.add_argument("--out", type=Path, help="Markdown destination; also writes an adjacent CSV")
    compare = commands.add_parser("compare")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("optimized", type=Path)
    compare.add_argument("--out", type=Path, help="Markdown destination; also writes an adjacent CSV")
    summary = commands.add_parser("summary", help="Summarize saved usage offline; never starts an agent")
    summary.add_argument("paths", nargs="+", type=Path, help="JSONL ledgers or directories searched for runs.jsonl")
    summary.add_argument("--group-by", nargs="+", choices=("model", "task", "day"), default=["model", "task", "day"])
    summary.add_argument("--out", type=Path, help="Markdown destination; also writes an adjacent CSV")
    for sub in (report, compare, summary):
        sub.add_argument("--prices", type=Path, help="Optional local TOML price snapshot for API-equivalent estimates")
        sub.add_argument("--context", choices=("short", "long"), default="short", help="Assumed API context tier; default short, not inferred from thread totals")
    importer = commands.add_parser("import-codex", help="Import selected Codex rollout logs offline")
    importer.add_argument("paths", nargs="+", type=Path, help="Rollout JSONL files or directories searched for rollout-*.jsonl")
    importer.add_argument("--ledger", type=Path, default=Path.cwd() / "artifacts/imported-codex/runs.jsonl")
    importer.add_argument("--task-label", default="codex-session", help="Non-sensitive task identifier; imported sessions remain unverified")
    demo = commands.add_parser("demo-report")
    demo.add_argument("--out", type=Path, required=True)
    return parser


def _measurement(value: int, name: str) -> Measurement:
    return Measurement(value, "tokens", "synthetic.fixture." + name, "thread_total", "complete")


def synthetic_demo() -> list[dict]:
    """Illustrative records only. These numbers were invented for parser/report UI tests."""
    records = []
    for config, input_tokens, cached, output, agent, total, passed in (
        ("codex_baseline", 200, 20, 55, 35.0, 42.0, True),
        ("codex_headroom", 180, 25, 58, 39.0, 49.0, True),
    ):
        usage = Usage(
            input_tokens=_measurement(input_tokens, "input"),
            cached_input_tokens=_measurement(cached, "cached_input"),
            output_tokens=_measurement(output, "output"),
            status="complete",
            raw_snapshot={"input_tokens": input_tokens, "cached_input_tokens": cached, "output_tokens": output},
            terminal_events=1,
        )
        record = RunRecord(
            task_id="fix-midnight", run_id="synthetic-" + config, pair_id="synthetic-pair",
            attempt_id="synthetic-" + config, configuration=config, fixture_hash="synthetic", fixture_commit="synthetic",
            task_hash="synthetic", verifier_hash="synthetic", config_hash="synthetic",
            agent_version="synthetic", model="synthetic-model", reasoning="medium",
            billing_mode="subscription", outcome="synthetic_completed", agent_seconds=agent,
            end_to_end_seconds=total, usage=usage,
            verification=VerificationResult(passed, "passed", 5, 5),
            treatment_status="active_proxy_estimate" if config == "codex_headroom" else "not_applicable",
            optimizer_engine="Headroom" if config == "codex_headroom" else None,
            optimizer_version="synthetic" if config == "codex_headroom" else None,
            optimizer_observations={"declared_settings": "synthetic demonstration only", "effective_settings": "synthetic demonstration only"},
            environment_observations={"control_hash": "synthetic-controls"},
            source_kind="synthetic",
        )
        records.append(record.to_dict())
    return records


def _config_defaults(args, explicit_args: list[str]) -> None:
    if args.command != "run" or args.config is None:
        return
    raw = tomllib.loads(args.config.read_text())
    allowed = {"task", "model", "reasoning", "max_runs", "timeout", "verifier_timeout", "max_total_seconds"}
    if set(raw) - allowed:
        raise ValueError("unsupported run config fields")
    if args.task is None and "task" in raw:
        args.task = Path(raw["task"])
    if args.model is None and "model" in raw:
        args.model = raw["model"]
    for field in ("reasoning", "max_runs", "timeout", "verifier_timeout", "max_total_seconds"):
        if field in raw and "--" + field.replace("_", "-") not in explicit_args:
            setattr(args, field, raw[field])


def main(argv: list[str] | None = None) -> int:
    explicit_args = list(argv) if argv is not None else sys.argv[1:]
    args = _parser().parse_args(explicit_args)
    try:
        if args.command in {"doctor", "run", "optimize", "headroom-check"}:
            require_checkout()
        if args.command == "import-codex":
            result = import_sessions(args.paths, args.ledger, task_label=args.task_label)
            print(json.dumps({**result, "ledger": str(args.ledger), "agent_or_api_started": False}, indent=2))
            return 0
        if args.command == "summary":
            records, duplicates = load_collection(args.paths)
            prices = load_prices(args.prices) if args.prices else None
            rows = summarize(records, list(dict.fromkeys(args.group_by)), prices=prices, context=args.context)
            document = render_summary(records, rows, duplicates=duplicates, prices=prices, context=args.context)
            if args.out:
                if args.out.suffix.lower() != ".md":
                    raise ValueError("summary output must use the .md suffix")
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(document, encoding="utf-8")
                write_summary_csv(args.out.with_suffix(".csv"), rows)
                print(args.out)
            else:
                print(document)
            return 0
        if args.command == "doctor":
            status = {
                "codex_version": codex_version(), "auth_mode": auth_method(),
                "headroom_project_local_version": headroom_version(ROOT),
                "sandbox_executable_present": sandbox_available(),
                "baseline_blockers": declared_blockers(ROOT, optimized=False),
                "optimization_blockers": declared_blockers(ROOT, optimized=True),
                "note": "No agent, proxy, or model was started. Doctor checks CLI options, restricted boundaries, and buggy/reference fixture verification; live model routing still needs a bounded pilot.",
            }
            print(json.dumps(status, indent=2))
            return 0
        if args.command == "demo-report":
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(render_markdown(synthetic_demo()), encoding="utf-8")
            print(args.out)
            return 0
        if args.command in ("report", "compare"):
            paths = [args.path] if args.command == "report" else [args.baseline, args.optimized]
            records = []
            for path in paths:
                records.extend(read_records(path / "runs.jsonl" if path.is_dir() else path))
            prices = load_prices(args.prices) if args.prices else None
            document = render_markdown(records, prices=prices, context=args.context)
            if args.out:
                if args.out.suffix.lower() == ".csv":
                    raise ValueError("Markdown output must not use the .csv suffix")
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(document, encoding="utf-8")
                write_csv(args.out.with_suffix(".csv"), records, prices=prices, context=args.context)
            else:
                print(document)
            return 0
        _config_defaults(args, explicit_args)
        if args.task is None:
            raise ValueError("--task is required")
        task = load_task(args.task, ROOT)
        optimized = args.command in ("optimize", "headroom-check")
        validation_probe = args.command == "headroom-check"
        if not all(type(value) is int and value > 0 for value in (args.max_runs, args.timeout, args.verifier_timeout, args.max_total_seconds)):
            raise ValueError("run and timeout limits must be positive integers")
        if validation_probe and args.max_runs != 1:
            raise ValueError("headroom-check requires --max-runs 1")
        if args.command == "optimize" and (args.max_runs < 2 or args.max_runs % 2):
            raise ValueError("optimize requires an even --max-runs of at least two")
        blockers = declared_blockers(ROOT, optimized=optimized, validation_probe=validation_probe)
        if args.model == "MODEL":
            blockers.append("MODEL is a placeholder; select a real subscription model ID")
        if validation_probe:
            if args.baseline_records is None:
                blockers.append("real baseline pilot records are required before the Headroom check")
            else:
                baseline_path = args.baseline_records / "runs.jsonl" if args.baseline_records.is_dir() else args.baseline_records
                try:
                    baseline = read_records(baseline_path)
                except (OSError, ValueError, json.JSONDecodeError):
                    blockers.append("baseline pilot records are unreadable or unsupported")
                else:
                    eligible = any(
                        record.get("configuration") == "codex_baseline"
                        and record.get("source_kind") == "real"
                        and record.get("task_id") == task.id
                        and record.get("model") == args.model
                        and record.get("outcome") == "completed"
                        and record.get("verification", {}).get("passed") is True
                        and record.get("usage", {}).get("status") == "complete"
                        for record in baseline
                    )
                    if not eligible:
                        blockers.append("baseline pilot lacks a matching verified run with complete telemetry")
        if args.dry_run:
            print(json.dumps({
                "mode": args.command, "task": task.id, "task_hash": task.manifest_hash,
                "model": args.model or "unselected", "reasoning": args.reasoning,
                "max_runs": args.max_runs, "agent_timeout_seconds": args.timeout,
                "verifier_timeout_seconds": args.verifier_timeout,
                "campaign_deadline_seconds": args.max_total_seconds,
                "subscription_attempts": args.max_runs,
                "candidate_patches_applied_to_user_repo": False,
                "validation_probe": validation_probe,
                "blockers": blockers + (["explicit model is required for execution"] if not args.model else []),
                "agent_or_proxy_started": False,
            }, indent=2))
            return 0
        if not args.model:
            raise ValueError("--model is required for execution")
        if blockers:
            raise RuntimeError("execution blocked: " + "; ".join(blockers))
        campaign = execute(task, ROOT, optimized=optimized, model=args.model, reasoning=args.reasoning,
                           max_runs=args.max_runs, timeout=args.timeout, verifier_timeout=args.verifier_timeout,
                           max_total_seconds=args.max_total_seconds, artifacts_root=args.artifacts,
                           validation_probe=validation_probe)
        print(campaign)
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print("agent-cost-lab: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
