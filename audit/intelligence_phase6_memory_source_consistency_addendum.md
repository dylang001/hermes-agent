# Phase 6 Addendum: Memory and Source-of-Truth Consistency Audit

Date: 2026-07-09

Status: Requirement added for Phase 6. This is a read-only audit requirement until Dylan approves any cleanup or write-back.

## Objective

Add a dedicated read-only audit for Hermes memory and operational-context discrepancies that prevent optimal operation.

The immediate problem is conflicting operational facts across local memory, external memory, project notes, decision logs, scripts, config references, and connector metadata. Example: local memory can reference one ClickUp list ID while Mem0 references another, causing Hermes to waste turns verifying basic facts or act on stale context. These discrepancies must be resolved through a deliberate canonical source-of-truth layer, not by blind deletion.

## Scope

Audit all operational-context sources Hermes may use:

- local memory files
- Mem0 or other external memory
- project notes
- decision logs
- skill metadata
- environment and config references
- ClickUp, Drive, Obsidian, and workspace references
- old worktrees
- stale scripts and command references
- prior task summaries that may now be outdated

## Read-Only Discrepancy Report

For each discrepancy, report:

- conflicting fact
- source A
- source B
- last modified timestamp or confidence signal, where available
- likely canonical value
- evidence
- risk if left unresolved
- proposed action: keep, update, archive, delete candidate, or needs Dylan review

The report must cover:

- Conflicting IDs: ClickUp list IDs, workspace IDs, folder IDs, project IDs, repo paths, VPS paths, service names, deployment URLs.
- Conflicting commands: commands Hermes believes exist but are not installed, old bridge commands, renamed scripts, deprecated CLI paths, stale helper tools.
- Conflicting project state: old decisions contradicting newer decisions, completed work still marked active, abandoned experiments referenced as current, wrong canonical runtime paths.
- Stale memory: old ClickUp references, old Hermes paths, old provider/model assumptions, old MCP assumptions, stale VPS state, dead tool names.
- Missing canonical facts: places where multiple memories exist but no source of truth is marked.

No memory, VPS state, worktree, config, or decision log may be modified during this first pass.

## Canonical Source-of-Truth Proposal

Phase 6 should propose a concise `CANONICAL_CONTEXT.md` or equivalent central source-of-truth file for stable Hermes operational facts.

Include only stable operational facts:

- active local Hermes path
- active VPS Hermes path
- canonical repo and branch
- canonical ClickUp workspace/list IDs
- active project names
- active skill paths
- approved provider/model setup
- active MCP/tool setup
- current deployment URLs
- current approval policy
- current memory policy
- deprecated commands/tools to avoid

This file is a proposal until approved. It should be maintained deliberately and should not become a dumping ground for transient task state.

## Cleanup Rules

Do not silently delete memory.

Before cleanup, produce:

- active facts to keep
- stale facts to archive
- conflicting facts needing Dylan review
- duplicate facts to consolidate
- outdated commands/tools to remove from memory
- proposed canonical replacements

Only after explicit approval:

- archive stale memory
- update incorrect references
- remove or mark deprecated command assumptions
- write canonical facts back to the correct memory layer

## Runtime Resolution Rule

Hermes should prefer operational sources in this order:

1. live config, environment, and filesystem state
2. canonical context file
3. current repo docs
4. recent audited decision logs
5. external memory or Mem0
6. older local memory

When sources conflict, Hermes should resolve quietly and report briefly instead of exposing long internal traces.

Example concise user-facing status:

```text
Found conflicting ClickUp list IDs. I’m using the live configured value and will flag the stale memory for cleanup.
```

## Telegram Behavior

Telegram discrepancy handling should be brief.

Bad:

- long thinking dump
- every command attempted
- full discrepancy narration

Good:

```text
Found a stale memory conflict around the ClickUp list ID. I’m verifying against live config before touching anything.
```

Then:

```text
Confirmed the live config value. I’ll flag the stale memory for cleanup after this task.
```

## Phase 6 Acceptance Additions

Phase 6 is not complete unless:

- read-only discrepancy report is completed
- canonical operational facts are proposed
- no memory is deleted without approval
- no VPS cleanup is performed without approval
- Hermes has a clear source precedence rule for resolving memory conflicts
- Telegram no longer receives verbose internal discrepancy traces
- known stale commands/IDs are archived or marked deprecated only after approval

## Non-Changes

This addendum does not authorize:

- memory deletion
- Mem0 writes
- VPS cleanup
- service restarts
- provider/model routing changes
- MCP redesign
- production deployment
