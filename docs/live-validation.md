# Bounded live validation — 2026-10-03

Public-release note (2026-10-09): these results describe one historical installation. The public `configs/headroom-compatibility.toml` now ships with all gates false. Reviewed installation-specific approvals belong in an ignored `.local.toml` override; this historical evidence does not authorize new runs or enable a fresh clone.

These are authorized feasibility pilots on this Mac, not the frozen repeated campaign. Codex 0.160.0, Headroom 0.39.1, requested model gpt-6-sol, medium reasoning, one attempt per pilot, agent timeout 600 seconds, verifier budget 60 seconds, campaign deadline 900 seconds. Subscription mode; no API fallback, token extraction, model download, or global configuration edit.

| Observation | Baseline pilot | Headroom pilot |
| --- | ---: | ---: |
| Campaign | `campaign-4e8a53ea6dab` | `campaign-4726757d0dc9` |
| Input tokens | 173,531 | 333,267 |
| Cached-input subset | 135,808 | 308,608 |
| Output tokens | 2,609 | 5,442 |
| Reasoning-output subset | 737 | 1,875 |
| Agent seconds | 129.740 | 262.603 |
| End-to-end seconds | 130.267 | 271.096 |
| Specified independent checks | 6/6 passed | 6/6 passed |
| Usage completeness | complete terminal snapshot | complete terminal snapshot |
| Observable tool completions | 14 | 34 |

The pilots were separate compatibility checks. Their numbers do not establish a matched optimization effect. Headroom's successful pilot used more total tokens and time; its compression estimates do not establish overall savings. Cached and reasoning subsets are not added again. Monetary cost is **not calculated: subscription mode**.

## Gate evidence and limitations

- Subscription routing: the successful Headroom pilot observed 20 proxy requests, streamed events and complete terminal CLI usage without observed rerouting or error events. This is one account/version/task; server model identity and allowance use remain unobservable.
- Treatment activity: Headroom observed 391 context units, 133 modified units, 20 frames attempted/compressed and zero frame failures. Its unit/frame estimates and `proxy_compression_saved` counter have different granularity; none are added to provider usage or called billed savings. Task success alone was not used as activity proof.
- Retrieval: actual restricted MCP initialization/listing passed. A separate synthetic original seeded through upstream's inspected local store API was retrieved byte-for-byte through the proxy by the restricted MCP server; a missing original returned an error. Compression-only synthetic probes also ran locally; they emitted no retrieval hash and do not demonstrate marker creation or savings on the coding fixture. Source inspection checks marker/hash handling. This gate validates retrieval plumbing, not exhaustive resolution of every possible future marker. A retrieval failure or unresolvable marker invalidates that future setup.
- Multi-turn/event preservation: the successful task included multiple frames and observable tool events and completed external verification. Internal provider-call counts, per-request usage and all agent retries are not inferred.
- Effective settings: real `/health.config` confirmed coding profile, semantic cache/memory/learning/code graph/Kompress/fallback/rate limiter disabled, output shaper `0`, user-message compression on, system-message compression off, analysis protection on, protection window 0, minimum 10 tokens, maximum 15 items, compaction on, target ratio and accuracy guard unset. The source-inspected CLI leaves model routing disabled; isolated environment disables tool search and unrelated features. The observed user-message treatment is explicitly disclosed.
- Cleanup: real completed/failed checks removed owned proxy and MCP state. A model-free simulated interruption stopped the proxy listener and removed owned state. Offline tests exercise descendant cleanup after leader exit and runner cancellation. Descendants that deliberately escape into another session are not certified by process-group cleanup.

## Fixes needed for this Mac

Canonical temporary paths and uv interpreter-alias metadata access enable restricted Python execution. Codex's trusted client uses its native restrictive command/filesystem policy; a second Seatbelt sandbox around the client failed native sandbox initialization and was removed explicitly. Independent candidate verification stays deny-by-default with no network, credential, verifier or unrelated-repository access. The proxy has separate narrow resolver permissions and uses the project-local public CA bundle with strict TLS. Provider routing is `/v1`; health and retrieval use the root. Required retrieval MCP uses an owned working directory and exposes only `headroom_retrieve` to Codex.

SQLite/log/temp state is owned per run. The supported client may maintain ordinary authentication/runtime state; Agent Cost Lab does not inspect tokens or edit global configuration.

## Failed development attempts

All normalized records remain under ignored `artifacts/campaign-*`. At the end of these separate pilots there were 19 real fix-midnight attempt records: 14 baseline and 5 Headroom, with two completed results, 12 startup failures, two integration failures and three failed runs. Only the two successful pilots exposed complete token totals. The other attempts are unknown usage, never zero. Controls changed during diagnosis, so this heterogeneous history cannot support a resource-effect estimate. A complete validation-session token total is unknown.

After these pilots, the gated `optimize` workflow was ready for one bounded matched-pair smoke test on this installation (result below). This does not authorize or substitute for the later repeated three-task campaign. Revalidate gates if either dependency version or the chosen integration changes.

## Integrated matched-pair result

The authorized `optimize` smoke test subsequently completed under `artifacts/campaign-fff3a3a11bbe`, with exactly two attempts, identical gpt-6-sol/medium, 600-second agent timeout, 60-second verifier budget and 1800-second campaign limit. Both candidates passed 6/6 specified checks with complete telemetry. Headroom treatment was active by supplementary proxy evidence. Both owned proxy and MCP directories were removed; no candidate patch was applied to the working project.

| Measure | Baseline | Context optimization |
| --- | ---: | ---: |
| Input tokens | 125,102 | 214,221 |
| Cached-input subset | 105,728 | 180,736 |
| Output tokens | 2,502 | 3,186 |
| Agent seconds | 127.231 | 151.555 |
| End-to-end seconds | 127.811 | 162.547 |
| Specified independent checks | 6/6 passed | 6/6 passed |

Input increased **71.2%**, output increased **27.3%**, agent runtime increased **19.1%**, and end-to-end runtime increased **27.2%**. This is one matched pair with uncontrolled provider cache state; it establishes a regression in these measured runs, not general performance or quality preservation. Compression activity does not imply improved total resources. Monetary savings are not calculated for subscription mode.

The updated development-history report at `artifacts/validation-history-2026-10-03/report.md` includes 21 real attempts (four complete usage observations). All other usage remains unknown. Heterogeneous setup attempts and separate feasibility pilots are excluded from matched-effect calculations, and their resources remain visible. Real paired reports now require a common campaign identity and explicit `matched_comparison` role; coincidentally repeated `pair-001` names cannot turn separate pilots into a matched comparison.

Final offline validation: **43 pytest tests and 2 subtests passed**. Doctor and dry-run report no baseline or optimization blockers on this installation and launch no model/proxy. PR readiness remains **NOT PR READY** because this directory is not a Git repository; the analyzer could not inspect repository changes. The full repeated three-task campaign remains later work.
