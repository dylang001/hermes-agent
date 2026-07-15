# Hermes Protected Optimizations Audit

Date: 2026-07-15  
Auditor: Cursor agent (read-only verification + local focused tests)  
Scope: Confirm protected optimization work survived Phase 1 upstream merge + VPS deployment **before** enabling ClickUp Task OS cron.

**Cron status:** Task OS cron is **not enabled**. Do not enable until the acceptance criteria at the end of this document are met.

---

## 1. Deployment identity

| Surface | Branch | Commit | Tag |
|---------|--------|--------|-----|
| Local checkout | `codex/hermes-phase1-upstream-merge-20260715` | `07bdd098c0398390218190504f162146db8ae7bc` | `hermes-v2-phase1-approved-20260715` → **same SHA** |
| VPS production | `hermes-phase1-approved` | `07bdd098c0398390218190504f162146db8ae7bc` | matches approved tag |
| VPS app path | — | `/opt/hermes/app` | (legacy docs mentioning `/usr/local/lib/hermes-agent` are stale) |
| VPS HERMES_HOME | — | `/opt/hermes/home` | |

**SHA match:** Local approved tip and VPS HEAD are identical (`07bdd098c`). Left/right count vs tag: `0 0`.

### Working-tree caveats

| Location | Delta vs approved SHA |
|----------|------------------------|
| Local | **Dirty / uncommitted:** Desktop backend-start-ownership WIP; `CANONICAL_CONTEXT.md`; entire `plugins/clickup_task_os/`; audit preservation trees; `tasks/` plan docs. These are **not** on the approved deploy SHA. |
| VPS | Clean aside from `package-lock.json` modification. **No** `plugins/clickup_task_os`. |

**Implication:** Production code parity for protected intelligence/Telegram work is good. ClickUp Task OS and Desktop ownership WIP are local-only until committed and deliberately deployed.

---

## 2. Preservation inventory (refs / bundles)

### Local branches

| Ref | Tip | Ancestor of `07bdd098c`? |
|-----|-----|---------------------------|
| `preserve/local-intelligence-before-upstream-sync-20260710` | `237484f28` | No (content re-landed under new SHAs) |
| `codex/phase6-intelligence-integration-20260709` | `237484f28` | No (same tip family) |
| `preserve/local-phase6-intelligence-20260709` | `7d23fad2c` | No |
| `preserve/phase1-pre-upstream-20260715T100301Z` | `99b8087a5` | **Yes** |
| `preserve/local-detached-upstream-sync-20260710` | `c1a32421e` | No |
| `codex/hermes-bounded-delivery-loop` | `90bf6f34e` | **No** |
| `remotes/vps/codex/phase6-intelligence-integration-20260709` | phase6 family | historical |

### Tags

- `hermes-v2-phase1-approved-20260715` → `07bdd098c` (approved deploy)

### Bundles / patch archives (forensic; not runtime)

Under `audit/`:

- `preservation-20260709T104644Z/` (local/vps bundles, uncommitted patch, lineage)
- `preservation-20260710T065854Z-pre-upstream-sync/`
- `preservation-20260710T071900Z-final-fix-bundle/`
- `preservation-20260710T073000Z-latest-origin-merge-bundle/`
- `preservation-20260710T074000Z-final-upstream-bundle/`
- `preservation-20260710T081500Z-protected-update-bundle/`
- `vps-apply-20260709/` (intelligence scaffold + Telegram concise patches)
- `vps-apply-canonical-20260709/`, `vps-apply-fix-20260709/`

These prove lineage; they must not be blindly applied.

---

## 3. Master classification table

