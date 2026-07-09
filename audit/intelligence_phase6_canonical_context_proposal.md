# CANONICAL_CONTEXT Proposal For Hermes

Status: proposal only. Do not install as active context until Dylan approves.

Last proposed: 2026-07-09

## Source Precedence

For Hermes operational facts, prefer sources in this order:

1. live config, environment, and filesystem state
2. this canonical context file
3. current repo docs
4. recent audited decision logs
5. external memory or Mem0
6. older local memory

When sources conflict, resolve quietly against the highest-confidence source and report briefly:

> Found conflicting operational context. I am using the live configured value and will flag the stale memory for cleanup.

## Stable Operational Facts

- active local Hermes implementation path: `/Users/dylanangloher/.hermes/hermes-agent`
- visible/sparse placeholder path sometimes used by Codex threads: `/Users/dylanangloher/Documents/Hermes`
- active VPS host: `hermes-agent-2025`
- active VPS Hermes production path: `/usr/local/lib/hermes-agent`
- public/Desktop remote URL: `https://hermes.meetlyra.live`
- Desktop current mode: remote
- public dashboard/backend split:
  - dashboard service: `hermes-dashboard.service`
  - gateway service: `hermes-gateway.service`
  - dashboard internal port: `9119`
  - gateway internal health port: `8642`
- current approved Phase 1-5 intelligence flags:
  - `HERMES_INTELLIGENCE_POLICY`
  - `HERMES_INTELLIGENCE_MEMORY_POLICY`
  - `HERMES_INTELLIGENCE_TOOL_POLICY`
  - `HERMES_INTELLIGENCE_EVIDENCE_COMPACTION`
  - `HERMES_INTELLIGENCE_FAILURE_POLICY`
- all intelligence flags remain disabled by default unless Dylan explicitly approves enabling them.

## Provider And Model Policy

- Do not change provider/model routing without explicit approval.
- Current VPS runtime evidence points to OpenCode Go with MiniMax M3 behavior.
- Current local staged config differs from VPS and must not be treated as production truth.
- Same-provider fallback/key rotation must not be treated as a provider identity change.

## Memory Policy

- No memory deletion, Mem0 writes, or cleanup write-back without explicit approval.
- Current local external memory provider: empty/unset.
- Current VPS external memory provider: `mem0`.
- Treat memory provider facts as environment-specific until Dylan approves a unified canonical rule.
- Request-aware memory gating remains disabled by default.

## MCP And Tool Setup

- Current VPS active MCP children observed in Phase 6:
  - Exa MCP
  - Obsidian filesystem MCP at `/root/obsidian-vault`
- Zoho MCP endpoints/tokens may be configured, but no active Zoho MCP child process was observed in Phase 6.
- Do not start MCP servers merely for discovery.
- Do not initiate OAuth or connector authorization unless Dylan explicitly approves.

## ClickUp / Drive / Obsidian / Workspace IDs

- Canonical ClickUp workspace/list IDs are not yet established in this audit.
- Do not act on ClickUp list IDs from memory alone.
- If ClickUp facts conflict, verify against live configured values or connector-safe read-only evidence and flag stale memory for review.
- Obsidian active VPS filesystem path observed: `/root/obsidian-vault`.

## Deprecated Or Historical Facts To Avoid

- Do not assume `/Users/dylanangloher/Documents/Hermes` is the implementation checkout.
- Do not assume `http://212.86.105.178:9119` is the current Desktop remote URL.
- Do not treat old `/root/.hermes/worktrees/*` directories as current state without checking active process/branch references.
- Do not report Zoho MCP as active solely because config/token files exist.
- Do not run old helper scripts such as Supermemory cleanup/flush tools unless current docs/config explicitly require them and Dylan approves.

## Approval Policy

- No production deployment without Dylan approval.
- No VPS changes without Dylan approval.
- No service restarts without Dylan approval.
- No credential/config/MCP/schedule/approval-gate changes without Dylan approval.
- No destructive commands.
