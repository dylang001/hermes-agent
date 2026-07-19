# Memory Reliability Benchmark — Design

**Program:** Hermes Reliability Program  
**Baseline tag:** `runtime-2026-07-19`  
**Harness:** `audit/_memory_reliability_benchmark.py`  
**Status:** Offline scaffold v0 (no live API). Live MiniMax eval is a follow-up.

## Why this exists

Token and cache metrics can look excellent while the agent still loses track of actions and decisions from two turns ago. This suite measures **continuity quality**.

## Dimensions

| Dimension | Question | Offline proxy (v0) | Live eval (v1) |
|-----------|----------|--------------------|----------------|
| Conversation continuity | Can Hermes recall a user-stated fact after N intervening turns? | Fact strings still present in protected tail / summary after govern+compress | Probe turn with graded recall |
| Engineering continuity | Are architecture decisions, open files, and TODOs retained? | Marker retention rate across compaction | Task resume probe |
| Working-memory retention | After compaction, does the handoff preserve working memory (not “discard”)? | `SUMMARY_PREFIX` semantics + required sections present; latest-wins conflicts | Human/LLM judge vs gold |
| Hallucination rate | Does Hermes invent decisions/files it never established? | Injected distractors must not appear as “Key Decisions” after compress | Probe asks for never-stated facts → must refuse / unknown |

## Scenarios (v0 offline)

1. **two_turn_action** — Record action at turn T; fill T+1 with noise tools; assert action markers still in live context after governor.  
2. **decision_latest_wins** — Decision A then conflicting Decision B; after summary construction rules, B wins and A is not restated as current.  
3. **engineering_markers** — JWT/cookies/singleflight + file paths survive protect_last_n / optimisation prune.  
4. **compact_working_memory** — Force compact-stage config; verify summary prefix is working-memory (not discard-era) and key markers remain in output messages.  
5. **hallucination_guard** — Distractor tokens never uttered as decisions must not appear in summary body when we only pass real markers (structural).  

## Scoring (v0)

Each scenario returns `{passed: bool, score: 0..1, details}`.  
Suite score = mean of scenario scores.  
**Baseline expectation at `runtime-2026-07-19`:** all offline scenarios pass (score ≥ 0.95 suite).

## What v0 does not claim

- Live MiniMax conversational quality  
- Cross-session `session_search` / memory-provider correctness  
- End-to-end Telegram UX  

Those land in **long-session evaluation** once this offline gate stays green.

## How to run

```bash
./venv/bin/python audit/_memory_reliability_benchmark.py
# or:
scripts/run_tests.sh tests/agent/test_memory_reliability_benchmark.py -q
```

Writes:

* `audit/HERMES_MEMORY_RELIABILITY_BENCHMARK.json`  
* `audit/HERMES_MEMORY_RELIABILITY_BENCHMARK.md` (results section regenerated)

## Results (auto-generated)

**Suite passed:** `True`  
**Suite score:** `1.0`  
**Mode:** `offline`  
**Baseline tag:** `runtime-2026-07-19`  

| Scenario | Dimension | Passed | Score |
|----------|-----------|--------|-------|
| `working_memory_prefix` | working-memory retention | True | 1.00 |
| `two_turn_action` | conversation continuity | True | 1.00 |
| `engineering_markers` | engineering continuity | True | 1.00 |
| `decision_latest_wins` | conversation continuity | True | 1.00 |
| `hallucination_guard` | hallucination rate | True | 1.00 |

### Dimension scores

| Dimension | Score |
|-----------|-------|
| conversation_continuity | 1.0 |
| engineering_continuity | 1.0 |
| working_memory_retention | 1.0 |
| hallucination_guard | 1.0 |