| Change | Original branch/commit | Present locally | Present on VPS | Enabled | Upstream equivalent | Classification | Action |
|--------|------------------------|-----------------|----------------|---------|---------------------|----------------|--------|
| Intelligence policy scaffold | preserve/phase6 · blob `c56932b91…` · scaffold `670504bdf` | Yes (`agent/intelligence_policy.py`) | Yes (same blob) | **VPS gateway: ON** via systemd; local shell: OFF by default | None (fork-local) | **Preserved exactly** (code); **Enabled on VPS gateway** | Keep flag-gated. Re-benchmark before changing defaults. Do **not** expand tool-policy aggressiveness without measurement. |
| Memory policy | same + phase2 checkpoints | Yes | Yes | VPS gateway ON | None | **Preserved exactly** / enabled gateway | Same |
| Tool policy | same + phase3 checkpoints | Yes | Yes | VPS gateway ON | None | **Preserved exactly** / enabled gateway | High latency sensitivity — verify with smoke before more stacks (Task OS) add load |
| Evidence compaction | same + phase4 | Yes | Yes | VPS gateway ON | Partial overlap with other summarizers | **Preserved exactly** / enabled gateway | Keep; avoid double summarization elsewhere |
| Failure policy | same + phase5 | Yes | Yes | VPS gateway ON | Overlaps native retry/fallback | **Preserved exactly** / enabled gateway | Keep; watch for retry amplification |
| Telegram concise responses | `b8843dfbc` / `4153c1346` · blob `c50883c24…` | Yes (`gateway/telegram_response_policy.py`) | Yes (same blob) | **VPS gateway: ON**; dashboard unit: not set; local: OFF | None | **Preserved exactly** / enabled gateway | Keep. Boundary-only; good. |
| Canonical context | `CANONICAL_CONTEXT.md` + vps-apply-canonical | Yes (local dirty edits) | Yes (deployed copy) | N/A (docs) | N/A | **Preserved** | Sync VPS path note (`/opt/hermes/app`) in next doc commit |
| Protected dashboard update guard | `2b33f66ab` | Yes | Yes (on SHA) | Always | Surfaced via carry | **Preserved exactly** | Keep |
| Desktop cookie / AT-or-RT / revalidate / OAuth partition | `439f53cab`, `f3af066b8`, `65712bf78`, … | Yes on SHA | N/A for headless VPS (Desktop is client) | Always-on desktop | Upstream desktop evolution also present | **Preserved through equivalent upstream + carried fixes** | Keep |
| Desktop backend start ownership / abandon race | local WIP `backend-start-ownership.ts` | **WIP only** (uncommitted) | No | N/A | Partial older patterns | **Missing from approved SHA** (local WIP) | Finish tests → commit → then consider desktop ship; **not** blocking Task OS cron |
| Kanban/desktop artifact delivery | `8030b01a2` / `e6c42b5d8` / desktop | Yes | Yes (gateway code) | When kanban used | Upstream | **Preserved through equivalent upstream** | Keep |
| Dashboard host/WS auth / MCP disable / quota fallback | preserve patch series 0001–0009; later SHAs on HEAD | Yes via later commits | Yes on SHA | Always | Re-landed / equivalent | **Preserved through equivalent upstream implementation** | Keep; do not replay old patches |
| Intelligence fixture benchmarks / Phase6 reports | `audit/intelligence_*`, `scripts/benchmark_intelligence_*` | Yes (many untracked audit trees also) | Partial (audit dir on VPS) | Offline only | N/A | **Preserved** (evidence artifacts) | Keep as forensic; not a runtime reviewer |
| **Loop Engineering / bounded delivery loop** | `codex/hermes-bounded-delivery-loop` @ `90bf6f34e` | **Absent on HEAD** | Absent | N/A | None | **Obsolete and should remain removed** *unless* a measured restoration is approved | Do **not** cherry-pick. See §4. |
| Summarize-only / action-evidence guard (named) | No single renamed core symbol | Closest: intelligence `direct_answer` class + `file_mutation_verifier` | Same on VPS | advisory / classification only | Partial relatives only | **Resolved 2026-07-15:** no exact core rename; Task OS owns an independent deterministic completion gate (`plugins/clickup_task_os/worker.py` `evidence_is_resolvable` / prose-only → Waiting) | Keep Task OS gate; do not invent a core restore |
| ClickUp Task OS (`clickup_task_os`) | 2026-07-15 local Phase 1 | Local uncommitted plugin | **Not deployed** | Local profiles only; **no cron** | None | New work, not a preservation item | Deploy only after this audit’s ClickUp hygiene |
| clickup-bridge (user) | `~/.hermes/plugins/clickup-bridge` / VPS `/opt/hermes/home/plugins/clickup-bridge` | Enabled default | Enabled | On-demand CLI | N/A | Separate product surface | Keep; see §5 |

---

## 4. Loop Engineering — exact determination

### What it is

No skill, SOUL entry, Obsidian note, or prompt pack named “Loop Engineering” was found under:

- repo `skills/` / `optional-skills/`
- `~/.hermes/skills` (matches are **Loops.so** email skills: `loops-api`, `loops-cli`, … — unrelated)
- `CANONICAL_CONTEXT.md`, memory files, plugins

**Best evidence:** the unmerged prototype on branch `codex/hermes-bounded-delivery-loop` (`90bf6f34e` / `e835093d4`):

