---
name: wiki-daily
description: Orient on Growth OS via hot.md and indexes.
version: 0.1.0
author: Dylan Angloher
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: knowledge-os
    tags: [obsidian, wiki, hot-cache, knowledge-os]
    related_skills: [wiki-query, wiki-ingest, wiki-lint, self-improvement]
---

# Wiki Daily

Session orientation for Hermes Knowledge OS. Read the hot cache and progressive indexes only — never dump the vault into the system prompt.

## When to Use

- Starting substantial knowledge, research, or ops work that needs Growth OS.
- Cron daily job `knowledge-os-daily`.
- After a long gap since last vault touch.

## Prerequisites

- Growth OS path: Mac `…/Obsidian Vault/Growth OS` or VPS `/opt/hermes/data/obsidian/Growth OS`.
- Read `AGENTS.md` + `SCHEMA.md` once per unfamiliar session.
- Tools: MCP filesystem or `read_file` / `search_files` / `write_file` under Growth OS only.
- Do not use Local REST API for Hermes.

## How to Run

1. Read `hot.md` (≤150 words target).
2. Read `INDEX.md` Knowledge OS section + `AGENTS.md` (if unfamiliar) + `brain/_indexes/root.md`.
3. Skim last 15–30 lines of `compile-log.md`.
4. Summarize for the user: focus, open problems, 3–5 active pages.
5. Optionally refresh `hot.md` if today's focus changed (keep ≤150 words).
6. Stop — do not open the whole brain tree.

## Quick Reference

| File | Action |
|------|--------|
| `hot.md` | Read; maybe rewrite short |
| `brain/_indexes/root.md` | Read |
| `compile-log.md` | Tail only |
| `brain/**` pages | Not in daily orient unless user asks |

## Procedure

```text
hot.md → INDEX / brain/_indexes/root.md → compile-log tail → brief summary → optional hot update
```

## Pitfalls

- Do not load Business Context wholesale or treat it as SoT.
- Do not use vault-root PARA as the working brain.
- Do not put vault text into SOUL.md.
- Do not set CANONICAL here.

## After substantial knowledge work

When this session also ingested, linted, or refactored the brain: load skill `self-improvement` before closing. Propose SOUL/skill diffs only — do not bloat `SCHEMA.md` with session narrative.

## Mutation contract (mandatory if this run writes)

If this skill run creates or updates any Growth OS file, follow `_mutation-contract.md` end-to-end:

1. `knowledge_os_mutation.py begin --session <id> --skill <name>`
2. `preflight` / gated `write` / `note` for every touched path
3. `finalize --run-cycle` — **do not report success** unless finalize returns `"ok": true`

Approved lanes only. No CANONICAL. No governance edits. No existing-raw edits.
Unattended write cron remains paused (Model B pilot).

## Verification

If any file was written: receipt finalize `ok: true` and Model B cycle started or deferred with explicit next step.

Orientation used ≤4 files before answering; hot.md still ≤~150 words if updated.
