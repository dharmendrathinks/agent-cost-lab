# Third-party attribution

Agent Cost Lab's own source, fixtures, verification cases, and tests are distributed under the [MIT license](LICENSE).

## Headroom

The optional context-optimization integration invokes [Headroom](https://github.com/headroomlabs-ai/headroom), installed separately as `headroom-ai[proxy,mcp]==0.39.1`. Headroom provides the compression implementation. Agent Cost Lab provides experiment control, integration, accounting, verification, and reports; it does not claim authorship of Headroom's algorithms or imply endorsement.

Headroom is licensed under [Apache-2.0](https://github.com/headroomlabs-ai/headroom/blob/d13e1966f820220b482a33c30bde1e926743939a/LICENSE). Its [NOTICE](https://github.com/headroomlabs-ai/headroom/blob/d13e1966f820220b482a33c30bde1e926743939a/NOTICE) and license must be retained when redistributing applicable upstream material. This repository does not vendor Headroom source, dependencies, binaries, or a configured virtual environment.

## Codex and development tools

Codex is an external client installed and authenticated by the user. No Codex client, credentials, or service access is distributed with this project. OpenAI service access remains subject to the user's account and applicable service terms.

Python, Git, pytest, setuptools, and the build frontend are separately installed development/runtime tools with their own licenses. GitHub Actions used in CI run in the repository's workflow; their source is not vendored. The core Python package declares no third-party runtime dependencies. Optional Headroom dependencies are not covered by Agent Cost Lab's MIT license.
