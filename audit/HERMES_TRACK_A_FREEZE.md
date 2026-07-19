# Track A — Frozen (2026-07-19)

**Status:** COMPLETE / FROZEN  
**Do not spend more engineering time here until Go quota resets.**

## Achieved

| Item | Status |
|------|--------|
| Prompt cache is transport/capability-scoped | ✅ |
| Planner / loop / workers / delegation isolated from cache | ✅ |
| Provider adapters own `prompt_cache_capability()` | ✅ |
| Session telemetry + `hermes insights` cache modes | ✅ |
| A/B harness (`audit/_cache_control_ab_harness.py`) | ✅ |
| Live OpenCode Go A/B | ⏸️ Blocked on monthly quota |

## Deferred validation (no architecture risk)

When Go quota returns:

```bash
./venv/bin/python audit/_cache_control_ab_harness.py --turns 20
```

This validates EXPLICIT markers on the Anthropic wire. It does **not** change Track B.

## Non-negotiable (carries into Track B)

Prompt Cache Capability sits **below** Hermes Core (provider adapter / request serializer only).  
Execution code must never call `planner.enable_cache(...)` or set cache mode.
