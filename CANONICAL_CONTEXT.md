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
- VPS production checkout: `/usr/local/lib/hermes-agent`
- VPS state/config home: `/root/.hermes`
- Obsidian filesystem MCP path on VPS: `/root/obsidian-vault`

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

The completed intelligence work remains feature-flagged:

- `HERMES_INTELLIGENCE_POLICY`
- `HERMES_INTELLIGENCE_MEMORY_POLICY`
- `HERMES_INTELLIGENCE_TOOL_POLICY`
- `HERMES_INTELLIGENCE_EVIDENCE_COMPACTION`
- `HERMES_INTELLIGENCE_FAILURE_POLICY`
- `HERMES_TELEGRAM_CONCISE_RESPONSES`

Production rollout policy:

- observability may be staged with `HERMES_INTELLIGENCE_POLICY=1`.
- memory, tool, evidence, and failure policies stay off until separately approved.
- Telegram concise mode requires explicit approval and a gateway restart.

## Historical Facts To Avoid

- Do not treat `/Users/dylanangloher/Documents/Hermes` as the implementation checkout without re-verifying.
- Do not treat `http://212.86.105.178:9119` as the current Desktop remote URL.
- Do not treat `/root/.hermes/worktrees/*` paths as current runtime state without active process/branch evidence.
- Do not report configured Zoho MCP endpoints as active solely because config or token files exist.
- Do not run old memory helper scripts unless current docs/config explicitly require them.

## Missing Canonical Facts

- Canonical ClickUp workspace/list IDs are not established yet.
- Do not invent ClickUp IDs or act on IDs from memory alone.
- Verify ClickUp IDs from a safe live/configured source before canonicalizing them.
