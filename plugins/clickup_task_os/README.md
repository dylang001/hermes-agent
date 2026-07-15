# ClickUp Task OS (Phase 1)

Fork-local plugin. Keeps ClickUp out of the Hermes core tool schema.

## Confirmed Orchidea Ops board (2026-07-15)

| Fact | Value |
|------|-------|
| Workspace | `90152507264` (`Workspace`) |
| Space | `901511216857` (`Orchidea`) |
| Folder | `901516535453` (hidden) |
| List | `901524109892` (`Ops`) |

### Status mapping

| Logical | Live ClickUp status |
|---------|---------------------|
| Inbox | `inbox` |
| Ready (go) | `next` |
| In Progress | `in-progress` |
| Waiting | `waiting` |
| Review | `waiting` + tag `hermes-review` |
| Done | `done` (human only) |

There is **no native `Ready` or `Review` column** on Ops. API cannot create `review`. Review is represented as `waiting` + `hermes-review` until you add a Review status in the ClickUp UI, then update `clickup_task_os.statuses.review` in config.

### Tags created

`hermes-ready`, `hermes-review`, `waiting-on-dylan`, `waiting-external`, `approval-required`, `risk:low|medium|high`

### Trigger

`status = next` **AND** tag `hermes-ready`

## Commands

```bash
# Enable + profile + cron script
hermes plugins enable clickup_task_os
hermes task-os setup

# Verify live board mapping
hermes task-os verify-board

# Dry-run scan
hermes task-os poll --dry-run

# Live poll (idempotent)
hermes task-os poll
```

Secret: `CLICKUP_API_TOKEN` in the `task-os` profile `.env` (or active HERMES_HOME `.env`). Never commit.

## Worker models (profile hints)

| Role | Model |
|------|-------|
| planner | `glm-5.2` |
| executor | `minimax-m3` |
| verify | `deepseek-v4-flash` |
| reviewer | `deepseek-v4-pro` |

Phase 1 one-shot runs pin the executor; planner/verify/reviewer are recorded for Phase 5 routing.

## Cron (after smoke)

Conservative default: every 5 minutes, task-os profile only.

```bash
hermes -p task-os cron create "every 5m" \
  --no-agent \
  --script clickup-task-os-poll.sh \
  --deliver local \
  --name clickup-task-os-poll
```

Do **not** enable on the default profile. Do **not** use `--deterministic-worker` in cron.

## Rollback

1. Pause cron: `hermes -p task-os cron pause <job-id>` (or remove the job)
2. `hermes -p task-os plugins disable clickup_task_os`
3. Confirm default profile does **not** list `clickup_task_os` in `plugins.enabled`
4. Optional: `hermes profile delete task-os`
5. Plugin code lives only under `plugins/clickup_task_os/` — reverting the deploying commit removes it from the checkout

Disabling the plugin + pausing cron stops all claiming. In-flight ClickUp tasks already in `in-progress` stay there for manual triage.

## Completion / action-evidence gate

The historical name “summarize-only / action-evidence guard” does **not**
exist as a single core symbol. Closest related core behaviors:

- Intelligence request class `direct_answer` (tools only when needed) — flag-gated
- `display.file_mutation_verifier` — advisory over-claim notice for failed writes

Task OS Phase 1 adds an **independent deterministic completion gate** in
`worker.parse_worker_output` / `evidence_is_resolvable`:

- Prose-only “success” → Waiting (not Review)
- Bookkeeping (mem0/todo/session) rejected as evidence
- Local paths must `Path.exists()`; URLs must be `http(s)` with a host
- `STATUS: done` is never honored as Done (Review/Waiting only)

## Acceptance (Phase 1)

1. Eligible task claimed once (`idempotency_key=clickup:<id>`)
2. Plan comment posted
3. Status → `in-progress`
4. Dedicated `task-os` profile executes
5. Evidence/summary/blockers commented
6. Success → Review mapping (`waiting` + `hermes-review`), never auto-Done
7. Missing info → `waiting` + `waiting-on-dylan`
8. Failures bounded (`max_repair_attempts=2` / kanban failure_limit)
9. Poller restart does not duplicate
10. Non-eligible tasks untouched
