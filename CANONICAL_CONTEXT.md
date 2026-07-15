# Hermes Canonical Context

This file records stable operational facts only. Prefer live evidence over this file when they conflict.

## Source Precedence

1. live config, environment, and filesystem state
2. canonical context file
3. current repo docs
4. recent audited decision logs
5. external memory or Mem0
6. older local memory

When sources conflict, resolve against the highest-confidence source quietly and report briefly.

## Active Paths

- local implementation checkout: `/Users/dylanangloher/.hermes/hermes-agent`
- historical/sparse local placeholder: `/Users/dylanangloher/Documents/Hermes`
- VPS production checkout: `/opt/hermes/app` (branch `hermes-phase1-approved`; approved SHA recorded in `HERMES_PROTECTED_OPTIMIZATIONS_AUDIT.md`)
- VPS state/config home: `/opt/hermes/home`
- Legacy path `/usr/local/lib/hermes-agent` is stale — do not treat as current
- Obsidian filesystem MCP path on VPS: verify live; historically `/root/obsidian-vault`

## VPS Runtime

- host: `hermes-agent-2025`
- public/Desktop remote URL: `https://hermes.meetlyra.live`
- dashboard service: `hermes-dashboard.service`
- gateway service: `hermes-gateway.service`
- dashboard internal port: `9119`
- gateway internal health port: `8642`
- active MCP children observed during Phase 6: Exa and Obsidian filesystem
- Zoho MCP endpoints/tokens may be configured, but Zoho was not observed as an active MCP child during Phase 6.

## Provider And Memory Facts

- Do not change provider/model routing without explicit approval.
- Current VPS runtime evidence points to OpenCode Go with MiniMax M3 behavior.
- Local and VPS provider/fallback config can differ; do not project local config onto VPS production.
- Local external memory provider was empty/unset during Phase 6.
- VPS external memory provider was `mem0` during Phase 6.
- Treat memory-provider truth as environment-specific unless Dylan approves a unified change.

## Intelligence Flags

The completed intelligence work remains feature-flagged and is controlled by
environment variables:

- `HERMES_INTELLIGENCE_POLICY`
- `HERMES_INTELLIGENCE_MEMORY_POLICY`
- `HERMES_INTELLIGENCE_TOOL_POLICY`
- `HERMES_INTELLIGENCE_EVIDENCE_COMPACTION`
- `HERMES_INTELLIGENCE_FAILURE_POLICY`
- `HERMES_TELEGRAM_CONCISE_RESPONSES`

Current VPS rollout state:

- `hermes-gateway.service` has all six flags enabled as of the approved
  July 9, 2026 rollout.
- Keep flags explicit in the service environment; do not make them implicit
  defaults without separate approval.
- Disable individual flags first if a regression appears, then restart only the
  required service.

## ClickUp / Drive / Obsidian / Workspace IDs

Verified from read-only ClickUp workspace hierarchy on July 9, 2026;
Ops Task OS mapping re-verified live on July 15, 2026:

- ClickUp workspace: `Workspace` (`90152507264`)
- Orchidea space: `Orchidea` (`901511216857`)
- Orchidea prospecting list: `Pipeline` (`901524109891`)
- Orchidea ops list: `Ops` (`901524109892`)
- Orchidea Ops folder: `901516535453` (hidden)
- Prospecting list source: ClickUp list metadata says `Pipeline` is for
  sales/outbound work with statuses from `prospecting` through `won/lost`.

### Hermes Task OS board (Orchidea Ops)

- List ID: `901524109892`
- Trigger: status `next` AND tag `hermes-ready`
- Status map: Inbox=`inbox`, Ready=`next`, In Progress=`in-progress`,
  Waiting=`waiting`, Review=`waiting` + tag `hermes-review` (no native
  Review column yet), Done=`done` (human only)
- Plugin: `plugins/clickup_task_os/` (fork-local; not a core toolset)
- Config key: `clickup_task_os` / `$HERMES_HOME/clickup_task_os.yaml`
- Secret: `CLICKUP_API_TOKEN` in profile `.env` only

## Historical Facts To Avoid

- Do not treat `/Users/dylanangloher/Documents/Hermes` as the implementation checkout without re-verifying.
- Do not treat `http://212.86.105.178:9119` as the current Desktop remote URL.
- Do not treat `/root/.hermes/worktrees/*` paths as current runtime state without active process/branch evidence.
- Do not report configured Zoho MCP endpoints as active solely because config or token files exist.
- Do not run old memory helper scripts unless current docs/config explicitly require them.

## Missing Canonical Facts

- No ClickUp folder ID is required for the current Orchidea `Pipeline` list; it
  is directly under the `Orchidea` space.
- Do not act on any different ClickUp IDs from memory alone; verify against a
  live/configured source first.
