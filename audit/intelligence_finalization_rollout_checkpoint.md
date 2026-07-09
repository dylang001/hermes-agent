# Hermes Intelligence Finalization Rollout Checkpoint

Generated: 2026-07-09

Scope: finalization, preservation, lineage analysis, and rollout planning only. No new intelligence feature work was added. No production deployment, service restart, credential change, provider/model routing change, MCP config/startup change, memory/Mem0 write, cleanup deletion, force-push, reset, rebase, prune, or destructive command was performed.

## 1. Local Preservation Report

Active checkout: `/Users/dylanangloher/.hermes/hermes-agent`

Local state recorded:

- HEAD: `7d23fad2c25968aa5ebb694e7de36ab33c281002`
- branch: `main`
- upstream relation at final check: `ahead 12, behind 41`
- tracked modified files:
  - `agent/agent_init.py`
  - `agent/conversation_loop.py`
  - `agent/tool_executor.py`
  - `agent/turn_context.py`
  - `agent/turn_finalizer.py`
  - `gateway/run.py`
  - `hermes_cli/main.py`
  - `run_agent.py`
- key untracked runtime/intelligence files:
  - `agent/intelligence_policy.py`
  - `hermes_cli/intelligence_policy.py`
  - `hermes_cli/subcommands/intelligence_policy.py`
- Telegram files:
  - `gateway/telegram_response_policy.py`
  - `tests/gateway/test_telegram_response_policy.py`
- benchmark/smoke scripts:
  - `scripts/benchmark_intelligence_policy_phase1.py`
  - `scripts/collect_intelligence_policy_runtime_samples.py`
  - `scripts/benchmark_intelligence_memory_policy_phase2.py`
  - `scripts/benchmark_intelligence_tool_policy_phase3.py`
  - `scripts/benchmark_intelligence_evidence_compaction_phase4.py`
  - `scripts/benchmark_intelligence_phase6.py`
  - `scripts/smoke_intelligence_phase6.py`
- test files:
  - `tests/agent/test_intelligence_policy.py`
  - `tests/agent/test_intelligence_policy_phase1_5.py`
  - `tests/gateway/test_telegram_response_policy.py`
- audit/report files:
  - `audit/intelligence_policy_phase1_fixture_contract.json`
  - `audit/intelligence_policy_phase1_5_runtime_samples.json`
  - `audit/intelligence_policy_phase1_5_checkpoint.md`
  - `audit/intelligence_memory_policy_phase2_benchmark.json`
  - `audit/intelligence_memory_policy_phase2_checkpoint.md`
  - `audit/intelligence_tool_policy_phase3_benchmark.json`
  - `audit/intelligence_tool_policy_phase3_checkpoint.md`
  - `audit/intelligence_evidence_compaction_phase4_benchmark.json`
  - `audit/intelligence_evidence_compaction_phase4_checkpoint.md`
  - `audit/intelligence_failure_policy_phase5_prerequisite.md`
  - `audit/intelligence_failure_policy_phase5_checkpoint.md`
  - `audit/intelligence_phase6_*`

Preservation artifacts:

- local preservation directory: `audit/preservation-20260709T104644Z/`
- full uncommitted patch: `audit/preservation-20260709T104644Z/local-uncommitted-work.patch`
- untracked file list: `audit/preservation-20260709T104644Z/local-untracked-files.txt`
- untracked archive: `audit/preservation-20260709T104644Z/local-untracked-files.tgz`
- local ahead bundle: `audit/preservation-20260709T104644Z/local-ahead-origin-main.bundle`
- local ahead format patches: `audit/preservation-20260709T104644Z/local-ahead-origin-main-patches/`
- state snapshots:
  - `local-head.txt`
  - `local-status.txt`
  - `local-log-30.txt`
  - `local-diff-stat.txt`
  - `local-tracked-name-status.txt`

No local changes were discarded.

## 2. Git Lineage Report

Lineage analysis used a temporary bare analysis repo under `audit/preservation-20260709T104644Z/lineage-analysis.git` and imported the freshly copied VPS bundle, avoiding stale local `vps/main` refs.

Summary:

