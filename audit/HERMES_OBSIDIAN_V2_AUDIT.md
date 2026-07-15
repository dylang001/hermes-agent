# Hermes Obsidian V2 Audit — Phase 7E

**Date:** 2026-07-15  
**Scope:** Docs-first inventory of existing Obsidian / Growth OS work for a pragmatic MVP.  
**Canonical Mac vault:** `/Users/dylanangloher/Documents/Obsidian Vault/Growth OS`  
**VPS mirror:** `/opt/hermes/data/obsidian/Growth OS`  
**Do not use:** `/root/obsidian-vault` (stale; absent/inaccessible for `dylan` on current VPS)

Companion docs:

- `audit/HERMES_OBSIDIAN_SYNC_DESIGN.md`
- `audit/HERMES_OBSIDIAN_ACCESS_POLICY.md`
- `audit/HERMES_OBSIDIAN_VALIDATION_REPORT.md`
- `docs/HERMES_KNOWLEDGE_MAINTENANCE_RUNBOOK.md`

---

## 1. Verdict (one paragraph)

Growth OS exists and is populated on both Mac and VPS. Hermes already mounts it via `@modelcontextprotocol/server-filesystem` (correct VPS path as of the July 15 path fix). Mac→VPS push and an older bidirectional rsync exist under `~/.hermes/bin/`, but the sync LaunchAgent is **not loaded**, so automated sync is not running. A reverse tunnel LaunchAgent **is** running and **failing** (port 27124). Policy docs in the vault are partially superseded and inconsistent (cycle-1 REST API vs filesystem MCP; missing `AGENTS.md` and `Drafts/Hermes`). MVP is: one Mac→VPS sync workflow + staged drafts + approval for canon — not a new knowledge system.

---

## 2. Architecture reminder (non-negotiable splits)

| System | Owns | Does not own |
|--------|------|--------------|
| **Obsidian Growth OS** | Curated company knowledge: strategy, decisions, playbooks, research inbox, agent rules | Live tasks, due dates, approvals, session transcripts, ephemeral memories |
| **Mem0 / memory providers** | Durable facts/preferences (environment-specific) | Canon SOPs; do not dump vault into Mem0 |
| **Session Search** | Transcripts / prior-session detail | Strategy docs |
| **Kanban** | Local multi-agent execution state | Company knowledge |
| **ClickUp** | Queue, task state, approvals, due dates | Strategy second brain |

Do not invent a second knowledge base. Do not treat Obsidian as Mem0 or as a task queue.

---

## 3. Inventory — what exists

### 3.1 Vault (Mac) — **exists**

Path: `/Users/dylanangloher/Documents/Obsidian Vault/`

| Item | Status |
|------|--------|
| `Growth OS/` | Present; core docs + `Business Context/` + `Templates/` |
| PARA folders (`00 Inbox` … `05 Receipts`) | Present at vault root (outside Growth OS MCP mount) |
| `SYNC_SETUP.md` | Present; documents Git-primary workflow; still mentions `/root/obsidian-vault-rollback-*` |
| Private git remote | `git@github.com:dylang001/obsidian-vault-private.git` |
| `Growth OS/Drafts/Hermes/` | **Missing** (needed for MVP write staging) |
| Vault-root `AGENTS.md` | **Missing** (referenced by Agent Rules / templates; not on disk) |
| `.claude/agents/` | Present (Claude-side agent defs; not Hermes runtime) |

Growth OS root documents observed: `INDEX.md`, `Agent Rules.md`, `Operating Principles.md`, `Decision Log.md`, `Current Priorities.md`, `Agent Run Logs.md`, `Research Inbox.md`, `INTEGRATION_SPEC.md`, `ClickUp Documented Baseline.md`, templates, business context files.

### 3.2 Vault (VPS) — **exists**

```
/opt/hermes/data/obsidian/
  Growth OS/     # live mirror (content aligned with Mac as of last successful push/clone)
  GrowthOS -> Growth OS   # no-space symlink for rsync path safety
```

- `/root/obsidian-vault`: absent/inaccessible for service user `dylan` (correct).
- VPS still contains `INTEGRATION_SPEC.patch` (Decision Log said delete on Mac cleanup; mirror not fully reconciled).

### 3.3 Sync scripts — **exist; automation incomplete**

