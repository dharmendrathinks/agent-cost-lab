"""Managed Headroom proxy lifecycle; project-local dependency only."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from .codex import CONFLICTING_ENV, installed_version as codex_version, stop_owned_process
from .verifier import _literal, _profile, sandbox_available

PINNED_VERSION = "0.39.1"
DECLARED_SETTINGS = "coding profile; cache-preserving compression; local telemetry; no semantic cache, routing, learning, memory, tool search, output shaping, Kompress, model downloads, or proxy retries"

# macOS's resolver follows /etc and /var aliases and contacts configd. These
# grants apply only to the trusted proxy, never candidate verification/tools.
PROXY_DNS_PERMISSIONS = '''
(allow mach-lookup
  (global-name "com.apple.SystemConfiguration.DNSConfiguration")
  (global-name "com.apple.SystemConfiguration.configd"))
(allow file-read-metadata
  (literal "/etc") (literal "/var") (literal "/var/run")
  (literal "/private/etc") (literal "/private/var/run")
  (literal "/private/var/run/mDNSResponder"))
(allow file-read*
  (literal "/private/etc/resolv.conf")
  (literal "/private/var/run/resolv.conf")
  (literal "/private/etc/hosts") (literal "/private/etc/services"))
'''


class HeadroomBlocker(RuntimeError):
    pass


def compatibility_path(project_root: Path) -> Path:
    local = project_root / "configs/headroom-compatibility.local.toml"
    return local if local.is_file() else project_root / "configs/headroom-compatibility.toml"


def local_executable(project_root: Path) -> Path | None:
    path = project_root / ".venv" / "bin" / "headroom"
    return path if path.is_file() and os.access(path, os.X_OK) else None


def installed_version(project_root: Path) -> str | None:
    path = local_executable(project_root)
    if path is None:
        return None
    try:
        result = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"\b(\d+\.\d+\.\d+)\b", result.stdout + result.stderr)
    return match.group(1) if result.returncode == 0 and match else None


def compatibility_blockers(project_root: Path) -> list[str]:
    blockers = []
    version = installed_version(project_root)
    if version is None:
        blockers.append("project-local Headroom is not installed")
    elif version != PINNED_VERSION:
        blockers.append("Headroom version differs from inspected 0.39.1")
    else:
        executable = local_executable(project_root)
        assert executable is not None
        for arguments, required in (
            (["proxy", "--help"], {"--host", "--port", "--mode", "--telemetry", "--no-cache", "--no-learn", "--no-memory-tools", "--no-memory-context", "--disable-kompress", "--disable-kompress-fallback", "--no-rate-limit", "--no-subscription-tracking", "--retry-max-attempts"}),
            (["mcp", "serve", "--help"], {"--proxy-url"}),
        ):
            try:
                result = subprocess.run([str(executable), *arguments], capture_output=True, text=True, timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                blockers.append("Headroom CLI option check could not complete")
                continue
            if result.returncode != 0 or not required.issubset(set(re.findall(r"--[a-z-]+", result.stdout))):
                blockers.append("installed Headroom CLI lacks required managed-integration options")
    file = compatibility_path(project_root)
    if not file.is_file():
        blockers.append("Headroom compatibility gate file is missing")
        return blockers
    state = tomllib.loads(file.read_text())
    if state.get("codex_version") != codex_version() or state.get("headroom_version") != PINNED_VERSION:
        blockers.append("compatibility record targets different versions")
    for key in ("subscription_routing_validated", "compression_status_validated", "retrieval_validated", "events_and_usage_validated", "cleanup_validated", "effective_settings_validated"):
        if state.get(key) is not True:
            blockers.append("Headroom live gate pending: " + key)
    description = state.get("effective_settings")
    if state.get("effective_settings_validated") is True and (not isinstance(description, str) or not description.strip()):
        blockers.append("validated effective settings description is missing")
    return blockers


def _port() -> int:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _json_get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=1) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise HeadroomBlocker("Headroom endpoint returned unsupported shape")
    return value


class ManagedHeadroom:
    """Start the upstream proxy; provide per-run Codex overrides and cleanup."""

    def __init__(self, project_root: Path, state: Path, *, validation_probe: bool = False):
        self.project_root = project_root
        self.state = state
        self.validation_probe = validation_probe
        self.process: subprocess.Popen | None = None
        self.port: int | None = None
        self.initial_stats: dict | None = None
        self.effective_health: dict = {}

    @property
    def url(self) -> str:
        if self.port is None:
            raise HeadroomBlocker("Headroom proxy is not started")
        return f"http://127.0.0.1:{self.port}"

    @property
    def declared_settings(self) -> str:
        return DECLARED_SETTINGS

    def __enter__(self) -> "ManagedHeadroom":
        if CONFLICTING_ENV & set(os.environ):
            raise HeadroomBlocker("API credentials or endpoint overrides are present; subscription-only mode requires an uncontaminated environment")
        blockers = compatibility_blockers(self.project_root)
        if self.validation_probe:
            blockers = [blocker for blocker in blockers if not blocker.startswith("Headroom live gate pending:")]
        if blockers:
            raise HeadroomBlocker("; ".join(blockers))
        executable = local_executable(self.project_root)
        assert executable is not None
        if not sandbox_available():
            raise HeadroomBlocker("restricted proxy boundary is unavailable")
        self.state.mkdir(parents=True, exist_ok=False)
        self.port = _port()
        proxy_profile = self.state / "proxy.sb"
        proxy_profile.write_text(
            _profile(self.project_root / ".venv", self.state, Path(sys.executable))
            + "(allow file-read* (subpath " + _literal(self.state) + "))\n"
            + "(allow network*)\n"
            + PROXY_DNS_PERMISSIONS
        )
        # Inherited Headroom feature/endpoint knobs would confound the treatment.
        environment = {key: value for key, value in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE"}}
        environment.update({
            "HOME": str(self.state), "TMPDIR": str(self.state),
            "XDG_CACHE_HOME": str(self.state / "cache"),
            "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
            "HEADROOM_CONFIG_DIR": str(self.state),
            "HEADROOM_WORKSPACE_DIR": str(self.state),
            "HEADROOM_SAVINGS_PATH": str(self.state / "savings.json"),
            "HEADROOM_SAVINGS_PROFILE": "coding",
            "HEADROOM_BEACON": "off",
            "DO_NOT_TRACK": "1",
            "HEADROOM_TELEMETRY": "on",
            "HEADROOM_MODEL_ROUTER_ENABLED": "0",
            "HEADROOM_TOOL_SEARCH": "0",
            "HEADROOM_DISABLE_KOMPRESS": "1",
            "HEADROOM_DISABLE_KOMPRESS_FALLBACK": "1",
            "HEADROOM_OUTPUT_SHAPER": "0",
            "HEADROOM_ROLLOUT_CHANNEL": "stable",
            "HEADROOM_LOG_MESSAGES": "0",
            "HEADROOM_SKIP_UPSTREAM_CHECK": "1",
            "HEADROOM_FORCE_KOMPRESS_ALL": "0",
            "HEADROOM_LOG_PAYLOAD_PREVIEW": "off",
        })
        # Headroom's WebSocket stack uses Python's default TLS context, whose
        # macOS CA path is outside this boundary. Use the installed dependency's
        # public CA bundle for both HTTP and WebSocket TLS; verification stays on.
        ca_bundle = self.project_root / ".venv/lib/python3.12/site-packages/certifi/cacert.pem"
        if not ca_bundle.is_file():
            self.__exit__(None, None, None)
            raise HeadroomBlocker("project-local public TLS CA bundle is unavailable")
        environment["SSL_CERT_FILE"] = str(ca_bundle)
        environment.pop("SSL_CERT_DIR", None)
        environment.pop("REQUESTS_CA_BUNDLE", None)
        command = ["sandbox-exec", "-f", str(proxy_profile), str(executable), "proxy", "--host", "127.0.0.1", "--port", str(self.port), "--mode", "cache", "--telemetry", "--no-cache", "--no-learn", "--no-memory-tools", "--no-memory-context", "--disable-kompress", "--disable-kompress-fallback", "--no-rate-limit", "--no-subscription-tracking", "--retry-max-attempts", "1"]
        try:
            probe = subprocess.run(
                ["sandbox-exec", "-f", str(proxy_profile),
                 str(self.project_root / ".venv/bin/python"), "-c",
                 'import socket, ssl; socket.getaddrinfo("chatgpt.com", 443); '
                 'assert ssl.create_default_context().get_ca_certs()'],
                cwd=self.state, env=environment, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=8,
            )
            if probe.returncode != 0:
                raise HeadroomBlocker("restricted proxy DNS or TLS trust readiness failed")
            self.process = subprocess.Popen(command, cwd=self.state, env=environment, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise HeadroomBlocker("Headroom proxy exited during startup")
                try:
                    health = _json_get(self.url + "/health")
                    config = health.get("config", {})
                    if health.get("status") == "healthy" and health.get("version") == PINNED_VERSION and isinstance(config, dict) and config.get("optimize") is True:
                        expected = {"cache": False, "memory": False, "learn": False, "disable_kompress": True, "disable_kompress_fallback": True, "code_graph": False}
                        if any(config.get(key) is not value for key, value in expected.items()):
                            raise HeadroomBlocker("Headroom effective health settings differ from the declared treatment")
                        self.effective_health = {key: config[key] for key in expected}
                        runtime = config.get("runtime_env", {})
                        if config.get("savings_profile") != "coding" or not isinstance(runtime, dict) or runtime.get("HEADROOM_OUTPUT_SHAPER") != "0":
                            raise HeadroomBlocker("Headroom profile or output shaping differs from the declared treatment")
                        for key in ("savings_profile", "rate_limit", "target_ratio", "compress_user_messages", "compress_system_messages", "protect_recent", "protect_analysis_context", "min_tokens_to_crush", "max_items_after_crush", "smart_crusher_with_compaction", "force_kompress", "accuracy_guard"):
                            self.effective_health[key] = config.get(key)
                        self.effective_health["output_shaper"] = runtime["HEADROOM_OUTPUT_SHAPER"]
                        self.initial_stats = _json_get(self.url + "/stats")
                        return self
                except (urllib.error.URLError, TimeoutError, ValueError, HeadroomBlocker):
                    pass
                time.sleep(0.2)
            raise HeadroomBlocker("Headroom readiness was not established")
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def prepare_mcp_profile(self, mcp_state: Path) -> Path:
        profile = mcp_state / "mcp.sb"
        profile.write_text(
            _profile(self.project_root / ".venv", mcp_state, Path(sys.executable))
            + "(allow file-read* (subpath " + _literal(mcp_state) + "))\n"
            + "(allow network*)\n"
        )
        return profile

    def codex_overrides(self, mcp_state: Path, mcp_profile: Path) -> tuple[str, ...]:
        executable = local_executable(self.project_root)
        if executable is None:
            raise HeadroomBlocker("Headroom executable disappeared")
        return (
            "openai_base_url=" + json.dumps(self.url + "/v1"),
            "mcp_servers.headroom.command=" + json.dumps("/usr/bin/sandbox-exec"),
            "mcp_servers.headroom.cwd=" + json.dumps(str(mcp_state)),
            "mcp_servers.headroom.required=true",
            "mcp_servers.headroom.args=" + json.dumps(["-f", str(mcp_profile), str(executable), "mcp", "serve", "--proxy-url", self.url]),
            'mcp_servers.headroom.enabled_tools=["headroom_retrieve"]',
            "mcp_servers.headroom.env.HEADROOM_PROXY_URL=" + json.dumps(self.url),
            "mcp_servers.headroom.env.HEADROOM_CONFIG_DIR=" + json.dumps(str(mcp_state)),
            "mcp_servers.headroom.env.HEADROOM_WORKSPACE_DIR=" + json.dumps(str(mcp_state)),
            'mcp_servers.headroom.env.HEADROOM_MCP_READ="off"',
            'mcp_servers.headroom.env.HF_HUB_OFFLINE="1"',
            "mcp_servers.headroom.env.HOME=" + json.dumps(str(mcp_state)),
            "mcp_servers.headroom.env.TMPDIR=" + json.dumps(str(mcp_state)),
        )

    def observations(self) -> dict:
        current = _json_get(self.url + "/stats")
        stats = current
        previous = self.initial_stats or {}
        if not isinstance(stats, dict):
            stats = {}
        if not isinstance(previous, dict):
            previous = {}
        def delta(section: str, name: str):
            after = stats.get(section, {}).get(name) if isinstance(stats.get(section), dict) else None
            before = previous.get(section, {}).get(name) if isinstance(previous.get(section), dict) else None
            return after - before if type(after) is int and type(before) is int and after >= before else None
        gate = tomllib.loads(compatibility_path(self.project_root).read_text())
        effective = gate.get("effective_settings") if gate.get("effective_settings_validated") is True else None
        return {
            "declared_settings": self.declared_settings,
            "effective_settings": effective,
            "effective_health_settings": self.effective_health,
            "proxy_total_requests": delta("requests", "total"),
            "proxy_tokens_saved_estimate": delta("tokens", "proxy_compression_saved"),
            "codex_ws": {key: delta("codex_ws", key) for key in (
                "units_total", "units_modified_total", "frames_attempted_total",
                "frames_compressed_total", "frames_failed_total",
                "unit_tokens_saved_sum", "frame_tokens_saved_sum",
            )},
            "measurement_source": "Headroom 0.39.1 /stats cumulative counter deltas",
        }

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        if self.process is not None:
            stop_owned_process(self.process)
            self.process = None
        # Retain state only until after metrics collection; normalized reports omit proxy traffic.
        if self.state.exists():
            shutil.rmtree(self.state)
