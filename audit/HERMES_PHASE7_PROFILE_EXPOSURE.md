# Hermes Phase 7B — Profile Exposure & Schema Notes

**Date:** 2026-07-15  
**Measured on:** local checkout `python -m hermes_cli.capability_profiles measure --profile <name>`  
**Caveat:** `check_fn` drops tools that need live sessions/keys (browser CDP, kanban mode, web API key, cronjob requirements). Measured counts are **lower bounds of what would load in a fully provisioned session**, but useful for relative footprint.

## Existing capability profiles (YAML)

| Profile | Intent | Enabled toolsets (cli) | Explicitly disabled | Plugins note | Schema (tools / KB) |
|---------|--------|------------------------|---------------------|--------------|---------------------|
| daily-ops | Default chat | file, terminal, memory, skills, session_search, web, clarify, todo, delegation | browser, computer_use, homeassistant, spotify, image_gen, video, kanban | do not enable `clickup_task_os` | **14 / 34.18** |
| task-os | ClickUp workers | file, terminal, memory, skills, web, kanban, clarify, todo, delegation | browser, computer_use, image_gen, spotify | `clickup_task_os` on / bridge off | **13 / 28.53**† |
| engineering | Code/git | file, terminal, memory, skills, session_search, web, code_execution, clarify, todo, delegation | browser, computer_use, image_gen, spotify, kanban | — | **15 / 36.51** |
| research | Search | file, terminal, memory, skills, session_search, web, browser, clarify, todo | computer_use, image_gen, kanban, spotify | MCP allow obsidian | **22 / 33.57** |
| content | Drafting | file, terminal, memory, skills, session_search, web, clarify, todo | browser, computer_use, kanban | publish approval required | **13 / 28.84** |
| prospecting | Outreach prep | file, terminal, memory, skills, session_search, web, clarify, todo | computer_use, kanban | outbound/CRM approval required | **13 / 28.84** |
| admin | Human setup | file, terminal, memory, skills, session_search, web, cronjob, clarify, todo, kanban | computer_use | not forever-on gateway | **13 / 28.84**†† |
| browser-ops | Explicit browser | file, terminal, memory, skills, web, browser, vision, clarify, todo | computer_use, kanban | — | **21 / 27.92** |

† Kanban tools listed in YAML but check_fn `_check_kanban_mode` returned false during measure → not in final tool list.  
†† `cronjob` check_fn false in measure env → not in final list.

## Missing profiles (Phase 7B list vs repo)

| Requested | Status | Interim substitute |
|-----------|--------|--------------------|
| community-research | **missing YAML** | `research` + public web |
| social-content | **missing YAML** | `content` |
| social-operator | **missing YAML** | none — do not enable publish tools globally |
| email-ops | **missing YAML** | `daily-ops` + himalaya skill when auth exists |

Do **not** invent these as forever-on gateway surfaces until daily pain proves them. When added, mirror `daily-ops` size discipline (&lt;40 KB tool schema target) and approval gates.

## VPS application state (2026-07-15)

| Fact | Value |
|------|-------|
| Default `agent.capability_profile` | **None** (presets not applied) |
| Default plugins | `browser/browser_use`, `web/firecrawl`, `clickup-bridge` |
| task-os profile | `plugins.enabled: [clickup_task_os]` + board mapping |
| MCP on default | Obsidian OK path; Exa **disabled**; Composio URL present; Zoho leads **enabled but URL unset** |
| Telegram tool exposure | Not constrained by capability-profile YAML yet (`tools` only has `tool_search`) |

## Prompt / schema risk notes

- **Default VPS chat is wider than `daily-ops` YAML** because profile apply is pending and plugins pull browser/firecrawl. Expect higher schema + latency than the measured 34 KB daily-ops baseline.  
- **Delegation `inherit_mcp_toolsets: true`** on VPS multiplies child cost when MCP servers are attached — flip false for default chat.  
- **Dashboard/Desktop** should keep MCP off (`HERMES_DISABLE_MCP_IN_DASHBOARD` / `no_mcp`) — already the intended latency posture.  
- Measuring after apply:

```bash
python -m hermes_cli.capability_profiles measure --profile daily-ops
# On VPS after apply, also capture an actual gateway tool list dump if available
```

## Recommended profile rollout

1. Apply **daily-ops** → default Hermes home (Telegram/Desktop chat).  
2. Keep **task-os** isolated (already).  
3. Apply **engineering** / **research** only when those sessions start.  
4. Leave social/email operator profiles uncreated until Gmail or social publish is authenticated and approval-gated.