| Fact | Value |
| --- | --- |
| local HEAD | `7d23fad2c25968aa5ebb694e7de36ab33c281002` |
| VPS HEAD | `58f22c2f1069d651b75ab90a52901c5cf1f8a192` |
| origin/main HEAD | `73b611ad19720d70308dad6b0fb64648aaadc216` |
| merge-base local/origin | `88a58ff1355eabe468b4dcd4e152a596932632e6` |
| merge-base VPS/origin | `88a58ff1355eabe468b4dcd4e152a596932632e6` |
| merge-base local/VPS | `88a58ff1355eabe468b4dcd4e152a596932632e6` |
| local ahead of origin | 12 commits |
| VPS ahead of origin | 12 commits |
| local commits not in VPS | 6 commits |
| VPS commits not in local | 6 commits |
| origin commits not in local | 41 commits |
| origin commits not in VPS | 41 commits |

Commit lists are stored in `audit/preservation-20260709T104644Z/lineage-commit-lists.txt`.

## 3. Local / VPS / Origin Commit Comparison

The local and VPS lines are not identical, even though both report `ahead 12, behind 41`.

Shared ahead commits by exact hash:

- `2d5f55791` dashboard public URL host validation
- `5c7cedc4a` dashboard auth gate for public URL
- `2199ef127` public websocket auth behind proxy
- `550c32507` websocket host guard public URL helper
- `250d69088` websocket origin guard public URL helper
- `d2f72189c` loopback websocket auth-mode test

Equivalent-but-different-hash commits:

| Local | VPS | Result |
| --- | --- | --- |
| `1057e471a` restore OpenCode Go quota key fallback | `d448c1f07` restore OpenCode Go quota key fallback | source patch-id matches; local additionally contains `tests/run_agent/test_provider_fallback.py` coverage |
| `c07332202` honor MCP disable during startup | `f211c4002` honor MCP disable during startup | stable patch-id matches |
| `a9c5fdb6a` skip noninteractive OAuth startup without tokens | `94ada9cb7` skip noninteractive OAuth startup without tokens | stable patch-id matches |

Merge commits differ by hash because local and VPS merged origin independently.

Conclusion: no unique VPS production source fix was found that is missing from local source content. The only content difference identified in equivalent commits is extra local test coverage for the quota-fallback fix. This still needs review before rollout because commit hashes and merge history differ.

## 4. Ahead-Commit Preservation Confirmation

Local ahead commits are preserved in:

- `audit/preservation-20260709T104644Z/local-ahead-origin-main.bundle`
- `audit/preservation-20260709T104644Z/local-ahead-origin-main-patches/`

VPS ahead commits are preserved in:

- VPS path: `/root/hermes-preservation/20260709T104644Z/vps-ahead-origin-main.bundle`
- VPS path: `/root/hermes-preservation/20260709T104644Z/vps-ahead-origin-main-patches/`
- local copy: `audit/preservation-20260709T104644Z/vps-ahead-origin-main.bundle`

VPS preservation also recorded:

- `/root/hermes-preservation/20260709T104644Z/vps-head.txt`
- `/root/hermes-preservation/20260709T104644Z/vps-status.txt`
- `/root/hermes-preservation/20260709T104644Z/vps-log-30.txt`
- `/root/hermes-preservation/20260709T104644Z/vps-diff-stat.txt`
- `/root/hermes-preservation/20260709T104644Z/vps-name-status.txt`

No VPS branch was created, and the running checkout branch was not changed.

## 5. Recommended Canonical Integration Branch / Commit

Recommended target: a new local integration branch from local HEAD:

- proposed branch: `codex/phase6-intelligence-integration-20260709`
- proposed base commit: `7d23fad2c25968aa5ebb694e7de36ab33c281002`

Rationale:

- local HEAD contains the same production-fix source content as VPS for the audited unique fixes.
- local HEAD additionally contains test coverage for the quota-fallback fix.
- local uncommitted Phase 1.5-6 work was developed and validated against this line.
- using local HEAD avoids replaying a large uncommitted patch onto a separately merged VPS commit line until review confirms lineage.

Included local commits:

- all 12 local ahead commits listed in `lineage-commit-lists.txt`
- Phase 1.5-6 local uncommitted patch from `local-uncommitted-work.patch`

Included VPS commits:

- preserve exact VPS ahead commits in bundle/patchset.
- do not cherry-pick exact VPS hashes initially because the three unique source fixes are content-equivalent to local commits and the merge commits differ only by lineage.

Conflict risk:

- low for the Phase 1.5-6 patch on local HEAD because it is already applied and tests pass.
- medium for applying to VPS because VPS commit hash differs and config/runtime differs.
- specific review point: confirm `agent/chat_completion_helpers.py`, `agent/conversation_loop.py`, and `agent/error_classifier.py` match the intended quota fallback source behaviour before deployment.

