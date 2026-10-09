# Session handoff — 2026-10-09

Read this file and README.md before continuing.

## Objective and constraints

Measure model and agent usage, including Codex, without paid API calls. Prefer saved records and explicitly selected local Codex logs. Do not start new subscription tasks merely to validate offline features. The user requested open-source review, followed by publication to https://github.com/dharmendrathinks/agent-cost-lab.

## Implemented

- Offline summaries by model, task, and UTC start day, with deduplication, measurement coverage, failures, runtime, and tokens per verified success.
- Selected Codex 0.160.0 session import with cumulative snapshots, duplicate handling, and atomic updates of growing logs. Conversation content is excluded from normalized records.
- Optional local, dated API-equivalent pricing scenarios. Actual subscription charges and allowance are unmeasured.
- Requested versus confirmed effective model reporting; these adapters do not independently confirm the serving model.
- Comparison verdicts that report observed token changes alongside independent verification.

See docs/offline-accounting.md for commands and limits. Important implementation modules are accounting.py, importing.py, pricing.py, summary.py, reporting.py, cli.py, and headroom.py under src/agent_cost_lab/.

## Public-release preparation

Public Headroom compatibility defaults are unvalidated. Installation-specific approvals belong in ignored configs/headroom-compatibility.local.toml. The original installation's prior gate evidence was preserved there; it is intentionally absent from published files and distributions.

The project includes an MIT license, upstream attribution, contributor/security guidance, macOS/Linux offline CI, distribution-content checks, installed-CLI smoke checks, and regression coverage for public defaults and exported labels. Offline commands require no installed Codex or Headroom. Live commands require the source checkout, macOS, and the supported execution boundary.

**Published successfully on 2026-10-09.** This folder is now a Git repository on `main`, tracking `origin/main` at https://github.com/dharmendrathinks/agent-cost-lab. The implementation release is commit `af0fd676078fa2a25a07e5a1ca52d7404f535ee5`, following MIT-license baseline `2e7caa2`. Ordinary Git push and an independent remote-head check succeeded after approved permission escalation.

The deterministic checker returned **PR READY** for the staged release: build, tests, and distribution validation passed; lint was skipped because none is configured. [Release CI run 37895108063](https://github.com/dharmendrathinks/agent-cost-lab/actions/runs/37895108063) passed on both Ubuntu and macOS, including the installed-wheel smoke check. See docs/release-review.md for evidence. Later documentation-only commits save this publication result; use Git history for the latest head.

Local validation passed **77 tests and 2 subtests**, clean source/wheel builds, distribution-content checks, and installed-wheel CLI checks outside the checkout. The explicit publication inventory passed a targeted credential/personal-path scan. `.pr-ready.json` declares the offline build, test, and distribution checks. Local release archives and publication metadata are under ignored artifacts/release-build/ and artifacts/release-publication/. No paid API call or new Codex task was made.

## Existing evidence

The original development history contains 21 unique attempts, four with complete usage. Duplicate copies and unknown usage are handled explicitly. Local reports are in artifacts/offline-summary/ and are intentionally ignored. The matched campaign campaign-fff3a3a11bbe used 70.4% more total input-plus-output tokens with Headroom (71.2% more input alone); both candidates passed the specified checks. This is one observation. The public evidence summary is docs/live-validation.md.

## Remaining limits and next-session checks

- Read docs/release-review.md, then inspect Git status, the remote main branch, and hosted CI before continuing.
- Session import supports the inspected 0.160.0 shape. Unsupported versions, forks, rollbacks, foreign-thread usage, and conflicting history fail explicitly.
- Day groups use UTC session/run start dates; old records without timestamps remain unknown.
- Imported sessions are unverified for task correctness; child-thread usage is not inferred.
- The three-task repeated live campaign remains unrun. Do not start it automatically.
- Preserve the no-paid-API constraint. There is no need to launch a model to rerun the offline suite.
