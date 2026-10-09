# Experiment protocol

Agent Cost Lab applies managed context optimization and compares the same coding agent on the same work with normal execution. It independently verifies both candidates and separates code correctness from resource use. A null measurement, no saving, worse performance, or an invalid treatment is a reportable result. Each matched comparison runs the task twice and consumes subscription allowance for both attempts; the measurement exercise itself does not save usage.

## Fixture, tasks, and external verification

Use the small, dependency-light Python repository named `timeledger`. It parses work-session rows and produces summaries. Its documentation, sample input, and public development test provide context without artificial padding or inflated tool output. Each task is defined in a public manifest with its behavioral requirements; held-out cases live outside candidate workspaces.

| Task | Public acceptance criteria | Separate held-out cases |
| --- | --- | --- |
| Bug fix | Allocate a session's elapsed seconds to the correct UTC calendar days when it crosses midnight. Intervals are half-open; total seconds are conserved. Existing same-day summaries stay the same. | Exact-midnight boundaries, multi-day sessions, timezone offsets, overlapping entries, and total conservation. |
| Validation | Reject missing identifiers, invalid or timezone-naive timestamps, non-positive intervals, and duplicate entry IDs. Raise `ValueError` identifying the first faulty CSV row. Preserve valid-input behavior. | Whitespace, malformed rows, duplicates, valid offsets, and first-error ordering. |
| Behavior extension | Allow grouping by user, with project grouping still the default. Keep deterministic ordering and existing default output. | Empty input, multiple projects/users, ties, formatting regression, and unchanged totals. |

Each task has a pinned starting Git snapshot. All configurations and repetitions for that task start from that same snapshot, with a fresh Codex session. Tasks do not inherit earlier agent solutions. Before using any task in a paid or subscription run, confirm offline that its starting snapshot fails the targeted acceptance check and a privately prepared reference solution passes; keep reference patches inaccessible to the agent.

Public development tests and task instructions are visible in the fixture. Held-out case definitions and expected answers live outside every agent-readable workspace. Success requires the trusted external verifier to pass after the agent has stopped. Reject changes to public tests, the task brief, verifier entry points, or paths outside the permitted source tree rather than treating edited tests as success. The verifier checks trusted-file hashes before executing public and held-out checks through restricted subprocesses and a narrow JSON stdin/stdout harness. It does not import agent-produced code into the unrestricted controller.

## Arms and controls

`codex_baseline` uses competent normal Codex execution. Do not reorder tools, vary prompts with timestamps, add irrelevant files, pad context, or attempt to disable the provider's existing caching. Describe its cache state as uncontrolled or provider-observed, never "caching disabled."

`codex_cache_optimized` remains deferred. An arm bearing this name must identify a supported caching-only control, hold content and all other settings fixed, and expose an observable effect. Neither a new CLI session nor wrapping the CLI grants control over internal message layout, every model request, prompt-cache keys, or cache breakpoints. If no supported control is available, no trial is scheduled.

`codex_headroom` is the first managed strategy, conditional on compatibility gates. Its declared treatment is **context compression with cache-preserving behavior**, including the dedicated Headroom proxy and any retrieval tool required by reversible compression. Agent Cost Lab owns setup, routing, readiness, telemetry, and cleanup; users do not configure the wrapper or global files. It is compared with unchanged native Codex. A Headroom passthrough smoke test validates plumbing but is not a required third measured arm. If a separate caching-only arm becomes feasible later, evaluate adding Headroom on top of it as a new experiment, not as part of this initial comparison.

Record treatment status separately from verified success and resource change: **active with measured effect**, **active with no improvement**, **inapplicable (no eligible content)**, **unexpected bypass**, **integration failure**, or **unknown**. A task pass alone is not evidence that compression ran. A legitimate zero-compression outcome must not trigger fixture padding. Treat unexpected bypass and integration failure as invalid treatment comparisons, preserving their attempt resource records. Verify that unrelated routing, reasoning changes, output steering, persistent learning, and navigation are disabled where supported, and record effective settings rather than intended defaults.

Hold these factors fixed within each matched comparison:

