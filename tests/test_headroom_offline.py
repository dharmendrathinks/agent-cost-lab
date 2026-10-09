"""Synthetic endpoint responses only; no proxy, model, or agent is launched."""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from agent_cost_lab.headroom import ManagedHeadroom, PINNED_VERSION


def backend(tmp_path):
    gate = tmp_path / "configs/headroom-compatibility.toml"
    gate.parent.mkdir()
    gate.write_text('effective_settings_validated = false\neffective_settings = ""\n')
    return ManagedHeadroom(tmp_path, tmp_path / "proxy")


def test_nested_cumulative_counters_not_obsolete_top_level_fields(tmp_path):
    managed = backend(tmp_path)
    managed.port = 12345
    managed.initial_stats = {"requests": {"total": 4}, "tokens": {"proxy_compression_saved": 10}, "codex_ws": {"frames_attempted_total": 2}}
    current = {"total_requests": 999, "tokens_saved": 999,
               "requests": {"total": 7}, "tokens": {"proxy_compression_saved": 12},
               "codex_ws": {"frames_attempted_total": 5}}
    with patch("agent_cost_lab.headroom._json_get", return_value=current):
        observations = managed.observations()
    assert observations["proxy_total_requests"] == 3
    assert observations["proxy_tokens_saved_estimate"] == 2
    assert observations["codex_ws"]["frames_attempted_total"] == 3
    assert observations["codex_ws"]["units_modified_total"] is None
    assert observations["effective_settings"] is None


def test_invalid_or_missing_counters_stay_unknown(tmp_path):
    managed = backend(tmp_path)
    managed.port = 12345
    managed.initial_stats = {"requests": {"total": 4}, "tokens": {"proxy_compression_saved": 10}}
    for current in ({}, {"requests": {"total": 3}}, {"requests": {"total": True}}, {"requests": {"total": "9"}}):
        with patch("agent_cost_lab.headroom._json_get", return_value=current):
            observed = managed.observations()
        assert observed["proxy_total_requests"] is None
        assert observed["proxy_tokens_saved_estimate"] is None


def test_retrieval_is_required_and_has_an_owned_working_directory(tmp_path):
    managed = backend(tmp_path)
    managed.port = 12345
    state = tmp_path / "mcp"
    executable = tmp_path / ".venv/bin/headroom"
    with patch("agent_cost_lab.headroom.local_executable", return_value=executable):
        overrides = dict(item.split("=", 1) for item in managed.codex_overrides(state, state / "mcp.sb"))
    assert json.loads(overrides["mcp_servers.headroom.cwd"]) == str(state)
    assert json.loads(overrides["openai_base_url"]) == "http://127.0.0.1:12345/v1"
    assert overrides["mcp_servers.headroom.required"] == "true"
    assert json.loads(overrides["mcp_servers.headroom.enabled_tools"]) == ["headroom_retrieve"]
    assert json.loads(overrides["mcp_servers.headroom.env.HOME"]) == str(state)
    assert json.loads(overrides["mcp_servers.headroom.env.HEADROOM_MCP_READ"]) == "off"
    assert "wrap" not in json.loads(overrides["mcp_servers.headroom.args"])


def test_managed_startup_isolates_inherited_settings_and_preserves_tls(tmp_path):
    managed = backend(tmp_path)
    ca = tmp_path / ".venv/lib/python3.12/site-packages/certifi/cacert.pem"
    ca.parent.mkdir(parents=True)
    ca.write_text("synthetic CA path fixture; never used for a real TLS connection")
    settings = {"optimize": True, "cache": False, "memory": False, "learn": False,
                "disable_kompress": True, "disable_kompress_fallback": True,
                "code_graph": False, "savings_profile": "coding",
                "runtime_env": {"HEADROOM_OUTPUT_SHAPER": "0"}}
    with patch.dict(os.environ, {"PATH": "/usr/bin:/bin", "HEADROOM_FORCE_KOMPRESS_ALL": "1", "HEADROOM_MODEL_ROUTER_ENABLED": "1", "UNRELATED_SECRET": "synthetic-do-not-inherit"}, clear=True), \
         patch("agent_cost_lab.headroom.compatibility_blockers", return_value=[]), \
         patch("agent_cost_lab.headroom.local_executable", return_value=tmp_path / ".venv/bin/headroom"), \
         patch("agent_cost_lab.headroom.sandbox_available", return_value=True), \
         patch("agent_cost_lab.headroom._port", return_value=12345), \
         patch("agent_cost_lab.headroom.subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as probe, \
         patch("agent_cost_lab.headroom.subprocess.Popen") as launch, \
         patch("agent_cost_lab.headroom.stop_owned_process"), \
         patch("agent_cost_lab.headroom._json_get", side_effect=[{"status": "healthy", "version": PINNED_VERSION, "config": settings}, {"requests": {"total": 0}}]):
        launch.return_value.poll.return_value = None
        with managed:
            env = launch.call_args.kwargs["env"]
            assert "UNRELATED_SECRET" not in env
            assert env["HEADROOM_FORCE_KOMPRESS_ALL"] == "0"
            assert env["HEADROOM_MODEL_ROUTER_ENABLED"] == "0"
            assert env["HEADROOM_DISABLE_KOMPRESS_FALLBACK"] == "1"
            assert env["HF_HUB_OFFLINE"] == "1"
            assert env["SSL_CERT_FILE"] == str(ca)
            assert managed.effective_health["cache"] is False
            assert probe.call_args.kwargs["env"] == env
    assert not managed.state.exists()
