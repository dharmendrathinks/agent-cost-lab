# Agent Cost Lab

## Purpose

Agent Cost Lab **applies coding-agent optimizations and measures their effect on tokens, time, and independently verified task success**. It manages an optimization, runs a comparable normal Codex baseline, verifies both resulting candidates, and reports the difference. An unchanged result, a regression, or an unsupported integration is a valid outcome. The first strategy is `context_optimization`, powered by Headroom. Agent Cost Lab provides the integrated workflow, safe lifecycle, controlled trials, verifier, accounting, and report; Headroom supplies the compression algorithm.

The first version uses Codex CLI as the coding agent. It does not implement another agent loop, an OpenAI-compatible facade around subscription authentication, a compressor, a model router, or an observability platform. It does not treat subscription tokens as API-dollar savings. See [the experiment protocol](docs/experiment-protocol.md) for comparison rules and [the feasibility assessment](docs/integration-feasibility.md) for the evidence behind each integration.

## Current state and assumptions

**2026-10-09 public-release preparation:** fresh clones keep Headroom live gates unvalidated. The original installation's approvals are in ignored `configs/headroom-compatibility.local.toml`, which takes precedence locally and is excluded from distributions. The repository includes contributor/security guidance, upstream attribution, offline CI, package-content checks, and installed-CLI output handling. See [release review](docs/release-review.md) and [session handoff](SESSION_STATE.md).

**2026-10-05 offline extension:** `summary` groups deduplicated saved records by requested/confirmed model, task, and UTC start day. `import-codex` imports selected supported 0.160.0 rollout logs with cumulative-snapshot accounting and idempotent updates. Optional local `--prices` scenarios provide explicitly hypothetical API-equivalent USD, not subscription charges or allowance. Reports expose model-identity uncertainty and lead with observed comparison verdicts. New runs record UTC timestamps. See [offline accounting](docs/offline-accounting.md). These features do not require or authorize new model tasks or paid API calls.

The project directory was not a Git repository when inspected on 2026-09-28, and remains so on 2026-10-03. No `AGENTS.md` was present in it or its ancestor directories. The Python package, three task manifests in one fixture, event parser, controller, restricted verifier, doctor/dry-run, and reporting code now exist. Offline tests use synthetic events and a private reference. The authorized 2026-10-03 subscription baseline passed all six independent checks; see `artifacts/campaign-4e8a53ea6dab/report.md`. Earlier startup failures remain recorded with unknown usage. Headroom compatibility remains gated; implementation is not evidence that compression ran.

The initial inspection found Codex CLI `0.157.1`, Ollama `0.34.1`, and uv `0.11.32`. On 2026-10-03, installed Codex is `0.160.0`; both exact Codex versions have source-reviewed accounting adapters. Headroom `0.39.1` and pytest are explicitly installed in the project-local Python 3.12 environment. `codex login status` classifies the current method as subscription without exposing its output. The baseline requested `gpt-6-sol`, with no observed model-reroute event; the server's effective model is not independently established. Reassess when versions change.

Reviewed execution access resolved the earlier environment-level sandbox and PyPI blockers. A separate architecture flaw was found: wrapping the Codex client in another Seatbelt profile prevents its native tool/filesystem sandboxes from initializing. The trusted supported client now runs on the host and applies the restrictive native permission profile to agent tools and filesystem operations; the verifier, proxy, and retrieval process retain independent OS restrictions. No bypass flag, token extraction, or API fallback is used. The project-local `./agent-cost-lab` launcher avoids a global installation.

For the first live pilot, use one task, one attempt, `medium` reasoning if the selected model supports it, a 600-second agent timeout, a 60-second verifier budget across checks, and a 900-second campaign deadline. The model ID is required in the run configuration: doctor establishes local readiness, while the pilot must establish model access. The runner must not silently substitute another model.

## Recommended V1 architecture

```text
task manifest and experiment controller
  -> preflight and bounded run schedule
  -> two isolated workspaces from the same fixture snapshot
  -> normal Codex CLI baseline / same Codex through managed Headroom
  -> versioned event normalizer
  -> independent restricted verification of each candidate
  -> local JSONL ledger, Markdown comparison, CSV report, separate candidate artifacts
```

Use a small Python 3.12 package managed with uv, a CLI built with the standard library, pytest, TOML configuration, typed dataclasses, and JSONL events. Do not require a database, service, frontend, general-purpose plugin system, or Headroom installation for baseline operation.

Current layout:

