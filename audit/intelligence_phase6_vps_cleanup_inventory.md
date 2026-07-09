# Phase 6 Read-Only VPS Cleanup Inventory

Generated: 2026-07-09

Scope: inventory only. Nothing was deleted, archived, moved, edited, restarted, or reconfigured.

| Item | Evidence | Classification | Proposed action |
| --- | --- | --- | --- |
| `/usr/local/lib/hermes-agent` | active production checkout and running service cwd | keep | Do not touch except through an approved rollout plan. |
| `/root/.hermes/worktrees/audit-containment-rc` | stale-looking worktree under `/root/.hermes/worktrees` | needs Dylan review | Verify no active process or branch depends on it, then archive/delete only after approval. |
| `/root/.hermes/worktrees/audit-containment-rc-v2` | stale-looking worktree | needs Dylan review | Same as above. |
| `/root/.hermes/worktrees/audit-convergence` | stale-looking worktree | needs Dylan review | Same as above. |
| `/root/.hermes/worktrees/cycle-2026-07-01-clickup-gated-tools` | old ClickUp-related worktree | needs Dylan review | Candidate for archive after source-of-truth review. |
| `/root/.hermes/worktrees/cycle-2026-07-01-spacemail-registry-and-cap` | old worktree | needs Dylan review | Candidate for archive after confirming no active schedule/process references it. |
| `/root/.hermes/worktrees/hermes-audit-superpowers-loop` | old audit worktree | needs Dylan review | Candidate for archive. |
| `/root/.hermes/worktrees/phase-0b-readiness` | old readiness worktree | needs Dylan review | Candidate for archive. |
| `/root/.hermes/worktrees/phase2-r5` | old phase worktree | needs Dylan review | Candidate for archive. |
| `/root/.hermes/worktrees/recovery-baseline-2a58fee1` | recovery baseline worktree | archive | Keep until the current rollout line is approved; then archive with note instead of deleting first. |
| `/root/.hermes/worktrees/supermemory-fail-closed-remediation` | old memory-provider remediation worktree | needs Dylan review | Review against current `memory.provider: mem0` before archiving. |
| `/root/.hermes/worktrees/synthetic-latency-instrumentation-20260624` | old instrumentation worktree | needs Dylan review | Candidate for archive after confirming no live diagnostics reference it. |
| `/root/.hermes/worktrees/zoho-mcp-oauth-runtime-validation` | old Zoho validation worktree | needs Dylan review | Keep until Zoho source-of-truth is settled; do not delete tokens/config. |
| `/root/hermes-update-validation/20260703T065220Z/hermes-agent` | old validation checkout | archive | Archive after confirming no active process references it. |
| `/root/hermes-update-validation/20260703T070656Z/hermes-agent` | old validation checkout | archive | Archive after confirming no active process references it. |
| `/root/agenticmail-research` | unrelated/old checkout | needs Dylan review | Determine ownership before any cleanup. |
| `/root/SkillClaw` | unrelated/old checkout | needs Dylan review | Determine ownership before any cleanup. |
| `/root/.hermes/backups` | backup root | keep | Preserve unless Dylan approves retention policy. |
| `/root/.hermes/cleanup-backups` | cleanup backup root | keep | Preserve unless Dylan approves retention policy. |
| `/root/.hermes/migration-backups` | migration backup root | keep | Preserve. |
| `/root/.hermes/update-backups` | update backup root | keep | Preserve. |
| `/root/.hermes/config.yaml.bak-zoho-oauth-20260701T082230Z` | old config backup | archive | Keep as audit evidence; do not delete yet. |
| `/root/.hermes/config.yaml.pre-orchidea-zoho-enable-20260703T160103Z` | old config backup | archive | Keep as audit evidence. |
| `/root/.hermes/mcp-tokens/orchidea-zoho-*` | token metadata/files present | unsafe to touch | Do not inspect deeply, print, move, or delete without an explicit credential-safe plan. |
| `/root/.hermes/scripts/supermemory-flush.py` | old helper script | needs Dylan review | Validate whether it is still referenced before marking deprecated. |
| `/root/.hermes/bin/verify-memory-overhaul.py` | old helper script found in prior runtime-file listing | needs Dylan review | Validate current references before cleanup. |
| `/root/.hermes/supermemory.json` and pre-containment backup | old Supermemory profile/config artifacts | needs Dylan review | Review against current `memory.provider: mem0`; do not delete. |
| `/root/.hermes/cache/web/www.zoho.com-*.md` | old Zoho web cache artifacts | archive | Low-risk archive candidate after confirming no audit needs them. |
| `/root/.hermes/desktop-attachments/skill-playwright-audit*.json` | old audit attachments | delete candidate | Delete only after Dylan approves and any useful evidence is retained. |
| `/root/.hermes/skills/.curator_backups` | skill backup directory | keep | Preserve. |
| `/root/.hermes/skills/saraev-direct-proposal-outreach/SKILL.md.backup-*` | skill backup | archive | Keep unless skill owner approves cleanup. |

## Cleanup Risks

- Several items are likely useful as rollback/audit evidence even if stale.
- Token/config paths must not be archived or deleted without a credential-handling plan.
- Old worktrees may contain unmerged local fixes; archive only after branch/commit review.