Files affected by Phase 1.5-6 and finalization:

- `agent/agent_init.py`
- `agent/conversation_loop.py`
- `agent/tool_executor.py`
- `agent/turn_context.py`
- `agent/turn_finalizer.py`
- `agent/intelligence_policy.py`
- `gateway/run.py`
- `gateway/telegram_response_policy.py`
- `hermes_cli/main.py`
- `hermes_cli/intelligence_policy.py`
- `hermes_cli/subcommands/intelligence_policy.py`
- `run_agent.py`
- scripts under `scripts/benchmark_intelligence_*` and `scripts/smoke_intelligence_phase6.py`
- tests under `tests/agent/` and `tests/gateway/`
- audit reports under `audit/`

Do not implement this integration branch on VPS until Dylan reviews the plan.

## 6. Clean Local Branch / Commit Or Patch Proposal

Current safe package: patch-based review package.

Primary review patch:

- `audit/preservation-20260709T104644Z/local-uncommitted-work.patch`

Recommended commit strategy after Dylan approves:

1. `intelligence: add observational policy reports and classifiers`
2. `intelligence: add disabled memory policy`
3. `intelligence: add disabled tool exposure policy`
4. `intelligence: add disabled evidence compaction`
5. `intelligence: add disabled failure policy`
6. `gateway: add disabled Telegram concise response policy`
7. `audit: add benchmarks, smoke tests, and rollout reports`

If review speed matters more than bisectability, one squashed commit is acceptable because all behaviours are disabled by default and the policy layers are tightly coupled in the test suite.

Do not include `audit/preservation-20260709T104644Z/lineage-analysis.git` in a review commit. Keep preservation bundles/patchsets as local audit artifacts unless Dylan explicitly wants them committed.

## 7. Test Results

Focused pytest suite:

```bash
./.venv/bin/python -m pytest tests/gateway/test_telegram_response_policy.py tests/agent/test_intelligence_policy.py tests/agent/test_intelligence_policy_phase1_5.py -q
```

Result: `40 passed in 9.23s`

Py compile sweep:

```bash
./.venv/bin/python -m py_compile agent/intelligence_policy.py agent/agent_init.py agent/conversation_loop.py agent/tool_executor.py agent/turn_context.py agent/turn_finalizer.py gateway/telegram_response_policy.py gateway/run.py hermes_cli/intelligence_policy.py hermes_cli/subcommands/intelligence_policy.py hermes_cli/main.py run_agent.py scripts/benchmark_intelligence_policy_phase1.py scripts/collect_intelligence_policy_runtime_samples.py scripts/benchmark_intelligence_memory_policy_phase2.py scripts/benchmark_intelligence_tool_policy_phase3.py scripts/benchmark_intelligence_evidence_compaction_phase4.py scripts/benchmark_intelligence_phase6.py scripts/smoke_intelligence_phase6.py tests/agent/test_intelligence_policy.py tests/agent/test_intelligence_policy_phase1_5.py tests/gateway/test_telegram_response_policy.py
```

Result: passed.

Phase 6 benchmark:

```bash
./.venv/bin/python scripts/benchmark_intelligence_phase6.py
```

Result:

- cases: 20
- quality regressions: 0
- approval-gate regressions: 0
- provider/model routing changes: 0
- MCP startup regressions: 0
- tool availability regressions: 0
- request-size delta: `-891,421` bytes
- token-estimate delta: `-222,850`
- evidence savings: `66,098` bytes

Phase 6 smoke:

```bash
./.venv/bin/python scripts/smoke_intelligence_phase6.py
```

Result:

- cases: 7
- side effects: none
- quality regressions: 0
- approval-required cases: 1
- simulated failure cases: 2

Diff hygiene:

```bash
git diff --check
```

Result: passed.

## 8. VPS Application Plan

Do not execute until Dylan approves.

Default recommendation:

1. Apply code with all flags disabled.
2. Run tests.
3. Optionally enable only `HERMES_INTELLIGENCE_POLICY=1` for staged observability.
4. Do not enable memory/tool/evidence/failure/Telegram flags until later approval.
5. Do not restart gateway for Telegram concise behaviour until Dylan approves.

Exact patch/branch to apply after approval:

- branch/patch source: `codex/phase6-intelligence-integration-20260709` from local HEAD `7d23fad2c25968aa5ebb694e7de36ab33c281002`, or the patch `audit/preservation-20260709T104644Z/local-uncommitted-work.patch`

