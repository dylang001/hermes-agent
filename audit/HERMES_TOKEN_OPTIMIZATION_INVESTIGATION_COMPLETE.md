# Token Optimization Investigation — Complete

**Status:** OFFICIALLY CLOSED (2026-07-19)  
**Milestone:** [Hermes v1 Runtime — Frozen](HERMES_V1_RUNTIME_FROZEN.md)

**Verdict:** Hermes does not currently have an execution *efficiency* problem. Remaining cost is largely normal agentic *exploration strategy*.

Runtime architecture is now considered stable. Future work prioritizes measurable improvements in task success, reliability, and developer productivity over reductions in raw token consumption.

## What we disproved

| Hypothesis | Result | Decision |
|------------|--------|----------|
| Prompt floor is the problem | ❌ No (already optimized) | Gains realized earlier |
| Prompt cache is broken | ❌ No (93%+ hits) | No further cache work now |
| SAFE/LOOKUP batching will help materially | ❌ No (~3% max) | Archived |
| Terminal retries are the culprit | ❌ No (~0%) | None |
| Duplicate commands are high | ❌ No (~1.1%) | None |
| Delegation is wasteful | ❌ No (productive workers) | Don’t optimize |
| Runtime Coordinator foundation | ✅ Keep | Scaffold only |

Evidence artifacts:

- `HERMES_WAKEUP_ANALYSIS.md`
- `HERMES_TERMINAL_LOOP_ANALYSIS.md`
- `HERMES_DELEGATION_ROI.md`
- `HERMES_INSPECTION_POLICY.md`
- `HERMES_TRACK_B_BATCHING_ARCHIVED.md`
- `HERMES_TRACK_A_FREEZE.md`

## What the data actually says

- The agent isn’t thrashing.
- The cache isn’t broken.
- Workers aren’t wasteful.
- Retries aren’t the problem.
- The parent spends time **exploring** — inspect → git → inspect → test — consistent with modern coding-agent loops.

Suppressing exploration without evidence risks hurting solution quality more than it saves tokens.

## Durable keep-list (do not rip out)

| Asset | Why |
|-------|-----|
| Prompt floor / context governor | Realized savings |
| Prompt-cache capability layer (Track A) | Transport-correct, future-proof |
| Execution Coordinator scaffold + invariants | Thin waist if strategy later needs runtime help |
| Analytics suite (wake-up, terminal, delegation, inspection) | Measure-before-modify infrastructure |

## Ideas backlog (not roadmap)

- SAFE/LOOKUP batching scheduler  
- Terminal macros  
- Dependency graphs / speculative execution  
- Generic execution batching  
- Aggressive inspection caps  

## New north-star + scorecard

Stop optimizing primarily for **cost per token**.

Optimize for:

> **Cost per successful engineering task**

Full scorecard (outcome / efficiency / diagnostic tiers):  
`HERMES_V1_RUNTIME_FROZEN.md`

A change that uses +10% tokens but −40% completion time with fewer interventions is a **win**.

## Gate for any future change

Before building, answer:

1. **Which metric is currently underperforming?**  
2. **What evidence shows this change targets that bottleneck?**  
3. **What benchmark will prove the change was worthwhile?**  

If those answers aren’t available → **ideas backlog**, not roadmap.

## Next phase (not continuation of this project)

1. **Permanent benchmark suite** — same tasks, every Hermes version  
   - Fix a failing test  
   - Refactor a module  
   - Implement a feature  
   - Debug a runtime issue  
   Metrics: time, credits, edits, interventions, regressions, wake-ups, inspection depth  

2. **Exploration efficiency** (still interesting to *measure*)  
   Not “how many terminal commands?” but:  
   - New files / symbols discovered per execute  
   - Did the decision change?  
   - Did a mutation become enabled?  

See `HERMES_AGENT_ANALYTICS_ROADMAP.md` for the active measurement posture.