- Model and reasoning settings; service tier where selectable.
- Exact public task instructions and acceptance criteria.
- Starting commit and repository contents.
- Agent tool and permission surface, except a precisely declared treatment requirement such as Headroom retrieval.
- Agent timeout, verifier timeout, and no-repair policy.
- Raw-capture policy and reporting parser version.

Record inherited skills, MCP tools, memory, hooks, environment configuration, agent compaction, and other incidental differences. Do not assume `--ignore-user-config` removes every inherited instruction. If a difference cannot be held fixed, report it as a threat to attribution.

Trial workspaces, scratch directories, and report outputs are distinct. The agent cannot read earlier patches or held-out results. Warm-up work, including proxy startup, remains visible in the ledger.

On macOS the trusted Codex client runs normally with its native restrictive command/filesystem permissions; it is not nested inside a second Seatbelt sandbox. The verifier, proxy and retrieval process have separate restricted boundaries. The proxy alone receives narrow DNS service/resolver permissions and the project-local public CA bundle with certificate verification enabled. These grants do not apply to candidate code. Required retrieval startup uses an owned working directory and exposes only `headroom_retrieve` to Codex.

## Scheduling and campaign limits

Start with one baseline pilot on the bug task. Pilot runs assess feasibility and are excluded from the primary matched estimate, but their time and usage are reported separately. Do not start an optimization pilot until its offline gates pass. Any live pilot requires explicit authorization and bounded limits.

The authorized 2026-10-03 baseline pilot passed 6/6 specified checks and captured one complete terminal usage snapshot. Earlier setup/routing failures remain in their campaign records. Missing usage on those attempts makes a complete validation-session token total unknown; do not count them as zero or present the successful pilot's total as all development usage. A separate synthetic seeded-store/MCP roundtrip checks retrieval plumbing; it is not captured agent traffic, measured savings, or proof that compression markers from the task resolve. Local compression-only input emitted no marker in one probe; no fixture padding is permitted to change that result.

After the pilot, freeze the prompt, model, settings, task snapshot, tool surface, integration versions, timeouts, and metric definitions. Use at least three matched repetitions per task; the initial default is **four**. For two arms, counterbalance order as `AB`, `BA`, `AB`, `BA`, and reverse the starting order for successive tasks. Run sequentially on the 18 GB Mac. With three tasks and two arms, this produces 24 measured attempts. Predeclare `--max-runs`, per-run timeout, verifier timeout, and `--max-total-seconds` before execution.

There is no lab-level automatic repair or retry in the first comparison. If Codex itself retries internally, record only what its telemetry exposes. Once a rate limit, auth error, unsupported schema, treatment failure, or campaign limit stops further work, leave remaining scheduled runs unstarted and report them separately. Count every started attempt in the resource ledger whether or not its code passes.

## Measurements and usage accounting

Capture run identity and provenance; process and end-to-end duration; observed tool activity; failures, retries, cancellations, timeouts, and rate-limit stops; external verification; and all usage categories exposed by the chosen interface. For Codex these may include input, cached input, cache-write input, output, and reasoning output. Optional Headroom measurements are supplementary.