Backup commands to run first on VPS:

```bash
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /root/hermes-rollout-backups/$STAMP
git -C /usr/local/lib/hermes-agent rev-parse HEAD > /root/hermes-rollout-backups/$STAMP/head.txt
git -C /usr/local/lib/hermes-agent status --short --branch > /root/hermes-rollout-backups/$STAMP/status.txt
git -C /usr/local/lib/hermes-agent bundle create /root/hermes-rollout-backups/$STAMP/pre-rollout.bundle HEAD
tar -C /usr/local/lib -czf /root/hermes-rollout-backups/$STAMP/hermes-agent-worktree.tgz hermes-agent
```

Expected files changed on VPS:

- same Phase 1.5-6 file list in section 5.
- no credential/config/env files.
- no MCP config files.
- no service unit files.

VPS tests to run after applying, before any restart:

```bash
./.venv/bin/python -m pytest tests/agent/test_intelligence_policy.py tests/agent/test_intelligence_policy_phase1_5.py tests/gateway/test_telegram_response_policy.py -q
./.venv/bin/python scripts/benchmark_intelligence_phase6.py
./.venv/bin/python scripts/smoke_intelligence_phase6.py
./.venv/bin/python -m py_compile agent/intelligence_policy.py gateway/telegram_response_policy.py gateway/run.py scripts/benchmark_intelligence_phase6.py scripts/smoke_intelligence_phase6.py
git diff --check
```

Service restart:

- a gateway restart is required only for live Telegram concise mode or gateway runtime code changes to take effect.
- no restart should occur without explicit approval.

Flags that remain disabled:

- `HERMES_INTELLIGENCE_POLICY`
- `HERMES_INTELLIGENCE_MEMORY_POLICY`
- `HERMES_INTELLIGENCE_TOOL_POLICY`
- `HERMES_INTELLIGENCE_EVIDENCE_COMPACTION`
- `HERMES_INTELLIGENCE_FAILURE_POLICY`
- `HERMES_TELEGRAM_CONCISE_RESPONSES`

First staged flag, if any:

- `HERMES_INTELLIGENCE_POLICY=1` only, for observability.

Post-application verification:

```bash
git -C /usr/local/lib/hermes-agent rev-parse HEAD
git -C /usr/local/lib/hermes-agent status --short --branch
systemctl is-active hermes-dashboard.service hermes-gateway.service
ps -eo pid,ppid,cmd --sort=pid | grep -E 'mcp_stdio_watchdog|exa-mcp|server-filesystem|zohomcp|obsidian' | grep -v grep || true
systemctl show hermes-gateway.service hermes-dashboard.service -p Environment --no-pager | tr ' ' '\n' | grep -E '^(HERMES_INTELLIGENCE|HERMES_TELEGRAM_CONCISE)' || true
```

## 9. VPS Cleanup Plan

Do not execute until Dylan approves item by item.