| Attribute | Value |
|-----------|--------|
| Kind | Custom runtime workflow / state machine (**not** a skill; **not** system-prompt injection) |
| Modules | `hermes_cli/bounded_loop.py` (`BoundedDeliveryLoop`), `run_receipt.py` (`ReviewerResult`), `scope_audit.py`, `task_lock.py` |
| Tests | `tests/hermes_cli/test_bounded_loop.py`, `test_run_receipt.py`, `test_scope_audit.py` |
| CLI registration | Not wired as `hermes` subcommand |
| On `07bdd098c` | **Missing** |
| Always-on injection? | No — and should stay that way |

### Token / context overhead if restored always-on

Restoring as always-on planner→execute→review→verify would reintroduce:

- extra reviewer/receipt stages per task
- additional tool/schema surface if wired into the agent loop
- high risk of recreating the “over-optimization / latency” failure mode

### Recommendation

| Option | Verdict |
|--------|---------|
| Always inject into every prompt | **Reject** |
| Skill-triggered for engineering tasks only | Acceptable **after** focused benchmark vs current Task OS + Kanban |
| Leave removed | **Default** — classify Obsolete unless Dylan explicitly reopens |

Nearby confusion to avoid: `loops-*` skills (email product) ≠ Loop Engineering.

---

## 5. ClickUp plugin overlap (`clickup-bridge` vs `clickup_task_os`)

| | clickup-bridge | clickup_task_os |
|--|----------------|-----------------|
| Path | User plugin: local `~/.hermes/plugins/clickup-bridge`; VPS `/opt/hermes/home/plugins/clickup-bridge` | Bundled: local repo `plugins/clickup_task_os/` (**uncommitted**, **not on VPS**) |
| Mode | On-demand CLI (`hermes clickup …`) | Poll CLI + intended cron (`hermes task-os poll`) |
| Poll / webhook / cron | **None** | Cron planned; **not installed** (VPS `cron/jobs.json` job_count=0; local task-os cron empty) |
| Mutates status/comments | **No** (create-task only, approval-gated) | **Yes** (status/tag/comment) |
| Credentials | `CLICKUP_API_TOKEN` | Same token family |
| Enabled default profile | Yes | Yes (local hygiene issue) |
| Enabled task-os profile | No | Yes |
| Double execution risk | **None from bridge** | Only if two pollers/crons both run |

### Consolidation decision

- **Keep** `clickup-bridge` for Growth OS triage / gated create.
- **Do not merge** mutators into bridge (opposite safety model).
- **Before enabling Task OS cron:**
  1. Remove `clickup_task_os` from **default** `~/.hermes/config.yaml` `plugins.enabled` (leave on `task-os` profile only).
  2. Install cron **only** as `hermes -p task-os …` / profile HERMES_HOME.
  3. Do not deploy/enable Task OS on VPS until that hygiene + this audit’s other gates pass.

---

## 6. Runtime flags (VPS vs local)

### VPS `hermes-gateway.service` live process environ (pid verified)

```
HERMES_INTELLIGENCE_POLICY=1
HERMES_INTELLIGENCE_MEMORY_POLICY=1
HERMES_INTELLIGENCE_TOOL_POLICY=1
HERMES_INTELLIGENCE_EVIDENCE_COMPACTION=1
HERMES_INTELLIGENCE_FAILURE_POLICY=1
HERMES_TELEGRAM_CONCISE_RESPONSES=1
```

Source: `/etc/systemd/system/hermes-gateway.service.d/40-runtime-guardrails.conf` (+ EnvironmentFiles).

Smoke under equivalent env: all six gates report `True`.

Bare import without those env vars reports `False` — code defaults remain off; **systemd opt-in is what enables production**.

### VPS `hermes-dashboard.service`

Intelligence/Telegram flags **not** present on dashboard unit Environment. Dashboard uses other guardrails (`HERMES_DISABLE_MCP_IN_DASHBOARD`, public URL, etc.).

### Local workstation

No `HERMES_INTELLIGENCE_*` / `HERMES_TELEGRAM_CONCISE_RESPONSES` in checked `.env` files → policies **Present but disabled** unless set.

### Latency caution

Tool policy + evidence compaction + failure policy are **already ON** for the production gateway. Adding Task OS poll workers on top increases concurrency/tool pressure. Prefer Task OS on dedicated `task-os` profile with its own model routing, and keep concurrency at 2 until a focused smoke says otherwise.

---

## 7. Verification evidence