```text
src/agent_cost_lab/
  cli.py              # commands, doctor, and dry-run
  controller.py       # bounded matched trials
  codex.py            # guarded Codex runner and process cleanup
  headroom.py         # gated upstream proxy lifecycle
  events.py           # versioned JSONL accounting
  records.py          # normalized records
  tasks.py            # public manifest loading
  workspace.py        # fresh snapshots and patch restrictions
  verifier.py         # restricted independent verifier
  reporting.py        # JSONL, Markdown, and CSV
fixtures/timeledger/  # one Python coding fixture
tasks/               # three public task manifests
verification/        # protected acceptance cases and reference
tests/event_fixtures/ # explicitly synthetic event streams
configs/             # baseline defaults, Headroom compatibility gate and pin
docs/
```

### Boundaries and data flow

`AgentRunner.run(task, workspace, configuration) -> AgentRunResult` remains the agent boundary. A `CodexCliRunner` prepares one invocation, captures structured events and stderr concurrently in memory, enforces its timeout, and returns an outcome. `Verifier.verify(candidate, task) -> VerificationResult` operates after the agent's owned process group stops. A small managed-optimizer lifecycle prepares Headroom, supplies supported per-run Codex routing and retrieval configuration, collects supplementary evidence, and cleans up. It cannot directly optimize every internal Codex prompt. It is not a general plugin interface.

Each run record carries task, matched-pair, run, attempt, and configuration IDs; fixture commit; hashes of task, verifier, and secret-free effective configuration and shared controls; actual installed agent and optional Headroom versions; requested model; reasoning, permissions, and authentication/billing classification; process outcome; wall time; observable tool activity; retry and error signals; usage; and independent verification results. The campaign is identified by its artifact directory. The CLI does not establish the effective server model; an observed model-reroute event stops the campaign. Do not store raw credentials or account identifiers.

Each usage measurement has a value or `null`, unit, source, granularity, and completeness status. Preserve raw reported usage fields separately from normalized totals. Version the lab's record schema independently from Codex's event schema. A parser that does not understand an event must retain an explicit `unknown` classification and avoid guessing usage.

### Proposed CLI

| Command | Required behavior |
| --- | --- |
| `agent-cost-lab optimize --task tasks/fix-midnight.toml --dry-run` | Implemented. Show the paired experiment, controls, limits, readiness, and blockers without starting Codex or a proxy. |
| `agent-cost-lab optimize --task tasks/fix-midnight.toml --max-runs 2 --timeout 600` | Implemented path, **live-gated**. Two attempts allow one matched baseline/optimized pair. Preflight both arms, isolate candidates, verify both, report, and clean up. A comparison consumes subscription allowance twice; it does not itself save usage. |
| `agent-cost-lab headroom-check --task tasks/fix-midnight.toml --baseline-records PILOT/runs.jsonl --model MODEL --max-runs 1 --timeout 600` | Implemented path, **live-gated**. Separate bounded integration probe requiring a matching real baseline pilot. It gathers evidence but cannot automatically certify routing, retrieval, and event compatibility. |
| `agent-cost-lab doctor` | Report installed versions, supported flags, auth classification, configured capabilities, and blockers. It makes no model call and never prints credential material. |
| `agent-cost-lab run --config FILE --dry-run` | Validate and show a sanitized launch plan, workspace locations, limits, and unresolved gates. It starts no agent or proxy. |
| `agent-cost-lab run --config FILE --max-runs N --timeout SECONDS --max-total-seconds SECONDS` | Execute only the predeclared number of bounded attempts. Positive limits are mandatory. |
| `agent-cost-lab report PATH` | Regenerate Markdown and CSV from local normalized records. |
| `agent-cost-lab compare BASE TREATMENT` | Compare compatible campaigns; show success, measurement coverage, and negative results beside efficiency. |

`--dry-run` and ordinary CI make no model calls. Report and compare read existing records only. Never default an unavailable configuration to another billing mode, model, or provider. The current `run` CLI accepts `--task` or `--config FILE`; a config file supplies public task/model/limit defaults. Execution remains blocked until boundary and integration gates pass.

The primary `optimize` flow owns the Headroom setup. Users do not need to run `headroom wrap codex`, modify global files, register retrieval manually, or assemble the comparison. Baseline operation never depends on Headroom. An optimized attempt requires a validated backend; an absent or bypassed engine must not be mislabeled optimized. Candidate patches remain separate and are never applied to the user's working repository. V1 verifies defined tasks with public behavior and independent acceptance tests, not arbitrary repository correctness.

### Codex invocation

