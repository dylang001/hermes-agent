---
name: wiki-refactor
description: Merge, split, and archive to reduce knowledge entropy.
version: 0.1.0
author: Dylan Angloher
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: knowledge-os
    tags: [obsidian, wiki, refactor, entropy, knowledge-os]
    related_skills: [wiki-lint, wiki-promote, wiki-ingest]
---

# Wiki Refactor

Entropy reduction: knowledge should get smaller over time. Merge duplicates, split overloaded pages, propose archives. Prefer proposals for destructive changes.

## When to Use

- After `wiki-lint` finds duplicates/stale pages.
- Weekly synthesis / monthly archive cron.
- User asks to clean the brain.

## How to Run

1. Start from latest lint report or run `wiki-lint`.
2. **Merge** duplicate DRAFT…VERIFIED pages into one CONNECTED page; leave stub redirect note on loser pointing to winner; update indexes.
3. **Split** pages with unrelated claim clusters into typed pages; cross-link.
4. **Archive proposal** for obsolete pages: draft package under `Drafts/Hermes/promotions/` or `workspace/drafts/` with list to set `status: ARCHIVED` — apply ARCHIVED on non-CANONICAL when user asks; CANONICAL archive needs Dylan.
5. Remove redundant index rows; fix links touched.
6. Append compile-log `REFACTOR`.
7. Refresh `hot.md` if active set changed.

## Goals

| Prefer | Avoid |
|--------|-------|
| Fewer overlapping pages | Endless new near-dupes |
| Clear entity/concept split | Mega-pages |
| Explicit ARCHIVE | Silent delete |

## Pitfalls

- Do not delete `raw/`.
- Do not merge away unresolved contradictions — keep `## Open questions`.
- Do not touch CANONICAL without approval.

## Mutation contract (mandatory if this run writes)

If this skill run creates or updates any Growth OS file, follow `_mutation-contract.md` end-to-end:

1. `knowledge_os_mutation.py begin --session <id> --skill <name>`
2. `preflight` / gated `write` / `note` for every touched path
3. `finalize --run-cycle` — **do not report success** unless finalize returns `"ok": true`

Approved lanes only. No CANONICAL. No governance edits. No existing-raw edits.
Unattended write cron remains paused (Model B pilot).

## Verification

If any file was written: receipt finalize `ok: true` and Model B cycle started or deferred with explicit next step.

Net page count for the touched cluster did not increase without justification; indexes consistent; compile-log REFACTOR line present.
