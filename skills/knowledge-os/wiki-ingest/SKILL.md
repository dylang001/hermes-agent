---
name: wiki-ingest
description: Capture raw sources and compile into brain.
version: 0.1.0
author: Dylan Angloher
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: knowledge-os
    tags: [obsidian, wiki, ingest, compiler, knowledge-os]
    related_skills: [wiki-query, wiki-promote, wiki-lint, wiki-research]
---

# Wiki Ingest

Hermes Knowledge OS compiler: capture immutable raw sources, then compile into `brain/` at DRAFT→CONNECTED (VERIFIED when evidence is strong). Never auto-CANONICAL.

## When to Use

- User provides an article, transcript, PDF notes, meeting dump, or research clip.
- `wiki-query` / user says a valuable answer should become knowledge.
- Daily cron finds unprocessed files under `raw/`.

## Prerequisites

- Read Growth OS `SCHEMA.md` frontmatter rules.
- Access Policy authority B: auto-write `raw/` append + `brain/**` ≤ VERIFIED.
- Tools: `read_file`, `write_file`, `search_files` (or MCP equivalents) under Growth OS only.

## How to Run

### A. Capture (immutable)

1. Write a **new** file under `raw/<articles|transcripts|pdfs|exports>/YYYY-MM-DD-<slug>.md`.
2. Include YAML: `captured: YYYY-MM-DD`, `origin: <url or note>`, `title:`.
3. Never edit an existing raw file. If correction needed, add `raw/.../<slug>.amend-YYYY-MM-DD.md`.

### B. Compile (knowledge compiler)

For each source (or batch):

1. **Read** raw (immutable).
2. **Extract** claims, entities, concepts, decisions — each with optional quote/span.
3. **Compare** against `brain/_indexes/*` and existing pages (`search_files` under `brain/`).
4. **Merge / dedupe** — update existing page when same entity; do not fork duplicates.
5. **Cross-link** — add `## Related` wikilinks; fix obvious broken links you touch.
6. **Structure** pages with required frontmatter (`status`, `confidence`, `sources`, `updated`).
7. **Status gate** — set `EXTRACTED` → `STRUCTURED` → `CONNECTED` in one pass when links+index updated; `VERIFIED` only if multiple sources or strong primary evidence.
8. **Indexes** — upsert one-line row in the matching `brain/_indexes/<type>.md`.
9. **Log** — append `compile-log.md`: `YYYY-MM-DD | INGEST | <raw> → <brain pages> | status≤CONNECTED`.
10. **Hot** — if material to today's focus, refresh `hot.md` (≤150 words).

### C. Output contract

Return:

- Raw path(s) created
- Brain pages created/updated + status
- Index rows touched
- Contradictions found (do not silently overwrite; note under `## Open questions`)
- Promote candidates (CONNECTED/VERIFIED) — do not promote without Dylan

## Page template

```markdown
---
title: Example Entity
type: entity
status: CONNECTED
confidence: 0.7
sources:
  - raw/articles/2026-07-20-example.md
updated: 2026-07-20
promoted_by: null
tags: []
---

# Example Entity

## Summary

## Claims

- Claim text `(confidence)` — source

## Related

- [[Other Page]]

## Open questions

## Sources

- [[raw path or external URL]]
```

## Quick Reference

| Allowed status after ingest | Forbidden without approval |
|----------------------------|----------------------------|
| DRAFT, EXTRACTED, STRUCTURED, CONNECTED, VERIFIED | CANONICAL |
| Index + compile-log + hot updates | Business Context overwrite |
| New raw files | Edit/delete existing raw |

## Pitfalls

- Do not use `~/wiki` or generic `llm-wiki` path for Growth OS.
- Do not put thinking-only notes in `brain/` — use `workspace/drafts/`.
- Do not inflate confidence above evidence.
- Do not treat `Business Context/` or vault-root PARA as canonical destinations — update/create under `brain/` and leave stubs for migration.
- Before creating a page: check `brain/_indexes/*` for an existing canonical page.

## Verification

Raw file exists unchanged after compile; every new/updated brain page has frontmatter `status` ≤ VERIFIED; index row present; compile-log line appended.
