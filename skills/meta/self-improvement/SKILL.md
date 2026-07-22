---
name: self-improvement
description: Evolve SOUL.md from repeated session corrections.
version: 0.1.0
author: Dylan Angloher
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: meta
    tags: [self-improvement, soul, memory, lessons, continuous-learning]
---

# Self-Improvement Skill

Run at the end of substantial work so Hermes improves from friction without bloating `SOUL.md`. Propose diffs only — never silently rewrite identity or project memory.

## When to Use

- End of a non-trivial engineering or ops session (multi-step fix, deploy, investigation).
- End of substantial **Knowledge OS** work (multi-page ingest, lint/refactor, research compile) — after `wiki-ingest` / `wiki-lint` / `wiki-refactor`.
- The user corrected Hermes, or the same mistake appeared twice.
- A reusable workflow or project convention became clear.
- After a failed approach that revealed a durable rule.
- When a Knowledge OS procedure should become a **new skill** rather than more SOUL.md text.

## Do Not Use

- Trivial one-liners or pure Q&A with no durable lesson.
- To dump session transcripts into `SOUL.md`.
- To add procedure detail that belongs in a dedicated skill.

## Prerequisites

- Read current `SOUL.md` at `$HERMES_HOME/SOUL.md`.
- Check project `HERMES.md` / `.hermes.md` and any active skill that already covers the lesson.
- Prefer evidence from this session (corrections, failed commands, repeated asks).

## How to Run

Execute the checklist below. Output a proposed diff for approval. Do not apply changes unless the user explicitly asks.

## Checklist

1. **Review the session** — what was attempted, what failed, what the user corrected.
2. **Identify repeated friction** — same confusion, same wrong path, same missing check.
3. **Identify incorrect assumptions** — what Hermes treated as fact without evidence.
4. **Identify reusable conventions** — project-specific norms worth remembering.
5. **Deduplicate** — does `SOUL.md`, `HERMES.md`, or an existing skill already cover it?
6. **Draft a concise addition** — one rule, high leverage, ≤5 lines when possible.
7. **Prune** — if adding, also propose removals or merges for redundant/conflicting rules.
8. **Propose a diff** — show exact before/after; wait for approval before writing files.

## Where to put the lesson

| Kind of lesson | Destination |
|----------------|-------------|
| Durable agent behaviour (all sessions) | `$HERMES_HOME/SOUL.md` |
| Repo / project convention | project `HERMES.md` or `.hermes.md` |
| Multi-step procedure (Composio, deploy, Knowledge OS ops) | dedicated skill under `$HERMES_HOME/skills/` (prefer `knowledge-os/` for vault compiler workflows) |
| Compiled company knowledge | Growth OS `brain/` via `wiki-ingest` — not SOUL.md |
| One-off fact | do not store |

Keep `SOUL.md` around 150–200 lines of principles. If a draft would push it past that, extract procedure into a skill instead.

## Output contract

Return:

- **Session lessons** (bullets)
- **Already covered** (skip)
- **Proposed changes** (path + unified diff or exact replacement text)
- **Prune candidates** (rules to remove/merge)
- **Ask** — apply / edit / discard

## Pitfalls

- Do not add rules that only restate priorities already in `SOUL.md`.
- Do not encode secrets, absolute private paths, or one-off ticket IDs as standing rules.
- Do not auto-edit `SOUL.md` on the VPS without explicit approval (production home is `/opt/hermes/home`).
- Two corrections of the same class → almost always a rule; one typo correction → usually not.

## Verification

Before closing: the proposal is shorter than the session narrative, points at a single destination file, and includes a prune check — not only additions.
