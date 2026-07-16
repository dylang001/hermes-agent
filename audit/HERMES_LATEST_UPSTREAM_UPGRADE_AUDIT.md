# Hermes Latest-Upstream Upgrade Audit

**Date (UTC):** 2026-07-16  
**Operator:** Dylan / Auto  
**Production:** `hermes-production` → `138.128.247.49` · `/opt/hermes/app` · `HERMES_HOME=/opt/hermes/home`

## Pre-upgrade inventory

| Surface | Value |
|---------|--------|
| Local branch (pre) | `codex/hermes-phase1-upstream-merge-20260715` |
| Local SHA (pre) | `18b78dd1febab91c4e337807c16d018edf08060f` |
| Local dirty | clean (3 commits ahead of fork remote) |
| Preservation branch | `preserve/hermes-pre-upstream-20260716T0958Z` @ `18b78dd1f` |
| Preservation bundle | `/tmp/preserve-hermes-pre-upstream-20260716T0958Z.bundle` (254M) |
| Upgrade branch | `upgrade/hermes-latest-upstream-20260716` |
| Upstream remote | `origin` → `NousResearch/hermes-agent` |
| Upstream tip merged | `origin/main` @ `1d48863b856d7a82412e1b47d87e30d0378b851f` |
| Upstream release tag | `v2026.7.7.2` (local already on this release lineage; main +22 commits beyond local tip) |
| VPS SHA (pre) | `18b78dd1f` |
| Desktop package version | `0.17.0` (`apps/desktop`) |
| Hermes version string | `v0.18.2 (2026.7.7.2)` |
| Fork-only commits (pre) | 55 ahead of `origin/main` |
| Upstream-only commits | 22 (clean merge into fork tip) |

## Active worktrees (pre)

| Path | Branch / HEAD |
|------|----------------|
| `~/.hermes/hermes-agent` | active upgrade branch |
| `/private/tmp/hermes-memory-telegram-boundary-20260712` | prunable |
| `/private/tmp/hermes-merge-validation-20260711` | prunable detached |
| Codex plugin-creator worktree | `codex/orchidea-creative-skills` |

## Immediate runtime cleanup (completed before merge)

### Stale `/root/.hermes/agent-hooks/skill_finder_hook.sh`

| Finding | Detail |
|---------|--------|
| Live config | `hooks.pre_llm_call` pointed at `/root/.hermes/agent-hooks/skill_finder_hook.sh` |
| Behavior | Auto `hermes skills search` + **`hermes skills install --yes`** — installs without approval |
| Env | `HERMES_DISABLE_SHELL_HOOKS=1` already set on gateway systemd — hook was skipped + logged |
| Supported replacement | `agent/skill_discovery.py` (propose → quarantine → approval) |
| Decision | **Remove** — obsolete, unsafe auto-install, redundant with skill_discovery |

### Other stale `/root/.hermes` config keys cleaned

| Key | Action |
|-----|--------|
| `hooks` block | Removed entirely |
| `security.tirith_path` | Cleared (binary not under `/opt/hermes`) |
| `plugins.hermes-memory-store.db_path` | → `/opt/hermes/home/memory_store.db` |
| Hook script under `/opt/hermes/home/agent-hooks/` | Archived to `.archive/skill_finder_hook.sh.obsolete` |
| Config backup | `/opt/hermes/home/config.yaml.bak-root-cleanup-20260716T095853Z` |
| Remaining `/root/.hermes` in live config | Only instructional `environment_hint` text (anti-stale guidance) |

## Upstream delta (22 commits) — categories

- Desktop: worktree tracking, composer input sanitize (bracketed-paste)
- Auxiliary LLM: call_llm routing, Anthropic extra_body, bootstrap version skew warn
- MCP catalog: exact version pins; Blender MCP catalog entry
- Codex: request-time hard ceiling; WAL PASSIVE checkpoint
- Config: preserve platforms on partial `save_config`
- Ollama: `reasoning_effort=none` on chat completions
- Compressor: unwrap web_extract dict URLs

## Conflict expectation

`git merge-tree` predicted “changed in both” on several paths; **actual merge completed with no conflict markers**. Fork Obsidian migration (`_config_version` 34) and path-boundary code preserved.

## Preserve checklist (must remain after merge)

| Capability | Status in tree |
|------------|----------------|
| OpenCode Go / MiniMax routing | present (config + providers) |
| Mem0 | present |
| ClickUp Task OS | `plugins/clickup_task_os/` |
| ClickUp bridge | user plugin `/opt/hermes/home/plugins/clickup-bridge` |
| Capability profiles | `config/capability_profiles/` |
| Skill discovery | `agent/skill_discovery.py` |
| Capability-gap | wired + tests |
| Path boundaries / runtime metadata | `agent/path_boundary.py`, `agent/runtime_metadata.py` |
| Equivalent-failure guard | present |
| Obsidian MCP normalize | `hermes_cli/obsidian_mcp_normalize.py` + config v34 |
| Telegram concise / response policy | `gateway/telegram_response_policy.py` |
| Intelligence flags | systemd env still set |
| Capability check / production docs | `audit/capability_check_2026-07-16.py` |

## Risks / follow-ups

1. Gateway restart still requires Dylan password sudo (NOPASSWD removed).
2. Desktop package version remains `0.17.0` while CLI reports `0.18.2` — packaging lag, not a merge failure; build SHA must still match approved git tip.
3. Full pytest suite not blocking merge; focused suites green (see report).
