# Hermes Task OS — ClickUp + Kanban Integration Plan

Date: 2026-07-15  
Source: Modern AI Productivity Pack (Nick) + Dylan’s Hermes adaptation brief  
Status: **Phase 1 implemented** (plugin `plugins/clickup_task_os/`)

## Confirmed Orchidea Ops (live 2026-07-15)

| Fact | Value |
|------|-------|
| Workspace | `90152507264` |
| Space | `901511216857` (Orchidea) |
| Folder | `901516535453` (hidden) |
| List | `901524109892` (Ops) |
| Ready | `next` |
| In Progress | `in-progress` |
| Waiting | `waiting` |
| Review | `waiting` + tag `hermes-review` (no native Review column) |
| Done | `done` (human only) |
| Trigger tag | `hermes-ready` |

## Success criteria (what “done” looks like for Phase 1)

1. A ClickUp task that is **Ready + tag `hermes-ready`** is claimed once (idempotent), commented with plan, moved to **In Progress**, executed, eval-gated, then moved to **Review** or **Waiting** with artifacts.
2. Chat (Telegram/Desktop) is never the durable work queue for long jobs.
3. No Linear, no second task DB, no separate agent runner, no new core tool schemas on every API call.
4. Public/destructive/financial/customer-facing actions always stop in Review for explicit approval.

---

## 1. Pack summary (what to keep)

Nick’s four ideas map cleanly:

| Pack idea | Hermes mapping |
|-----------|----------------|
| Shared human/agent queue | ClickUp Main Workspace (not Linear) |
| Low-friction capture | Telegram `/capture`, Desktop, iPhone Shortcut → ClickUp Inbox |
| Async agents | Cron/webhook ingest → Kanban dispatcher or single agent |
| Mandatory evals | Deterministic preflight + completion evals before Review |

**Explicitly do not copy:** 20–50 parallel agents, full KB injection, unbounded retries, agent writing through Dylan’s identity, permanent-knowledge from every Done task, a new webhook runner outside Hermes.

Pack evals to adapt (from `03-evals/`):

- `task-definition-eval.md` → pre-dispatch gate (deterministic)
- `completeness-eval.md` → universal completion eval
- `principles-eval.md` → reuse / minimize Dylan-work / evidence
- `publish-safety-eval.md` → public-action hard hold
- `tov-eval.md` → Orchidea / Flockline voice variants later
- `visual-asset-eval.md` → visual assets later

---

## 2. Audit — current Hermes capabilities

### ClickUp product integration

**Verdict: none in this checkout.**

| Capability | Exists? | Closest reuse |
|------------|---------|---------------|
| Status-triggered dispatch on Ready + tag | No | Kanban `dispatch_once` / gateway dispatcher |
| ClickUp webhooks | No | Generic `gateway/platforms/webhook.py` (**signature gap**: ClickUp `X-Signature` not in native validators) |
| Comments / status / tags / attachments | No | No ClickUp API client, skill, plugin, or MCP |
| Idempotency by ClickUp task ID | No | `kanban_db.create_task(idempotency_key=…)` |
| Human approval tied to ClickUp | No | Gateway `/approve`, `tools/approval.py`, Kanban `review` + notifier |
| ClickUp ↔ Kanban foreign key | No | Convention: `idempotency_key=clickup:<id>` (+ metadata in body) |
| Core toolset / plugin / skill / cron for ClickUp | No | — |
| Linear alternative | Yes (skip) | `optional-mcps/linear/` — do not use |

Canonical IDs already recorded (`CANONICAL_CONTEXT.md`):

- Workspace `90152507264`
- Orchidea space / `Pipeline` / `Ops` lists verified 2026-07-09  
- Main Workspace Ready-list for Hermes Task OS still needs **live confirm** of list + status IDs for Inbox/Ready/In Progress/Waiting/Review/Done.

Historical note: audit docs mention worktree `cycle-2026-07-01-clickup-gated-tools` — **not present in this tree**. Do not assume prior ClickUp tooling survived.

### Kanban / delegation (internal execution)

Reusable as the durable runner:

