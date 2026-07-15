# Hermes Phase 7 — Current-State Inventory

**Date:** 2026-07-15
**Checkout:** `/Users/dylanangloher/.hermes/hermes-agent`
**Lens:** Minimal viable personal operating assistant (reuse > rebuild)

## Executive map

| Domain | Completeness | Location(s) | MVP posture |
|--------|--------------|-------------|-------------|
| Intelligence Phase 6 | Done, flag-gated | `agent/intelligence_policy.py`, `gateway/telegram_response_policy.py`, `audit/intelligence_phase6_*` | Keep ON on VPS gateway; do not expand aggressiveness |
| Path/failure hardening | Done locally + partial VPS | `agent/runtime_metadata.py`, guardrails, Mem0 remap, `audit/HERMES_TOOL_FAILURE_ROOT_CAUSE.md` | Harden with Desktop new-session smoke |
| Capability profiles | Code done, apply pending | `config/capability_profiles/`, `hermes_cli/capability_profiles.py` | Apply `daily-ops` week 1 |
| Skill discovery | Library done, unwired | `agent/skill_discovery.py`, tests | Thin wire into Task OS / help |
| Capability gap | Library done, unwired | `agent/capability_gap.py`, tests | Emit on missing integrations |
| ClickUp Task OS | Phase 1 code local | `plugins/clickup_task_os/`, plan `tasks/plans/2026-07-15-…` | Deploy behind `task-os` profile only |
| clickup-bridge | Live user plugin | `~/.hermes/plugins/clickup-bridge/` | Keep for chat updates |
| Mem0 | Live on VPS | `plugins/memory/mem0/` | Keep; do not replace with new memory system |
| Obsidian | Data + skill OK; MCP historically wrong | Mac Growth OS; VPS `/opt/hermes/data/obsidian/Growth OS`; `skills/note-taking/obsidian/` | File tools + sync > MCP theater |
| Browser / social | Partial | Core browser; `plugins/browser/*`; capability-lab OFF | Public research only for MVP |
| Agent-Reach | Not installed as product | capability-lab `agent_reach: false` + `public-platform-research` | Optional thin enable later |
| SpaceMail | Not in repo | Obsidian PRD / priorities only | Defer past 30d |
| Prospecting pipeline | Spec only | Obsidian + PRD attachment; HyperAgent code missing | Defer live send; ClickUp Pipeline list exists |
| Success.ai | Absent in checkout | — | Archive/remove external refs later |

## Phase 6 / 7 work already present

### Phase 6 (intelligence) — finished artifacts
- Code: intelligence policy stack + Telegram concise responses
- Scripts: `scripts/benchmark_intelligence_phase6.py`, `scripts/smoke_intelligence_phase6.py`
- Audits: `audit/intelligence_phase6_checkpoint.md`, integrated/local JSON, VPS parity/cleanup, memory SoT addenda, canonical context proposal → `CANONICAL_CONTEXT.md`
- Preservation trees under `audit/preservation-*`
- Rollout: VPS gateway flags documented in `CANONICAL_CONTEXT.md`

### Phase 7 in *this* fork (capability OS, not relay/dashboard auth “Phase 7”)
Source of truth: `tasks/todo.md`

| Phase | Item | Status |
|-------|------|--------|
| 1 | Stale path / guardrail / Mem0 remap / VPS path fixes | Mostly done; Desktop new-session smoke open |
| 2 | `HERMES_CAPABILITY_INVENTORY.md` | Done |
| 3 | Capability profiles YAML + CLI | Done; VPS apply + measure open |
| 4 | `skill_discovery.py` | Done; wire + staged skill install open |
| 5 | Obsidian/Exa MCP ops | Path fix claimed; MCP health open; Zoho/Composio stay off |
| 6 | `capability_gap.py` | Done; Task OS emit open |
| 7 | Validation matrix | Open (artifact, Obsidian, ClickUp, Gmail, GH, browser, cron/recovery) |

**Note:** Unrelated “Phase 7” strings exist in gateway relay / dashboard auth / research-paper skill — ignore for personal-OS MVP.

## Core module status

### `agent/skill_discovery.py` — FINISHED library (not stub)
- `classify_task_tags`, `search_installed_skills`, `evaluate_skill_dir`, `propose_discovery`
- Approval gates for scripts/secrets/external-write
- Hub quarantine not auto-implemented beyond guidance strings
- Callers: tests only — **no Task OS / chat import**

### `agent/capability_gap.py` — FINISHED library (not stub)
- `CapabilityGapReport`, `build_gap_report`, markdown export
- Callers: tests only — **not emitted from workers**

## ClickUp / Mem0 / Obsidian / browser

- **Task OS:** fork-local plugin; poll/claim/review safety; README confirms Ops board; **not on approved VPS tip** per `HERMES_PROTECTED_OPTIMIZATIONS_AUDIT.md`
- **Mem0:** keep; stale-path remap is load-bearing
- **Obsidian:** curated KB; Mem0 ≠ Obsidian; prefer file tools + `OBSIDIAN_VAULT_PATH`
- **Browser:** native Hermes + `agent-browser` present locally; VPS browser fragile — profile-gate `browser-ops`
- **Agent-Reach:** expected Reddit/YT/X install **not found**; stand-in skill exists OFF in capability-lab
- **SpaceMail:** documented debt in Growth OS; no adapter in checkout
- **Success.ai:** no repo references — candidate for later archive of *external* plans/memory only

## Plans / memory / audits to read next
- `tasks/todo.md`, `tasks/plans/2026-07-15-hermes-clickup-task-os.md`
- `audit/HERMES_CAPABILITY_INVENTORY.md`, `HERMES_TOOL_FAILURE_ROOT_CAUSE.md`, `HERMES_PROTECTED_OPTIMIZATIONS_AUDIT.md`
- `CANONICAL_CONTEXT.md`
- Growth OS: `Prospecting Requirements.md`, `Current Priorities.md`, `Remote Gateway Status.md`

## Completeness verdict for Dylan daily-ops MVP

**Already enough to run thin daily OS:** Telegram/Desktop chat, files, web, skills, session search, Mem0, ClickUp bridge, cron/kanban primitives, intelligence flags.

**Not enough until hardened:** Task OS on VPS, daily-ops profile applied, Obsidian path proven, discovery/gap wired lightly, Desktop session path hygiene confirmed.

**Explicitly out of 7-day MVP:** SpaceMail live send, HyperAgent prospecting import, Zoho/Composio, Success.ai, full social automations, second memory/runtime.
