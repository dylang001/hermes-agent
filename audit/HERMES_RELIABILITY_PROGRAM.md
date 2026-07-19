# Hermes Reliability Program

**Supersedes the framing:** “Runtime optimization”  
**Declared:** 2026-07-19  
**Baseline tag:** `runtime-2026-07-19`

Runtime architecture is good enough to stop chasing token counts as the primary KPI. The program now optimizes **what Hermes remembers and whether it finishes engineering work correctly**.

## Roadmap

| # | Track | Status |
|---|-------|--------|
| 1 | Runtime architecture (freeze, EC, cache abstraction, recover-first governor) | ✅ Done |
| 2 | Observability Phase 1 | ✅ Done — soak, don’t expand |
| 3 | Deployment reproducibility (clean trees; SHA parity next) | ✅ Trees match; 🔄 SHA parity pending |
| 4 | **Memory reliability** | 🔄 Active |
| 5 | Continuity / reliability benchmark suite | 🔄 Scaffolded |
| 6 | Long-session evaluation | Pending |
| 7 | Autonomous agent quality | Pending |
| 8 | Product features | Deferred until reliability baselines exist |

## Priority #1 symptom

> Hermes forgetting what it literally did two turns ago.

That is a **memory / continuity** failure, not a token-budget failure. Diagnose with continuity benchmarks and live soak (Observatory + structured eval), not cache-hit %.

## Outcome metrics (optimize these)

* Conversation continuity score (facts recalled N turns later)  
* Engineering continuity score (decisions, open files, TODOs retained)  
* Working-memory retention after compression  
* Hallucination / invented-state rate  
* Task success / human interventions (existing scorecard)

## Efficiency metrics (explain, don’t chase)

* Cache reads, credits, prompt size — secondary  
* Use them when they correlate with worse continuity or task failure  

## Gate (unchanged)

1. Which reliability metric is underperforming?  
2. What evidence (benchmark / Observatory / transcript) shows it?  
3. Which benchmark proves the fix?

No answers → backlog, not implementation.
