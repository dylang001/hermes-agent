# Hermes Obsidian Access Policy — Phase 7E

**Date:** 2026-07-15  
**Audience:** Hermes agents (CLI, gateway, Task OS), operators  
**Vault scope:** Growth OS only (`…/Obsidian Vault/Growth OS`)

Related: Agent Rules in vault (partially superseded), Templates/Permissions.md, this Phase 7E set.

---

## 1. Principles

1. **Obsidian = curated company knowledge**, not memory, tasks, or transcripts.
2. **Default posture: list / search / read.** Writes are exceptional and scoped.
3. **Mac Growth OS is authoring authority.** VPS is a mirror for agents running on `hermes-production`.
4. **Fail closed** on canon writes, full-vault access, secrets, and bidirectional sync without approval.
5. Prefer **one MCP filesystem mount on Growth OS** — do not also open the parent vault.

---

## 2. Allowed operations by default

| Op | Allowed | Notes |
|----|---------|-------|
| List directories under Growth OS | Yes | Prefer MCP / file tools over shell |
| Search filenames / content | Yes | Stay under Growth OS |
| Read any note under Growth OS | Yes | Treat `sensitivity: confidential` as restricted when frontmatter says so and agent Permissions does not grant it |
| Read outside Growth OS (rest of vault) | No | MCP must not mount parent vault |
| Write / patch / delete under canonical folders | No | Requires Dylan approval |
| Write under staging (below) | Yes | Default agent write target |

Canonical folders (approval required to mutate):

- Root Growth OS markdown that defines operating context (`INDEX.md`, `Agent Rules.md`, `Operating Principles.md`, `Current Priorities.md`, `Decision Log.md`, `Weekly Review.md`, `Research Inbox.md`, `ClickUp Documented Baseline.md`, etc.)
- `Business Context/`
- `Templates/`
- Future `02 Areas/`-style canon if promoted into Growth OS
- Vault-root PARA (`00 Inbox` … `05 Receipts`) — outside mount; agents should not reach them

---

## 3. Staging writes (MVP)

**Path:** `Growth OS/Drafts/Hermes/`

| Rule | Detail |
|------|--------|
| Create if missing | Operator creates once; agents may create dated subfolders under it |
| Naming | `YYYY-MM-DD-<slug>.md` or `Drafts/Hermes/<agent-or-task-id>/…` |
| Content | Proposals, research syntheses, draft SOPs, decision proposals — **not** live task state |
| Promotion | Humans (or Dylan-approved agent action) move/merge into canon |
| Sync | Staging rides Mac→VPS sync like any other Growth OS file |

Agents must not “fix” a canonical file by overwriting it from a draft without approval.

---

## 4. Append safe-zones (narrow; optional continuity)

Vault Agent Rules still allow appends to:

- `Agent Run Logs.md`
- `Decision Log.md` (only for decisions Dylan explicitly made **in the current session**)

Phase 7E MVP preference: prefer **new notes under `Drafts/Hermes/`** over appends. If appends continue, keep them line/row append only — no rewrites of prior rows, no edits to INDEX / Business Context / Templates.

Anything else (including Research Inbox promotion into Business Context) needs approval.

---

## 5. Approval for canonical folders

**Required when the agent would:**

- Create, edit, move, rename, or delete under any canonical path (§2)
- Promote `Drafts/Hermes/*` into a canonical path
- Change Agent Rules, Operating Principles, or INDEX
- Touch credentials, `.env`, API tokens, or REST plugin data

**Approval channel:** Dylan in the same session/channel, or ClickUp approval task (ClickUp owns approval records). Record a one-line receipt in Agent Run Logs or the ClickUp task.

**Not sufficient:** inferred silence, “obviously desired,” campaign approval for outreach, or Kanban task completion.

---

## 6. MCP configuration posture

| Setting | Required posture |
|---------|------------------|
| Mount path | Growth OS only (Mac or VPS absolute path) |
| Forbidden mount | `/root/obsidian-vault`, full `Obsidian Vault` parent, home directories |
| Local Mac | Keep `tools.include` read tools unless staging writes are explicitly enabled |
| VPS | Align with Mac: either read-only include list, or allow writes only after Drafts policy is enforced by path/skill instructions |
| Local REST API + reverse tunnel | Optional future; not required for MVP filesystem MCP |

Bundled `obsidian` skill teaches unrestricted create/edit — **operators must load Access Policy / Growth OS Agent Rules so skill guidance does not override this document.**

---

## 7. System boundaries (do not mix)

| Need | Use |
|------|-----|
| Durable user/agent fact | Mem0 / configured memory provider |
| “What did we say last Tuesday?” | Session Search |
| Worker execution state | Kanban |
| Queue / due / assignee / approve | ClickUp |
| Strategy / SOP / decision / playbook | Obsidian Growth OS |

Writing ClickUp task dumps or session transcripts into Growth OS canon is out of policy (weekly review distillations may land as **drafts** first).

---

## 8. Agent onboarding checklist

1. Read `INDEX.md`, `Operating Principles.md`, `Agent Rules.md`, this Access Policy (repo copy).
2. Confirm vault path (Mac Growth OS or VPS Growth OS) — never `/root/obsidian-vault`.
3. Default tools: list / search / read.
4. Default writes: `Drafts/Hermes/` only.
5. Stop and ask before touching canon.

---

## 9. Reconciliation of older docs

| Older source | Treat as |
|--------------|----------|
| `INTEGRATION_SPEC.md` cycle-1 REST + `approval_required` on every read | Historical; filesystem MCP is live; default reads without per-call approval |
| `INTEGRATION_SPEC.patch` | Obsolete; should not be reapplied |
| `SYNC_SETUP.md` Hermes write to vault-root PARA + Git commit | Outside Growth OS MCP mount; still requires Dylan before git push |
| Missing vault `AGENTS.md` | Create later from this policy + Agent Rules; until then this file + Agent Rules govern |
| Templates/Permissions.md | Compatible with Drafts-first; keep “never edit Areas/Decisions without approval” |
