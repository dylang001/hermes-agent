# Hermes Obsidian Sync Design — Phase 7E

**Date:** 2026-07-15  
**Status:** Design for implementation (docs-first). Do not enable automation until dry-run + one manual successful run are signed off.

Related: `audit/HERMES_OBSIDIAN_V2_AUDIT.md`, `docs/HERMES_KNOWLEDGE_MAINTENANCE_RUNBOOK.md`

---

## 1. Goal

Keep the VPS Hermes working copy of **Growth OS** current from the Mac vault so gateway/MCP sessions read the same curated knowledge Dylan edits locally.

MVP = **one unidirectional workflow**: Mac → VPS over SSH alias `hermes-production`.

---

## 2. Source of truth and direction

| Role | Path |
|------|------|
| Authoring source of truth (Mac) | `/Users/dylanangloher/Documents/Obsidian Vault/Growth OS` |
| Hermes working mirror (VPS) | `/opt/hermes/data/obsidian/Growth OS` |
| rsync-friendly symlink (VPS) | `/opt/hermes/data/obsidian/GrowthOS` → `Growth OS` (already present) |
| SSH | `hermes-production` (user `dylan`, BatchMode) |

**Policy**

- Default and only automated direction: **Mac → VPS**.
- VPS → Mac is **fail closed**: not scheduled, not in LaunchAgent, not in cron.
- Unrestricted bidirectional or VPS→Mac pull requires **explicit Dylan approval** (ticket/Chat sign-off recorded in Decision Log or ClickUp).
- Existing `sync-obsidian-vault.sh` (bidirectional `--update`) is **legacy / do not load** until superseded or explicitly approved for a one-off recovery.

Git on the Mac vault remains Dylan’s backup/history lane; it is not the Hermes runtime mirror.

---

## 3. Recommended script (evolve the push-only script)

**Base:** `~/.hermes/bin/sync-obsidian-to-hermes-remote.sh`  
**Promote to:** `~/.hermes/bin/sync-growth-os-mac-to-vps.sh` (or harden in place)

### 3.1 Required behaviors

| Control | Requirement |
|---------|-------------|
| **Lock** | Exclusive lock dir (e.g. `/tmp/hermes-growth-os-sync.lock`); second instance exits 0 with log line |
| **Dry-run** | `HERMES_OBSIDIAN_SYNC_DRY_RUN=1` or `--dry-run` → `rsync -n`; no remote mkdir of content |
| **Logs** | Append UTC ISO lines to `~/.hermes/logs/obsidian-growth-os-sync.log` and `.err.log` |
| **Retries** | Up to 3 attempts on SSH/rsync transient failures; exponential backoff (5s / 15s / 45s) |
| **Mass-delete guard** | Never pass `--delete` by default. If `--delete` ever added: require `HERMES_OBSIDIAN_SYNC_ALLOW_DELETE=1` **and** refuse if dry-run delete count > threshold (e.g. 20 files) unless `HERMES_OBSIDIAN_SYNC_FORCE_DELETE=1` |
| **Fail closed** | Missing local Growth OS → exit 1. SSH BatchMode failure → exit 1 (no silent skip that looks like success). Do not create a second vault under `/root` |
| **Excludes** | Cache, trash, secrets (see §4) |
| **Scope** | Sync **only** `Growth OS/`, never the full Obsidian vault |

### 3.2 Suggested rsync shape

```bash
RSYNC_RSH='ssh -o BatchMode=yes -o ControlMaster=no -o IdentitiesOnly=yes'
rsync -az --partial --timeout=120 \
  -e "$RSYNC_RSH" \
  --exclude-from="$EXCLUDE_FILE" \
  "${LOCAL_GROWTH}/" \
  "hermes-production:/opt/hermes/data/obsidian/GrowthOS/"
```

Prefer the no-space `GrowthOS` symlink for shell safety; ensure symlink exists before sync (`ln -sfn 'Growth OS' GrowthOS` on VPS if missing).

Do **not** use `--update` pull before push in the MVP script (that recreates bidirectional semantics).

### 3.3 Excludes (minimum)

```
.trash/
.trash/**
.obsidian/cache/
.obsidian/cache/**
.obsidian/workspace
.obsidian/workspace.json
.obsidian/workspace-mobile.json
.obsidian/plugins/obsidian-local-rest-api/data.json*
**/.env
**/.env.*
**/secrets/**
**/*api*token*
**/*.pem
**/*.key
```

Growth OS today has little `.obsidian` of its own (vault-level `.obsidian` sits above Growth OS). Keep excludes anyway so future nesting does not leak.

---

## 4. Scheduling (after manual proof)

| Option | When |
|--------|------|
| Manual | `sync-growth-os-mac-to-vps.sh` from Mac when Dylan edits knowledge |
| LaunchAgent | Point `com.hermes.obsidian-vault-sync.plist` at the **push-only** script; StartInterval ≥ 300s |
| Do not | Cron on VPS that pulls from Mac; reverse-tunnel-dependent file sync |

Unload or fix the reverse tunnel separately (§6); sync must not depend on port 27124.

---

## 5. Failure modes and fail-closed rules

| Situation | Behavior |
|-----------|----------|
| Local Growth OS missing | Abort; do not invent path |
| SSH auth/host failure | Abort; log; LaunchAgent leaves last good VPS tree untouched |
| Partial rsync interrupt | `--partial` + next full run; no auto `--delete` cleanup |
| Remote path is `/root/obsidian-vault` | Hard refuse (string guard in script) |
| Operator requests VPS→Mac | Document one-off procedure under approval; not in LaunchAgent |

---

## 6. Legacy to park

| Item | Action |
|------|--------|
| `sync-obsidian-vault.sh` bidirectional | Keep for emergency only; do not reload LaunchAgent on it |
| `com.hermes.obsidian-reverse-tunnel` | Unload when REST API bridge is not needed; currently failing on 27124 |
| Syncthing / full-vault Git→VPS | Research only; not MVP |
| Auto git commit/push from Hermes | Forbidden (`SYNC_SETUP.md` already: no auto-commit) |

---

## 7. Acceptance criteria (sync MVP)

1. Dry-run prints file list; no remote mutation.
2. Live run updates a known marker file on VPS within seconds of Mac change.
3. Concurrent second run is noop (lock).
4. Intentional mass-delete without force flags is refused.
5. Logs show start/end/duration/exit code for every run.
6. Gateway Obsidian MCP `list_directory` / search sees the new file on VPS without remount (filesystem is live on disk).

---

## 8. Implementation order

1. Harden push-only script (lock, dry-run, logs, retries, excludes, path guards).
2. Manual dry-run + live run; record evidence in validation report.
3. Retarget or rewrite LaunchAgent to push-only; enable only after (2).
4. Unload reverse tunnel unless Local REST API is revived by explicit approval.
