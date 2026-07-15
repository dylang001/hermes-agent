# Hermes Phase 7 — MVP Implementation Sequence

**Date:** 2026-07-15
**Goal:** Minimal working personal operating assistant for Dylan daily ops
**Rules:** Harden existing systems; no new memory/runtime; no Success.ai; no cookie theft / CAPTCHA bypass

Deliverables: **19** = inventory · **20** = this sequence

---

## North-star MVP (definition of done)

Dylan can, most days:

1. Chat (Telegram/Desktop) without `/root` loops
2. Capture → ClickUp Ops → review/approve
3. Read/write Growth OS knowledge (Mac or VPS-synced)
4. Light research (native web; optional public social read)
5. Engineering tasks via profile, not on default chat schema
6. Missing capability → structured gap note, not terminal thrash

Non-goals (60–90d): live SpaceMail volume, full HyperAgent SDR, LinkedIn mass-auto, Agent-Reach product depth, Zoho CRM activation.

---

## Days 0–7 — Harden what exists (ruthless)

| Day | Deliverable | Why | Exit check |
|-----|-------------|-----|------------|
| 0–1 | Desktop **new session** smoke vs `/opt/hermes/app/audit` | Close Phase 1 gap | No `/root` in logs |
| 1 | Confirm Obsidian MCP → Growth OS **or** disable MCP + use file skill | Kill wrong-path noise | Search vault succeeds |
| 1–2 | Apply `daily-ops` to default VPS chat; measure schema | Latency/cost | Exa/browser off default |
| 2 | MCP health: disable flaky Exa if bad; keep Zoho/Composio off | Stability | Child list clean |
| 2–3 | Commit + deploy `clickup_task_os` to **task-os profile only**; enable cron after protect-audit gates | Durable queue | Smoke claim → review |
| 3 | Wire thin `propose_discovery` / `build_gap_report` into Task OS failure path | Stop silent thrash | Gap comment on missing integ |
| 4 | One staged official skill install via discovery eval | Prove hub path | Approval gate works |
| 4–5 | Validation matrix mini: artifact, Obsidian search, ClickUp update, GH if token | Evidence | Checked in todo |
| 5–6 | Optional: enable `public-platform-research` skill for research profile only | Cheap social read | No cookies/writes |
| 6–7 | Freeze: no prospecting send / SpaceMail / Success.ai | Focus | Only review-gated outreach drafts if any |

**7-day stop condition:** daily chat reliable + Ops Task OS smoke green + Obsidian readable. If conflict, **drop** social enable and schema optimization before dropping Task OS/Obsidian.

---

## Days 8–30 — Ordered backlog

### P0 (must)
1. Task OS Phase 1 evals hardening (definition/completeness/publish-safety) — adapt pack, don’t rebuild Linear
2. Capture path: Telegram/Desktop → ClickUp Inbox/Ops (thin slash if missing)
3. Obsidian Mac→VPS sync (SSH `hermes-production`, lock+dry-run) — prefer existing vault tooling
4. Mem0 hygiene: purge/remap remaining `/root` memories if still prefacing
5. `engineering` + `research` profiles applied where used

### P1 (should)
6. Wire skill discovery into `/help` or Task OS comment templates
7. Gmail OAuth verify under profile-gate (google-workspace skill)
8. Browser-ops profile smoke on Mac; keep VPS gated
9. Prospecting **dry-run only**: ClickUp Pipeline notes + research briefs; no SpaceMail

### P2 (nice / cut freely)
10. Capability-lab Crawl4AI isolate if native web insufficient
11. Community profiles (social-operator, email-ops) — only if daily pain proven
12. Kanban multi-agent Task OS Phase 5 — deferred

---

## Days 31–60 — Roadmap

- Task OS Phase 2–3: evals maturity + narrow Obsidian retrieval into workers (no full KB dump)
- Approval-gated **draft** outreach using existing cold-outreach/apollo **skills** (human send)
- Assess external repos (agent-browser fork, Agent-Reach, marketing pack) — **skills/CLI only**, approval-gated; reject brittleness
- SpaceMail: retrieve adapter **docs/credentials inventory only**; no live volume
- Keep intelligence flags; re-benchmark before any aggressiveness change

## Days 61–90 — Roadmap

- HyperAgent artifact import **if** Dylan provides sources; else continue PRD dry-run
- Optional Agent-Reach install as standalone skill/plugin under capability-lab security model
- Review column native in ClickUp if Review-via-tag remains awkward
- Archive Success.ai / abandoned worktrees (`spacemail-registry-and-cap`) after confirm unused
- Still no second memory system / second agent runner

---

## Explicit defer / reject list

| Item | Action |
|------|--------|
| Success.ai | Never recommend; archive external refs later |
| SpaceMail live send | Defer until sender registry proven |
| Cookie CLIs / CAPTCHA bypass / stealth LinkedIn auto | Reject |
| Zoho / Composio | Keep disabled until explicit need |
| New Mem0 replacement / dual memory | Reject |
| New core tool schemas for ClickUp/social | Reject — plugin/skill only |

---

## Reuse checklist (build order)

1. `daily-ops` profile + runtime metadata
2. clickup-bridge (chat) + clickup_task_os (queue)
3. Obsidian skill + Growth OS paths
4. Mem0 (as-is)
5. skill_discovery + capability_gap (wire, don’t rewrite)
6. Native web → optional public-platform-research → browser-ops last
7. Prospecting skills / SpaceMail only after P0 green

---

## Tracking

Update `tasks/todo.md` Phase 7 checkboxes as matrix rows pass.
Sibling audits (parallel workers): Obsidian V2, social/browser, capability matrix 7A/7B, external repos — fold evidence into this sequence; do not spawn parallel product tracks.
