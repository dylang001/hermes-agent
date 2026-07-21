# Hermes Obsidian Access Policy — Knowledge OS v2

**Date:** 2026-07-21  
**Audience:** Hermes agents (CLI, gateway, Task OS), operators  
**Vault scope:** Growth OS only (`…/Obsidian Vault/Growth OS`)  
**Operating model:** Controlled Model B

Related: vault `AGENTS.md` (`source_of_truth: true`), `SCHEMA.md`, `ONTOLOGY.md`, `TAXONOMY.md`, Agent Rules.

---

## 1. Principles

1. **Obsidian = curated company knowledge + compiled Knowledge OS brain**, not Mem0, tasks, or raw transcripts-as-canon.
2. **Capture once. Compile forever.** New `raw/` files may be created; once created they are **immutable**. Hermes compiles into `brain/`.
3. **Mac Growth OS is versioned authority.** VPS is Hermes’ **writable runtime mirror**. Durability = hash-based VPS→Mac pull-back → Mac Git → Mac→VPS sync.
4. **Fail closed** on CANONICAL / governance writes, full-vault access, secrets, and treating bidirectional sync as authority.
5. Prefer **one MCP filesystem mount on Growth OS** — do not also open the parent vault.
6. **Never inject vault bodies into SOUL.md / system prompt.** Orient via `wiki-daily` → `hot.md` + progressive indexes.
7. **Business Context and vault-root PARA are not SoT** (archived).
8. **No parallel top-level SoT trees.** Compile into `brain/**`; proposals for new top-level folders only.

---

## 2. Controlled Model B

| Field | Value |
|-------|--------|
| Authoritative copy | Mac Git vault `Growth OS/` |
| Hermes runtime copy | `/opt/hermes/data/obsidian/Growth OS` |
| Hermes may write | Approved lanes on VPS (and Mac only if that is the active mount) |
| Durability | Pull-back consumes touched-path receipts; hash compare vs `last_common_hash` |
| Conflicts | Both sides changed → quarantine both; live Mac untouched |
| Sync restore | Mac→VPS after commit |

### Hermes may directly write

- `workspace/**`
- `logs/**` (append)
- `hot.md`
- `compile-log.md` (append only)
- `brain/_indexes/**`
- `brain/**` at DRAFT…VERIFIED (autonomous DRAFT→VERIFIED when SCHEMA criteria met)
- **new** `raw/**` artifacts only

### Hermes may only propose

- Governance changes
- CANONICAL promote/demote / CANONICAL edits
- Deletes, moves, archives
- New top-level folders
- Unsupported status changes

### Raw rules (explicit)

| Op | Allowed? |
|----|----------|
| Create new raw file | Yes |
| Edit existing raw | No |
| Move existing raw | No |
| Delete existing raw | No |

---

## 3. Decision Log

- Subagents **never** append.
- Coordinating Hermes session may append **verified factual** entries.
- Dylan approvals require a **traceable approval reference**.
- Material governance decisions remain proposals until approved.

---

## 4. Staging and promotions

**Default proposal path:** `Growth OS/workspace/promotions/`  
**Touched-path receipts:** `Growth OS/workspace/receipts/`  
**CANONICAL packages:** `YYYY-MM-DD-<slug>.md` via `wiki-promote` + Dylan OK.

Do **not** mirror into Business Context as a second SoT.

---

## 5. Lint during reconciliation (and generally)

`knowledge-os-lint` is **read-only** regarding vault content:

- May run `scripts/knowledge_os_lint.py`
- May write a **new UTC-timestamped** report under `workspace/drafts/`
- Must **not** overwrite prior reports
- Must **not** append `compile-log.md`
- Must **not** create refactor/promote packages
- Must **not** merge, ingest, archive, or rewrite pages

Write-capable cron (daily/nightly/weekly/monthly) stays **paused** until Phase 5 exit criteria:

1. All mutating Knowledge OS skills are receipt-aware (`scripts/knowledge_os_mutation.py`)
2. Obsolete VPS trees retired (`Constitution/`, `Strategy/`, `Playbooks/`, `SOPs/`, …)
3. One scheduled job completes an observed Model B cycle

**Limited Model B pilot (2026-07-21):** Hermes may perform **explicitly user-directed** writes in approved lanes only, using the receipt wrapper + immediate pull-back cycle. Lint cron may remain enabled.

---

## 6. MCP / sync posture

| Setting | Required posture |
|---------|------------------|
| Mount path | Growth OS only |
| Forbidden mount | `/root/obsidian-vault`, full vault parent |
| Sync push | Mac→VPS via `sync-obsidian-to-hermes-remote.sh` (Documents-capable shell) |
| Sync pull-back | Controlled hash-based VPS→Mac (Model B) |
| Local REST | Deprecated for Hermes |

Prefer `knowledge-os/*` skills over generic `llm-wiki`.

---

## 7. System boundaries

| Need | Use |
|------|-----|
| Durable user/agent fact | Mem0 — not SOPs / implementation-state |
| Session recall | Session Search |
| Runtime engineering state | CE V2 Working Memory |
| Queue / due / approve | ClickUp |
| Compiled knowledge | Growth OS `brain/` |

---

## 8. Onboarding checklist

1. Read `AGENTS.md` (SoT), `hot.md`, `SCHEMA.md`, Agent Rules, this policy.
2. Confirm Growth OS path (Mac or VPS) — never `/root/obsidian-vault`.
3. Orient: indexes → page. No vault dump.
4. Write only approved lanes; CANONICAL via promote package.
5. Emit touched-path receipt after knowledge-heavy runs.

---

## 9. Model B tooling (Mac)

| Tool | Role |
|------|------|
| `~/.hermes/bin/kos-mac-to-vps.sh` | Mac→VPS convergence (**no `--delete`**) |
| `~/.hermes/bin/kos-model-b.py` | Receipts, baseline, pull-back, hash verify |

Receipt schema: `kos-touched-path-receipt/v1` under `Growth OS/workspace/receipts/`.  
Baseline: `Growth OS/workspace/sync/baseline-hashes.json`.  
Quarantine: `Growth OS/workspace/quarantine/`.

Hermes must emit a touched-path receipt after knowledge-heavy writes. Pull-back is Mac-side; Hermes does not Git-commit the Mac vault.
