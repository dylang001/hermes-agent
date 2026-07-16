# Hermes Production Baseline

**Date (UTC):** 2026-07-16 — latest-upstream upgrade tip  
**Migration milestone:** Phase 7.1 baseline + latest-upstream merge (`origin/main` @ `1d48863b8`)  
**Production host only:** `hermes-production` → `hermes90210` / `138.128.247.49`  
**Checkout:** `/opt/hermes/app` · `HERMES_HOME=/opt/hermes/home`

## Immutable release

| Field | Value |
|-------|--------|
| Git SHA (full) | *(set on tag commit — see `.deployed-sha`)* |
| Canonical tag | `production-2026-07-16-upstream` |
| Historical tag | `production-2026-07-16b` → `64d9a6982aa8e3f63f49274176b69eda64745a7b` |
| Preservation tip | `preserve/hermes-pre-upstream-20260716T0958Z` @ `18b78dd1f` |
| Branch (Desktop / upgrade) | `upgrade/hermes-latest-upstream-20260716` |
| VPS branch name | `hermes-phase1-approved` (tracks deployed SHA) |
| Deploy method | git bundle → `git fetch` + `git reset --hard <SHA>` + clean worktree + `.deployed-sha` |
| Compatibility | Week-1 `daily-ops`; Task OS; Mem0; Obsidian filesystem MCP Growth OS; path-boundary / skill_discovery; no obsolete skill_finder shell hook |
| Hermes version | `v0.18.2 (2026.7.7.2)` |

## Systemd services (running)

- `hermes-gateway.service` — messaging gateway
- `hermes-dashboard.service` — dashboard / Desktop backend API
- `caddy.service` — TLS reverse proxy
- `docker.service` — container engine (present; not Hermes core loop)

## Capability profile

- Default VPS chat: `agent.capability_profile: daily-ops`
- Telegram tools enabled: `file`, `terminal`, `memory`, `skills`, `session_search`, `web`, `clarify`, `todo`
- Telegram tools disabled: `browser`, `computer_use`, `kanban`, `image_gen`
- CLI tools enabled: above + `delegation`
- `delegation.inherit_mcp_toolsets: false`

## Plugins

- `plugins.enabled: [clickup-bridge]` (ClickUp capture on default chat)
- Task OS plugin code path: `plugins/clickup_task_os` (poller/worker; discovery wire)

## MCP servers (config)

| Server | Enabled |
|--------|---------|
| composio | true |
| parallel-search | true |
| obsidian | true (initial connect may retry if vault MCP flaky) |
| exa | false |
| zoho-crm-* | false |
| orchidea-zoho-leads / activity / notes | false |

## Authenticated integrations (env keys present; values not recorded)

Telegram, ClickUp, OpenCode Go / OpenRouter, Mem0, Obsidian vault path + API token, Composio, GitHub, Dashboard OAuth/session, NVIDIA (aux), Freellmapi, Agent Social credentials (present but **automation not enabled** for SpaceMail send / LinkedIn / social publish).

## Memory

- `memory.provider: mem0`
- Session search available via toolset

## Active models

- Provider: `opencode-go`
- Default model: `minimax-m3`
- Base URL: `https://opencode.ai/zen/go`
- API mode: `anthropic_messages`
- Terminal backend: `local`

## Cron

- Single active job: `4dcf0a86d0e8` — `clickup-task-os-poll` — `every 5m` — script mode `no-agent`
- Profile `task-os` cron store must remain empty (no second poller)
- Last observed status at baseline inventory: `ok`

## Gateway flags (config excerpt)

Observed keys under `gateway:` include `message_timestamps`, `max_inbound_media_bytes`, `strict`, `media_delivery_allow_dirs`, `trust_recent_files`, `trust_recent_files_seconds`, `api_server`.

## Privilege model (post-migration)

- SSH: `dylan@138.128.247.49` via Host `hermes-production`
- Dylan is in OS group `sudo` → password sudo `ALL`
- Temporary file `/etc/sudoers.d/hermes-migration-temp` (scoped NOPASSWD for deploy/migrate) is **removed** after Phase 7.1 acceptance
- Cloud-init `90-cloud-init-users` (`ubuntu NOPASSWD:ALL`) left untouched (distro default; not Hermes migration)
- Do **not** lock out Dylan: password sudo remains

## Retired host

- Old VPS `212.86.105.178` powered off / decommissioned 2026-07-15 (SSH timeout post-`poweroff -f`). **Hard-delete still requires Kamatera console** — no API credentials on Mac; cancel remaining bill / delete the powered-off server in the Kamatera UI if it still appears.
- Archive (secrets redacted): `audit/old-vps-retire-20260715/hermes-old-vps-archive-20260715T2355Z.tgz`  
- Docs and SSH aliases must reference **only** `138.128.247.49` / `hermes-production`

## Known limitations

- Obsidian MCP: filesystem Growth OS mount on VPS (not localhost HTTP). Pin `@modelcontextprotocol/server-filesystem@2026.7.10`.
- Obsolete `skill_finder_hook.sh` removed (auto-install without approval); use `agent/skill_discovery.py`.
- Shell hook `/root/.hermes/...` references cleared from live config; `HERMES_DISABLE_SHELL_HOOKS=1` remains.
- Service restart requires Dylan password sudo (migration NOPASSWD removed).
- SpaceMail send / LinkedIn automation / social publishing remain **disabled**
- No second Task OS poller
- Phase 8+ is business capabilities, not further infra optimization

## Rollback (summary)

See `audit/HERMES_LATEST_UPSTREAM_UPGRADE_REPORT.md` — restore preservation tip `18b78dd1f` or prior tag `production-2026-07-16b` via bundle + `git reset --hard` + restart gateway/dashboard.
