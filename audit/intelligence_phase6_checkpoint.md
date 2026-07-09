# Phase 6 Checkpoint

Generated: 2026-07-09

Scope completed: integrated local validation, real local smoke tests, read-only VPS parity audit, read-only VPS cleanup inventory, read-only memory/source consistency audit, canonical context proposal, and Telegram response behaviour patch/tests.

No production deployment, VPS changes, service restarts, credential changes, provider/model routing changes, MCP startup/config changes, schedule changes, approval-gate changes, memory deletion, Mem0 writes, or external side effects were performed.

## Code Diff Summary

- Added `gateway/telegram_response_policy.py`.
  - Disabled by default via `HERMES_TELEGRAM_CONCISE_RESPONSES`.
  - Applies only to Telegram.
  - Keeps Desktop/CLI/local surfaces unchanged.
  - Summarizes long Telegram output, logs, approval-required states, blocked states, and source-discrepancy statuses.
  - Preserves expanded output when the user asks for a full report/details.
- Patched `gateway/run.py`.
  - Applies the Telegram response policy at final-response and status-message boundaries after existing redaction/provider-error handling.
  - Fails open to previous output if the policy import or shaping fails.
- Added `tests/gateway/test_telegram_response_policy.py`.
- Added `scripts/benchmark_intelligence_phase6.py`.
  - Produces `audit/intelligence_phase6_integrated_benchmark.json`.
- Added `scripts/smoke_intelligence_phase6.py`.
  - Produces `audit/intelligence_phase6_local_smoke.json`.
- Added Phase 6 audit/checkpoint artifacts under `audit/`.

Prior Phase 1-5 intelligence implementation remains disabled by default.

## Integrated 20-Case Benchmark

Report: `audit/intelligence_phase6_integrated_benchmark.json`

Mode: `phase6_integrated_fixture_benchmark`

Metric labels:

- benchmark: fixture-derived
- provider response: mock-runtime-derived
- connector data: fixture-derived
- request construction: fixture-derived-estimate

Summary:

- cases: 20
- quality regressions: 0
- approval-gate regressions: 0
- provider/model routing changes: 0
- MCP startup regressions: 0
- tool availability regressions: 0
- memory leakage in reports: false
- raw secret/sensitive payload in reports: false
- default flags-off behaviour unchanged: true
- safe auth/quota fallback cases: 1
- total evidence savings: 66,098 bytes
- total request-size delta: -891,421 bytes
- total token-estimate delta: -222,850

Case-level details are in the JSON report. Representative rows:

- research: analysis_or_research, memory skipped/light, research tools, 3,791-byte evidence savings per case, final completed, quality 1.0.
- engineering/ops: project memory, engineering/workspace readonly or execution group, 2,848-2,898-byte evidence savings, approval-required action remained approval_required.
- auth/quota failure: failure policy `activate_fallback`, retries `1 -> 0`, fallback attempted, provider/model unchanged.
- personal/business: user/project memory, personal_readonly or workspace_readonly groups, 2,848-3,791-byte evidence savings, quality 1.0.

## Real Local Smoke Tests

Report: `audit/intelligence_phase6_local_smoke.json`

Mode: `phase6_real_local_smoke_mocked_connectors`

Metric labels:

- prompt/schema construction: real-runtime-derived for AIAgent.run_conversation cases
- provider response: mock-runtime-derived
- connector data: fixture-derived
- simulated failures: policy-derived

Summary:

- cases: 7
- side effects: none
- quality regressions: 0
- approval-required cases: 1
- simulated failure cases: 2

Rows:

- `direct-answer`: direct_answer, memory skipped, tools none, final completed, runtime request 9,166 bytes, schema 2 bytes.
- `research`: analysis_or_research, memory skipped, research tools, final completed, runtime request 14,236 bytes, schema 5,023 bytes.
- `repo-log`: analysis_or_research, project memory, engineering_readonly tools, final completed, runtime request 35,226 bytes, schema 25,692 bytes.
- `personal-readonly`: scoped_lookup, user memory, personal_readonly tools, final completed, runtime request 22,541 bytes, schema 13,015 bytes.
- `approval-required`: execution_task, failure decision approval_required, final approval_required.
- `quota-auth`: auth_or_quota, failure decision activate_fallback, fallback attempted, final completed.
- `schema-config`: configuration_or_schema, failure decision fail_closed, no fallback, final failed.

