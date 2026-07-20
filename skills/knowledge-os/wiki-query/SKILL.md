---
name: wiki-query
description: Answer via progressive indexes; offer compile.
version: 0.1.0
author: Dylan Angloher
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: knowledge-os
    tags: [obsidian, wiki, query, knowledge-os]
    related_skills: [wiki-daily, wiki-ingest, wiki-promote]
---

# Wiki Query

Answer questions from the compiled Growth OS brain using a progressive index walk. High-value answers should be offered for compilation.

## When to Use

- User asks about strategy, entities, prior decisions, or compiled research in Growth OS.
- After `wiki-daily` when a specific fact is needed.

## Prerequisites

- Prefer `wiki-daily` orient first in a cold session.
- Never vault-dump into the prompt.

## How to Run

1. Walk: `brain/_indexes/root.md` → type index → candidate page(s).
2. Open only the pages needed; cite paths.
3. Answer with Facts / Assumptions / Unknowns / Recommendations.
4. If the answer is durable and not already in brain: ask **Should this become knowledge?**
5. If yes → hand off to `wiki-ingest` (compile ≤ CONNECTED) or draft under `workspace/drafts/` first if still messy.

## Quick Reference

| Step | Target |
|------|--------|
| Type pick | entities / concepts / projects / decisions |
| Index | `brain/_indexes/<type>.md` |
| Page | `brain/<type>/<Page>.md` |
| Missing | Say so; offer research + ingest |

## Pitfalls

- Do not invent CANONICAL status.
- Do not treat `workspace/` as facts.
- Do not treat Business Context or vault-root PARA as SoT — prefer `brain/`.
- Prefer citing `sources:` frontmatter.

## Verification

Answer cites at least one real path or explicitly says not in brain; compile offer only when durable.
