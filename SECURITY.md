# Security and data handling

The current development line is experimental. Fixes are made on `main`; there is no long-term support commitment for older versions.

## Reporting a vulnerability

Use [GitHub private vulnerability reporting](https://github.com/dharmendrathinks/agent-cost-lab/security/advisories/new) when it is enabled for this repository. If the private form is unavailable, open an issue asking the maintainer for a private contact channel, without exploit details, private logs, or credentials. Do not post credentials or conversation logs in a public issue.

## Boundaries

Offline reporting and importing do not contact a provider, start an agent, or read credential files. Import reads only selected logs and writes normalized usage and metadata. Source logs can contain private conversation content: retain them locally. Task labels and model names are user-supplied metadata, so choose non-sensitive labels. Reports and imported ledgers are not automatically safe to publish merely because prompts are excluded.

Live runs invoke a trusted installed Codex client, which uses its normal subscription authentication and sends task content to its service. A managed Headroom proxy sees routed content. Agent tools and candidate verification use separate restrictions; live execution requires the supported macOS boundary. A temporary working directory alone is not a sandbox. Missing or incompatible restrictions block execution.

Only trusted local task manifests and verifier code should be used. Verifier definitions are project-owned Python code. This tool is not a service for accepting untrusted uploads or running arbitrary users' agents. Public compatibility defaults are unvalidated; installation-specific approvals live in ignored `configs/headroom-compatibility.local.toml`.

API credentials and conflicting endpoint settings block live subscription execution. Do not disable authentication checks, use a sandbox bypass, or silently switch billing modes. Ordinary tests and CI must not start live agent/proxy work.
