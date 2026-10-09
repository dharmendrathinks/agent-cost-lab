# Public-release review — 2026-10-09

Release scope: an experimental source project for offline agent-usage accounting, with explicitly gated macOS live experiments. This review does not claim production hardening, universal Codex compatibility, or demonstrated optimization savings.

## Findings addressed

| Finding | Change |
| --- | --- |
| Shared compatibility file enabled this installation's live gates for every clone | Public gates now default to false. Reviewed approvals use an ignored local override, excluded from source/wheel distributions. |
| Installed CLI derived output locations from its package installation directory | Offline imports write to the current working directory by default. Live commands give a clear error when the source checkout is absent. |
| No contributor/security guidance or automated checks | Added CONTRIBUTING.md, SECURITY.md, and macOS/Linux offline CI with read-only repository permissions and pinned action commits. |
| Package metadata and source-distribution boundaries were incomplete | Added repository URLs/platform scope, a compatible build-backend minimum, an explicit source manifest, and distribution-content checks. |
| Public handoff included a machine-specific absolute tooling path | Handoff now uses project-relative paths and the user-supplied repository URL. |
| User-controlled CSV labels could be interpreted as spreadsheet formulas | Formula-like text is escaped in CSV exports; numeric counts remain numeric. |

## Evidence before publication

- Local offline suite: **77 tests and 2 subtests passed** on Python 3.12/macOS.
- Built the source distribution and wheel using the locally available setuptools 84.0.0 backend, without network access. An initial isolated `uv build --offline` could not resolve its uncached backend; direct use of the available compatible backend succeeded.
- Both archives passed `scripts/check_dist.py`: required files and license present; no local gate approvals, credentials directories, raw logs, campaign artifacts, caches, virtual environments, or bytecode included.
- Installed the wheel into an isolated environment. Help, synthetic demo, selected-log import, and priced summary passed from a temporary directory outside the checkout. `doctor` failed cleanly with its checkout requirement.
- Inspected the explicit publication file list for common high-confidence credential patterns, private key blocks, personal absolute paths, and symlinks; none were found. This is a targeted scan, not a guarantee against every possible secret format.
- Existing MIT license retained. Headroom's optional dependency metadata identifies Apache-2.0 and its license/notice files; attribution links and redistribution requirements are documented. No third-party source or environment is vendored.
- No paid API call, new Codex task, or live optimization trial was used in this review.

Hosted validation passed on **Ubuntu and macOS** in [release CI run 37895108063](https://github.com/dharmendrathinks/agent-cost-lab/actions/runs/37895108063), covering tests, source/wheel builds, archive contents, and installed-wheel smoke checks. Check [GitHub Actions](https://github.com/dharmendrathinks/agent-cost-lab/actions) for subsequent commits.

## Git and publication constraints

The initial deterministic PR Ready assessment returned **NOT PR READY** because the workspace had no Git repository and the managed session prevented creating `.git`. That historical result was separate from the directly executed tests and packaging checks above.

The earlier GitHub connector attempt was rejected because approval was unavailable; no remote write occurred in that attempt. On resumption, approved escalation successfully initialized local Git and enabled the network check. The destination was still empty. An MIT-license baseline commit permits a full staged-file assessment. `.pr-ready.json` declares an offline package build, the test suite, and archive-content validation; no linter is configured.

The staged-file assessment subsequently returned **PR READY**: build, test, and static/archive checks passed, with no suspicious files or blockers. Its remaining risk was the unconfigured lint check. The reviewed implementation was committed as `af0fd676078fa2a25a07e5a1ca52d7404f535ee5` and pushed to `main`. A remote-head check confirmed the exact SHA; hosted CI then passed on both supported offline operating systems.

Generated artifacts, raw session logs, and installation-specific compatibility approvals remain ignored locally. For next-session continuity, use SESSION_STATE.md and inspect Git status, the remote branch, and CI. The original workspace is now a normal checkout tracking `origin/main`; a new machine can clone the published repository. Preserve local-only evidence when reconciling work.