- Create/claim/dispatch: `hermes_cli/kanban_db.py` (`create_task`, `claim_task`, `dispatch_once`)
- Gateway host: `kanban.dispatch_in_gateway` + `_kanban_dispatcher_watcher`
- Idempotency: `idempotency_key` (perfect for `clickup:<task_id>`)
- Comments + attachments: `kanban_comment`, `add_attachment`
- Failure circuit: `kanban.failure_limit` (default 2) — matches “max two repair attempts”
- Swarm: `kanban_swarm.create_swarm` (workers + verifier + synthesizer) for complex tasks only
- Cron poll path: `no_agent=True` + script for ClickUp Ready scans
- Lifecycle hooks: `kanban_task_claimed|completed|blocked` → egress sync to ClickUp

Hard gaps for Kanban:

1. No typed planner/reviewer/verifier roles (use assignees + graph)
2. No task-definition gate in kernel (must be ingest-side Layer 3)
3. No ClickUp Review push (must be script/hook)
4. Delegation is process-local — not the durable ClickUp runner

### Knowledge / memory

| System | Role | Latency rule |
|--------|------|--------------|
| ClickUp | Active work + audit trail | Always |
| Obsidian Growth OS (MCP path on VPS) | SOPs / decisions / playbooks | Retrieve by task type only |
| Mem0 | Compact durable prefs/facts | Narrow prefetch, never full dump |
| Session search | Prior conversation detail | On demand |
| Kanban | Execution state | Always for durable jobs |
| 1Password / `.env` | Credentials | Never in task text |

### Capture / chat

Telegram + Desktop already exist as surfaces. Slash capture/delegate/review commands for ClickUp are **not** implemented. Voice must land in Inbox without `hermes-ready` unless explicitly escalated.

---

## 3. Target lifecycle

```
ClickUp:
  Inbox → Ready → In Progress → Waiting → Review → Done

Dispatch when BOTH:
  status = Ready
  AND tag = hermes-ready
```

Tag = permission. Ready = go. Inbox + `hermes-ready` must never execute.

### Execution path (no new runner)

```
ClickUp Ready + hermes-ready
  → Hermes ingest (cron poll preferred; webhook optional later)
  → lock via Kanban create idempotency_key=clickup:<id>
  → task-definition gate (deterministic; bounce → Waiting + waiting-on-dylan)
  → comment understanding + plan on ClickUp
  → set ClickUp In Progress
  → narrow knowledge retrieval
  → choose:
       thin  → single agent (spawn / one Kanban card)
       fat   → Kanban graph or create_swarm (planner/workers/reviewer/verifier)
  → progress comments + Kanban artifacts
  → role-specific evals (≤2 repair loops)
  → ClickUp Review (+ evidence) OR Waiting (+ waiting-on-dylan|waiting-external)
  → Dylan approval / Done (human moves Done for public/destructive)
```

**Chat role:** capture, approval nudges, status, emergency interrupt — not the queue.

---

## 4. Minimal architecture (footprint ladder)

Prefer Layer 3 scripts + CLI + skill. **Do not** add a core ClickUp toolset.

| Layer | Component | Form |
|-------|-----------|------|
| 3 | ClickUp REST client | Small Python module under `hermes_cli/` or `scripts/` (status/tag/comment/attach). Env: `CLICKUP_API_TOKEN` only |
| 3 | Ingest dispatcher | Cron job `no_agent` script: poll Ready + `hermes-ready`, enforce gate, create Kanban card |
| 3 | Egress sync | Kanban lifecycle hook or same cron: map done/blocked → ClickUp Review/Waiting |
| 3 | Task-definition gate | Deterministic checklist (no LLM required for FAIL/BOUNCE; optional LLM for “sharpened rewrite”) |
| 1 | Skill | `skills/...` or optional-skill: SOPs for Hermes Task OS, eval checklists, capture commands guidance |
| 1 | Slash | `/capture`, `/delegate`, `/review` → thin wrappers creating ClickUp tasks (Phase 4) |
| Avoid | Core tools | Do not register ClickUp schemas on every model call |
| Avoid | New webhook microservice | Use existing gateway webhook only if signature support is added; cron poll is simpler and safer for Phase 1 |
| Avoid | Linear MCP | Explicitly out of scope |

### Status / tag contract (ClickUp)

Statuses: `Inbox`, `Ready`, `In Progress`, `Waiting`, `Review`, `Done`  
Tags: `hermes-ready`, `waiting-on-dylan`, `waiting-external`, `risk:low|medium|high`, `agent-role`, `approval-required`

### Complexity routing

| Signal | Mode |
|--------|------|
| Single deliverable, <~2h, one domain | Single agent |
| Multi-step, multi-role, or approval graph | Kanban parents or `create_swarm` |
| Never | Spawn five agents by default |