| Check | Result |
|-------|--------|
| Local SHA == approved tag | Pass (`07bdd098c`) |
| VPS SHA == approved tag | Pass (`07bdd098c`) |
| Intelligence blob local == VPS | Pass (`c56932b91…`) |
| Telegram policy blob local == VPS | Pass (`c50883c24…`) |
| Focused tests | `tests/agent/test_intelligence_policy.py` 27✓; `tests/gateway/test_telegram_response_policy.py` 22✓ |
| VPS flag smoke (gateway-equivalent env) | All six True |
| VPS gateway `/proc` environ | All six present |
| Task OS cron | Not installed (VPS jobs=0) |
| Loop Engineering on deploy SHA | Absent (intentional) |

---

## 8. Decisions required before Task OS cron

| # | Item | Recommendation |
|---|------|----------------|
| 1 | Restore bounded delivery loop (“Loop Engineering”) | **No** — remains removed |
| 2 | Named “summarize-only / action-evidence” restore | **No** until source identified; use existing evidence compaction + Task OS evidence rules |
| 3 | Intelligence flags on VPS gateway | **Keep ON** for now; schedule focused latency check after Task OS smoke, not blind disable |
| 4 | Desktop backend-start-ownership WIP | Commit separately; not required for Task OS cron |
| 5 | clickup_task_os | Commit → deploy (if VPS should poll) or run local-only; strip from default `plugins.enabled` |
| 6 | clickup-bridge | Keep enabled; no disable needed for overlap |

**Explicit non-actions (this audit):** no cherry-picks of preserve bundles; no cron enable; no flag flips without approval.

---

## 9. Acceptance criteria vs this audit

| Criterion | Status |
|-----------|--------|
| 1. Local and VPS commits match approved deployment SHA | **Met** (`07bdd098c`) |
| 2. Required protected fixes present and enabled | **Met for intelligence/Telegram on VPS gateway**; code present locally (disabled by default) |
| 3. Missing changes explicitly approved before restoration | **Met** — only missing named items are Loop Engineering (recommend remain removed) and summarize-only (unknown); WIP desktop ownership not a restore |
| 4. Loop Engineering understood and loaded only where useful | **Met** — not loaded; remain skill/CLI optional if ever revived |
| 5. No duplicate ClickUp execution path | **Met today** (bridge has no poll; Task OS cron absent). Hygiene still required before cron |
| 6. Focused tests + runtime smoke | **Met** (49 local tests; VPS flag smoke) |
| 7. Audit added to production migration/runbook docs | **This file** — also reference from `tasks/todo.md` / plan |

### Remaining gates before cron (not yet met)

1. Remove `clickup_task_os` from default profile `plugins.enabled`.
2. Commit Task OS (or explicitly run uncommitted local-only) and decide VPS deploy scope.
3. One live Ops smoke: Ready + `hermes-ready` → single claim → Review mapping.
4. Confirm no second poller/script elsewhere.

---

## 10. Runbook pointer

Related prior docs:

- `CANONICAL_CONTEXT.md` (flag list; refresh VPS path to `/opt/hermes/app`)
- `audit/intelligence_finalization_rollout_checkpoint.md`
- `audit/intelligence_phase6_vps_parity_audit.md` (stale paths/SHAs — superseded by this audit for 2026-07-15)
- `tasks/plans/2026-07-15-hermes-clickup-task-os.md`
- `plugins/clickup_task_os/README.md`

**Bottom line:** Protected intelligence + Telegram concise work survived and is **enabled on the production gateway**. Loop Engineering (bounded delivery loop) did **not** survive and should stay out. ClickUp bridge does not compete with Task OS polling. **Do not enable Task OS cron until the remaining hygiene gates in §9 are closed.**


## 11. Task OS gate closure (2026-07-15 evening)

| Gate | Result |
|------|--------|
| Default `plugins.enabled` without `clickup_task_os` | Local + VPS confirmed |
| Dedicated `task-os` profile only | Yes |
| Commits | `db02cbdd0` (plugin) + `e41555c90` (audit docs) |
| VPS HEAD | `e41555c900d9285a236ba88de7c721619e408637` |
| Live Ops smoke task | `86carck03` — claimed once → waiting + `hermes-review`; second poll eligible=0 |
| Evidence/completion gate | Independent Task OS gate (`evidence_is_resolvable`); no core rename for summarize-only/action-evidence |
| Cron | VPS **default** HERMES_HOME job `4dcf0a86d0e8` every 5m runs `hermes -p task-os task-os poll`. Profile job `840ebe6313fb` paused. **Do not enable local cron.** |
| Concurrency | 2 |
| Loop Engineering | Not restored |
| Intelligence/Telegram flags | Left ON at VPS gateway |
| clickup-bridge | Kept; no poll overlap |

Rollback cron: `HERMES_HOME=/opt/hermes/home hermes cron pause 4dcf0a86d0e8` (or remove).
