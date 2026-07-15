# Hermes Week-1 Acceptance Report

**Date:** 2026-07-15 (UTC)  
**Hosts:** Mac local worktree `~/.hermes/hermes-agent` · VPS `hermes-production` (`hermes90210`, `HERMES_HOME=/opt/hermes/home`)  
**Operator posture:** conservative — no SpaceMail send, LinkedIn automation, or social publishing.

---

## HARD GATE — Task OS cron discrepancy (resolved)

### Discrepancy
- Prior live reports referred to poller job id `4dcf0a86d0e8`.
- Latest Phase 7 audit claimed the same job was **paused** (`enabled: false`).
- Empty `~/.hermes/cron` on the VPS login home can mislead CLI runs without `HERMES_HOME=/opt/hermes/home`.

### Authoritative poller (single)
| Field | Value |
|--------|--------|
| **Job id** | `4dcf0a86d0e8` |
| **Name** | `clickup-task-os-poll` |
| **Host** | `hermes90210` (`hermes-production`) |
| **Store** | `/opt/hermes/home/cron/jobs.json` (gateway `HERMES_HOME`) |
| **Script** | `/opt/hermes/home/scripts/clickup-task-os-poll.sh` → `hermes -p task-os task-os poll` |
| **Schedule** | every 5m (`interval`) |
| **Duplicates** | **None.** `/opt/hermes/home/profiles/task-os/cron/jobs.json` is empty (`jobs: []`). No second poller created. |

### Before (2026-07-15T20:32:24Z pause)
- `enabled: false`, `state: paused`
- `last_run_at: 2026-07-15T20:30:39Z`, `last_status: ok`
- Gateway ticker healthy; `hermes cron status` showed **0 active jobs** while paused.

### After (deliberate resume)
- Command: `HERMES_HOME=/opt/hermes/home hermes cron resume 4dcf0a86d0e8`
- `enabled: true`, `state: scheduled` / list shows **[active]**
- Subsequent ticker runs observed (`last_run_at` advanced to `2026-07-15T21:26:24Z`, `last_status: ok`)
- **Decision:** resume deliberately so Week-1 Ready→Review smoke and Ops queue theater work. Pause again only with an explicit ops reason.

---

## Week-1 checklist (items 1–7)

| # | Item | Status | Evidence |
|---|------|--------|----------|
| 1 | Apply `daily-ops` to default VPS chat | **PASS** | `agent.capability_profile: daily-ops`; `tools.cli` / `tools.telegram` enabled/disabled from YAML; kept `plugins.enabled: [clickup-bridge]`; removed `browser/browser_use` + `web/firecrawl`; `delegation.inherit_mcp_toolsets: false`; Mem0 unchanged (`memory.provider: mem0`); gateway restarted |
| 2 | Exactly one Task OS poller + Ready→Review smoke | **PASS** | Single job `4dcf0a86d0e8`; created task `86carf2p2` (next + `hermes-ready`); `hermes -p task-os task-os poll --deterministic-worker` → claimed → status `waiting` + tag `hermes-review` |
| 3 | Harden Mac→VPS Obsidian sync; Drafts/Hermes; unload reverse tunnel | **PASS** (with notes) | Created `Growth OS/Drafts/Hermes`; push script space-quoting fixed; manual sync verified on VPS; LaunchAgent retargeted to `sync-obsidian-to-hermes-remote.sh` (running); reverse tunnel plist moved to `~/Library/LaunchAgents/disabled/`; no `27124` tunnel process |
| 4 | Disable invalid Zoho MCP | **PASS** | `orchidea-zoho-leads.enabled: false` (URL was `${ZOHO_MCP_LEAD_MANAGEMENT_URL}` unset) |
| 5 | Wire `skill_discovery` + `capability_gap` (no new global tools) | **PASS** | Task OS poller failure comments + waiting-worker enrichment; `/help` tip in `gateway_help_lines` + CLI `show_help`; tests `test_clickup_task_os_discovery_wire.py` green; files overlay-copied to VPS app |
| 6 | Desktop stale-path / latency / tool-selection tests | **PASS** | See commands + results below |
| 7 | Commit / deploy exact SHA | **PARTIAL** | Code left **commit-ready** (not committed: large untracked audit tree + no explicit commit ask). VPS git tip remains `d1908cfcf2a6779c58d003ad81469364f6cac4bd` with **file overlay** for Week-1 wire + live config changes. Full tip SHA deploy of local `cec86055…` **not** performed. |

---

## Before / after footprint & latency

| Measure | Before | After |
|---------|--------|-------|
| Default VPS `get_tool_definitions()` (wide / no platform filter) | **39 tools / 47.84 KB / ~791 ms** (includes ClickUp + vision/video/etc.) | N/A (platform toolsets now set) |
| Telegram toolsets after `daily-ops` | (unset → wide) | **15 tools / 30.6 KB / ~26 ms** (`file`,`terminal`,`memory`,`skills`,`session_search`,`web`,`clarify`,`todo`) |
| Profile measure `daily-ops` toolsets | — | **16 tools / 35.91 KB** on VPS (w/ delegation); local measure ~14–16 / ~34 KB |
| Task OS list/API (prior audit) | ~899 ms list | Smoke poll claimed 1 eligible task same session |
| Cron job | paused | active every 5m |