Use the installed client's supported interface: a fresh `codex exec --json` process with `-C` set to the trial workspace, a specified model, invocation-local reasoning and permission configuration, task instructions on stdin, `--ephemeral`, `--ignore-user-config`, `--strict-config`, and `--color never`. Do not use `resume`, `fork`, or `--skip-git-repo-check`; each trial begins in a real clean fixture repository. Capture stdout and stderr separately and concurrently. Treat stdout as the Codex JSONL source, never the final assistant message as proof of success.

`--ignore-user-config` helps reduce inherited behavior but still uses the normal Codex authentication location. If it prevents access to the user's existing credential store, stop and request only the non-secret store choice needed for a per-run override. Do not read, copy, or export saved auth files. Record inherited instructions, skills, MCP servers, memory, environment policy, and compaction behavior that cannot be excluded.

Default to subscription mode. Before every run, classify auth using `codex login status`, capturing its output in memory and emitting only a small allowlisted enum. Source inspection shows that API-key status may display part of a masked key, so the original text must never reach artifacts or diagnostics. Reject API-key, workload-identity, other-provider, missing, and unknown modes. Check the presence of API credential and endpoint override environment-variable names without printing values. Launch with the built-in OpenAI provider and a controlled environment. An invocation-local `forced_login_method="chatgpt"` may be applied only after a positive preflight; its documented mismatch behavior can log out the client, so a mismatch must never be used as a probe. Refuse auth changes or conflicting overrides rather than falling back to paid API access.

Use a restrictive, invocation-local Codex permission profile, with an offline `codex sandbox` probe before a live task. The trusted client handles saved authentication normally; model-generated commands and filesystem operations are denied that path, verifier material, unrelated repositories, and network access. Grant workspace writes, scratch access, and minimal runtime reads. Do not place a second Seatbelt profile around the client: native sandbox initialization failed under that arrangement. The optimized arm receives only retrieval through an independently restricted MCP process, with an owned working directory and required startup. SQLite, logs, and temporary state are isolated per run; the supported client may maintain ordinary authentication/runtime state. Agent Cost Lab does not edit global configuration. Disable plugins, memory, web search, and multi-agent features; ignore user configuration and project rules. Headless approval requests fail; no bypass or unrestricted modes. A temporary directory is not a security sandbox.

### Independent verification and artifacts

After stopping the agent, validate that its patch touches only allowed fixture source. Copy allowed changes into a separate clean verification workspace, check trusted-file hashes, run the public development test and held-out acceptance cases through restricted subprocesses. Trusted verifier code calls candidate behavior through a narrow JSON stdin/stdout harness. Never import agent-generated modules into an unrestricted verifier process. Store held-out cases and expected answers outside agent-readable paths.

Keep normalized records local and secret-free. Normalized records and reports omit prompts, reasoning text, tool output, command text, code, request headers, proxy traffic, and account identifiers. Candidate fixture source is retained separately as the requested artifact; it is not copied into telemetry. Raw capture is opt-in, permission-restricted, and Git-ignored. Codex sends relevant task content to its remote service; an enabled Headroom proxy sees the traffic it forwards.

Start agent, verifier, and optional proxy in owned process groups. On cancellation or timeout send SIGINT, allow two seconds, then SIGTERM, allow two seconds, and finally SIGKILL if necessary. Cleanup also reaches group members whose leader has exited. Reap the owned leader and preserve partial records; group termination cannot establish cleanup of descendants that escape into a separate session. Do not terminate an unrelated listener merely because it occupies the intended proxy port. A cleanup failure blocks the next trial.

Stop the campaign on authentication failures, rate-limit or subscription-limit stops, unsupported event formats, treatment failure, or elapsed/run limits. Do not retry indefinitely or promise a hard token cap when usage becomes visible only after the request. Codex's own internal retries may not be observable; distinguish observed retries from an unknown internal total.

## Configurations and milestones

| Configuration | V1 status | Intervention |
| --- | --- | --- |
| `codex_baseline` | Required | Normal Codex execution, with existing provider caching left as is. |
| `codex_cache_optimized` | Unsupported/deferred | No documented subscription CLI caching-only control was established. Do not create this arm by changing prompts, model, reasoning, content, or billing mode. |
| `codex_headroom` | First managed optimization, gated | Headroom context compression in cache-preserving mode; dedicated proxy, retrieval tool, and overhead are declared parts of the treatment. |

**Milestone 1:** Offline foundation implemented: runner interfaces, synthetic-event parser tests, task manifests, independent verifier, and reports. Restricted probes confirm workspace access and held-out verifier denial; the buggy fixture fails targeted checks and the private reference passes. No model call in CI.

