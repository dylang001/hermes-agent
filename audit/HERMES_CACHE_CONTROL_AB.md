# Track A — OpenCode Go + MiniMax cache_control A/B

**Measured at:** 2026-07-19T06:28:23.569197+00:00
**Model:** `minimax-m3` via `opencode-go`
**Turns:** 20

## Decision

- **decision:** `blocked`
- **keep_markers:** `True`
- **reason:** OpenCode Go unavailable (quota/500). Policy patch kept (correct for MiniMax Anthropic wire). A/B not measured.

## Provider blocked

```
HTTP 429: {'type': 'error', 'error': {'type': 'GoUsageLimitError', 'message': 'Monthly usage limit reached. Resets in 16 days. To continue using this model now, enable usage from your available balance: https://opencode.ai/workspace/wrk_01KWP89FWC7AS
```

Policy patch retained (docs-correct). No credit-savings claim.

## Policy after patch

```json
{
  "should_cache": true,
  "native_layout": true
}
```

## Next

If keep or blocked-with-docs-correct: leave policy patch.
If rollback_policy_optional and team prefers zero-marker Go path: revert `agent/agent_runtime_helpers.py` MiniMax-on-OpenCode branch.
Then proceed to Track B Milestone 1 (execution batching).
