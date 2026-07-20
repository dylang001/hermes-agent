# Hermes Knowledge Maintenance Runbook

**Date:** 2026-07-20  
**Owner:** Dylan (+ Hermes operators)  
**Purpose:** Operate Growth OS as a Knowledge OS — Hermes compiles; Obsidian persists — without turning the vault into Mem0, ClickUp, or a prompt dump.

Canonical paths:

- Mac: `/Users/dylanangloher/Documents/Obsidian Vault/Growth OS`
- VPS: `/opt/hermes/data/obsidian/Growth OS`
- Never: `/root/obsidian-vault`

Policy: `audit/HERMES_OBSIDIAN_ACCESS_POLICY.md` · Vault: `SCHEMA.md` · `AGENTS.md` · `ONTOLOGY.md`

Skills: `$HERMES_HOME/skills/knowledge-os/` (`wiki-daily`, `wiki-ingest`, `wiki-query`, `wiki-promote`, `wiki-lint`, `wiki-refactor`, `wiki-research`)

Lint script: `scripts/knowledge_os_lint.py` (read-only)

---

## 1. Cadence

| Cadence | Action | Skill / job |
|---------|--------|-------------|
| Session start (knowledge work) | Read `hot.md` + indexes only | `wiki-daily` |
| On capture / research | Append `raw/` → compile ≤ CONNECTED | `wiki-ingest` / `wiki-research` (**after Phase C**) |
| After valuable answers | Offer “become knowledge?” | `wiki-query` |
| Every 6h (cron) | Read-only lint | `knowledge-os-lint` (**enabled**) |
| Daily (cron) | Ingest nudge + hot refresh | `knowledge-os-daily` (**disabled until Phase C critical-clean**) |
| Nightly (cron) | Lint + light repair | `knowledge-os-nightly` (**disabled until Phase C**) |
| Weekly (human 15–20m + agent) | Synthesis, gap analysis, promote review | `wiki-refactor` + Dylan promote |
| Monthly | Archive entropy reduction | `wiki-refactor` archive pass |
| After substantial work | Propose SOUL/skill diffs | `self-improvement` |

---

## 2. What goes where

| Content | Put it in | Do not put it in Obsidian |
|---------|-----------|---------------------------|
| Immutable captures | `raw/` | Editing prior raw files |
| Compiled facts (auto) | `brain/**` status DRAFT…VERIFIED | System prompt / SOUL |
| Approved durable truth | `brain/**` CANONICAL (Dylan via wiki-promote) | Auto-CANONICAL without Dylan |
| Thinking / scratch | `workspace/` | Treated as facts |
| Promote packages | `workspace/promotions/` or `Drafts/Hermes/promotions/` | Silent overwrite of canon |
| Strategy / ICP | `brain/projects|entities|…` | Archived `Business Context/`; Mem0 as SOP substitute |
| Live tasks / due dates | ClickUp | Growth OS |
| Session engineering state | CE V2 WM (runtime) | Vault “working memory” |
| Ephemeral preferences | Mem0 | Growth OS |

---

## 3. Sync operations (Mac)

**Preferred script:** `~/.hermes/bin/sync-obsidian-to-hermes-remote.sh`

```bash
HERMES_OBSIDIAN_SYNC_DRY_RUN=1 ~/.hermes/bin/sync-obsidian-to-hermes-remote.sh
~/.hermes/bin/sync-obsidian-to-hermes-remote.sh
```

```bash
ssh hermes-production 'ls -la "/opt/hermes/data/obsidian/Growth OS" | head'
ssh hermes-production 'test -f "/opt/hermes/data/obsidian/Growth OS/SCHEMA.md" && echo SCHEMA_OK'
```

**Do not** load bidirectional sync, sync the full vault root, or use `--delete` without guards.

---

## 4. Agent access (ops)

