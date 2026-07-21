---
name: wiki-research
description: Research externally, then capture and compile.
version: 0.1.0
author: Dylan Angloher
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: knowledge-os
    tags: [obsidian, wiki, research, knowledge-os]
    related_skills: [wiki-ingest, wiki-query]
---

# Wiki Research

External research → immutable `raw/` capture → compile via `wiki-ingest`. Separates discovery from knowledge.

## When to Use

- User asks to research a topic into the Growth OS brain.
- Gaps found during `wiki-query` or weekly synthesis.

## How to Run

1. Search/read external sources (`web_search`, `web_extract`, etc.).
2. Capture each source as a new file under `raw/articles/` (or appropriate subfolder) with origin URL.
3. Load `wiki-ingest` and compile ≤ CONNECTED/VERIFIED.
4. Return: sources captured, pages updated, open questions, promote candidates.

## Pitfalls

- Do not write research prose straight into CANONICAL or Business Context.
- Attribute every claim; low-confidence stays DRAFT/STRUCTURED.
- Messy synthesis belongs in `workspace/drafts/` until compiled.

## Mutation contract (mandatory if this run writes)

If this skill run creates or updates any Growth OS file, follow `_mutation-contract.md` end-to-end:

1. `knowledge_os_mutation.py begin --session <id> --skill <name>`
2. `preflight` / gated `write` / `note` for every touched path
3. `finalize --run-cycle` — **do not report success** unless finalize returns `"ok": true`

Approved lanes only. No CANONICAL. No governance edits. No existing-raw edits.
Unattended write cron remains paused (Model B pilot).

## Verification

If any file was written: receipt finalize `ok: true` and Model B cycle started or deferred with explicit next step.

Every used URL has a raw file; brain pages list those raw paths in `sources:`.
