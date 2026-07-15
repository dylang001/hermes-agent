# Hermes Task OS + capability hardening

## Active — tool failure / capability (2026-07-15)

Plan audits:
- `audit/HERMES_TOOL_FAILURE_ROOT_CAUSE.md`
- `audit/HERMES_CAPABILITY_INVENTORY.md`
- `audit/HERMES_PROTECTED_OPTIMIZATIONS_AUDIT.md`

### Phase 1 — stale path / guardrail
- [x] Diagnose `/root/audit` + `same_tool_failure_halt` (Mem0 + coarse halt)
- [x] Runtime metadata + Mem0 remap + equivalent-path halt@2 + tests (25 green)
- [x] VPS config: Obsidian → `/opt/hermes/data/obsidian/Growth OS`; Exa MCP disabled; env hint; equivalent_failure:2
- [x] Deploy code to VPS `/opt/hermes/app` + restart dashboard/gateway (services active)
- [x] Fix `/root/.git` fatal (`cwd=/root` from Desktop memory) — path_boundary + heal 11 sessions
- [x] Deploy SHA `72ec5f64e` marker + VPS smoke (`completion/heal → /opt/hermes/app`)
- [ ] Desktop smoke: **genuinely new session** (clear remembered `/root` or update Desktop) — “Find and summarize the latest Hermes audit notes.” → `/opt/hermes/app/audit`, no `/root` in logs

### Phase 2 — inventory
- [x] `audit/HERMES_CAPABILITY_INVENTORY.md`

### Phase 3 — capability profiles
- [x] YAML presets under `config/capability_profiles/`
- [x] `hermes_cli/capability_profiles.py` (list/show/apply/measure)
- [ ] Apply `daily-ops` to default VPS chat profile (after code deploy)
- [ ] Measure schema size before/after on VPS

### Phase 4 — skill discovery
- [x] `agent/skill_discovery.py` (classify → search installed → evaluate → approval gates)
- [ ] Wire into Task OS /chat help text (optional thin)
- [ ] One staged install of a harmless official skill (validation)

### Phase 5 — MCP / plugins
- [x] Obsidian path fix (config)
- [x] Exa MCP parked (prefer native web)
- [ ] MCP health check after dashboard restart
- [ ] Zoho/Composio remain disabled until explicit need

### Phase 6 — capability-gap
- [x] `agent/capability_gap.py` structured report
- [ ] Emit from Task OS worker on missing integrations

### Phase 7 — validation matrix
- [ ] artifact create/update
- [ ] Obsidian search (fixed path)
- [ ] ClickUp update
- [ ] Gmail (if oauth present)
- [ ] GitHub work
- [ ] browser research (browser-ops profile)
- [ ] cron / delegate / skill stage / stale-path recovery / failed-MCP recovery

## Earlier — Task OS Phase 1 (done)

- Deploy tip previously `d1908cfcf`; VPS cron `4dcf0a86d0e8` every 5m
- Smoke task `86carck03` → waiting + hermes-review
- Default plugins: clickup-bridge only; task-os: clickup_task_os only

## Later (Task OS product phases)

- [ ] Task OS Phase 2 evals
- [ ] Task OS Phase 3 narrow knowledge retrieval
- [ ] Task OS Phase 4 capture slash commands
- [ ] Task OS Phase 5 Kanban multi-agent