For inspected Codex CLI `0.157.1` and `0.160.0`, `turn.completed.usage` is built from the **last thread-total usage notification**, even though the `Usage` type describes tokens "during the turn." The event processor supplies default zeros when no usage notification has arrived. These are two reviewed exact versions, not a permissive version range. [Original event processor](https://github.com/openai/codex/blob/36650394c5b38c2990ccf2a3457165ca3e9d9726/codex-rs/exec/src/event_processor_with_jsonl_output.rs), [0.160.0 event processor](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/exec/src/event_processor_with_jsonl_output.rs), [0.160.0 usage type](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/exec/src/exec_events.rs).

The installed version is recorded for each attempt. Unknown event or item types fail explicitly. Duplicate completed tool IDs are counted once. An observed model-rerouting event invalidates the fixed-model attempt and stops the campaign; absence of that event is not independent confirmation of the server's effective model. A nonzero process exit with no JSONL is classified as a startup failure, with only an allowlisted diagnostic category retained. Such an attempt is visible with unknown usage and verification marked unstarted.

Accounting rules:

1. For a fresh one-shot thread, take the final valid cumulative usage snapshot once. Do not sum successive `turn.completed` snapshots.
2. Treat duplicate terminal events with identical values as one observation. Conflicting or decreasing cumulative values invalidate the normalized total and retain the raw observations for diagnosis.
3. Preserve missing fields as `null`, never zero. A reported all-zero snapshot is recorded as observed zero with **ambiguous completeness** because it may be synthesized from missing telemetry.
4. A failure or interruption without terminal usage has unknown token totals. Do not equate the process exiting with zero usage.
5. Cached input is a subset of input where exposed; reasoning output is a subset of output where exposed. Do not add subsets to their totals as extra consumption.
6. A defaulted cache-write zero does not prove no upstream cache write. Record source and granularity for each category.
7. Do not infer the number of internal model calls from agent turns or tool events. CLI task totals do not establish first-request versus later-request token usage.
8. Keep Codex/provider counts, Headroom estimates, and local timing in separate namespaces. Never add proxy estimates to provider totals.

The parser must handle unknown schema revisions explicitly. When a field's meaning changes, retain the original event version and introduce a versioned normalization rule after inspection. Synthetic event fixtures and mocked runs cover parsing in ordinary CI without any subscription or API access.

## Analysis and report format

Show verified success count and success rate beside every efficiency comparison. Report total resource use over **all started attempts**, including failed attempts. For a complete resource category:

```text
resources per successful run = total resource use across all attempts
                               / number of independently verified successes
```

When there are zero successes, this metric is undefined. When any attempt's resource value is unknown, show the known subtotal and measurement coverage but do not label it a complete aggregate. A percentage change is undefined when its baseline denominator is unknown or zero. Report negative savings and unchanged performance without clamping them away.

Report paired absolute values and differences. Distinguish five concepts: content reduced by compression, provider-reported cached input, runtime, externally verified task success, and monetary cost. Measure agent runtime and end-to-end runtime separately. End-to-end duration spans workspace preparation, optimizer startup, agent execution (including proxy processing and retrieval), verification, and owned-process cleanup. Display setup, model/proxy warm-up, optimization, and verifier overhead where observable without adding overlapping phase durations twice.

The report withholds derived differences if pair IDs are duplicated or unmatched, provenance differs, or the shared-control hash is missing or unequal. Shared controls include installed Codex version, model, reasoning, per-attempt limits, permissions, and user-config policy; treatment-specific routing, retrieval, and optimizer settings remain declared differences. A resource category with no valid observations is reported as unknown, and an arm with no attempts is reported as unstarted.

The main report leads with Agent Cost Lab's task result and side-by-side baseline/optimized input, cached input, output, agent runtime, end-to-end runtime, verification, and telemetry completeness. Disclose Headroom engine/version, effective strategy/settings, and treatment status in implementation details. Show measured differences only for valid, comparable observations. Keep failed attempts and success rates visible. Use “Both candidates passed the specified acceptance tests” rather than an unrestricted correctness or quality-preservation claim.

For subscription Codex, monetary cost is **not calculated**. A smaller token count does not imply a smaller monthly subscription price or a proportional reduction in an allowance. For local Ollama, no per-token API charge does not mean zero operating cost. Paid API estimates require a separate explicit opt-in, dated provider prices, complete documented billable categories, failures, retries, cache writes, and a label distinguishing calculated estimates from invoice-reconciled charges.

## Cache state and interpretation limits

Provider cache contents cannot be cleared by creating a new Codex process or session ID. Counterbalancing reduces order bias but does not control hidden prompt content, provider routing, retention, eviction, or reuse across trials. Record run order, elapsed gap, pilot/warm-up activity, and observable cached-input tokens. Never add prompt padding or contrived entropy to manufacture a cache effect.

OpenAI documents prompt-cache prefix matching and API diagnostics, but diagnostics are not established in subscription CLI events. Local explanations for apparent misses remain hypotheses unless supported by provider telemetry. [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching), [diagnostics](https://developers.openai.com/api/docs/guides/prompt-caching/diagnostics).

Distinguish a task's first request from later-session behavior where the interface permits it; mark it unobservable where the CLI exposes only task totals. A small fixture and four matched repetitions yield an initial directional comparison, not proof of general quality preservation. Local Ollama results cannot establish OpenAI caching behavior, and runs using different Codex and Ollama models do not isolate one optimization.
