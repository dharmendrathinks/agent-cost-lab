# Measure the cost of one Codex task

You can keep using the **same terminal window and repository**. With the current importer, use a **separate Codex conversation for each task you want to measure**. Agent Cost Lab reads the saved conversation's usage after the work is done.

For example, if one conversation contains only the work needed to fix login, its recorded usage can be attributed to that task. If it contains login fixes, dashboard changes, and documentation work, the report combines all three.

Importing and reporting run entirely offline: they make no API calls and consume no additional Codex allowance. Doing the original work in Codex still uses your normal plan or billing arrangement. Dollar estimates are **hypothetical API-equivalent costs**, not actual subscription charges or allowance consumed.

## Before you start

Install Agent Cost Lab using the [README instructions](../README.md#install-from-source). The current session importer supports the inspected **Codex 0.160.0 rollout format**; other versions fail explicitly. Check your CLI version from your shell with `codex --version`.

The examples below use the source checkout and `rg` (ripgrep) to locate a log. Replace example IDs and paths with your own values.

## 1. Start a fresh conversation for the task

Inside Codex, in the repository where you are working, enter:

```text
/new
```

Then ask Codex to do your task, for example:

```text
Fix login so that a user with valid credentials can sign in.
```

Keep investigation, implementation, tests, and related follow-ups in this conversation. Wait for Codex to finish before measuring it.

`/new` starts a fresh conversation in the same terminal. It resets conversation context; it does not reset your repository files. Opening another terminal and resuming the old conversation does not separate its usage. See the [official Codex command reference](https://learn.chatgpt.com/docs/developer-commands?surface=cli) for `/new`, `/status`, `/statusline`, and `/quit`.

## 2. Record the session ID and return to your shell

Before switching to another task, enter `/status` and copy the session ID. If your CLI does not show it there, use `/statusline` to enable the session ID display.

The session ID identifies the saved conversation. It is different from a task label such as `fix-login`.

Once the task has finished, enter `/quit` to return to your shell. You can run the reporting commands there; a second terminal is optional.

## 3. Find that conversation's log

Replace `PASTE_SESSION_ID_HERE` with the ID you copied:

```sh
rg --files --hidden "${CODEX_HOME:-$HOME/.codex}/sessions" \
  | rg -F 'PASTE_SESSION_ID_HERE'
```

This lists matching paths under Codex's local session directory. The default is `~/.codex/sessions`; the command also honors a custom `CODEX_HOME` environment variable. Use the matching `rollout-*.jsonl` file. If nothing matches, confirm the ID and storage location before continuing. Do not select an unrelated log just because it is the newest.

Keep raw logs private: they can contain prompts, code, and tool output. Agent Cost Lab imports selected usage metadata without copying conversation content into its ledger.

## 4. Import the log and generate a report

Change into your **agent-cost-lab checkout**, rather than the repository you were fixing. Replace `/actual/path/to/rollout.jsonl` with the path from the previous step:

```sh
./agent-cost-lab import-codex /actual/path/to/rollout.jsonl \
  --task-label fix-login \
  --ledger artifacts/fix-login/runs.jsonl

./agent-cost-lab summary artifacts/fix-login \
  --prices configs/pricing.toml \
  --out artifacts/fix-login/report.md
```

Open `artifacts/fix-login/report.md` to see recorded token usage, measurement coverage, available runtime, and the optional cost estimate. An adjacent CSV is also generated. Omit `--prices configs/pricing.toml` if you only want usage without a dollar estimate.

**You choose `fix-login` yourself.** The `--task-label` option names the imported record for reporting. It does not search prompts or select part of a conversation. Use a simple label such as `fix-login` or `add-dashboard`, without spaces.

If you later resume the same conversation for more login work, import the updated log using the same ledger and label, then regenerate the report. Supported appended history updates the existing record instead of counting the session twice.

## 5. Start the next task separately

For the next unrelated task, start a fresh Codex conversation. Give its imported record a different label and, for a separate report, a different artifact directory.

You can repeat this workflow in the same terminal and repository. Each task's conversation supplies its own usage record.

## What the current tool cannot measure

- **An individual task inside an already mixed conversation.** Importing that log gives the combined recorded usage. Changing the label does not split it. Start/end task checkpoints and an automatic session picker are not implemented.
- **Your actual subscription bill or allowance consumption.** The optional estimate applies a dated local price table and stated assumptions to recorded tokens. It does not create a charge.
- **A guaranteed complete cost for delegated work.** The importer accounts for the selected thread; child-agent usage is not automatically added.
- **Every session's dollar value.** Unsupported models, mixed-model sessions, and incomplete measurements may remain unpriced. Unknown values are not treated as zero.
- **Proof that the task succeeded.** Imported conversations have no independent task verifier, even when Codex finishes normally.

See [offline accounting details](offline-accounting.md) for supported log shapes, re-import behavior, pricing assumptions, and coverage limitations.