| Classification | Path | Reason | Risk | May contain unmerged code | May contain credentials/tokens | Proposed archive/backup | Later command, not executed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| keep | `/usr/local/lib/hermes-agent` | active production checkout | production runtime | yes | config adjacent | n/a | n/a |
| keep | `/root/.hermes/backups` | rollback evidence | losing rollback history | possible | possible | n/a | n/a |
| keep | `/root/.hermes/cleanup-backups` | rollback evidence | losing cleanup rollback | possible | possible | n/a | n/a |
| keep | `/root/.hermes/migration-backups` | migration evidence | losing migration rollback | possible | possible | n/a | n/a |
| keep | `/root/.hermes/update-backups` | update evidence | losing update rollback | possible | possible | n/a | n/a |
| archive after approval | `/root/hermes-update-validation/20260703T065220Z/hermes-agent` | old validation checkout | may contain useful test evidence | yes | unlikely | `/root/hermes-archives/$STAMP/` | `mkdir -p /root/hermes-archives/$STAMP && tar -C /root/hermes-update-validation/20260703T065220Z -czf /root/hermes-archives/$STAMP/hermes-agent-20260703T065220Z.tgz hermes-agent` |
| archive after approval | `/root/hermes-update-validation/20260703T070656Z/hermes-agent` | old validation checkout | may contain useful test evidence | yes | unlikely | `/root/hermes-archives/$STAMP/` | `mkdir -p /root/hermes-archives/$STAMP && tar -C /root/hermes-update-validation/20260703T070656Z -czf /root/hermes-archives/$STAMP/hermes-agent-20260703T070656Z.tgz hermes-agent` |
| archive after approval | `/root/.hermes/config.yaml.bak-zoho-oauth-20260701T082230Z` | old config backup | could contain config evidence | no | possible | `/root/hermes-archives/$STAMP/config/` | `mkdir -p /root/hermes-archives/$STAMP/config && cp -p /root/.hermes/config.yaml.bak-zoho-oauth-20260701T082230Z /root/hermes-archives/$STAMP/config/` |
| archive after approval | `/root/.hermes/config.yaml.pre-orchidea-zoho-enable-20260703T160103Z` | old config backup | could contain config evidence | no | possible | `/root/hermes-archives/$STAMP/config/` | `mkdir -p /root/hermes-archives/$STAMP/config && cp -p /root/.hermes/config.yaml.pre-orchidea-zoho-enable-20260703T160103Z /root/hermes-archives/$STAMP/config/` |
| delete candidate after approval | `/root/.hermes/desktop-attachments/skill-playwright-audit*.json` | old audit attachments | low, but may contain useful screenshots/paths | no | unlikely | archive first | `mkdir -p /root/hermes-archives/$STAMP/desktop-attachments && cp -p /root/.hermes/desktop-attachments/skill-playwright-audit*.json /root/hermes-archives/$STAMP/desktop-attachments/ && rm /root/.hermes/desktop-attachments/skill-playwright-audit*.json` |
| needs Dylan review | `/root/.hermes/worktrees/*` | many old worktrees | may contain unmerged fixes | yes | possible | per-worktree tar before removal | `git -C <worktree> status --short --branch && tar -C <parent> -czf /root/hermes-archives/$STAMP/<name>.tgz <name>` |
| needs Dylan review | `/root/.hermes/scripts/supermemory-flush.py` | possibly stale helper | stale command risk | no | possible | copy to scripts archive | `mkdir -p /root/hermes-archives/$STAMP/scripts && cp -p /root/.hermes/scripts/supermemory-flush.py /root/hermes-archives/$STAMP/scripts/` |
| needs Dylan review | `/root/.hermes/bin/verify-memory-overhaul.py` | possibly stale helper | stale command risk | no | possible | copy to scripts archive | `mkdir -p /root/hermes-archives/$STAMP/bin && cp -p /root/.hermes/bin/verify-memory-overhaul.py /root/hermes-archives/$STAMP/bin/` |
| unsafe to touch | `/root/.hermes/mcp-tokens/orchidea-zoho-*` | token-adjacent files | credential loss/exposure | no | yes | none without credential plan | n/a |
| needs Dylan review | `/root/.hermes/supermemory.json*` | old Supermemory artifacts | memory/provider confusion | no | possible | copy only after credential review | n/a |

## 10. Memory / Source Cleanup Plan

Do not write memory, Mem0, repo docs, or canonical context until Dylan approves.

| Category | Fact / issue | Proposed action |
| --- | --- | --- |
| active facts to keep | active local implementation path is `/Users/dylanangloher/.hermes/hermes-agent` | keep and canonicalize |
| active facts to keep | active VPS production path is `/usr/local/lib/hermes-agent` | keep and canonicalize |
| active facts to keep | public/Desktop URL is `https://hermes.meetlyra.live` | keep and canonicalize |
| stale facts to archive | `/Users/dylanangloher/Documents/Hermes` as implementation checkout | archive/mark historical placeholder |
| stale facts to archive | direct IP Desktop URL `http://212.86.105.178:9119` | archive/mark historical incident value |
| facts needing Dylan review | canonical ClickUp workspace/list IDs are missing | verify via safe source before canonicalizing |
| facts needing Dylan review | local memory provider empty/unset versus VPS `mem0` | decide environment-specific truth |
| facts needing Dylan review | local fallback model chain differs from VPS MiniMax M3 setup | preserve VPS provider/model until reviewed |
| facts needing Dylan review | active MCP children Exa/Obsidian differ from configured Zoho endpoints | canonicalize active-vs-configured wording |
| facts needing Dylan review | Zoho configured/tokened but not active | mark configured-only until live CLI/MCP health says active |
| duplicates to consolidate | multiple path/service/provider memories across rollout summaries | consolidate into canonical context after approval |
| dangerous stale commands/tools | old `/root/.hermes/worktrees/*` paths | mark as historical, not current runtime |
| dangerous stale commands/tools | `supermemory-flush.py`, `verify-memory-overhaul.py` | mark deprecated only after reference search |
| missing canonical facts | ClickUp workspace/list IDs | needs Dylan review |
| missing canonical facts | cleanup retention policy for old worktrees/backups | needs Dylan review |