## Read-Only VPS Parity Audit

Report: `audit/intelligence_phase6_vps_parity_audit.md`

Key findings:

- Local HEAD: `7d23fad2c25968aa5ebb694e7de36ab33c281002`.
- VPS HEAD: `58f22c2f1069d651b75ab90a52901c5cf1f8a192`.
- Both local and VPS report `behind 41, ahead 12` relative to `origin/main`, but they are not the same commit.
- VPS active services: `hermes-dashboard.service`, `hermes-gateway.service`.
- VPS active MCP children: Exa and Obsidian filesystem only.
- No intelligence flags were enabled in VPS service environments.
- Local and VPS configs differ on fallback models and memory provider; this must be reviewed before rollout.

## Read-Only VPS Cleanup Inventory

Report: `audit/intelligence_phase6_vps_cleanup_inventory.md`

High-level inventory:

- keep: production checkout, backup roots, active service state, skill backup roots.
- archive candidates after approval: old recovery/update validation checkouts, some old config backups, old Zoho web cache.
- delete candidates after approval: old desktop audit attachments.
- needs Dylan review: old worktrees, memory helper scripts, Supermemory artifacts, unrelated checkouts.
- unsafe to touch: token/config credential paths such as `/root/.hermes/mcp-tokens/orchidea-zoho-*`.

## Memory / Source Consistency Audit

Report: `audit/intelligence_phase6_memory_source_discrepancy_report.md`

Key discrepancies:

- active local path: `.hermes/hermes-agent` versus older `Documents/Hermes` assumptions.
- active VPS path: `/usr/local/lib/hermes-agent` versus older worktree/state-path assumptions.
- current Desktop remote URL: `https://hermes.meetlyra.live` versus older direct-IP URL memories.
- local and VPS commits differ.
- local and VPS provider/fallback config differ.
- local external memory provider is empty/unset; VPS external memory provider is `mem0`.
- active MCP children are Exa and Obsidian; Zoho is configured/tokened but not observed active.
- canonical ClickUp list/workspace IDs were not found in this read-only pass.
- old worktrees and helper scripts should not be treated as current state.

No memory was deleted or written.

## Canonical Context Proposal

Proposal: `audit/intelligence_phase6_canonical_context_proposal.md`

It proposes:

- source precedence: live state, canonical file, repo docs, recent decisions, external memory, older memory.
- stable active local path, VPS path, services, public URL, and approval constraints.
- explicit split between active MCP children and configured-but-not-active MCPs.
- no ClickUp ID canonicalization until live/configured evidence is verified.
- no memory writes/deletes until approved.

## Telegram Behaviour Patch

Feature flag: `HERMES_TELEGRAM_CONCISE_RESPONSES=1`

Default: disabled.

Before/after examples:

- direct answer:
  - before: `JSON is a text format for structured data.`
  - after: `JSON is a text format for structured data.`
- long task:
  - before: dozens of detail lines
  - after: `Done - Validation completed. Ask for details for the full report.`
- approval required:
  - before: approval line plus long command/details
  - after: `Need approval - Approval required before running: ...`
- log-heavy task:
  - before: raw traceback/log dump
  - after: `Found issue - I summarized the log evidence instead of sending raw logs. Ask for details for the full report.`
- discrepancy:
  - before: long memory/source discrepancy narration
  - after: `Found a stale memory/source conflict. I am verifying against live config before touching anything.`
- details requested:
  - before/after: full report is preserved.
- Desktop/CLI/local:
  - unchanged.

## Tests Run

```bash
./.venv/bin/python -m pytest tests/gateway/test_telegram_response_policy.py tests/agent/test_intelligence_policy.py tests/agent/test_intelligence_policy_phase1_5.py -q
```

Result: `40 passed in 8.94s`

```bash
./.venv/bin/python scripts/benchmark_intelligence_phase6.py
./.venv/bin/python scripts/smoke_intelligence_phase6.py
```

Result: generated Phase 6 benchmark and smoke reports.

