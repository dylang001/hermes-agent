# Hermes Knowledge Maintenance Runbook

**Date:** 2026-07-15  
**Owner:** Dylan (+ Hermes operators)  
**Purpose:** Keep Growth OS accurate, synced to VPS, and safely readable by agents — without turning Obsidian into a second task system or memory backend.

Canonical paths:

- Mac: `/Users/dylanangloher/Documents/Obsidian Vault/Growth OS`
- VPS: `/opt/hermes/data/obsidian/Growth OS`
- Never: `/root/obsidian-vault`

Policy refs: `audit/HERMES_OBSIDIAN_ACCESS_POLICY.md`, `audit/HERMES_OBSIDIAN_SYNC_DESIGN.md`

---

## 1. Weekly rhythm (15–20 minutes)

1. **Scan Research Inbox** — promote verified claims into `Business Context/` or reject; leave unverified as inbox/drafts.
2. **Decision Log** — ensure any architecture calls from the week have a dated row.
3. **Current Priorities** — sync wording with ClickUp (priorities live in Obsidian; due dates stay in ClickUp).
4. **Drafts review** — walk `Growth OS/Drafts/Hermes/`; promote, archive, or delete.
5. **Sync** — run Mac→VPS push (or confirm LaunchAgent succeeded) after edits (§3).
6. **Smoke** — one list/search via Hermes against Growth OS; no stale `/root` paths in logs.

Optional: append a short note to Weekly Review from the week’s distillations only (not raw ClickUp dumps).

---

## 2. What goes where

| Content | Put it in | Do not put it in Obsidian |
|---------|-----------|---------------------------|
| Strategy / ICP / voice | `Business Context/` | Mem0 as a substitute for the SOP |
| Operating rules | `Agent Rules.md` / Access Policy | Chat-only tribal knowledge |
| Decisions | `Decision Log.md` | ClickUp comments alone (link both ways by ID) |
| Agent proposals | `Drafts/Hermes/` | Overwriting INDEX / Templates |
| Live tasks / due dates | ClickUp | Growth OS canon |
| Session transcripts | Session Search | Growth OS (except distilled lessons) |
| Ephemeral preferences | Mem0 | Growth OS |

---

## 3. Sync operations (Mac)

**Preferred script:** `~/.hermes/bin/sync-obsidian-to-hermes-remote.sh`  
(Harden per sync design before relying on automation.)

```bash
# Dry-run once tooling supports it
HERMES_OBSIDIAN_SYNC_DRY_RUN=1 ~/.hermes/bin/sync-obsidian-to-hermes-remote.sh

# Live push (Growth OS only → hermes-production)
~/.hermes/bin/sync-obsidian-to-hermes-remote.sh
```

**Checks**

```bash
ssh hermes-production 'ls -la "/opt/hermes/data/obsidian/Growth OS" | head'
ssh hermes-production 'test -L /opt/hermes/data/obsidian/GrowthOS && readlink /opt/hermes/data/obsidian/GrowthOS'
```

**Do not**

- Load bidirectional `sync-obsidian-vault.sh` without approval.
- Sync the entire Obsidian vault root to the VPS MCP mount.
- Use `--delete` without mass-delete guards + explicit force env.

**LaunchAgent**

- Sync plist: `~/Library/LaunchAgents/com.hermes.obsidian-vault-sync.plist` — currently unloaded; when enabled, must call the **push-only** script.
- Reverse tunnel plist: unload if Local REST API is unused (`launchctl bootout gui/$(id -u)/com.hermes.obsidian-reverse-tunnel`).

---

## 4. Agent access (ops)

1. MCP mount = Growth OS only (local + VPS configs).
2. Default tools: list / search / read.
3. Agent writes → `Drafts/Hermes/` (create the folder if missing).
4. Canon edits → Dylan approval in-session or via ClickUp.
5. After config changes: `hermes mcp list` / restart gateway if required; verify tools against Growth OS.

Secrets (`OBSIDIAN_API_TOKEN`, etc.) stay in `.env` / secrets files — never in vault notes.

---

## 5. Incident responses

| Symptom | Action |
|---------|--------|
| Agent uses `/root/obsidian-vault` | Confirm remap + VPS MCP args; heal memory/session text if needed; never recreate that path |
| VPS knowledge stale | Run Mac→VPS push; check sync logs / LaunchAgent |
| Accidental canon overwrite | Restore from Mac vault git history; re-sync Mac→VPS; append Agent Run Log |
| Reverse tunnel spam / exit 255 | `bootout` the LaunchAgent; confirm FS MCP still healthy |
| Suspected bidirectional conflict | Stop sync LaunchAgent; compare mtimes Mac vs VPS; restore from Mac git; resume push-only only |

---

## 6. Promotion checklist (Draft → canon)

1. Draft exists under `Drafts/Hermes/`.
2. Dylan reviews (or ClickUp approval linked).
3. Move/merge into target path (`Business Context/`, Templates fill, Decision Log row, etc.).
4. Leave a stub or delete draft; avoid duplicates.
5. Mac→VPS sync.
6. Log promotion in Agent Run Logs if an agent assisted.

---

## 7. Explicit non-maintenance

- Do not rebuild a parallel “Hermes knowledge DB.”
- Do not auto-commit or auto-push the private vault git repo from Hermes.
- Do not expand MCP to the full vault “for convenience.”
- Do not store API keys, SMTP passwords, or session tokens in Growth OS notes.

---

## 8. Pointers

| Doc | Path |
|-----|------|
| Full inventory | `audit/HERMES_OBSIDIAN_V2_AUDIT.md` |
| Sync design | `audit/HERMES_OBSIDIAN_SYNC_DESIGN.md` |
| Access policy | `audit/HERMES_OBSIDIAN_ACCESS_POLICY.md` |
| Validation snapshot | `audit/HERMES_OBSIDIAN_VALIDATION_REPORT.md` |
| Runtime paths | `CANONICAL_CONTEXT.md` |
