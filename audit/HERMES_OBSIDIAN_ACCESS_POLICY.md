# Hermes Obsidian Access Policy — Knowledge OS v2

**Date:** 2026-07-20  
**Audience:** Hermes agents (CLI, gateway, Task OS), operators  
**Vault scope:** Growth OS only (`…/Obsidian Vault/Growth OS`)

Related: vault `AGENTS.md`, `SCHEMA.md`, `ONTOLOGY.md`, `TAXONOMY.md`, Agent Rules.

---

## 1. Principles

1. **Obsidian = curated company knowledge + compiled Knowledge OS brain**, not Mem0, tasks, or raw transcripts-as-canon.
2. **Capture once. Compile forever.** `raw/` is immutable; Hermes compiles into `brain/`.
3. **Mac Growth OS is authoring authority.** VPS is a mirror for agents on `hermes-production`.
4. **Fail closed** on CANONICAL / root policy writes, full-vault access, secrets, and bidirectional sync without approval.
5. Prefer **one MCP filesystem mount on Growth OS** — do not also open the parent vault.
6. **Never inject vault bodies into SOUL.md / system prompt.** Orient via `hot.md` + progressive indexes.
7. **Business Context is transitional** — not a parallel source of truth after entity migration.
8. **Vault-root PARA is not the working brain** — migrating to `archive/para-migration/`.

---

## 2. Allowed operations by default

| Op | Allowed | Notes |
|----|---------|-------|
| List / search / read under Growth OS | Yes | Prefer MCP / file tools |
| Read outside Growth OS | No | MCP must not mount parent vault |
| Append new files under `raw/` | Yes | Never edit/delete existing raw |
| Write `brain/**` at DRAFT…VERIFIED | Yes | Frontmatter `status` required |
| Update `hot.md`, append `compile-log.md` | Yes | Keep hot ≤150 words |
| Write `workspace/**` (incl. promotions) | Yes | Thinking + promote packages |
| Read-only lint + report under `workspace/drafts/` | Yes | No auto-merge/delete |
| Set `status: CANONICAL` or edit CANONICAL | No | Requires Dylan + `wiki-promote` |
| Mutate root policy / treat BC as SoT | No | Requires Dylan approval |

### Canonical (approval required)

- Root operating docs: `INDEX.md`, `AGENTS.md`, `SCHEMA.md`, `ONTOLOGY.md`, `Agent Rules.md`, `Operating Principles.md`, `Current Priorities.md`, …
- Brain pages with `status: CANONICAL`
- Destructive archive/delete of `raw/` or mass delete of brain pages
- Vault-root PARA outside the Growth OS mount (except read during migration)
- Enabling autonomous ingest/merge/archive cron before Phase C critical-clean

### Knowledge OS auto-write lanes (authority B)

| Path | Rule |
|------|------|
| `raw/**` | Create new files only |
| `brain/**` | Create/update when `status` ∈ {DRAFT, EXTRACTED, STRUCTURED, CONNECTED, VERIFIED} |
| `brain/_indexes/**` | Maintain indexes |
| `hot.md` | Rewrite allowed (keep short) |
| `compile-log.md` | Append only |
| `workspace/**` | Free (non-factual) + promotion packages |
| `logs/**` | Append |
| `Drafts/Hermes/**` | Transitional; prefer `workspace/promotions/` |
| `Templates/Knowledge OS/**` | May copy from |

---

## 3. Staging and promotions

**Default proposal path:** `Growth OS/workspace/promotions/` (legacy: `Drafts/Hermes/promotions/`)  
**CANONICAL packages:** `YYYY-MM-DD-<slug>.md`

Promotion to CANONICAL requires Dylan approval. Do **not** mirror into Business Context as a second SoT.

---

## 4. Append safe-zones (continuity)

Still allowed as append-only:

- `Agent Run Logs.md`
- `Decision Log.md` (only for decisions Dylan explicitly made **in the current session**)

Prefer Knowledge OS compile + promote packages over rewriting root docs.

---

## 5. Approval channel

**Required when the agent would:**

- Set or edit CANONICAL brain pages
- Change Agent Rules, Operating Principles, INDEX/SCHEMA/ONTOLOGY/AGENTS authority
- Treat `Business Context/` as live SoT
- Edit/delete immutable `raw/` sources
- Expand MCP beyond Growth OS
- Auto-resolve substantive contradictions or delete knowledge

**Approval channel:** Dylan in the same session/channel, or ClickUp approval task.  
**Not sufficient:** inferred silence, “obviously desired,” campaign approval for outreach.

---

## 6. MCP configuration posture

| Setting | Required posture |
|---------|------------------|
| Mount path | Growth OS only (Mac or VPS absolute path) |
| Forbidden mount | `/root/obsidian-vault`, full `Obsidian Vault` parent |
| Writes | Allowed under Knowledge OS lanes; skills enforce status gates |
| Sync | Mac→VPS push only (paused during KOS v2 freeze) |
| Local REST API | **Deprecated for Hermes**; filesystem MCP is canonical. Plugin may remain for Claudian/personal use — Hermes must not depend on it. |

Bundled generic `obsidian` / `llm-wiki` skills must defer to this policy and Growth OS `SCHEMA.md`. Prefer `knowledge-os/*` skills.

---

## 7. System boundaries (do not mix)

| Need | Use |
|------|-----|
| Durable user/agent fact | Mem0 / configured memory provider |
| “What did we say last Tuesday?” | Session Search |
| Session engineering state | CE V2 Working Memory (runtime — not vault) |
| Worker execution state | Kanban |
| Queue / due / assignee / approve | ClickUp |
| Strategy / compiled knowledge | Obsidian Growth OS `brain/` |

---

## 8. Agent onboarding checklist

1. Read `hot.md`, `INDEX.md`, `AGENTS.md`, `SCHEMA.md`, `Agent Rules.md`, this Access Policy.
2. Confirm vault path (Mac or VPS Growth OS) — never `/root/obsidian-vault`.
3. Progressive open: indexes → page. No vault dump into prompts.
4. Auto-writes only in Knowledge OS lanes; CANONICAL via `wiki-promote`.
5. After substantial knowledge work: load `self-improvement` if reusable rules emerged.

---

## 9. Reconciliation of older docs

| Older source | Treat as |
|--------------|----------|
| Phase 7E “Drafts-only writes” | Superseded by Knowledge OS authority B for `raw/` + `brain/` DRAFT…VERIFIED |
| `INTEGRATION_SPEC.md` cycle-1 REST | **Deprecated for Hermes**; filesystem MCP is live |
| Generic `llm-wiki` → `~/wiki` | Do not use for Growth OS; use `knowledge-os` skills |
| Vault-root `Home.md` PARA layout | Pointer only; not working brain |
| `Business Context/` | Transitional until Phase E archive |
| Templates/note-template.md | Retired; use Templates/Knowledge OS |
