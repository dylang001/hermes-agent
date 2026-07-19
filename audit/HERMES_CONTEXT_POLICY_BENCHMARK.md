# Hermes Context Policy P0 — Before/After Benchmark

**Turns in synthetic transcript:** 120

## Verdict

Legacy absolute 28k **requests compaction** on this engineering transcript; adaptive interactive @ 1M stays in **`normal`** without compaction — continuity preserved.

## Budgets

| Scenario | Window | Opt | Compact | Emergency | Stage | Recovery |
|----------|--------|-----|---------|-----------|-------|----------|
| legacy_absolute_28k | n/a | 24,000 | 27,000 | 28,000 | emergency | compact |
| adaptive_interactive_1M | 1000000 | 550,000 | 750,000 | 900,000 | normal | none |
| adaptive_interactive_128k | 128000 | 70,400 | 96,000 | 115,200 | normal | none |
| adaptive_batch_1M | 1000000 | 300,000 | 500,000 | 750,000 | normal | none |

## Continuity proxy

- Decision markers in input: 120
- Kept under legacy: 120
- Kept under adaptive 1M: 120

## Token pressure (same transcript)

| Scenario | Live before | Live after | Pruned tool results |
|----------|-------------|------------|---------------------|
| legacy 28k | ~151k | ~41k then compact signal | yes (then emergency) |
| adaptive interactive 1M | ~151k | ~151k unchanged | no |
| adaptive interactive 128k | ~151k | ~41k (optimisation prune only) | yes |
| adaptive batch 1M | ~151k | ~151k unchanged | no |

**Interpretation:** On MiniMax-class windows, a long engineering chat that
already blows the old 28k absolute cap stays in Stage 1 (normal) — no
compaction, no tool-trace destruction. On a 128k model the same chat enters
Stage 2 (background optimisation) and prunes tool dumps without summarising
user dialogue. Legacy absolute always escalates to emergency/compact.

## What this does **not** measure (live soak)

- Real engineering task completion rate
- Prompt-cache hit % / cost USD
- End-to-end latency with MiniMax
- Subjective UX vs ChatGPT/Claude

Use Observatory (`hermes_engineering_tasks_*`, compression counters) during a 1–2 week interactive soak on MiniMax M3.
