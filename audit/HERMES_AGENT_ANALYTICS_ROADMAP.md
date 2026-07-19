# Hermes — Measure Before Modify

**Token optimization investigation:** CLOSED  
→ `HERMES_TOKEN_OPTIMIZATION_INVESTIGATION_COMPLETE.md`

**Mode:** Permanent analytics + benchmarking. No runtime “optimization” without evidence.

## North-star

**Cost per successful engineering task**  
(not cost per token)

## Completed measurement stack

| Report | Artifact | Finding |
|--------|----------|---------|
| Wake-up / batching gate | `HERMES_WAKEUP_ANALYSIS.md` | Batching ~3% — archived |
| Terminal loops | `HERMES_TERMINAL_LOOP_ANALYSIS.md` | Shell-as-chat; ~0% retries |
| Delegation ROI | `HERMES_DELEGATION_ROI.md` | Productive workers |
| Inspection policy | `HERMES_INSPECTION_POLICY.md` | Balanced overall; monster is cautious outlier |

## Next phase

### A. Permanent benchmark suite (priority)

Same tasks, every Hermes version. Reject token wins that hurt success; keep token increases that cut time/interventions.

| Benchmark | Measure |
|-----------|---------|
| Fix a failing test | Time, credits, edits |
| Refactor a module | Time, quality, regressions |
| Implement a feature | Human interventions |
| Debug a runtime issue | Wake-ups, inspection depth |

*Not started — charter only until explicitly kicked off.*

### B. Exploration efficiency (measure only)

Per inspection:

- New files discovered?  
- New symbols discovered?  
- Decision changed?  
- Mutation enabled?  

High-value inspections ≠ waste. Low-value inspections → *then* consider behavioural policy.

### C. Ideas backlog

SAFE batching, terminal macros, schedulers, inspection caps — see investigation complete doc.

## Gate (mandatory)

1. Which metric is underperforming?  
2. What evidence targets that bottleneck?  
3. What benchmark proves the change helped?  

```bash
./venv/bin/python audit/_wakeup_analysis.py --limit 20
./venv/bin/python audit/_terminal_loop_analysis.py --limit 20
./venv/bin/python audit/_agent_behavior_analytics.py --limit 20
```
