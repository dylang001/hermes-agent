# P0 — Hermes Context Management: Root-Cause Analysis & Recommendation

**Date:** 2026-07-19  
**Primary objective:** Reliable working memory across long engineering sessions  
**Not the objective:** Minimum prompt tokens  

**Frozen (do not remove):** Execution Coordinator · Prompt-cache capability layer · Observatory · Recover-first governor mechanics  

**Related:** [docs/context-policy.md](../docs/context-policy.md) · [HERMES_CONTEXT_POLICY_BENCHMARK.md](./HERMES_CONTEXT_POLICY_BENCHMARK.md) · [MiniMax Prompt Caching](https://platform.minimax.io/docs/api-reference/text-prompt-caching)

---

## 1. Root-cause analysis

### 1.1 What users experienced

After the Phase-1 “absolute live budget (~28k)” optimisation:

- Compaction started far too early on MiniMax M3 (~1M window)
- Long engineering chats lost architectural decisions mid-session
- Answers shortened / felt less coherent than ChatGPT or Claude
- Trust broke: the agent forgot what it was doing two turns ago

That is a **continuity failure**, not a token-accounting success.

### 1.2 Lifecycle map (where pressure is applied)

```
Context growth (tool traces + dialogue)
    ↓
Prompt construction (system byte-stable; API copies only)
    ↓
Prompt caching (MiniMax passive prefix OR Anthropic explicit markers)
    ↓
% ContextCompressor (threshold of window)
    ↓
Adaptive context governor (live transcript stages)
    ↓
Gateway hygiene (≈85% safety net)
```

| Layer | What it counts | Default interactive @ 1M | Default @ 128k |
|-------|----------------|--------------------------|----------------|
| Compressor | `prompt_tokens` (includes cache_read) | **700k (70%)** | **96k (75% floor)** |
| Governor compaction | live transcript only | **750k (75%)** | **96k (75%)** |
| Governor emergency | live transcript | **900k (90%)** | **115k (90%)** |
| Gateway hygiene | session estimate | **850k (85%)** | **109k (85%)** |
| Legacy absolute (old) | live transcript | **28k** | **28k** |

The old absolute 28k governor alone forced compaction at ~3% of MiniMax capacity.

### 1.3 Investigation findings (required questions)

#### Q: Is OpenCode changing message serialization between turns and reducing cache?

**No.** OpenCode in this repo is provider/routing + cache-capability (`plugins/model-providers/opencode-zen/`, `hermes_cli/models.py:opencode_model_api_mode`). There is no OpenCode history rewriter.

Cache markers are applied on a **deep-copied API payload** (`agent/prompt_caching.py:apply_anthropic_cache_control`, called from `conversation_loop`). History is not mutated by those markers. Wire sanitizers strip underscore keys on copies only.

**Real cache breakers:** compaction (system rebuild + middle rewrite), mid-session tool/system changes, governor tool-trace rewrite past the optimisation stage.

#### Q: Are cached tokens incorrectly influencing compaction?

**Partially — by inclusion, not by a dedicated anti-cache policy.**

- `CanonicalUsage.prompt_tokens = input + cache_read + cache_write` (`agent/usage_pricing.py`)
- `ContextCompressor.should_compress` compares that total to `threshold_tokens`
- There is **no** “high cache hit → delay compact” branch

For window occupancy this is correct (cached tokens still occupy the window).  
For product intent (“don’t sacrifice continuity to reduce cache reads”) the failure mode was **compacting too early**, not “treating cache as free.” Paying for cache reads is fine; **forgetting** is not.

#### Q: Is Hermes summarizing active working memory instead of obsolete history?

**Yes — two mechanisms:**

1. **Lossy middle summarization** — head/tail kept; middle → aux LLM (or weak fallback). Template *asks* for Key Decisions / Files / TODOs but does not enforce them.
2. **`SUMMARY_PREFIX` discard-era wording** (now fixed) — told the model to **discard** Historical Task / In-Progress / Pending / Remaining Work unless the latest message re-asked. That erased ephemeral engineering reasoning even when the summary still contained it.

Additionally, `_MAX_TAIL_MESSAGE_FLOOR` was **8**, so `protect_last_n: 24` was mostly marketing; the hard floor capped recent verbatim turns.

#### Q: Are prompt prefixes stable enough for MiniMax caching?

**Mostly yes for the system + tools prefix; history is the variable.**

MiniMax docs ([Prompt Caching](https://platform.minimax.io/docs/api-reference/text-prompt-caching)):

- Passive/automatic caching on repeated prefixes
- Prefix order: **tool list → system → user messages**
- ≥512 input tokens to engage cache
- Static content first; dynamic content last
- M3 long-context pricing tier when input **>512k** (including cache hits)

Hermes already:

- Keeps system prompt byte-stable for the session (`conversation_loop`)
- Strips/sorts on API copies for stable prefixes
- Emits explicit Anthropic `cache_control` when capability is `EXPLICIT` (MiniMax `/anthropic`, OpenCode Go + MiniMax → `anthropic_messages`)

Risks to maximize:

- Compaction rebuilds system prompt → cache miss on system
- Tool-result pruning in mid-history after optimisation stage
- Any mid-session toolset swap (forbidden by cache doctrine)

Third-party note: some clients report Anthropic-wire `cache_control` ignored while OpenAI-wire passive cache works. Hermes supports both paths via `prompt_cache_capabilities`; validate on the live MiniMax route during soak.

### 1.4 Root causes (ranked)

| Rank | Cause | Impact on continuity |
|------|-------|----------------------|
| **R1** | Absolute ~28k live budget on a 1M model | Premature compaction / prune |
| **R2** | Compaction handoff told the model to discard working-memory sections | Forgot decisions/TODOs mid-session |
| **R3** | Tail floor capped at 8 messages | Recent reasoning truncated too aggressively when compacting |
| **R4** | Single global policy for interactive vs workers | Day-long chat constrained like a disposable subagent |
| **R5** | OpenCode serialization | **Not a cause** |

---

## 2. Proposed architecture

### 2.1 Principles

1. **Working memory > token vanity** — prefer 20–40% higher cache-read cost over forgetting.
2. **Exploit MiniMax’s window** — stages are % of `context_length`, not fixed absolutes.
3. **Compact only when beneficial or necessary** — evidence = approaching hard limit, or clear low-value bulk (tool dumps), never “cache reads look high.”
4. **Stable prefixes** — never mutate system/tools mid-conversation except at intentional compaction.
5. **Profiles** — interactive / autonomous / batch.

### 2.2 Adaptive multi-stage policy (implemented)

| Stage | Interactive | Behaviour |
|-------|-------------|-----------|
| 1 Normal | &lt; 35% | No prune, no compact, no user-visible behaviour |
| 2 Optimisation | ≥ 55% | Prune/collapse **tool traces** only |
| 3 Intelligent compaction | ≥ 75% (compressor 70%) | Summarize obsolete middle; preserve engineering state |
| 4 Emergency | ≥ 90% | Aggressive recovery — rare |

Profiles: `interactive` (CLI/Telegram/Desktop), `autonomous` (cron), `batch` (subagents).  
Legacy escape: `context_governor.budget_mode: absolute`.

### 2.3 Working-memory handoff (implemented this pass)

`SUMMARY_PREFIX` now:

- **Preserves** Key Decisions, Relevant Files, Active State, unfinished engineering work
- **Wins on conflict only** (cancel / reverse signals / explicit topic change)
- **Does not** blanket-discard historical working-memory sections on topic overlap

Tail floor raised **8 → 16** so recent decision turns survive compaction more often.

### 2.4 Still recommended (follow-ups, not blocking)

| Item | Why |
|------|-----|
| Structured session scratchpad (decisions/TODOs/files) outside the transcript | Survives even bad summaries |
| Role-aware tail floor (count user/assistant, skip bulky tools) | Better than a flat message floor |
| Optional “delay compact when cache_hit_ratio high AND live &lt; emergency” | Aligns accounting with product intent |
| Validate MiniMax Anthropic vs OpenAI wire cache hits in soak | Vendor path differences |
| Refresh website compression docs (still show 50% / old template) | Docs drift |

---

## 3. Before / after benchmarks

Offline harness: `audit/_context_policy_benchmark.py` → [HERMES_CONTEXT_POLICY_BENCHMARK.md](./HERMES_CONTEXT_POLICY_BENCHMARK.md)

Same ~151k-token synthetic engineering transcript (120 turns):

| Scenario | Stage | Recovery | Transcript |
|----------|-------|----------|------------|
| **Before:** absolute 28k | emergency | **compact** | pruned then compact signal |
| **After:** adaptive interactive @ 1M | **normal** | **none** | untouched |
| After: adaptive interactive @ 128k | normal (after tool prune) | none | tool dumps pruned only |
| After: adaptive batch @ 1M | normal | none | untouched at this size |

**Interpretation:** On MiniMax-class windows, work that blew the old 28k ceiling no longer triggers compaction at all. Continuity is preserved by **not destroying the transcript**, not by a cleverer summary.

Live soak still required for: task completion rate, real cache %, USD, latency, subjective UX.

---

## 4. Estimated impact

| Metric | Direction | Confidence | Notes |
|--------|-----------|------------|-------|
| **Task completion** | ↑ | Medium | Fewer “forgot the plan” failures |
| **Conversation continuity** | ↑↑ | High | Primary win; verified offline for premature compact |
| **Cache efficiency** | ↑ or flat | Medium | Longer stable prefixes; fewer system rebuilds from early compact. May see higher absolute cache-read volume (desired) |
| **Total cost** | ↑ 10–40% cache-read possible on long chats | Medium | Acceptable per product choice; avoid &gt;512k tier until needed |
| **Latency** | ↓ mid-session (fewer compact pauses); ↑ slightly on larger prompts | Medium | Cache hits should dominate |

**Trade-off endorsement:** Prefer higher cache-read cost over forgetting ephemeral reasoning. A personal engineering agent dies by broken trust, not by a few extra cents of cached tokens.

---

## 5. Recommendation (new adaptive context policy)

**Adopt and ship** the adaptive %-of-window + profile policy already in tree, plus the working-memory handoff fix:

1. Keep `budget_mode: adaptive` (default) on interactive MiniMax.
2. Do **not** reintroduce absolute 28k for Telegram/Desktop day-long chats.
3. Treat compaction as rare; Stage 2 tool-trace hygiene first.
4. Never optimise for lower cache-read counts at the expense of continuity.
5. Measure success with Observatory KPI: **cost per successful engineering task** + compaction frequency + subjective continuity — not minimum live tokens.

### Config sketch (already in `DEFAULT_CONFIG`)

```yaml
context_governor:
  enabled: true
  budget_mode: adaptive
  profile: auto   # interactive | autonomous | batch
compression:
  threshold: 0.70
  target_ratio: 0.25
  protect_last_n: 24
```

### Success criteria (soak, 1–2 weeks)

- Interactive sessions run for hours without user noticing compaction
- Compaction events rare on MiniMax (&lt;1 per long session unless &gt;750k live)
- Users do not report “forgot what we decided”
- Cache-read share remains high on stable prefixes (observatory / usage logs)
- Engineering task success rate does not regress

---

## 6. Code map (this P0)

| Piece | Path |
|-------|------|
| Adaptive governor + profiles | `agent/context_governor.py` |
| Working-memory SUMMARY_PREFIX | `agent/context_compressor.py` |
| Init wiring | `agent/agent_init.py` |
| Config defaults | `hermes_cli/config.py` |
| Policy doc | `docs/context-policy.md` |
| Prefix semantics tests | `tests/agent/test_summary_prefix_semantics.py` |
| Governor tests | `tests/agent/test_context_governor.py` |
| Offline benchmark | `audit/_context_policy_benchmark.py` |

---

## 7. Bottom line

The previous optimisation solved the wrong problem.  
OpenCode is not the villain. Absolute 28k + discard-era compaction handoffs were.

Hermes should behave like a personal engineering OS with a 1M-window model: **grow, cache, prune junk, compact late, never forget the session.**
