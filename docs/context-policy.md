# Hermes Context Policy (P0 redesign)

**Status:** Implemented  
**Date:** 2026-07-19  
**Constraint:** Runtime architecture remains frozen (Execution Coordinator,
prompt-cache capability layer, recover-first governor *mechanics*,
observability, analytics, freeze principles). This document redesigns the
**context management strategy** only.

## Problem

The Phase-1 absolute live budget (~28k tokens) compacted far too early on
large-window models (MiniMax M3 ≈ 1M). Continuity, architectural memory, and
interactive quality degraded even though raw prompt size looked “efficient.”

Primary KPI: **successful engineering work**, not minimum live transcript size.

## Philosophy

Hermes is a personal engineering OS, not a stateless API worker.

- Exploit large context windows; do not artificially pin to a small absolute
  fraction of MiniMax capacity.
- Preserve conversational continuity for as long as possible.
- Cost optimisation must not noticeably degrade interactive UX.
- Cached tokens are not wasted — prompt caching exists to make long sessions
  practical. Do not sacrifice quality merely to reduce cache reads.
- “Use as much context as needed” ≠ “always send 1M tokens.” Keep useful
  context, exploit caching, compact only for clear benefit or hard limits.

## Four stages

Thresholds are **percentages of the active model’s context window**, resolved
at agent init (and on model switch). They scale automatically across MiniMax
M3, 128k models, etc.

| Stage | Name | Default (interactive) | Behaviour |
|-------|------|------------------------|-----------|
| 1 | Normal | &lt; 35% | Grow naturally. No compaction. No summarisation. No user-visible behaviour. |
| 2 | Background optimisation | ≥ 35% / &lt; 55% | Prune redundant tool traces, collapse verbose logs, dedupe diagnostics. **Do not** summarise the user’s conversation. |
| 3 | Intelligent compaction | ≥ 75% (interactive) | Caller auto-compacts; compressor must preserve engineering state (decisions, TODOs, files, open issues, plans). |
| 4 | Emergency recovery | ≥ emergency ratio | Aggressive compact / emergency truncate / fail-after-recovery. Rare. |

Exact interactive defaults (fractions of `context_length`):

| Knob | Ratio |
|------|-------|
| `informational_ratio` | 0.35 |
| `optimization_ratio` | 0.55 |
| `compaction_ratio` | 0.75 |
| `emergency_ratio` | 0.90 |

Tool/prefetch budgets are also window-relative (with sane floors/ceilings).

## Profiles

| Profile | When (`profile: auto`) | Intent |
|---------|------------------------|--------|
| `interactive` | CLI, TUI, Desktop, Telegram/Discord/… | Maximise continuity; use most of the window. |
| `autonomous` | Cron / background jobs | Leaner; earlier optimisation. |
| `batch` | Subagents / workers | Disposable focused contexts; compact earlier. |

Override with `context_governor.profile: interactive|autonomous|batch|auto`.

## Absolute mode (legacy)

`context_governor.budget_mode: absolute` restores the old fixed-token knobs
(`max_live_tokens`, …) for experiments or tiny models. Default is
`budget_mode: adaptive`.

## What must survive compaction

- Current task / open TODOs  
- Active files and repo understanding  
- Architecture decisions and prior conclusions  
- Unresolved questions  
- Session-established user preferences  

The assistant must not “forget where it was.”

Compaction handoff (`SUMMARY_PREFIX`) preserves Key Decisions / Relevant Files /
Active State as working memory. The latest user message wins **on conflict /
cancellation only** — topic overlap alone must not erase session continuity.
See `audit/HERMES_CONTEXT_POLICY_P0_RCA.md`.

## Stack (unchanged layering)

```
Gateway hygiene (safety net)
  → % ContextCompressor (profile-aligned threshold)
  → Adaptive context governor (this policy)
```

Live-transcript vs tool-schema split remains: schemas never alone hard-block
(Telegram “Hello” regression).

## Frozen / do not rewrite

- Execution Coordinator  
- Prompt cache capability layer  
- Recover-first governor semantics (prune → compact → emergency → fail)  
- Observatory / runtime analytics  
- Runtime freeze principles  

## Benchmarks

See `audit/HERMES_CONTEXT_POLICY_BENCHMARK.md` and
`audit/_context_policy_benchmark.py`. Metrics: task continuity proxies,
compaction frequency, cache-efficiency notes, estimated cost, latency
proxies, UX observations.
