# Phase 6 Memory And Source-Of-Truth Discrepancy Report

Generated: 2026-07-09

Scope: read-only discrepancy audit. No memory, Mem0, config, VPS state, worktrees, decision logs, or notes were modified.

Source precedence proposed for operational facts:

1. live config, environment, and filesystem state
2. canonical context file
3. current repo docs
4. recent audited decision logs
5. external memory or Mem0
6. older local memory

## Discrepancies

| Conflicting fact | Source A | Source B | Timestamp/confidence signal | Likely canonical value | Evidence | Risk if unresolved | Proposed action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Active local Hermes path | Current user request and local git evidence: `/Users/dylanangloher/.hermes/hermes-agent` | Older/visible cwd references: `/Users/dylanangloher/Documents/Hermes` | Current turn verified local git in `.hermes/hermes-agent`; memory notes repeatedly warn `Documents/Hermes` may be sparse | `/Users/dylanangloher/.hermes/hermes-agent` for implementation work; `/Users/dylanangloher/Documents/Hermes` only as visible/placeholder path unless re-verified | `git rev-parse HEAD` in `.hermes/hermes-agent`; memory entries noting sparse placeholder | Hermes may patch or validate the wrong tree | update older memory/context to mark `.hermes/hermes-agent` canonical |
| Active VPS Hermes path | Live VPS process and git: `/usr/local/lib/hermes-agent` | Some older operational notes emphasize `/root/.hermes/...` worktrees/skills/checkouts | Current VPS process list and git status are live evidence | `/usr/local/lib/hermes-agent` for production checkout; `/root/.hermes/...` for state, skills, worktrees, backups | service command lines and `git -C /usr/local/lib/hermes-agent` | Confusing production checkout with state/skill directories can lead to unsafe patches | keep canonical value, archive stale path assumptions |
| Desktop backend URL | Current Desktop connection: `https://hermes.meetlyra.live` | Older memory mentions `http://212.86.105.178:9119` during an incident | Current local file verified this turn; older note was incident-specific | `https://hermes.meetlyra.live` for Desktop remote mode | sanitized `connection.json` read | Wrong target causes irrelevant local restarts or direct-port testing | update/mark older IP URL as historical |
| Local vs VPS commit | local HEAD `7d23fad2c25968aa5ebb694e7de36ab33c281002` | VPS HEAD `58f22c2f1069d651b75ab90a52901c5cf1f8a192` | Current git checks on both systems | No canonical single commit yet; deployment plan must choose approved patch/commit | read-only local and SSH git probes | Applying a patch to the wrong lineage can fail or overwrite live fixes | needs Dylan review before any VPS application |
| Upstream/ahead-behind state | local reports `behind 41, ahead 12` | VPS reports `behind 41, ahead 12` but at different HEAD | Current git checks | Treat both as divergent from origin and each other until lineage is inspected | `git rev-list --left-right --count @{upstream}...HEAD` on both | False parity claim | needs Dylan review before merge/deploy |
| Provider/model assumptions | Local config: primary `opencode-go`, fallbacks `glm-5.2`, `deepseek-v4-pro`, `deepseek-v4-flash`, `kimi-k2.7-code`, `qwen3.7-max` | VPS config/processes: `opencode-go`, fallback `minimax-m3`, slash workers `--model minimax-m3`; memory prefers preserving OpenCode Go MiniMax M3 | Current sanitized configs and process list | VPS canonical runtime appears OpenCode Go / MiniMax M3; local staged config differs and must not be projected onto VPS | sanitized config probes | Accidental provider/model routing change | keep VPS provider/model unchanged; needs Dylan review for local-vs-VPS config difference |
| Memory provider | Local config: external memory provider empty/unset | VPS config: `memory.provider: mem0`; older memory says built-in-only needs empty provider and Supermemory activation was blocked by missing key | Current sanitized config plus older memory | No global canonical value yet; environment-specific canonical values should be recorded | local YAML parse; VPS sanitized config | Hermes may receive conflicting recall/provider assumptions or report stale memory-provider facts | needs Dylan review; do not write memory |
| MCP runtime state | Live VPS active children: Exa and Obsidian filesystem | VPS config contains Zoho MCP URLs and token files; older memory says Zoho stayed off until authorized | Current process list has only Exa/Obsidian; config contains more potential servers | Active runtime: Exa + Obsidian only; configured-but-not-active: Zoho and other MCP endpoints | process list and sanitized config lines | Hermes may claim Zoho is active when it is only configured/tokened | update canonical context to distinguish active vs configured |
| Zoho endpoint/config state | VPS config includes several `zohomcp.com` URLs and `${ZOHO_MCP_*}` placeholders | Older memory includes warnings about `.in` vs `.com` endpoint confusion and OAuth safety | Current config read plus older memory | Do not initiate Zoho OAuth; treat `.com` endpoints as configured but not active until live CLI/MCP health verifies | sanitized config lines; memory warnings | Unsafe OAuth prompts or wrong-region auth | keep as needs Dylan review / verify before use |
| ClickUp list/workspace IDs | Addendum and old worktree name indicate ClickUp operational context exists | No concrete ClickUp list ID was found in the current quick local memory/repo grep | Current audit found the class of discrepancy but not a value pair | Missing canonical ClickUp list/workspace IDs | `cycle-2026-07-01-clickup-gated-tools` worktree; addendum requirement | Hermes may waste turns verifying basic ClickUp facts or use stale IDs if hidden in external memory | needs Dylan review and connector-safe audit before canonicalizing |
| Old worktrees as current state | Multiple `/root/.hermes/worktrees/*` names imply past active efforts | Current production process uses `/usr/local/lib/hermes-agent` | Current process/git evidence | Worktrees are historical unless a current branch/process proves otherwise | read-only VPS inventory | Old experiments may be surfaced as active guidance | archive candidates after approval |
| Old helper commands | `/root/.hermes/scripts/supermemory-flush.py`, `/root/.hermes/bin/verify-memory-overhaul.py` | Current config uses `mem0`; no live process evidence for these helpers | Current file inventory only; not command-validation proof | Unknown; not canonical until referenced by current docs/config | read-only inventory | Hermes may attempt stale helper commands | needs Dylan review; mark deprecated only after reference search |
| Service names | Current services: `hermes-dashboard.service`, `hermes-gateway.service` | Older notes include incident-specific restrictions and gateway immutability warnings | Current systemd list confirms names | `hermes-dashboard.service`, `hermes-gateway.service` | read-only `systemctl list-units` | Wrong service action or forbidden restart | keep canonical names and retain no-restart constraint |
| Deployment URL and ports | Public URL `https://hermes.meetlyra.live`; dashboard behind `9119`, gateway health on `8642` in memory | Direct IP URL and local ports appear in older incidents | Current Desktop remote URL plus recent memory; not live curl-tested in Phase 6 | `https://hermes.meetlyra.live` for public/Desktop; `9119` dashboard internal; `8642` gateway internal | sanitized connection config and memory notes | Wrong endpoint checks and noisy user-facing explanations | update canonical context |

## Missing Canonical Facts

- Canonical ClickUp workspace/list IDs were not found in this read-only pass.
- Canonical active project names are scattered across current requests, worktree names, and memory summaries.
- Environment-specific memory provider truth needs explicit split: local development vs VPS production.
- Configured MCP servers versus active MCP children need a stable canonical distinction.
- Cleanup retention rules for old VPS worktrees/backups are not yet documented.

## Proposed Cleanup Rules

- Keep active runtime facts that are proven by live config, systemd, process list, or filesystem state.
- Update memory entries that present historical URLs, paths, providers, or MCP state as current.
- Archive old worktree-derived facts once Dylan approves.
- Treat ClickUp IDs as unknown until live config/connector-safe evidence confirms them.
- Do not delete or write back memory during this first pass.
