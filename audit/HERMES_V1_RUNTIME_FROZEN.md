# Milestone: Hermes v1 Runtime — Frozen

**Declared:** 2026-07-19  
**Status:** FROZEN

Runtime architecture is now considered stable. Future work prioritizes measurable improvements in task success, reliability, and developer productivity over reductions in raw token consumption.

From this point on, the runtime only changes if a benchmark proves it is the bottleneck.

## Validated with data

| Investigation | Result | Action |
|---------------|--------|--------|
| Prompt floor | Significant win | ✅ Keep |
| Prompt caching | Healthy (>93% cache reads) | ✅ Keep |
| Cache capability abstraction | Correct architecture | ✅ Keep |
| SAFE batching | ~3% maximum gain | 📦 Archive |
| Terminal retries | Not a problem | 📦 Archive |
| Duplicate commands | Negligible | 📦 Archive |
| Delegation ROI | Productive workers | ✅ Keep |
| Coordinator | Good abstraction boundary | ✅ Freeze |

Close-out: `HERMES_TOKEN_OPTIMIZATION_INVESTIGATION_COMPLETE.md`  
Posture: `HERMES_AGENT_ANALYTICS_ROADMAP.md`

## Hermes Engineering Scorecard

### Outcome metrics (highest priority — optimize these)

* Task success rate  
* Human interventions per task  
* Time to successful completion  
* Regression rate after merge  
* **Cost per successful engineering task**

### Efficiency metrics (secondary — explain outcomes)

* Model turns per task  
* Cache reads per task  
* Credits per task  
* Inspection-to-mutation ratio  
* Delegation ROI  

### Diagnostic metrics (investigation only)

* Prompt size  
* Cache hit %  
* Duplicate commands  
* Retry rate  
* Shell/tool mix  

Do not optimize diagnostics directly unless they correlate with worse outcomes.

## Three-question gate (mandatory before implementation)

1. Which user-facing or benchmark metric is underperforming?  
2. What telemetry identifies this as the bottleneck?  
3. Which benchmark will prove the change improved Hermes?  

No answers → ideas backlog, not roadmap.

## Next project: evaluation (not optimization)

Permanent benchmark suite (charter — not yet built):

| Benchmark | Success criteria |
|-----------|------------------|
| Fix a failing unit test | Tests pass, no regressions |
| Implement a feature | Acceptance tests pass |
| Refactor module | Behaviour unchanged, quality improved |
| Debug production issue | Root cause found and fixed |
| Large migration | Completes within defined budget |

Still worth *measuring* later: **Information Gain per Inspection**.

## Philosophy

We are no longer trying to build the cheapest coding agent.

We are trying to build the **most effective** coding agent — and only optimize efficiency when the data shows it is limiting effectiveness.
