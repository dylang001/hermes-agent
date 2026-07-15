# Hermes Capability Inventory

**Date:** 2026-07-15  
**Environments:** Local `~/.hermes` · VPS `/opt/hermes/home` (app `/opt/hermes/app`)  
**Source:** live config probes + repo inventory (see also tool-failure root-cause audit)

Columns: Installed · Configured · Exposure · Health · Latency/Security · Action

---

## Built-in tools / toolsets

| Capability | Installed | Configured | Exposure | Health | Latency / security | Action |
|---|---|---|---|---|---|---|
| Core (`terminal`, files, web, browser, skills, memory, todo, session_search, clarify, code, delegate, cron, kanban…) | Yes | Platform toolsets via `hermes tools` | All surfaces unless gated | Healthy | Terminal = high blast radius | **keep** core; **profile-gate** Telegram |
| Native web search | Yes | Auto backends; Exa key on VPS env | CLI / gateway | Prefer native over Exa MCP | Med | **keep**; prefer over flaky Exa MCP |
| Browser (local/CDP/cloud) | Yes | Local auto; cloud incomplete | CLI-heavy | VPS browser fragile | High latency | **profile-gate** `browser-ops` |
| Vision / image_gen / video | Yes | Aux auto | CLI | Provider-dependent | Cost | **profile-gate** |
| Computer use | Yes | Mac local; VPS N/A | CLI | Off VPS | High risk | **disable** VPS |
| Delegation | Yes | depth 1, 3 children; MCP inherit on | Messaging+CLI | MCP inherit costly | Med–high | **keep**; `inherit_mcp_toolsets: false` on VPS chat |
| Cron / Kanban | Yes | VPS Task-OS poll 5m; kanban dispatch | Task-OS / gateway | Smoke OK | Worker budget | **keep** gated |

---

## Plugins

| Plugin | Installed | Configured | Exposure | Health | Risk | Action |
|---|---|---|---|---|---|---|
| `clickup-bridge` (user) | Yes | Token; default profile | CLI / skill | Healthy | Workspace token | **keep** |
| `clickup_task_os` | Yes | `task-os` only; VPS cron | Poller/workers | Smoke `86carck03` OK | Poll+2 workers | **keep** on `task-os` only |
| Mem0 provider | Bundled | VPS `memory.provider: mem0` | All VPS sessions | Healthy but stale paths | PII egress | **keep** + path remap (shipped) |
| Observability / crawl4ai | Present | Disabled local | None | Off | Telemetry/SSRF | **disable** |
| Model providers (OpenCode Go, …) | Bundled | Primary routing | All calls | Healthy | Cost | **keep** |

---

## MCP

| Server | Installed | Configured | Exposure | Health | Risk | Action |
|---|---|---|---|---|---|---|
| Obsidian filesystem | Yes (npx) | VPS path **`/root/obsidian-vault` (broken)**; live vault `/opt/hermes/data/obsidian/Growth OS` | Gateway toolsets list `obsidian` | **Unhealthy** | Vault exfil | **fix path** |
| Exa MCP | Yes (npx) | enabled + `EXA_API_KEY` | Schema inflate | Historically flaky | Dup with native web | **fix or disable**; prefer native |
| Parallel search | URL MCP | enabled | Schema | Unknown | Third-party | Health-check; else disable |
| Zoho CRM MCPs | OAuth URLs | mostly `enabled: false` | None while off | Inactive | Auth sprawl | **keep disabled** until needed |
| Dashboard MCP | N/A | `HERMES_DISABLE_MCP_IN_DASHBOARD=1` + `no_mcp` toolsets | Desktop/dashboard | Intentionally off | Low | **keep off** for Desktop latency |

---

## Skills / optional

| Area | Installed | Configured | Exposure | Health | Action |
|---|---|---|---|---|---|
| Bundled skills | Yes | Default load | All | OK | **keep**; curator prune |
| User growth/outreach skills | Yes local | Heavy | CLI/Telegram | Mixed | **profile-gate** `prospecting`/`content` |
| Optional-skills | Shipped inactive | Install on demand | Opt-in | Inactive | Staged install only |
| Gmail / Google Workspace | Skill | OAuth not verified VPS | Skill | Likely off | Setup then **profile-gate** |
| GitHub | Skill + `gh` | Token TBD | Terminal | Partial | **fix** token for `engineering` |

---

## Channels & knowledge

| Capability | Installed | Configured | Exposure | Health | Action |
|---|---|---|---|---|---|
| Telegram gateway | Yes | VPS primary | Core tools | Live | **keep**; gate toolsets |
| Artifact / MEDIA delivery | Yes | allow_dirs tight | Telegram | Hardened | **keep** |
| Obsidian Growth OS | Data present | MCP path wrong | Knowledge | Path fix required | **fix** |
| File memory + Mem0 | Yes | VPS Mem0 | Sessions | Path remap shipped | **keep** |

---

## Recommended posture

| Env | Keep | Profile-gate | Fix now | Disable |
|-----|------|--------------|---------|---------|
| **VPS chat / Desktop** | terminal, files, session_search, Mem0 (remapped), skills discovery, web, capture/approvals | browser, marketing skills, kanban admin, computer_use | Obsidian MCP path; Exa MCP health | Dead Zoho MCP children; Task-OS on default profile |
| **task-os** | clickup_task_os, kanban, terminal, files | browser/content | — | clickup-bridge duplication of polling (already non-overlapping) |
| **engineering** | gh, files, terminal, tests, git | image_gen, outreach | GH token | —
| **research** | web, browser, session_search | write tools limited | Exa vs native | —
| **Local Mac** | Obsidian MCP (Mac path), clickup-bridge, file memory | computer_use | audit local cron | incomplete Browserbase |

---

## Schema/latency notes

- Desktop dashboard already strips MCP (`no_mcp`) — good for chat latency.
- Exa MCP + filesystem MCP inflate tool schemas on gateway platforms that still list `obsidian`.
- Measure tool JSON size per profile after Phase 3 routing (see `config/capability_profiles/`).