Proposed canonical source precedence remains:

1. live config, environment, and filesystem state
2. canonical context file
3. current repo docs
4. recent audited decision logs
5. external memory or Mem0
6. older local memory

Canonical context proposal remains at:

- `audit/intelligence_phase6_canonical_context_proposal.md`

Do not install it as active context until approved.

## 11. Telegram Readiness Report

Policy file:

- `gateway/telegram_response_policy.py`

Gateway hook:

- `gateway/run.py`

Flag:

- `HERMES_TELEGRAM_CONCISE_RESPONSES=1`

Confirmed behaviour:

- disabled by default
- Telegram-only
- Desktop/CLI/local unaffected
- fail-open to old behaviour if policy shaping fails
- no chain-of-thought or scratchpad shaping
- no raw logs unless user asks for details/full report
- details/full report preserved when requested

Before/after examples:

| Scenario | Before | After with flag enabled |
| --- | --- | --- |
| direct answer | `JSON is a text format for structured data.` | unchanged |
| long task | dozens of detail lines | `Done - Validation completed. Ask for details for the full report.` |
| approval required | approval line plus long command/details | `Need approval - Approval required before running: ...` |
| log-heavy task | raw traceback/log dump | `Found issue - I summarized the log evidence instead of sending raw logs. Ask for details for the full report.` |
| discrepancy | long memory/source discrepancy narration | `Found a stale memory/source conflict. I am verifying against live config before touching anything.` |
| details requested | full report | full report preserved |

Gateway restart:

- required for the live VPS gateway to use this code/flag.
- do not restart without approval.

## 12. Rollback Plan

Local rollback before commit:

```bash
git apply -R audit/preservation-20260709T104644Z/local-uncommitted-work.patch
```

Only use that after confirming no newer edits exist. Safer manual rollback is to keep the patch and remove specific untracked files by list from `local-untracked-files.txt`.

VPS rollback after a future approved application:

```bash
git -C /usr/local/lib/hermes-agent status --short --branch
git -C /usr/local/lib/hermes-agent bundle verify /root/hermes-rollout-backups/$STAMP/pre-rollout.bundle
# Restore from approved backup snapshot or reset to the exact recorded pre-rollout commit only after Dylan approves.
```

Flag rollback:

```bash
unset HERMES_INTELLIGENCE_POLICY
unset HERMES_INTELLIGENCE_MEMORY_POLICY
unset HERMES_INTELLIGENCE_TOOL_POLICY
unset HERMES_INTELLIGENCE_EVIDENCE_COMPACTION
unset HERMES_INTELLIGENCE_FAILURE_POLICY
unset HERMES_TELEGRAM_CONCISE_RESPONSES
```

Do not restart services for rollback unless Dylan approves the restart.

## 13. Approval Checklist For Dylan

Approve or reject separately:

1. Preserve local/VPS ahead commits as named branches in addition to the bundles already created.
2. Create the local integration branch `codex/phase6-intelligence-integration-20260709`.
3. Commit the Phase 1.5-6 work using the proposed grouped commit plan, or squash it.
4. Apply code to VPS with all flags disabled.
5. Enable `HERMES_INTELLIGENCE_POLICY=1` only in staged VPS observability.
6. Enable Telegram concise mode later with `HERMES_TELEGRAM_CONCISE_RESPONSES=1` after gateway restart approval.
7. Archive specific stale VPS worktrees.
8. Archive/delete specific old artifacts.
9. Install `CANONICAL_CONTEXT.md`.
10. Update/archive specific stale memory facts.
11. Canonicalize ClickUp IDs once verified.

## 14. Definition Of Done Status

- no ahead commits lost: preserved via local and VPS bundles/patchsets
- local and VPS lineage understood: yes
- clear path to matching code line: proposed local HEAD integration branch, pending review
- Phase 1.5-6 packaged: patch/bundles/audit artifacts created
- default behaviour unchanged: flags remain disabled by default
- tests pass: yes
- production changes made: no
- cleanup planned but not executed: yes
- memory updates planned but not executed: yes
- Dylan approval list provided: yes
