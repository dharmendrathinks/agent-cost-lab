# Offline usage accounting

These commands read local files. They never invoke Codex, start Headroom, authenticate, download prices, or call a model API. Existing subscription execution guards remain unchanged.

## Saved-run summaries

```sh
./agent-cost-lab summary artifacts
./agent-cost-lab summary artifacts --group-by model day --out artifacts/offline-summary/report.md
./agent-cost-lab summary path/to/first.jsonl path/to/second.jsonl --group-by task
```

Directories are searched recursively for `runs.jsonl`; explicit file arguments can have any name. Identical copies of the same run are counted once, including copies in history reports. Conflicting records with the same identity produce an error instead of selecting an arbitrary value. Synthetic and real records cannot be mixed.

The Markdown report and adjacent CSV contain grouped token counts, measurement coverage, runtime, completed/failed/incomplete outcomes, verification status, and tokens per verified success. Failed attempts remain in resource accounting. Imported sessions have no independent verifier, so a session ending normally is not counted as a verified success. Per-success totals are withheld if usage or verification coverage is incomplete. Cached input and reasoning output are subsets and are not added twice.

Day means **UTC start day of the run or session**, not the calendar day each token was consumed. Sessions spanning midnight are attributed to their start day. Old lab records without timestamps remain in `unknown`; file modification time is not used as an invented run date. New lab attempts record UTC start/end timestamps.

The inventory does not compare the effectiveness of unrelated tasks, model settings, or campaigns. Controlled comparisons remain in `report` / `compare`.

## Import selected Codex session logs

```sh
./agent-cost-lab import-codex /path/to/rollout-session.jsonl
./agent-cost-lab import-codex /path/to/selected-session-directory \
  --ledger artifacts/my-sessions/runs.jsonl --task-label my-project
./agent-cost-lab summary artifacts/my-sessions --out artifacts/my-sessions/summary.md
```

File paths are explicit. A directory argument searches for `rollout-*.jsonl`. There is no automatic scan of all account history. The default destination is `artifacts/imported-codex/runs.jsonl`. Reuse the same destination and task label when refreshing a session.

The adapter supports the Codex **0.160.0** local rollout shape inspected on this installation. It reads `session_meta`, configured models in `turn_context`, cumulative `event_msg.token_count.info.total_token_usage`, and cumulative `token_usage_record.thread_token_usage`. It does not add these snapshots together. Per-response usage and cumulative usage are never added together. Repeated snapshots are counted as duplicates; decreasing totals are marked invalid. Other supported content events are ignored, not copied.

Each imported session is one normalized record:

- Session identity is hashed; raw session/account IDs and source paths are not exported.
- Only usage counts, safe model/version labels, timestamps, statuses, and import provenance are retained. Prompts, instructions, code, reasoning, tool outputs, rate-limit/account details, and conversation text are excluded.
- Authentication is not inferred from a rollout: billing mode remains `unknown`.
- Requested/configured models remain unconfirmed. A session with multiple model names is marked `mixed`; its aggregate usage is not allocated to one model or priced.
- Completed session runtime is the sum of available completed-turn durations, excluding idle gaps. Unfinished or partly timed sessions have unknown runtime. End-to-end runtime is not inferred from log timestamps.
- Usage covers the recorded thread. Child-agent usage is not inferred or automatically added. Import separately selected child logs only when their own lineage is supported.
- A trailing partial line, open turn, failed turn, or missing usage is marked incomplete/missing. A normally completed turn is still unverified for task correctness.

Exact re-imports do not rewrite the ledger. If a log grows by appending to the already imported bytes, the same record is replaced with the newer snapshot, not appended as another run. Shorter old copies are skipped. Rewritten/conflicting history, foreign-thread usage, forks, rollbacks, unsupported versions/providers/usage fields, and malformed non-tail JSON fail explicitly. A failed batch leaves the existing ledger unchanged. Imports use a local file lock and atomic replacement.

