# Hermes Context-Cost Remediation — Phase 1 Report

**Date:** 2026-07-17  
**API token:** not connected (offline estimates only)  
**Memory data:** unchanged  
**Config backup:** `/Users/dylanangloher/.hermes/backups/context-cost-phase1-20260717/config.yaml`

## Prompt-size baseline → after

| Metric | Before | After | Delta |
|--------|-------:|------:|------:|
| Fixed floor (sys+tools) | 37,402 | 20,181 | -17,221 |
| System prompt | 25,651 | 8,224 | -17,427 |
| Context tier (AGENTS.md) | 18,340 tok | 914 tok | -17,427 |
| Tool schemas | 11,751 | 11,956 | +205 |

## Absolute governor

- `max_live_tokens`: 28,000
- `max_retrieval_tokens`: 5,000
- `max_tool_result_tokens`: 6,000
- `max_memory_prefetch_tokens`: 1,500
- Behavior: prune/summarize first; **block** provider call if still over (never silently send oversized).

## Scenario estimates (input tokens)

| Scenario | Before input | After input | Δ | Est. $ before | Est. $ after | Gov actions | Blocked |
|----------|-------------:|------------:|--:|-------------:|------------:|-------------|---------|
| 1. simple conversational | 36,824 | 19,418 | -17,406 | $0.0147 | $0.0078 | 0 | False |
| 2. ten-turn conversation | 37,224 | 19,817 | -17,407 | $0.0149 | $0.0079 | 0 | False |
| 3. one coding task | 37,482 | 20,076 | -17,406 | $0.0150 | $0.0080 | 0 | False |
| 4. tool-heavy research | 81,738 | 22,239 | -59,499 | $0.0327 | $0.0089 | 3 | False |

Cache reads / output tokens / latency: **n/a** — no provider calls (token not connected).

## Applied config

```yaml
context_file_max_chars: 8000
context_project_brief: true
context_governor: {enabled, max_live_tokens: 28000, ...}
compression.protect_last_n: 8
tools.tool_search.enabled: on
platform_toolsets.conversational: [conversational]
```

CLI platform toolset left full for coding capability. Use `platform_toolsets.cli: [conversational]` to opt into the lean chat profile.

## Capability regression check (offline)

- Unit tests: `test_project_brief` (5), `test_context_governor` (5), `TestBuildContextFilesPrompt` (24) — pass
- Project brief retains section index + `read_file` path for AGENTS.md recovery
- Coding tools still on default CLI profile
- Governor blocks only when live estimate still exceeds 28k after prune

## Rollback

```bash
cp /Users/dylanangloher/.hermes/backups/context-cost-phase1-20260717/config.yaml ~/.hermes/config.yaml
# Optional: set context_project_brief: false and context_governor.enabled: false
# without reverting code, to restore legacy inject while keeping new modules inert.
```

Does **not** touch MEMORY.md, USER.md, or state.db.

## Approval gate

Ready for review. **Do not connect a new API token** until this report is approved.