Reports require matched identities, provenance, active treatment, and shared-control hashes before deriving differences; preserve unknown/incomplete measurements; and emit Markdown/CSV locally. Invalid cumulative snapshots retain observations for diagnosis. Live baseline evidence establishes one fixture result, not savings or general correctness.

**Milestone 2 (validated for this installation):** One bounded baseline completed and passed 6/6 checks: input 173,531, cached-input subset 135,808, output 2,609, reasoning-output subset 737; one final usage snapshot; agent runtime 129.740 seconds; end-to-end 130.267 seconds. Subscription cost is not calculated. Earlier failed diagnostic attempts are not included in these single-pilot values and remain in the ledger with unknown token totals.

**Milestone 3 (bounded validation complete):** The Headroom pilot passed 6/6 checks with complete CLI usage, observed active compression across multiple frames, and owned-state cleanup. Model-free restricted retrieval and interruption probes passed. Effective coding-profile settings are recorded in `configs/headroom-compatibility.toml`. See [live evidence and limits](docs/live-validation.md); this is not exhaustive future-marker or version compatibility.

**Milestone 4 (bounded workflow validated):** `optimize` completed one integrated matched pair in `artifacts/campaign-fff3a3a11bbe`; both candidates passed 6/6 specified checks with complete terminal usage and active Headroom telemetry. Input increased 71.2% and end-to-end time increased 27.2% in this pair. The result is a measured regression, not an optimization success or a general verdict on Headroom. Candidate artifacts remain separate; owned proxy/MCP state was removed.

**Milestone 5 (pending):** Freeze settings and evaluate all three defined tasks with matched repetitions and reproducible reports. Local Ollama and explicitly paid API costing remain later modes.

V1 is accepted when mocked tests and CI use no model access, a live run cannot silently enter API-key mode, task success requires the external verifier, incomplete telemetry remains visible, and reports distinguish compression, provider cache reuse, runtime, success, and money.

## Unresolved gates and next validation step

Subscription authentication, one baseline execution, real terminal usage, and restricted independent verification are validated on this installation. Headroom is pinned and installed; model-free proxy readiness and retrieval MCP initialization pass. Its health schema is nested under `config`, and statistics are cumulative nested counters. A bounded Headroom pilot and separate restricted retrieval/interruption probes now support the version-specific gates. The compatibility record discloses observed effective settings. Future versions and individual retrieval failures still block valid treatment. Mocks cannot promote gates.

**Next step:** freeze the now-working configuration and predeclare repeated matched trials before drawing a directional conclusion. The full repeated three-task campaign has not been run. Gates and the one-pair result are supported by [recorded evidence](docs/live-validation.md). Provider routing uses `/v1`; health/retrieval use the root. Caching-only remains deferred; do not tune the fixture to hide this regression.

## Report and attribution

The main report leads with **AGENT COST LAB**, task, “Context optimization,” and “Codex subscription.” It places baseline and optimized input, cached input, output, agent runtime, end-to-end runtime, independent verification, and telemetry completeness side by side. Differences appear only where observations are comparable. It shows failed attempts and success rates, limitations, and implementation details: Headroom version, effective settings, and treatment status (active with effect, active without improvement, inapplicable, unexpected bypass, failed, or unknown). Monetary savings read “Not calculated for subscription runs.” Passing specified tests supports only a bounded no-regression statement.

Proposed README opening: “Agent Cost Lab applies coding-agent context optimizations, runs a comparable baseline, and checks whether the resulting code still passes independent tests. The first optimization engine uses Headroom. Agent Cost Lab manages the integration, controlled task execution, verification, and reporting.” Link upstream, retain applicable Apache-2.0/NOTICE attribution, and do not imply Headroom endorsement or ownership of its algorithms. An honest video description is: “I built the workflow that applies the optimization and tests its effect. For the first optimization engine, I’m using Headroom underneath.”

## References

- [Codex non-interactive mode](https://developers.openai.com/codex/noninteractive), [CLI reference](https://developers.openai.com/codex/cli/reference), [authentication](https://developers.openai.com/codex/auth), [configuration](https://developers.openai.com/codex/config-reference), [approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security).
- [Codex event processor at inspected tag](https://github.com/openai/codex/blob/36650394c5b38c2990ccf2a3457165ca3e9d9726/codex-rs/exec/src/event_processor_with_jsonl_output.rs).
- [Headroom proxy](https://docs.headroomlabs.ai/docs/proxy) and [cache optimization](https://docs.headroomlabs.ai/docs/cache-optimization).
