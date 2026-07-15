# Hermes Task OS (ClickUp + Kanban)

Plan: `tasks/plans/2026-07-15-hermes-clickup-task-os.md`  
Plugin: `plugins/clickup_task_os/README.md`

## Confirmed Orchidea Ops (live 2026-07-15)

- Workspace `90152507264` · Space `901511216857` · Folder `901516535453` (hidden) · List `901524109892`
- Ready = `next` · In Progress = `in-progress` · Waiting = `waiting` · Review = `waiting` + `hermes-review` · Done = `done` (human)
- Trigger tag: `hermes-ready`

## Gate before Task OS cron

Protected optimizations audit: `HERMES_PROTECTED_OPTIMIZATIONS_AUDIT.md`

- [x] Local + VPS SHA match approved tag `07bdd098c`
- [x] Intelligence/Telegram policies present; VPS gateway flags ON
- [x] Loop Engineering = unmerged bounded-delivery-loop; remain removed
- [x] clickup-bridge does not poll (no duplicate executor vs task_os)
- [ ] Remove `clickup_task_os` from default `plugins.enabled` (keep on task-os only)
- [ ] Commit/deploy Task OS decision + one live Ops smoke
- [ ] Enable cron only after gates pass — **not yet**

## Phase 1

- [x] Audit + decisions
- [x] Thin ClickUp client/plugin (no core tools)
- [x] Poller with Kanban `idempotency_key=clickup:<id>` + pre-claim safety check
- [x] Review/Waiting terminal paths + high-risk approval wall
- [x] Focused tests (13) + rollback docs in plugin README
- [x] Run setup + verify-board on `task-os` profile (cron left for you to enable)
- [ ] Smoke: one Ready+hermes-ready Ops task through Review

## Later

- [ ] Phase 2 evals
- [ ] Phase 3 narrow knowledge retrieval
- [ ] Phase 4 capture slash commands
- [ ] Phase 5 Kanban multi-agent

Success: Ready+`hermes-ready` tasks run once asynchronously with evidence in Review mapping; chat is capture/approval only.
