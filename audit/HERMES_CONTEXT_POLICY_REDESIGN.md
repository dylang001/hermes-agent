# Context Policy Redesign (P0) — Implementation note

**Date:** 2026-07-19  
**Docs:** [docs/context-policy.md](../docs/context-policy.md)  
**Benchmark:** [HERMES_CONTEXT_POLICY_BENCHMARK.md](./HERMES_CONTEXT_POLICY_BENCHMARK.md)

## Frozen (untouched)

- Execution Coordinator  
- Prompt cache capability layer  
- Observatory / runtime analytics  
- Runtime freeze principles  
- Recover-first *mechanics* (prune → compact → emergency → fail; schemas ≠ live)

## Changed

| Area | Change |
|------|--------|
| `agent/context_governor.py` | Adaptive %-of-window stages + interactive/autonomous/batch profiles |
| `hermes_cli/config.py` | `context_governor.budget_mode/profile/profiles`; compression defaults 0.70 / protect_last_n 24 |
| `agent/agent_init.py` | Resolve governor from model window + platform; align compressor |
| `agent/conversation_loop.py` | Fail-open load via `load_resolved_governor_config` |
| Tests | Stage/profile/scale coverage in `test_context_governor.py` |

## Production tip

Interactive + MiniMax M3 (~1M): emergency ≈ 900k, compaction ≈ 750k.  
Legacy absolute 28k is opt-in via `context_governor.budget_mode: absolute`.

Restart gateway after deploy so agents rebuild with resolved budgets.
