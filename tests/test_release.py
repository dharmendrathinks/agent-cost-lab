"""Public defaults, installed CLI behavior, and exported-label regressions."""

import csv
import shutil
import socket
import subprocess
import sys
import tomllib
from pathlib import Path
from unittest.mock import patch

from agent_cost_lab.cli import _parser, main, project_root, synthetic_demo
from agent_cost_lab.headroom import compatibility_blockers, compatibility_path
from agent_cost_lab.reporting import write_csv
from agent_cost_lab.summary import summarize, write_summary_csv

ROOT = Path(__file__).resolve().parents[1]


def test_fresh_checkout_leaves_all_live_gates_pending(tmp_path):
    config = tmp_path / "configs"
    config.mkdir()
    source = ROOT / "configs/headroom-compatibility.toml"
    shutil.copyfile(source, config / source.name)
    public = tomllib.loads(source.read_text())
    gates = [key for key in public if key.endswith("_validated")]
    assert len(gates) == 6
    assert all(public[key] is False for key in gates)
    with patch("agent_cost_lab.headroom.installed_version", return_value=None), \
         patch("agent_cost_lab.headroom.codex_version", return_value="0.160.0"):
        blockers = compatibility_blockers(tmp_path)
    assert sum(message.startswith("Headroom live gate pending:") for message in blockers) == 6
    local = config / "headroom-compatibility.local.toml"
    local.write_text('codex_version = "0.160.0"\n')
    assert compatibility_path(tmp_path) == local


def test_installed_cli_uses_cwd_and_blocks_live_commands_without_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("agent_cost_lab.cli.__file__", str(tmp_path / "installed/site-packages/agent_cost_lab/cli.py")):
        assert project_root() == tmp_path
    assert _parser().parse_args(["import-codex", "selected.jsonl"]).ledger == tmp_path / "artifacts/imported-codex/runs.jsonl"
    with patch("agent_cost_lab.cli.ROOT", tmp_path), \
         patch.object(subprocess, "Popen", side_effect=AssertionError("unexpected subprocess")), \
         patch.object(socket, "socket", side_effect=AssertionError("unexpected network")):
        assert main(["doctor"]) == 2
        assert main(["demo-report", "--out", str(tmp_path / "demo.md")]) == 0


def test_csv_exports_escape_formula_labels_but_preserve_numeric_values(tmp_path):
    records = synthetic_demo()
    records[0]["task_id"] = "\t=1+1"
    records[0]["model"] = "+formula"
    target = tmp_path / "runs.csv"
    write_csv(target, records)
    with target.open() as stream:
        row = next(csv.DictReader(stream))
    assert row["task_id"] == "'\t=1+1"
    assert row["requested_model"] == "'+formula"
    assert row["input_tokens"] == "200"
    rows = summarize(records, ["task"])
    write_summary_csv(target, rows)
    with target.open() as stream:
        data = list(csv.DictReader(stream))
    assert any(row["group"] == "'\t=1+1" for row in data)


def test_import_without_codex_or_headroom_installation(tmp_path):
    # Exercise a fresh Python interpreter with no CLI executables on its PATH.
    result = subprocess.run([sys.executable, "-m", "agent_cost_lab.cli", "demo-report", "--out", str(tmp_path / "demo.md")],
                            cwd=tmp_path, env={"PATH": "/nonexistent", "PYTHONPATH": str(ROOT / "src")},
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "SYNTHETIC" in (tmp_path / "demo.md").read_text()
