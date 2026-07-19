# Track B SAFE/LOOKUP Batching — Archived

**Status:** Available optimisation if future telemetry changes.  
**Not** the next feature to build.

## Evidence (2026-07-19)

| Hypothesis | Result |
|------------|--------|
| SAFE/LOOKUP batching will significantly reduce model wake-ups | ❌ False |
| Estimated wake-up reduction (top 20 sessions) | **2.7–3.0%** |
| 261-turn monster session improved by batching | **0%** |

Source: `audit/HERMES_WAKEUP_ANALYSIS.md`

## What stays

- Execution Coordinator scaffold (`agent/execution_coordinator.py`)
- Stable `execute(plan, policy) → ExecutionResult` interface
- Invariants 1–5 and contract tests

These remain useful for *future* runtime work (terminal macros, budgets). They do not justify building a SAFE-read scheduler now.

## What moves next

Measurement order:

1. **Terminal loop analysis** ⭐ — `audit/HERMES_TERMINAL_LOOP_ANALYSIS.md`
2. Retry analysis (folded into terminal report)
3. Delegation ROI
4. Duplicate shell / duplicate edits

Revisit SAFE batching only if wake-up analysis later shows ≥ ~30% batchable tool-turn savings.