1. MCP mount = Growth OS only.
2. Orient: `hot.md` → `INDEX.md` / `AGENTS.md` / `brain/_indexes/root.md` → page.
3. Auto-writes: Knowledge OS lanes (Access Policy §2).
4. CANONICAL / root policy → Dylan + `wiki-promote`. Do not treat Business Context as SoT.
5. Never vault-dump into system prompt. Filesystem MCP only (Local REST deprecated for Hermes).

---

## 5. Promotion checklist (CONNECTED/VERIFIED → CANONICAL)

1. Page exists under `brain/` with status CONNECTED or VERIFIED.
2. `wiki-promote` writes package under `Drafts/Hermes/promotions/`.
3. Dylan reviews (or ClickUp approval linked).
4. Apply: set `status: CANONICAL`, `promoted_by`, update indexes. Do **not** mirror into Business Context.
5. Mac→VPS sync (when unpaused).
6. Log in Agent Run Logs + `compile-log.md`.

---

## 6. Cron jobs (VPS — production)

Production cron is **VPS only** (`HERMES_HOME=/opt/hermes/home`). Templates also live in repo `cron/knowledge_os_jobs.json`.

| Job id | Schedule (UTC expr) | Prompt focus | VPS status |
|--------|---------------------|--------------|------------|
| `knowledge-os-lint` | `0 */6 * * *` | read-only lint | template **enabled** (Phase G); VPS install after sync gate |
| `knowledge-os-daily` | `0 7 * * *` | hot/indexes + pending raw ingest ≤ VERIFIED | template **enabled**; VPS after sync gate |
| `knowledge-os-nightly` | `30 2 * * *` | lint + safe index/metadata; review queues | template **enabled**; VPS after sync gate |
| `knowledge-os-weekly` | `0 9 * * 1` | promote queue packages (no apply) | template **enabled**; VPS after sync gate |
| `knowledge-os-monthly` | `0 10 1 * *` | archive/ontology proposals only | template **enabled**; VPS after sync gate |

Cron sessions use skills `wiki-daily`, `wiki-ingest`, `wiki-lint`, `wiki-refactor`, `wiki-promote` as appropriate. Default `skip_memory` is fine.

**Never auto:** CANONICAL apply, raw edit/delete, substantive archive/delete, contradiction resolution, policy/AGENTS/SCHEMA rewrites, unapproved moves.

Install/resume on VPS only after Mac→VPS sync is unpaused:

```bash
ssh hermes-production 'cd /opt/hermes/app && HERMES_HOME=/opt/hermes/home .venv/bin/python -c "
from cron.jobs import resume_job
for n in [\"knowledge-os-lint\",\"knowledge-os-daily\",\"knowledge-os-nightly\",\"knowledge-os-weekly\",\"knowledge-os-monthly\"]:
    print(n, resume_job(n).get(\"next_run_at\"))
"'
```

---

## 7. Incident responses

| Symptom | Action |
|---------|--------|
| Agent uses `/root/obsidian-vault` | Remap + heal; never recreate that path |
| VPS knowledge stale | Mac→VPS push |
| Accidental CANONICAL / Business Context overwrite | Restore from Mac vault history; re-sync; Agent Run Log |
| Brain page without frontmatter status | Lint failure — add status ≤ CONNECTED or quarantine to workspace |
| Prompt cache / huge context | Stop vault dumps; use hot + indexes only |

---

## 8. Explicit non-maintenance

- Do not rebuild a parallel `~/wiki` for Growth OS.
- Do not auto-CANONICAL.
- Do not auto-commit the private vault git repo from Hermes.
- Do not expand MCP to the full vault.
- Do not store secrets in Growth OS notes.

---

## 9. Pointers

| Doc | Path |
|-----|------|
| Access policy | `audit/HERMES_OBSIDIAN_ACCESS_POLICY.md` |
| Sync design | `audit/HERMES_OBSIDIAN_SYNC_DESIGN.md` |
| Runtime paths | `CANONICAL_CONTEXT.md` |
| Vault schema | Growth OS `SCHEMA.md` |
