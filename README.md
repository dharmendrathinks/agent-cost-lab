# Agent Cost Lab

Agent Cost Lab applies coding-agent context optimizations, runs a comparable baseline, and checks whether the resulting code still passes independent tests.

For continuation status and pending repository steps, read [SESSION_STATE.md](SESSION_STATE.md).

This is an **experimental** project. Offline accounting supports macOS and Linux with Python 3.12 or newer. Live experiments currently require macOS, Python 3.12, a supported Codex CLI, and a working restricted execution boundary. Windows is not supported. See [contributing](CONTRIBUTING.md), [security and data handling](SECURITY.md), and [third-party attribution](THIRD_PARTY_NOTICES.md).

## Install from source

```sh
git clone https://github.com/dharmendrathinks/agent-cost-lab.git
cd agent-cost-lab
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
./agent-cost-lab demo-report --out artifacts/demo.md
```

Installation downloads Python packages; tests and the synthetic demo need no model access, subscription, API key, or Headroom. The fixture intentionally contains bugs for agent tasks; the project's tests verify that behavior. Wheels support offline commands; live commands and `doctor` need the source checkout and its fixtures. Optional Headroom installation is described below.

It also analyzes saved runs and selected Codex session logs **entirely offline**: no API key, paid API request, new agent run, or subscription allowance is needed for reporting. Actual subscription charges and allowance consumption are not measured. Optional API-equivalent estimates use a dated local price table and explicit assumptions.

## Analyze existing usage without running an agent

```sh
# All saved lab runs, deduplicated; group by model, task, and UTC start day.
./agent-cost-lab summary artifacts --out artifacts/offline-summary/report.md

# Optional hypothetical API-equivalent USD; this does not make API calls.
./agent-cost-lab summary artifacts --prices configs/pricing.toml \
  --context short --out artifacts/offline-summary/report.md

# Import a selected supported Codex rollout log (replace the example path).
./agent-cost-lab import-codex /path/to/rollout-session.jsonl \
  --ledger artifacts/imported-codex/runs.jsonl
./agent-cost-lab summary artifacts/imported-codex --out artifacts/imported-codex/summary.md
```

Session import currently supports the inspected **Codex 0.160.0 rollout shape**. It preserves final cumulative usage, skips duplicate copies, updates a growing session in place, and exports no prompts, code, reasoning, tool output, raw session IDs, or account identifiers. Unsupported versions, forks, conflicting history, and malformed input fail explicitly. Imported sessions have **unverified task success** and unknown billing mode. See [offline accounting details](docs/offline-accounting.md) for coverage, mixed models, timestamps, and pricing assumptions.

Reports show requested versus confirmed effective model separately. A matching configured model does not confirm what the server served. Comparison reports lead with the observed token result and verification status; active compression alone is not evidence of a benefit.

