# Model Wake-up Analysis

Evidence gate for Track B execution batching.

## Aggregate

- Sessions: **20**
- API calls: **549**
- Tool calls: **742**
- Tools / API call: **1.35**
- Batchable tool-turns: **45**
- Est. wake-ups saved if SAFE/LOOKUP coalesced: **15** (3.0% of tool-turns, 2.7% of API calls)
- Duplicate ops: **9**
- Files re-read: **9**
- Subagent spawns: **9**

**Verdict:** DEFER_BATCHING — look at duplicates / subagents / retries first

## Method

For consecutive assistant turns that only requested SAFE and/or LOOKUP tools, estimate that a perfect batching planner would need **1** wake-up per streak instead of **N** (save = N−1). Mutating / mixed / subagent turns break streaks. This is an upper bound on wake-ups removable by batching alone — it does not change reasoning quality assumptions.

## Per-session

| Session | API | Tools | Save% tool-turns | Saved | Dup ops | Subagents |
|---------|-----|-------|------------------|-------|---------|-----------|
| `20260619_092959_3be2c9` | 261 | 343 | 0.0% | 0 | 1 | 9 |
| `20260619_095922_535c41` | 50 | 65 | 0.0% | 0 | 0 | 0 |
| `20260619_095920_196c47` | 40 | 75 | 17.5% | 7 | 4 | 0 |
| `20260619_123925_17a2d7` | 42 | 60 | 7.3% | 3 | 4 | 0 |
| `20260619_100039_607cd4` | 33 | 61 | 0.0% | 0 | 0 | 0 |
| `20260619_100957_dd2e69` | 36 | 36 | 11.1% | 4 | 0 | 0 |
| `20260619_101202_4d8992` | 21 | 46 | 0.0% | 0 | 0 | 0 |
| `20260619_100133_aa2a31` | 34 | 33 | 3.0% | 1 | 0 | 0 |
| `20260618_215521_7587e6` | 6 | 5 | 0.0% | 0 | 0 | 0 |
| `20260619_090351_b95dd2` | 3 | 2 | 0.0% | 0 | 0 | 0 |
| `20260619_080940_8eecf9` | 4 | 5 | 0.0% | 0 | 0 | 0 |
| `20260619_083257_041ca1` | 4 | 3 | 0.0% | 0 | 0 | 0 |
| `20260619_091715_559cd7` | 3 | 3 | 0.0% | 0 | 0 | 0 |
| `20260618_223232_fcd83a` | 2 | 1 | 0.0% | 0 | 0 | 0 |
| `20260618_213748_95276f` | 2 | 1 | 0.0% | 0 | 0 | 0 |
| `20260618_213147_9f3fcb` | 2 | 1 | 0.0% | 0 | 0 | 0 |
| `20260618_215330_54f355` | 2 | 1 | 0.0% | 0 | 0 | 0 |
| `20260619_081052_19530b` | 1 | 0 | 0.0% | 0 | 0 | 0 |
| `cron_34b29b05add8_20260717_092113` | 2 | 1 | 0.0% | 0 | 0 | 0 |
| `cron_28295d7a4ac3_20260717_092113` | 1 | 0 | 0.0% | 0 | 0 | 0 |
