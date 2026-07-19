# Hermes Context-Cost Remediation — Phase 1 LIVE Report

**Measured at:** 2026-07-17T14:40:40.001797+00:00
**Provider / model:** `opencode-go` / `minimax-m3`
**API key:** present, redacted `***v1Xs`
**Status:** `blocked_provider_quota` — OpenCode Go monthly quota exhausted (HTTP 429 `GoUsageLimitError`).
**Hermes home:** `/Users/dylanangloher/.hermes`
**Workspace:** `/Users/dylanangloher/.hermes/hermes-agent`

## Blocker

Live completions against OpenCode Go failed for **all probed models** (including configured fallbacks):

- `minimax-m3`
- `glm-5.2`
- `deepseek-v4-flash`
- `deepseek-v4-pro`
- `kimi-k2.7-code`
- `qwen3.7-max`
- `glm-5`
- `minimax-m2.5`

Provider message: *Monthly usage limit reached. Resets in 17 days.*

Auth works (requests built and sent). Quota is exhausted before any successful completion, so **provider usage fields (input/cache/output) and true latency-to-first-token are unavailable**. Preflight measurements below still ran through the Phase 1 governor on the real assembled request.

To finish LIVE after numbers: enable Go balance usage at the OpenCode workspace link, or wait for the monthly reset (~17 days), then re-run `audit/_phase1_live_harness.py`.

## Prompt-size floor (healthy)

| Metric | Before (offline baseline) | After (Phase 1 file) | Live `hermes prompt-size` |
|--------|--------------------------:|---------------------:|--------------------------:|
| Fixed floor (sys+tools) | 37,402 | 20,181 | 20,181 |
| System prompt tok est | 25,651 | 8,224 | 8,224 |
| Tool schemas tok est | 11,751 | 11,956 | 11,956 |
| Context (AGENTS.md) chars | 73,363 | 3,657 | 3,657 |

Live fixed floor matches the Phase 1 after snapshot (**20,181**). No Phase 1 config was reverted.

## Scenario results

Cost column uses offline Phase 1 rate **$0.40 / MTok input** for apples-to-apples comparison. OpenCode Go billing is subscription-included when quota allows.

| Scenario | Offline before input | Live gov input est (after) | Δ vs before | Cache reads | Output | Wall latency | Est $ before | Est $ live gov | Gov actions | Blocked | Capability |
|----------|---------------------:|---------------------------:|------------:|------------:|-------:|-------------:|-------------:|---------------:|-------------|---------|------------|
| 1. simple conversational | 36,824 | 18,535 | -18,289 | n/a (429) | n/a (429) | 3.179s (fail-fast) | $0.0147 | $0.0074 | none | False | **blocked by provider quota** |
| 2. ten-turn conversation | 37,224 | 18,534 | -18,690 | n/a (429) | n/a (429) | 12.48s (fail-fast) | $0.0149 | $0.0074 | none | False | **blocked by provider quota** |
| 3. one coding task | 37,482 | 18,575 | -18,907 | n/a (429) | n/a (429) | 1.936s (fail-fast) | $0.0150 | $0.0074 | none | False | **blocked by provider quota** |
| 4. tool-heavy research | 81,738 | 18,620 | -63,118 | n/a (429) | n/a (429) | 1.355s (fail-fast) | $0.0327 | $0.0074 | none | False | **blocked by provider quota** |

### Notes per scenario

1. **Simple conversational** — Governor estimated **18,535** live input tokens (offline after est 19,418; before 36,824). No prune/block. Completion 429.
2. **Ten-turn conversation** — 10 provider attempts in one session; governor ran each turn (~18.5k→slight growth), **no prune/block**. All turns 429; no successful Q&A.
3. **One coding task** — Governor **18,575** tokens; no prune/block. Never reached `read_file` because completion 429.
4. **Tool-heavy research** — Governor **18,620** tokens on the initial prompt only; **did not fire prune** (no large tool results yet). Offline after scenario expected 3 prune actions once oversized tool payloads exist. Completion 429 before tools ran.

### Request dump preflight (first call per scenario)

| Scenario | Model | Msgs | Tools | System chars | Tools JSON bytes | Rough request tokens |
|----------|-------|-----:|------:|-------------:|-----------------:|---------------------:|
| 1. simple conversational | minimax-m3 | 2 | 30 | 29,445 | 48,027 | 18535 |
| 2. ten-turn conversation | minimax-m3 | 2 | 30 | 29,445 | 48,027 | 18534 |
| 3. one coding task | minimax-m3 | 2 | 30 | 29,445 | 48,027 | 18575 |
| 4. tool-heavy research | minimax-m3 | 2 | 30 | 29,445 | 48,027 | 18620 |

## Capability / governor confirmation

| Check | Result |
|-------|--------|
| Material capability regression | **Not verifiable** — provider returned 429 before answers |
| Governor blocked normal turns | **No** — all scenarios `blocked=False` |
| Governor pruned on scenario 4 | **No** (expected: prune triggers on oversized tool results mid-loop; call never progressed) |
| Fixed prompt floor healthy | **Yes** — live 20,181 matches Phase 1 after |
| MEMORY.md / USER.md / Phase 1 config | **Untouched** (`skip_memory=True`; config left as-is) |

## Artifacts

- JSON sibling: `audit/HERMES_CONTEXT_COST_PHASE1_LIVE.json`
- Harness: `audit/_phase1_live_harness.py`
- Offline baseline: `~/.hermes/backups/context-cost-phase1-20260717/phase1-scenario-report.json`
- Prompt baseline: `~/.hermes/backups/context-cost-phase1-20260717/prompt-size-baseline.json`

## Next step

1. Enable OpenCode Go usage-from-balance (or wait for monthly reset).
2. Re-run: `HERMES_HOME=~/.hermes .venv/bin/python audit/_phase1_live_harness.py`
3. Expect provider `usage` fields + scenario-4 governor prune once tool results inflate the live window.