The first optimization engine uses [Headroom](https://github.com/headroomlabs-ai/headroom). Agent Cost Lab manages the integration, controlled task execution, verification, and reporting. Headroom supplies its own compression implementation; this project does not claim that algorithm or imply Headroom endorsement. Preserve Headroom's [Apache-2.0 license](https://github.com/headroomlabs-ai/headroom/blob/d13e1966f820220b482a33c30bde1e926743939a/LICENSE) and [NOTICE](https://github.com/headroomlabs-ai/headroom/blob/d13e1966f820220b482a33c30bde1e926743939a/NOTICE) when distributing applicable upstream material.

Agent Cost Lab's own code is [MIT licensed](LICENSE). Codex sends relevant task content to its remote service, and a managed Headroom proxy sees the content routed through it.

The CLI provides `doctor`, `optimize --dry-run`, bounded execution, independent fixture verification, JSONL accounting, and Markdown/CSV reports. The three task manifests share one `timeledger` fixture. One authorized subscription baseline passed all six independent checks on 2026-10-03. A bounded Headroom pilot also passed the same six checks with complete usage and active context compression. Version-specific integration gates are validated on this installation; no general optimization benefit is claimed. See [live evidence](docs/live-validation.md). See [PLAN.md](PLAN.md), [experiment protocol](docs/experiment-protocol.md), and [integration feasibility](docs/integration-feasibility.md).

The accounting adapters cover the source-reviewed Codex versions 0.157.1 and 0.160.0; other versions stop explicitly. The current installation has Codex 0.160.0 and project-local Headroom 0.39.1. Codex's trusted client uses its native restrictive tool/filesystem sandbox; the verifier and retrieval use separate restricted processes. A second OS sandbox around the client proved incompatible on macOS and was removed explicitly. Pending optimization gates never cause an unrestricted or mislabeled baseline fallback.

Use Python 3.12. The project-local `./agent-cost-lab` launcher works from this checkout without installing a global command. `uv sync --extra dev` installs test dependencies locally when available. After compatibility review, `uv pip install --python .venv/bin/python -r configs/headroom-requirements.txt` explicitly adds the pinned Headroom dependency. Neither importing nor testing the package starts a model task or proxy.

```sh
uv run --extra dev pytest
./agent-cost-lab doctor
./agent-cost-lab optimize --task tasks/fix-midnight.toml --dry-run
```

The dry run lists current blockers. A real comparison requires an explicit model and run limits, a verified macOS restricted boundary, and the [Headroom compatibility gates](configs/headroom-compatibility.toml). The public defaults leave every live gate unvalidated. Copy that file to `configs/headroom-compatibility.local.toml` and record your installation's reviewed evidence there; the local override is ignored by Git and excluded from distribution builds. Historical validation on the maintainer's machine does not enable a fresh clone. The workflow creates separate candidates under ignored `artifacts/`; it never applies one to this repository. Each comparison runs Codex twice and consumes subscription allowance for both attempts. Monetary savings are not calculated for subscription execution. [The demo report](docs/synthetic-demo-report.md) contains invented example values only.

The bounded baseline pilot used on this installation is:

```sh
./agent-cost-lab run --task tasks/fix-midnight.toml --model gpt-6-sol \
  --max-runs 1 --timeout 600 --verifier-timeout 60 \
  --max-total-seconds 900
```

`gpt-6-sol` worked for this account in the pilot; availability on another account is not guaranteed. Run `./agent-cost-lab doctor` first and resolve blockers. Without `--dry-run`, this starts a subscription task. The successful pilot report is local at `artifacts/campaign-4e8a53ea6dab/report.md`; it is one observation, not an optimization comparison. Earlier failed startup attempts retain unknown usage rather than zero.

If an attempt stops, inspect the local report path shown by the CLI. A startup failure with no Codex JSONL events has unknown token usage and no independently verified agent result. `doctor` checks that the buggy fixture fails targeted acceptance checks and the private reference passes through the restricted verifier, as well as Codex CLI option startup; it launches no model task and cannot prove live model routing. `report --out report.md` and `compare --out report.md` also write the adjacent `report.csv`.

After a bounded baseline pilot, `./agent-cost-lab headroom-check --task tasks/fix-midnight.toml --baseline-records artifacts/PILOT/runs.jsonl --model YOUR_SUBSCRIPTION_MODEL_ID --max-runs 1 --timeout 600 --max-total-seconds 900` is the separate, explicitly invoked compatibility probe. It requires a matching real baseline with complete telemetry and passing verification. It never marks Headroom validated automatically. Review routing, compression or justified inapplicability, reversible retrieval, later-turn behavior, event preservation, and cleanup before updating the compatibility record. Its dry-run starts nothing.

After the recorded compatibility checks, the primary bounded workflow on this installation is:

```sh
./agent-cost-lab optimize --task tasks/fix-midnight.toml --model gpt-6-sol \
  --max-runs 2 --timeout 600 --verifier-timeout 60 --max-total-seconds 1800
```

This makes two subscription attempts. It stops on failures and version/gate mismatches, verifies both separate candidates, reports measured differences where comparable, and cleans up owned proxy/MCP state. The full repeated campaign has not been run.

The first integrated matched pair completed in `artifacts/campaign-fff3a3a11bbe`. Both candidates passed 6/6 specified checks; Headroom used 71.2% more input tokens and 27.2% more end-to-end time in that pair. This is a regression in one measured pair, not a general verdict or a savings claim. See [validation details](docs/live-validation.md).
