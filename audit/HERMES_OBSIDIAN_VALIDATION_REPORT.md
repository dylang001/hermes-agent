# Hermes Obsidian Validation Report — Phase 7E

**Date:** 2026-07-15  
**Method:** Live filesystem + `launchctl` + SSH to `hermes-production` (read-only checks). No new sync automation was enabled.

---

## 1. Summary board

| Area | Exists | Works today | Gap |
|------|--------|-------------|-----|
| Mac Growth OS | Yes | Yes — populated curated docs | No `Drafts/Hermes/`; no vault `AGENTS.md` |
| VPS Growth OS | Yes | Yes — mirror present + `GrowthOS` symlink | Slight artifact drift (`INTEGRATION_SPEC.patch` still on VPS) |
| Mac→VPS push script | Yes | Runnable manually (not exercised this audit beyond existence) | No lock/dry-run/logs/retries/delete guards |
| Bidirectional sync script | Yes | Must not be default | Loaded by unloaded LaunchAgent design — risky if reloaded |
| Sync LaunchAgent | Plist exists | **Not loaded**; **no sync logs** | Automation inactive |
| Reverse tunnel LaunchAgent | Plist exists | **Loaded but failing** (port 27124) | Unload or fix; not needed for filesystem MCP |
| SSH `hermes-production` | Yes | Yes (BatchMode checks succeeded) | — |
| Local Obsidian MCP | Yes | Mounts Mac Growth OS; read-leaning include list | Staging write path not in tools include |
| VPS Obsidian MCP | Yes | Mounts `/opt/hermes/data/obsidian/Growth OS` | Include list may be broader; live search smoke still open |
| Stale `/root/obsidian-vault` | N/A | Correctly unused / inaccessible | Keep remaps; never remount |
| Policy docs | Partial | Operating Principles / Agent Rules present | Conflict with INTEGRATION_SPEC cycle-1; Drafts policy not on disk |
| Knowledge maintenance runbook | Written this phase | `docs/HERMES_KNOWLEDGE_MAINTENANCE_RUNBOOK.md` | Ops must adopt |

---

## 2. What works

### 2.1 Growth OS content (Mac)

Verified directory at `/Users/dylanangloher/Documents/Obsidian Vault/Growth OS` with INDEX, Agent Rules, Operating Principles, Decision Log, Business Context, Templates, etc.

### 2.2 Growth OS content (VPS)

SSH listing confirms `/opt/hermes/data/obsidian/Growth OS` with the same core tree. Symlink `GrowthOS → Growth OS` exists (supports space-safe rsync).

### 2.3 Path hygiene

- `CANONICAL_CONTEXT.md` and `runtime_metadata.py` remap stale `/root/obsidian-vault`.
- VPS `config.yaml` `mcp_servers.obsidian` args point at Growth OS (path fix noted done in `tasks/todo.md`).
- Local Mac MCP args point at Mac Growth OS.

### 2.4 SSH

`hermes-production` resolves and accepts BatchMode sessions as user `dylan`.

### 2.5 Conceptual architecture

Vault Operating Principles already separate ClickUp (tasks) vs Obsidian (strategy) vs Hermes (operator). Repo plans correctly treat Obsidian ≠ Mem0.

---

## 3. What exists but does not work (or is unsafe as default)

| Item | Evidence | Risk |
|------|----------|------|
| Sync LaunchAgent | `launchctl print …/com.hermes.obsidian-vault-sync` → not found | No automated Mac→VPS refresh |
| Bidirectional script as LaunchAgent target | Plist points at `sync-obsidian-vault.sh` | If loaded: unsupervised VPS→Mac updates |
| Reverse tunnel | Running; stderr `remote port forwarding failed for listen port 27124` | Noise; possible dual-listener conflict; unused for FS MCP |
| INTEGRATION_SPEC “cycle 1 REST” | Still in Growth OS; describes unused stack | Agents may follow wrong instructions |
| Push-only script MVP controls | Missing lock/dry-run/logs/retries/guards | Ok for careful manual use; not production automation |

---

## 4. What is missing

1. `Growth OS/Drafts/Hermes/` staging tree.
2. Vault-root or Growth OS `AGENTS.md` constitution (referenced; not found by filesystem search).
3. Hardened Mac→VPS sync implementation matching `HERMES_OBSIDIAN_SYNC_DESIGN.md`.
4. End-to-end validation: gateway agent `search_grep` / `list_directory` after a marker-file sync (still open in Task OS todo Phase 7).
5. Aligned VPS MCP `tools.include` (or equivalent write allowlist) with Access Policy.
6. Unload/disable legacy reverse tunnel once confirmed unused.

---

## 5. Manual checks performed this audit

| Check | Result |
|-------|--------|
| `test -d` Mac Growth OS | Pass |
| SSH list VPS `/opt/hermes/data/obsidian/` | Pass; Growth OS + symlink |
| SSH probe `/root/obsidian-vault` | Absent/inaccessible for dylan |
| `launchctl` sync agent | Not loaded |
| `launchctl` reverse tunnel | Loaded; failing |
| Grep local MCP obsidian block | Filesystem → Mac Growth OS + read include |
| Grep VPS MCP obsidian block | Filesystem → VPS Growth OS, enabled |
| Find vault `AGENTS.md` | Not found |
| `Drafts/Hermes` | Not present |
| Live `rsync` / dry-run | **Not run** this phase (docs-first; avoid mutating VPS without sign-off) |
| Live Hermes tool call smoke | **Not run** this phase |

---

## 6. Recommended validation after implementation

1. Dry-run push; confirm log lines.
2. Touch `Growth OS/Drafts/Hermes/_sync_probe.md` on Mac; live sync; `ssh hermes-production cat …/_sync_probe.md`.
3. From Telegram/Desktop session: list/search Growth OS for probe text; confirm no `/root/obsidian-vault` in tool args/logs.
4. Attempt write outside Drafts (should require approval / be refused by include list).
5. Confirm reverse tunnel unloaded or documented as intentional.

---

## 7. Residual risks

- Stale agent instructions still pointing at REST MCP or `/root` paths in older Mem0/session text (runtime remap mitigates; does not cure bad writes).
- Skill `obsidian` encourages unconstrained writes — policy must override in system/operating docs.
- Private git remote exists; accidental agent `git push` of secrets remains a human vault hygiene concern (not Hermes sync).