### Eval policy

**Pre-dispatch (hard):** testable done-state, constraints, linked inputs, escalation, right-sized scope → else BOUNCE to Waiting + `waiting-on-dylan` with sharpened rewrite as comment.

**Pre-Review (hard):** universal Hermes completion eval; role family if tagged; publish-safety for public actions → HOLD.

**Evidence rule:** memory/todo/session bookkeeping is never completion evidence. Paths/URLs/IDs must resolve.

**Retry budget:** max 2 repair loops; then Waiting + `waiting-on-dylan`. Align with `kanban.failure_limit`.

---

## 5. Phased build order

### Phase 1 — Hermes-ready ClickUp loop (implement first)

1. Confirm/create ClickUp statuses + tags on the target list (live API read; update `CANONICAL_CONTEXT.md` with list/status IDs after verification).
2. Add `CLICKUP_API_TOKEN` to OPTIONAL_ENV_VARS (secret only).
3. Thin ClickUp client: get task, list Ready+tag, set status, add comment, add tag; optional attachment upload.
4. Cron `no_agent` ingest script + Kanban `idempotency_key=clickup:<id>`.
5. Worker profile path: claim → plan comment → In Progress → execute → complete with metadata → Review/Waiting sync.
6. Tests: idempotency double-ingest, wrong-status-no-run, gate bounce, review sync. No source-regex tests.

**Out of Phase 1:** capture slash commands, Obsidian auto-routing, multi-agent graphs, webhook ingress.

### Phase 2 — Evals

- Ship eval markdown under Hermes home or skill (`evals/`) adapted from pack.
- Wire deterministic preflight into ingest.
- Wire completion + publish-safety into worker complete path (script/judge, not forever-agent chat).
- Cap retries at 2.

### Phase 3 — Narrow knowledge retrieval

- Task-type → Obsidian folder / Mem0 query / skill map (config table, not prompt dump).
- Proposed knowledge writes → Obsidian staging only.

### Phase 4 — Capture & approvals

- `/capture` → Inbox
- `/delegate` → Ready + `hermes-ready`
- `/review` → list Waiting/Review needing Dylan
- iPhone Shortcut + Desktop hotkey
- Telegram notify on `waiting-on-dylan`

### Phase 5 — Multi-agent only when justified

- Kanban swarm / parent graphs
- Role-based model routing
- Concurrency + token budgets

---

## 6. Latency / schema / safety constraints

- **No core ClickUp tools** — keeps prompt cache and tool payload small.
- **Narrow retrieval** — never inject full Growth OS / Mem0 into every run.
- **Idempotency first** — ClickUp webhooks double-fire; cron overlaps; both must be safe.
- **Attribution** — agent comments clearly marked as Hermes, not Dylan.
- **Approval wall** — `approval-required` / risk:high / publish-safety HOLD → Review and stop; chat approve may resume.
- **Do not** treat Chat session survival as durability; ClickUp + Kanban own the job.

---

## 7. Verification plan (Phase 1)

1. Unit tests for ClickUp client mocks + gate logic + idempotency key behavior.
2. Integration: temp HERMES_HOME Kanban create twice with same key → one card.
3. Live dry-run (Dylan present): create ClickUp task Ready+hermes-ready → observe comment, In Progress, Review with fake artifact; no public send.
4. Negative: Inbox+hermes-ready must not run; Ready without tag must not run.
5. Confirm Telegram/Desktop remain unused as primary queue.

---

## 8. Open decisions (need Dylan)

1. **Which ClickUp list** is the Hermes Task OS board? (Orchidea `Ops`, a new space list, or Main Workspace list — confirm live.)
2. **Ingest transport for Phase 1:** cron poll only (recommended) vs webhook+signature support.
3. **Worker identity:** dedicated profile (e.g. `hermes-worker`) vs default profile with restricted tools.
4. **Should Phase 1 land as repo skill/scripts only** (user-local) or mergeable upstream Hermes contrib? (Affects footprint review.)

---

## 9. Recommendation

Ship **Phase 1 only** next: cron poll + thin ClickUp client + Kanban idempotent lock + status/comment loop. That delivers the operating-model shift (async, persistent, permission+go) without rebuilding Hermes or adding Linear/runners.

Phases 2–5 are additive and should not block proving the loop.