This is a conservative local adapter, not a promise that every future Codex build or restored/forked history has compatible accounting. The first unsupported file stops a directory batch; select supported files explicitly. No credential or authentication files are read.

## Optional API-equivalent estimates

```sh
./agent-cost-lab summary artifacts --prices configs/pricing.toml --context short
./agent-cost-lab report artifacts/campaign-fff3a3a11bbe \
  --prices configs/pricing.toml --context long \
  --out artifacts/offline-summary/comparison-long.md
```

Estimates are disabled unless `--prices` is supplied. The checked-in table is a **2026-10-05** snapshot of standard USD rates for the exact model IDs `gpt-6-sol`, `gpt-6.1-sol`, `gpt-6-astra`, and `gpt-6-luna`, from [official OpenAI pricing](https://developers.openai.com/api/docs/pricing). Nothing refreshes or downloads prices automatically. Tables older than 30 days and future-dated tables are flagged in reports. Unsupported IDs remain unpriced; no alias or nearest-model guessing occurs.

`--context short` (default) assumes every request used the short-context tier (at most 272K input tokens); `--context long` assumes every request used the long-context tier. A cumulative session input total is not a per-request context length. These are scenarios, not a reconstruction of actual billing. Effective service tier and regional charges are not established by local session totals.

The estimator computes, using decimal arithmetic:

```text
((input - cached_input - cache_write_input) × input_rate
 + cached_input × cached_rate
 + cache_write_input × cache_write_rate
 + output × output_rate) / 1,000,000
```

Cache counts must fit inside total input. Missing cache-write counts assume zero **with a visible note**; missing input/cached-input/output or incomplete usage leaves the record unpriced. Reasoning tokens are already in output. If the effective model is unconfirmed, the requested model is an explicit scenario assumption. Mixed or rerouted sessions are unpriced. Unknowns are never converted to a zero-dollar total. Reports show the priced fraction and call incomplete totals a subtotal.

The table can be edited locally with rates from a dated source. Required metadata: `schema_version = 1`, `currency = "USD"`, `service_tier = "standard"`, ISO `as_of`, and an HTTPS `source`. Model sections are `[models."exact-model-id".short]` / `.long`, with nonnegative rates per million for `input`, `cached_input`, `output`, and optional `cache_write_input`. Rates can be decimal strings. Add only tiers actually published for that exact model.

**These estimates are not Codex subscription charges, subscription allowance consumed, or monetary savings.** Tool fees, taxes, regional uplifts, and subscription charges are excluded. No paid API integration has been added.

## Comparison verdicts and model identity

Matched reports lead with total input-plus-output usage: more, fewer, unchanged, or insufficient evidence. Both arms must have compatible controls, valid optimization evidence, complete telemetry, and passing specified checks before a directional result is presented as an observed comparison. A failed check or incomplete result prevents an improvement claim. Cache reuse is included once, and active Headroom compression is not evidence of reduced total usage.

Requested model, confirmed effective model, and identity status appear separately in Markdown/CSV. Legacy `model` fields are interpreted as requested, not confirmed. These adapters do not independently confirm a serving model; unknown stays unknown. Comparisons with differing model-identity evidence are withheld.

## Validation on 2026-10-05

The offline suite passed **73 tests and 2 subtests**. Coverage includes cumulative snapshots, duplicated records, growing/partial/conflicting logs, transactional imports, unknown schemas, mixed models, decimal pricing, cache subsets, incomplete coverage, model identity, and comparison verdicts. The CLI integration test makes subprocess creation and network socket creation fail if an offline command attempts either.

The saved-artifact smoke check found 21 unique attempts and excluded 21 copied records. Four attempts have complete token observations; all others remain unknown rather than zero. Refreshed Markdown/CSV outputs are under `artifacts/offline-summary/`. No live Codex task or paid API call was used for validation.

The PR Ready analyzer returned **NOT PR READY**: this directory has no `.git` repository, so repository inspection and its checks were skipped. This is separate from the passing local test suite.
