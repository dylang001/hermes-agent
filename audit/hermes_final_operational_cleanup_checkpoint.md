# Hermes Final Operational Cleanup Checkpoint

Date: 2026-07-09

## Scope

Final operational cleanup pass for Hermes local and VPS integration work. No new
feature phases, provider routing changes, credential changes, MCP config
changes, real sends, deletes, deployments, or token-adjacent edits were
performed.

## Final Code Line

- local branch: `codex/phase6-intelligence-integration-20260709`
- VPS branch: `codex/phase6-intelligence-integration-20260709`
- local tracked tree and VPS tracked tree matched at the end of cleanup.
- origin/main was not pushed or modified.

## Validation

Local and VPS validation passed:

- `pytest tests/gateway/test_telegram_response_policy.py tests/agent/test_intelligence_policy.py tests/agent/test_intelligence_policy_phase1_5.py -q`
- `scripts/benchmark_intelligence_phase6.py`
- `scripts/smoke_intelligence_phase6.py`
- `py_compile` sweep for intelligence, gateway, benchmark, and smoke files
- `git diff --check`

VPS health and runtime checks passed:

- `hermes-gateway.service`: active
- `hermes-dashboard.service`: active
- gateway health: `http://127.0.0.1:8642/health` returned OK
- active MCP children: Exa and Obsidian filesystem only

## Enabled VPS Flags

`hermes-gateway.service` has:

- `HERMES_INTELLIGENCE_POLICY=1`
- `HERMES_INTELLIGENCE_MEMORY_POLICY=1`
- `HERMES_INTELLIGENCE_TOOL_POLICY=1`
- `HERMES_INTELLIGENCE_EVIDENCE_COMPACTION=1`
- `HERMES_INTELLIGENCE_FAILURE_POLICY=1`
- `HERMES_TELEGRAM_CONCISE_RESPONSES=1`

## ClickUp Canonical IDs

Verified from read-only ClickUp hierarchy on 2026-07-09:

- workspace: `Workspace` (`90152507264`)
- Orchidea space: `Orchidea` (`901511216857`)
- Orchidea prospecting list: `Pipeline` (`901524109891`)
- Orchidea ops list: `Ops` (`901524109892`)

`Pipeline` metadata confirms it is for sales and outbound work, with statuses
from `prospecting` through `won/lost`.

## Cleanup Actions

- Archived `/root/hermes-update-validation` to
  `/root/hermes-archives/20260709T181526Z-final-cleanup/hermes-update-validation.tgz`.
- Left backup/archive roots intact.
- Left token-adjacent paths untouched.
- Left old helper scripts in place because they are still referenced by current
  memory-ledger/design docs and tests.
- Archived generated benchmark/smoke JSON outputs outside the tracked VPS repo
  before restoring tracked audit files.

## Telegram Verification

Gateway policy probes verified:

- short status is human and includes online, gateway/dashboard, Telegram concise,
  and canonical ClickUp facts.
- full report expands mobile-readably without tables, thinking text, raw command
  traces, false `Blocked`, or false `Need approval`.
- source-conflict prompt is summarized briefly and says no changes were made.

No live Telegram message was sent during this checkpoint because the operational
constraints prohibited real sends.

## Rollback

Rollback bundles were created before each VPS patch. Recent anchors include:

- `/root/hermes-rollout-backups/20260709T181758Z-pre-clickup-canonical-context/pre-clickup-canonical-context.bundle`
- `/root/hermes-rollout-backups/20260709T181852Z-pre-clickup-canonical-telegram-status/pre-clickup-canonical-telegram-status.bundle`
- `/root/hermes-rollout-backups/20260709T182029Z-pre-clickup-canonical-telegram-report/pre-clickup-canonical-telegram-report.bundle`

To roll back the latest code patch, reset to the selected saved commit or bundle
and restart only `hermes-gateway.service`.

## Remaining Risk

The only unperformed acceptance item is a real Telegram chat round trip. It was
not executed because the same objective also prohibited real sends. Dylan should
send the three approved prompts from Telegram to confirm the live chat surface.
