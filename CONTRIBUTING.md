# Contributing

Start with the source installation in README.md. Python 3.12 is the reference development environment. Git is needed for fixture snapshot tests. Offline tests run on macOS and Linux without Codex, Headroom, account credentials, or model calls.

```sh
.venv/bin/python -m pytest -q
./agent-cost-lab demo-report --out artifacts/demo.md
```

To check packaging, install the development-only build frontend and build both distributions:

```sh
.venv/bin/python -m pip install build
.venv/bin/python -m build
```

Include a concise problem statement and relevant validation in a pull request. Add regression coverage for accounting errors, parser changes, privacy boundaries, and lifecycle changes. Use invented events in tests and label synthetic evidence. Avoid tests that need a signed-in account or consume model usage. The checked-in fixture is intentionally buggy; fixes intended for agent experiments belong in candidate artifacts, not in the starting fixture.

Do not commit session logs, prompts, account information, credentials, local compatibility approvals, virtual environments, or generated campaigns. `artifacts/`, `raw-events/`, `.env*`, and `*.local.toml` are ignored. Keep example credentials obviously synthetic. Public price changes need an exact model ID, date, source, and cache/context assumptions.

New Codex log versions need inspected schemas and tests for cumulative snapshots, duplicates, incomplete data, and model identity. Unknown usage must remain unknown. Changes to live execution must preserve subscription-only authentication, explicit bounds, independent verification, isolated candidate workspaces, and fail-closed behavior. Offline tests cannot certify live compatibility gates.

Use GitHub issues for reproducible bugs and feature proposals. Follow SECURITY.md for sensitive reports. This project is experimental; support for additional agents, operating systems, or log formats should be scoped explicitly.
