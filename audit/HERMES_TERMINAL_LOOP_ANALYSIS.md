# Terminal Loop Analysis

Follow-up to Model Wake-up Analysis. SAFE batching archived; terminal micro-loops are the measured bottleneck candidate.

## Aggregate

- Sessions: **20**
- Terminal calls: **457**
- Duplicate rate: **1.1%**
- Retry rate: **0.0%**
- Exit success rate: **95.4%**
- Inspect+search+git share: **62.8%**

**Verdict:** TERMINAL_AS_CHAT — majority inspect/search/git via shell; consider read_file/search_files or terminal macros

### Categories

| Category | Count |
|----------|------:|
| inspect | 140 |
| git | 83 |
| test | 81 |
| search | 64 |
| hermes_cli | 29 |
| mutate | 28 |
| ssh | 23 |
| other | 9 |

## Method

- Pair each `terminal` tool_call with its tool result (`exit_code`).
- Classify command text (test/build/git/search/inspect/…).
- **Duplicate:** exact normalized command seen earlier in the session.
- **Retry:** same normalized command re-run after a prior non-zero exit of that command.

## Per-session

| Session | Terminal | Dup% | Retry% | Insp+git+search% | OK% |
|---------|----------|------|--------|------------------|-----|
| `20260619_092959_3be2c9` | 272 | 0.7% | 0.0% | 69.5% | 96.0% |
| `20260619_095922_535c41` | 39 | 0.0% | 0.0% | 56.4% | 89.7% |
| `20260619_123925_17a2d7` | 32 | 6.2% | 0.0% | 46.9% | 100.0% |
| `20260619_100039_607cd4` | 30 | 0.0% | 0.0% | 40.0% | 90.0% |
| `20260619_101202_4d8992` | 26 | 0.0% | 0.0% | 69.2% | 92.3% |
| `20260619_095920_196c47` | 25 | 0.0% | 0.0% | 48.0% | 96.0% |
| `20260619_100957_dd2e69` | 12 | 0.0% | 0.0% | 33.3% | 100.0% |
| `20260619_100133_aa2a31` | 11 | 9.1% | 0.0% | 90.9% | 100.0% |
| `20260618_215521_7587e6` | 2 | 0.0% | 0.0% | 100.0% | 100.0% |
| `20260619_090351_b95dd2` | 2 | 0.0% | 0.0% | 50.0% | 100.0% |
| `20260619_080940_8eecf9` | 2 | 0.0% | 0.0% | 50.0% | 100.0% |
| `20260619_083257_041ca1` | 1 | 0.0% | 0.0% | 100.0% | 100.0% |
| `20260618_213748_95276f` | 1 | 0.0% | 0.0% | 0.0% | 100.0% |
| `20260618_213147_9f3fcb` | 1 | 0.0% | 0.0% | 0.0% | 100.0% |
| `20260618_215330_54f355` | 1 | 0.0% | 0.0% | 0.0% | 100.0% |
| `20260619_091715_559cd7` | 0 | 0.0% | 0.0% | 0.0% | 0% |
| `20260618_223232_fcd83a` | 0 | 0.0% | 0.0% | 0.0% | 0% |
| `20260619_081052_19530b` | 0 | 0.0% | 0.0% | 0.0% | 0% |
| `cron_34b29b05add8_20260717_092113` | 0 | 0.0% | 0.0% | 0.0% | 0% |
| `cron_28295d7a4ac3_20260717_092113` | 0 | 0.0% | 0.0% | 0.0% | 0% |
