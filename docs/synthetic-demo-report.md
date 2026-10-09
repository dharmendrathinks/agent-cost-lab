# AGENT COST LAB

**SYNTHETIC DEMO DATA — not captured Codex runs or measured savings.**

Task: fix-midnight
Optimization: Context optimization (Headroom)
Execution: Codex subscription

| Measure | Baseline | Optimized |
| --- | ---: | ---: |
| Input tokens | 200 | 180 |
| Cached input | 20 | 25 |
| Output tokens | 55 | 58 |
| Agent runtime (s) | 35 | 39 |
| End-to-end runtime (s) | 42 | 49 |
| Independent verification | passed | passed |
| Telemetry completeness | complete | complete |

Success rate: baseline 1/1 (100.0%); optimized 1/1 (100.0%).

Started attempts: baseline 1; optimized 1. Failed attempts remain in resource totals.

The table shows the latest attempt in each configuration. Aggregate accounting includes every started attempt.

## Aggregate resource accounting

- Input tokens: baseline 200 (1/1 measured, complete total; 200 per verified success); optimized 180 (1/1 measured, complete total; 180 per verified success).
- Cached input: baseline 20 (1/1 measured, complete total; 20 per verified success); optimized 25 (1/1 measured, complete total; 25 per verified success).
- Output tokens: baseline 55 (1/1 measured, complete total; 55 per verified success); optimized 58 (1/1 measured, complete total; 58 per verified success).
- Agent runtime (s): baseline 35 (1/1 measured, complete total; 35 per verified success); optimized 39 (1/1 measured, complete total; 39 per verified success).
- End-to-end runtime (s): baseline 42 (1/1 measured, complete total; 42 per verified success); optimized 49 (1/1 measured, complete total; 49 per verified success).

## Illustrative differences (synthetic)

- Input tokens: -20 (-10.0%) optimized versus baseline across all started attempts.
- Cached input: +5 (+25.0%) optimized versus baseline across all started attempts.
- Output tokens: +3 (+5.5%) optimized versus baseline across all started attempts.
- Agent runtime: +4 (+11.4%) optimized versus baseline across all started attempts.
- End-to-end runtime: +7 (+16.7%) optimized versus baseline across all started attempts.

## Limitations

This report covers only the specified acceptance tests and available telemetry. Provider cache state is uncontrolled. Live attempts may consume subscription allowance; allowance use is not measured here.
The sample is too small for a general quality-preservation claim.

## Implementation details

Engine: Headroom synthetic
Treatment status: active_proxy_estimate
Declared strategy/settings: synthetic demonstration only
Effective strategy/settings: synthetic demonstration only

Monetary savings: **Not calculated for subscription runs.**