| Artifact | Path | Behavior | Notes |
|----------|------|----------|-------|
| Push-only rsync | `~/.hermes/bin/sync-obsidian-to-hermes-remote.sh` | Mac `Growth OS` → `hermes-production:/opt/hermes/data/obsidian/Growth OS` | Closest to MVP; excludes workspace/cache/trash; **no lock, dry-run, retries, mass-delete guard, logging** |
| Bidirectional rsync | `~/.hermes/bin/sync-obsidian-vault.sh` | `--update` pull then push via `GrowthOS` symlink | Unrestricted bidirectional; conflicts with Phase 7E “Mac primary / fail closed” without approval |
| LaunchAgent (sync) | `~/Library/LaunchAgents/com.hermes.obsidian-vault-sync.plist` | Every 300s → `sync-obsidian-vault.sh` | **Not loaded** (`launchctl` cannot find service); **no sync logs** under `~/.hermes/logs/` |
| LaunchAgent (tunnel) | `~/Library/LaunchAgents/com.hermes.obsidian-reverse-tunnel.plist` | `-R 127.0.0.1:27124:127.0.0.1:27124 hermes-production` | **Loaded, running, failing** (exit 255; remote listen port in use / forward fails). Legacy Local REST API path |

SSH alias `hermes-production` is valid (`HostName` + user `dylan` + ed25519).

Research notes only (no implementation): `~/.hermes/research/obsidian-remote/{git-sync,syncthing}.json`.

### 3.4 MCP — **configured both sides**

| Env | Mount | Tools posture |
|-----|-------|----------------|
| Local `~/.hermes/config.yaml` | filesystem MCP → Mac Growth OS | `tools.include`: `read_file`, `list_directory`, `search_grep`, `get_file_info` (read-leaning) |
| VPS `/opt/hermes/home/config.yaml` | filesystem MCP → `/opt/hermes/data/obsidian/Growth OS` | Path fixed (Phase 1); **no equivalent include list observed in the VPS snippet** — treat write surface as wider until tightened |

Also present locally: `OBSIDIAN_API_TOKEN` / `OBSIDIAN_MCP_URL` in `.env`, and `~/.hermes/secrets/obsidian_api_token` — leftovers from the unused Local REST API / remote MCP cycle. Bundled skill `skills/note-taking/obsidian/SKILL.md` is generic filesystem guidance (full create/edit), not Growth-OS policy-aware.

### 3.5 Repo / audit docs — prior Obsidian-for-agents work

| Doc | Role |
|-----|------|
| `CANONICAL_CONTEXT.md` | Documents VPS Growth OS path; forbids `/root/obsidian-vault` |
| `HERMES_OBSIDIAN_STATUS.md` (2026-06-19) | Stale (“no MCP”); superseded |
| `HERMES_CONTEXT_MEMORY_OBSIDIAN_PLAN.md` | Correct split: Obsidian ≠ memory |
| `agent/runtime_metadata.py` | Remaps `/root/obsidian-vault` → Growth OS |
| `audit/HERMES_*`, Phase 6 audits | Path breakage / capability inventory |
| `tasks/todo.md` | Obsidian path fix done; search validation open |
| Vault `INTEGRATION_SPEC.md` | Cycle-1 Local REST API proposal; **not how production MCP actually runs** |

### 3.6 Cleanup / unfinished threads

- Vault Decision Log (2026-07-05): cleanup plan referenced at `/root/audit/cleanup-plan-2026-07-05.md` (stale root path); Agent Rules cite AGENTS.md constitution that is **not in the vault**.
- Safe-zone write policy in Agent Rules (append to Agent Run Logs / Decision Log) vs Templates/Permissions (propose-only, humans promote) — **partially conflict**.
- Reverse tunnel kept alive despite filesystem MCP — operational noise and security surface.
- Bidirectional sync script should not be the default MVP path without explicit approval.

---

## 4. Gaps vs Phase 7E MVP

1. No production-grade **Mac→VPS** sync (lock, dry-run, logs, retries, mass-delete guards).
2. No `Growth OS/Drafts/Hermes/` staging directory.
3. Access policy not encoded in one runbook; Agent Rules / INTEGRATION_SPEC / Templates disagree.
4. VPS filesystem MCP likely allows writes beyond Mac’s include list.
5. Validation of Obsidian search/list/read on live gateway still open (`tasks/todo.md`).
6. Autostart sync Agent unloaded; failing reverse tunnel still loaded.

---

## 5. MVP recommendation (do this; nothing more)

1. **One sync workflow:** harden `sync-obsidian-to-hermes-remote.sh` (Mac→VPS only) per sync design; optionally wire LaunchAgent to that script after dry-run proof.
2. **Staged drafts:** create `Growth OS/Drafts/Hermes/`; agent writes land there by default.
3. **Canon approval:** list/search/read default; promote Drafts → canonical folders only with Dylan approval.
4. **Park:** bidirectional rsync, Syncthing, Obsidian Git as the Hermes mirror, reverse tunnel REST bridge, second knowledge stores.

---

## 6. Explicit non-goals

- Replacing Mem0 / Session Search / Kanban / ClickUp.
- Full dual-master sync or auto-promote to canon.
- Public vault exposure or cloud sync products as the Hermes path.
- Reintroducing `/root/obsidian-vault`.
