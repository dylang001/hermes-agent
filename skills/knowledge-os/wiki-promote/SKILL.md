---
name: wiki-promote
description: Package CONNECTED pages for CANONICAL approval.
version: 0.1.0
author: Dylan Angloher
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: knowledge-os
    tags: [obsidian, wiki, promote, canonical, knowledge-os]
    related_skills: [wiki-ingest, wiki-query, self-improvement]
---

# Wiki Promote

Package CONNECTED/VERIFIED brain pages for Dylan approval before CANONICAL (or Business Context) promotion. Never silently set CANONICAL.

## When to Use

- User asks to promote knowledge to canon.
- Ingest produced strong VERIFIED pages ready for approval.
- Weekly review of the promote queue.

## Prerequisites

- Page `status` is CONNECTED or VERIFIED.
- Access Policy: CANONICAL requires Dylan OK.

## How to Run

1. Select candidate page(s); verify sources and contradictions.
2. Write package to `workspace/promotions/YYYY-MM-DD-<slug>.md` (legacy path `Drafts/Hermes/promotions/` still accepted):
   - Target path(s) under `brain/`
   - Current → proposed frontmatter (`status: CANONICAL`, `promoted_by: dylan`, date)
   - Diff summary (claims added/changed)
   - **Do not** mirror into `Business Context/` (transitional; dual-SoT forbidden)
   - Rollback note
3. Present package to Dylan; **wait**.
4. Only after explicit approval: apply frontmatter + body edits; update indexes; append compile-log `PROMOTE`; Agent Run Log row.
5. Sync reminder: Mac→VPS push after approve (when sync unpaused).

## Package template

```markdown
# Promote: <title>

- Source page: `brain/...`
- Current status: VERIFIED
- Proposed status: CANONICAL
- Also mirror: none (Business Context is not SoT)

## Why

## Diff summary

## Rollback

Restore previous frontmatter from git / prior compile-log.
```

## Pitfalls

- Approval silence ≠ yes.
- Do not promote from `workspace/` without compiling via `wiki-ingest` first.

## Mutation contract (mandatory if this run writes)

If this skill run creates or updates any Growth OS file, follow `_mutation-contract.md` end-to-end:

1. `knowledge_os_mutation.py begin --session <id> --skill <name>`
2. `preflight` / gated `write` / `note` for every touched path
3. `finalize --run-cycle` — **do not report success** unless finalize returns `"ok": true`

Approved lanes only. No CANONICAL. No governance edits. No existing-raw edits.
Unattended write cron remains paused (Model B pilot).

## Verification

If any file was written: receipt finalize `ok: true` and Model B cycle started or deferred with explicit next step.

Without approval: only the promotions draft exists. With approval: page shows `status: CANONICAL` and compile-log PROMOTE line.