Preserved on default chat: file tools, artifacts dirs, Mem0, session_search, ClickUp capture (`clickup-bridge`), safe web research (`web_search` / `web_extract`). Heavy browser plugins removed from default.

Config backup: `/opt/hermes/home/config.yaml.bak-week1-*`.

---

## What changed — VPS vs local

### VPS (live)
- Resumed cron `4dcf0a86d0e8`
- Applied `daily-ops` routing + Zoho disable + `inherit_mcp_toolsets: false` in `/opt/hermes/home/config.yaml`
- Restarted `hermes-gateway.service` (twice: after config, after wire overlay)
- Overlay files under `/opt/hermes/app`: `plugins/clickup_task_os/{poller,worker}.py`, `hermes_cli/commands.py`, `cli.py`
- Obsidian: `Growth OS/Drafts/Hermes/README.md` present; removed mistaken truncated tree `/opt/hermes/data/obsidian/Growth` from earlier unquoted rsync

### Local (Mac / worktree)
- Code wire + tests (uncommitted)
- Obsidian Drafts folder + push script quoting fix (`~/.hermes/bin/sync-obsidian-to-hermes-remote.sh`)
- LaunchAgent: vault sync → push-only script; reverse tunnel disabled (plist relocated)

---

## Exact SHA deployed

| Ref | SHA | Notes |
|-----|-----|-------|
| VPS `/opt/hermes/app` git HEAD | `d1908cfcf2a6779c58d003ad81469364f6cac4bd` | Unchanged tip; Week-1 wire applied as **overlay** not a clean tip checkout |
| Local worktree HEAD | `cec86055157f65ff788ebce97def4ecd796fcf46` | Ahead of VPS tip; includes prior path-boundary commits; Week-1 wire **not yet committed** |

**Reason full SHA deploy deferred:** avoid force-syncing unrelated untracked audits / unfinished merge branch onto production without an explicit commit + promote path. Operational Week-1 outcomes are on VPS via config + overlay.

### Commit-ready (when you want a commit)
```bash
cd ~/.hermes/hermes-agent
git add plugins/clickup_task_os/poller.py plugins/clickup_task_os/worker.py \
  hermes_cli/commands.py cli.py tests/plugins/test_clickup_task_os_discovery_wire.py \
  audit/HERMES_WEEK1_ACCEPTANCE_REPORT.md audit/HERMES_PHASE7_CAPABILITY_VALIDATION.md
# commit message suggestion:
# feat(task-os): wire discovery/gap on failure; week-1 acceptance evidence
```

---

## Rollback commands

```bash
# Cron
ssh hermes-production 'export PATH=/opt/hermes/app/.venv/bin:$PATH HERMES_HOME=/opt/hermes/home
  hermes cron pause 4dcf0a86d0e8'

# Config (restore pre-week1 backup — pick newest bak-week1 file)
ssh hermes-production 'ls -t /opt/hermes/home/config.yaml.bak-week1-* | head -1
  # then: cp -a <that-file> /opt/hermes/home/config.yaml && sudo systemctl restart hermes-gateway'

# Code overlay: re-checkout tip files from VPS git
ssh hermes-production 'cd /opt/hermes/app && git checkout -- \
  plugins/clickup_task_os/poller.py plugins/clickup_task_os/worker.py \
  hermes_cli/commands.py cli.py && sudo systemctl restart hermes-gateway'

# Obsidian reverse tunnel (re-enable only if intentionally needed)
# mv ~/Library/LaunchAgents/disabled/com.hermes.obsidian-reverse-tunnel.plist ~/Library/LaunchAgents/
# launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.hermes.obsidian-reverse-tunnel.plist
```

---

## Desktop / tool-selection test log (item 6)

```text
scripts/run_tests.sh \
  tests/agent/test_path_boundary.py \
  tests/agent/test_platform_hint_desktop.py \
  tests/tools/test_file_staleness.py \
  tests/run_agent/test_stream_stale_circuit_breaker.py -q
→ 4 files, 45 tests passed, 0 failed

scripts/run_tests.sh \
  tests/plugins/test_clickup_task_os.py \
  tests/plugins/test_clickup_task_os_discovery_wire.py \
  tests/agent/test_capability_gap_and_skill_discovery.py \
  tests/agent/test_path_boundary.py -q
→ 4 files, 27 tests passed, 0 failed

python -m hermes_cli.capability_profiles measure --profile daily-ops
→ ~14–16 tools / ~34–36 KB (env-dependent web check_fn)
```

---

## SpaceMail stretch

**SKIPPED.** Parent decision: not on critical path ahead of items 1–5. Spot-check found no deployable SpaceMail adapter/credentials path on VPS clear enough for a trusted read-only inbox proof; sending remains disabled by policy. Revisit only after explicit credentials + adapter verification.

---

## Smoke artifacts

- ClickUp smoke task: `86carf2p2` → Review (`waiting` + `hermes-review`)
- Deterministic evidence path: `/tmp/hermes-task-os-smoke-86carf2p2.txt` (on VPS worker host)
- Obsidian: `/opt/hermes/data/obsidian/Growth OS/Drafts/Hermes/README.md`
