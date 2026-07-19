# P1 Fix — Context Governor UX Regression

**Date:** 2026-07-19  
**Commit target:** follow-on to `2ba34b7d43` (v1 runtime freeze)

## Root cause

The governor counted **tool schemas** toward `max_live_tokens` (28,000).
A Telegram session with ~4 messages (~1.5k transcript tokens) + large tool
schemas (~26k) reported **28,015** and hard-blocked `"Hello"`.

`/compress` only rewrites the **transcript**, so it correctly reported
“No changes / ~1,476 tokens”. The two components were measuring different
things; the user saw a contradictory dead-end.

## Fix

1. Budget **live transcript** (messages + memory prefetch) only.
2. Tool-schema overhead is diagnostic — never alone hard-blocks.
3. Recover-first orchestration in `conversation_loop`:
   prune → auto-compact → emergency truncate → fail only if still over.
4. Soft tiers: `target` / `soft_warning` / `auto_compact` / `max_live`.

## Tests

`tests/agent/test_context_governor.py` — includes regression
`test_tool_schema_overhead_never_hard_blocks_hello`.