```bash
./.venv/bin/python -m py_compile gateway/telegram_response_policy.py gateway/run.py scripts/benchmark_intelligence_phase6.py scripts/smoke_intelligence_phase6.py tests/gateway/test_telegram_response_policy.py
```

Result: passed.

```bash
git diff --check
```

Result: passed.

## Proposed VPS Application Plan Only

Do not apply until Dylan approves.

1. Re-check local/VPS lineage:
   - local: `git rev-parse HEAD && git status --short --branch`
   - VPS: `git -C /usr/local/lib/hermes-agent rev-parse HEAD && git -C /usr/local/lib/hermes-agent status --short --branch`
2. Create a rollback snapshot on VPS:
   - git bundle or tar snapshot of `/usr/local/lib/hermes-agent`
   - copy sanitized service environment and config metadata
3. Apply the approved local patch/commit only.
4. Keep all intelligence flags disabled by default:
   - `HERMES_INTELLIGENCE_POLICY`
   - `HERMES_INTELLIGENCE_MEMORY_POLICY`
   - `HERMES_INTELLIGENCE_TOOL_POLICY`
   - `HERMES_INTELLIGENCE_EVIDENCE_COMPACTION`
   - `HERMES_INTELLIGENCE_FAILURE_POLICY`
   - `HERMES_TELEGRAM_CONCISE_RESPONSES`
5. Run VPS tests without real sends/deletes/deployments:
   - `./.venv/bin/python -m pytest tests/agent/test_intelligence_policy.py tests/agent/test_intelligence_policy_phase1_5.py tests/gateway/test_telegram_response_policy.py -q`
   - `./.venv/bin/python scripts/benchmark_intelligence_phase6.py`
   - `./.venv/bin/python scripts/smoke_intelligence_phase6.py`
6. Service restart requirement:
   - Code changes in gateway runtime would require an approved service restart to affect live Telegram.
   - No restart should occur without explicit Dylan approval.
7. Verification checks after any approved restart:
   - `systemctl is-active hermes-dashboard.service hermes-gateway.service`
   - process list for MCP children; verify no new MCP startup regression
   - public health checks only if approved
   - verify no intelligence flags enabled unless explicitly intended

## Rollback Plan

No rollback was needed for Phase 6 because no VPS or production changes were made.

For local rollback before approval:

```bash
git diff -- gateway/run.py
rm -f gateway/telegram_response_policy.py tests/gateway/test_telegram_response_policy.py scripts/benchmark_intelligence_phase6.py scripts/smoke_intelligence_phase6.py
rm -f audit/intelligence_phase6_*.md audit/intelligence_phase6_*.json audit/intelligence_phase6_canonical_context_proposal.md
```

For a future approved VPS rollback:

1. Restore the pre-application git commit or backup snapshot.
2. Unset any newly enabled flags.
3. Restart only approved services.
4. Re-run service health and MCP child-process checks.

## Known Risks And Limitations

- The 20-case benchmark remains fixture/mock-derived; it proves non-regression of policy contracts, not live provider quality.
- The smoke suite uses real AIAgent request construction but mocked provider/connectors.
- VPS config was read in sanitized form only; hidden env/drop-in values may still require a credential-safe review before rollout.
- Local and VPS commits differ; patch application requires lineage review.
- Canonical ClickUp IDs were not found in the read-only pass.
- Memory provider truth differs by environment and needs Dylan review.
- Telegram concise behaviour is implemented behind a new flag, not enabled live.

## Recommendation

- Safe to consider first in a local/VPS staged test: `HERMES_INTELLIGENCE_POLICY=1` observational reporting only.
- Next safest staged flags after review: memory policy, tool policy, evidence compaction.
- Keep `HERMES_INTELLIGENCE_FAILURE_POLICY` off in production until provider/fallback lineage is reviewed on the VPS.
- Keep `HERMES_TELEGRAM_CONCISE_RESPONSES` off until Dylan approves a gateway restart/application plan.
- Cleanup needs Dylan review before any archive/delete/write-back, especially ClickUp IDs, memory provider facts, old worktrees, token-adjacent files, and Supermemory/Mem0 artifacts.
