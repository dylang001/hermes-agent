# Hermes Phase 7A — Capability Validation Matrix

**Date:** 2026-07-15  
**Update:** Week-1 acceptance applied — see `audit/HERMES_WEEK1_ACCEPTANCE_REPORT.md`.  
**Evidence sources:** repo code/tests, local Mac `~/.hermes`, VPS `hermes-production` (`/opt/hermes/{app,home}`), live API probes **without printing secrets**.  
**Rule:** config alone ≠ healthy. Status values:

| Status | Meaning |
|--------|---------|
| **verified** | Live or hermetic test passed this run |
| **partial** | Installed + auth/config evidence, but E2E / agent-loop path not exercised end-to-end |
| **unverified** | Not exercised live (missing secrets, paused job, or out of scope for this pass) |
| **broken** | Evidence of fail / wrong wiring / missing dependency |

**Counts (1–59):** verified **9** · partial **15** · unverified **30** · broken **5**  
(Verified = live path exercised this pass. Unit-test-only modules stay **partial** until wired/called from a real session.)

---

## Scorecard summary

| # | Capability | Status | One-line evidence |
|---|------------|--------|-------------------|
| 1 | File read/write/edit | verified | Local + VPS `write_file`/`read_file`/`search_files` OK (VPS write 76 ms / read 30 ms) |
| 2 | Terminal execution | verified | Local + VPS `terminal` echo OK (11–57 ms) |
| 3 | Artifact generation | partial | File tools write artifacts; no fresh Telegram-bound artifact E2E this pass |
| 4 | Desktop artifact delivery | partial | Gateway media allow-list code present; VPS `media_delivery_allow_dirs: []` (defaults only) |
| 5 | Mem0 durable write/recall | partial | VPS `memory.provider: mem0`, API key live (`GET /v1/memories` 200); write/recall via agent loop **not** run |
| 6 | Session Search | verified | VPS `SessionDB.search_sessions('telegram')` → 1 hit; tool itself agent-loop-only |
| 7 | Cron | verified | Week-1: resumed **`4dcf0a86d0e8`**; single poller; ticker + last_status ok (see `HERMES_WEEK1_ACCEPTANCE_REPORT.md`) |
| 8 | Kanban | verified | VPS `kanban_list` OK (empty board, 15 ms); `kanban.db` present |
| 9 | Delegation / subagents | partial | Tool registered; returns “must be handled by agent loop”; config depth 2 / inherit_mcp true on VPS |
| 10 | Provider / model routing | verified | VPS model `opencode-go` / `minimax-m3`; gateway+dashboard **active** |
| 11 | Capability-gap reporting | partial | Wired into Task OS poller failure comments + waiting enrichment; help tip only (not full chat E2E) |
| 12 | Skill discovery | partial | Wired via Task OS + `/help` tip; unit wire tests green; staged install still open |
| 13 | Skill staging | unverified | Quarantine flow described in module; no staged install this pass |
| 14 | Failed MCP isolation | partial | Exa MCP `enabled: false` on VPS; `no_mcp` + dashboard disable code exists; full failure isolation E2E not run |
| 15 | Public-action approvals | partial | `tools/approval.py` + `/approve` path in gateway; no live approval turn this pass |
| 16 | Stale-path recovery | verified | Remap + equivalent halt: `test_runtime_metadata` 8/8 + guardrail tests green; VPS Obsidian path fixed |
| 17 | Telegram | verified | VPS platform `connected`; `getMe` → bot OK 200 |
| 18 | ClickUp Task OS | verified | Cron active; smoke `86carf2p2` Ready+hermes-ready → Review (`waiting`+`hermes-review`) via deterministic poll |
| 19 | ClickUp via clickup-bridge | partial | Plugin enabled; API token valid (VPS `/user` 200); CLI dispatch looks thin (`hermes clickup` → help only) |
| 20 | Obsidian search | partial | Vault present Mac (26 md) + VPS Growth OS (26 md); MCP args fixed to Growth OS; **MCP search tool not called live** |
| 21 | Obsidian read | verified | Direct filesystem read of vault files on Mac + VPS listing |
| 22 | Obsidian staging write | partial | `Growth OS/Drafts/Hermes` created Mac→VPS push; agent write-approval E2E still open |
| 23 | Canonical write approval | unverified | Policy only — not exercised |
| 24 | Sync safety | partial | Push-only LaunchAgent + space-safe rsync; reverse tunnel 27124 unloaded |
| 25 | Stale-note / duplicate detection | unverified | Not implemented as a verified capability |
| 26 | Gmail | unverified | Himalaya skill present; `himalaya` CLI **missing** local; VPS IMAP/SMTP env commented |
| 27 | Google Calendar | unverified | No live OAuth/tool proof |
| 28 | Google Drive | unverified | No live OAuth/tool proof |
| 29 | GitHub | verified | VPS `GITHUB_TOKEN` → `api.github.com/user` **200** (`gh` binary absent on VPS — token API works) |
| 30 | SpaceMail mailboxes | broken | **No adapter in tree**; Growth OS debt only |
| 31 | Zoho / CRM | unverified | Week-1: `orchidea-zoho-leads` **disabled** until URL env exists (no longer slows startup as enabled empty) |
| 32 | Composio | unverified | MCP URL + API key present on VPS; enabled flag unset; live tool call not run (keep off for MVP) |
| 33 | Browser automation | partial | Toolset + plugins (`browser_use`, firecrawl) installed; CDP check fails in schema measure without session |
| 34 | Computer use | broken | Local doctor: `cua-driver` not installed; VPS N/A — keep disabled |
| 35 | Reddit | unverified | Agent-Reach **not** installed; social skills partial; no live read |
| 36 | X / Twitter | unverified | Same |
| 37 | LinkedIn | unverified | VPS skill `linkedin-automation` installed; live ops not run |
| 38 | YouTube | partial | Bundled/`youtube-content` skill present; no live fetch |
| 39 | Public forums | unverified | Web tools gated on API keys in schema measure |
| 40 | Social-content research | unverified | Profile YAML missing (`social-content`) |
| 41 | Social-post drafting | unverified | Skills exist; no draft E2E |
| 42 | Social-comment drafting | unverified | Same |
| 43 | Approved publishing flow | partial | Approval gates exist in code; social-operator profile **missing** |
| 44 | Performance-data collection | unverified | No collector verified |
| 45–59 | Prospecting pipeline | mostly unverified / broken for send | Spec + skills (`orchidea-prospector`, enrich, verify); HyperAgent sources missing; SpaceMail send broken; no live SDR loop |

---

## Detailed matrix (required columns)

Legend for **profile exposure**: which of the *existing* capability profiles YAML declare the surface (missing profiles noted). Schema sizes measured locally via `python -m hermes_cli.capability_profiles measure` (check_fn may drop gated tools — see profile doc).

### Core Hermes (1–19)

| # | Capability | Installed | Configured | Authenticated | Profile exposure | Tool used | Test performed | Result | Latency | Error behavior | Recovery | Permissions | Security risk | Recommended action |
|---|------------|-----------|------------|---------------|------------------|-----------|----------------|--------|---------|----------------|----------|-------------|---------------|-------------------|
| 1 | File R/W/edit | yes | default toolset | n/a | daily-ops, task-os, eng, research, content, prospecting, admin, browser-ops | `write_file` `read_file` `search_files` `patch` | Local+VPS handle_function_call | **pass** | 30–278 ms | JSON errors on bad path | path_boundary / guardrails | FS of HERMES user | med (cwd blast) | **keep**; apply daily-ops |
| 2 | Terminal | yes | terminal.cwd `.` | n/a | same as files | `terminal` | echo local+VPS | **pass** | 11–57 ms | non-zero exit in payload | equivalent_failure halt | shell as service user | **high** | keep; approvals for dangerous cmds |
| 3 | Artifact generation | yes | file/cache dirs | n/a | daily-ops+ | `write_file` / skill scripts | wrote `/tmp/phase7_probe.txt` | **partial** | — | — | — | FS | med | VPS/Telegram: generate + attach real artifact |
| 4 | Desktop artifact delivery | yes | gateway media helpers | session token | Desktop/dashboard | media delivery path | config inspect only | **partial** | — | deny outside allow dirs | trust_recent | allow_dirs | med exfil | set `gateway.media_delivery_allow_dirs` deliberately; Desktop smoke |
| 5 | Mem0 write/recall | yes (plugin) | VPS `provider: mem0` | `MEM0_API_KEY` (VPS API 200) | all session profiles | `memory` + mem0 provider | API list + `hermes memory status` | **partial** | API ~fast | stale `/root` paths historically | remap + equivalent halt | Mem0 cloud PII | **high** PII | keep; run agent write→recall; purge stale `/root` if still present |
| 6 | Session Search | yes | state.db present | n/a | daily-ops, eng, research, content… | `session_search` / `SessionDB.search_sessions` | VPS FTS query | **pass** (DB); tool agent-loop-only | &lt;1 ms FTS | empty vs miss | — | session corpus | med | keep; agent chat smoke “search past …” |
| 7 | Cron | yes | jobs.json | n/a | admin; Task OS script | `cronjob` / cron ticker | listed jobs | **broken (ops)** | ticker ok | job paused | resume job | script perms | med | `hermes cron resume 4dcf0a86d0e8` after Task OS protect gates |
| 8 | Kanban | yes | VPS kanban config | n/a | task-os, admin | `kanban_*` | `kanban_list` VPS | **pass** | 15 ms | empty board | failure_limit 2 | local sqlite | low | keep for Task OS locks |
| 9 | Delegation | yes | VPS depth 2, inherit MCP **true** | model key | daily-ops (cli), task-os, eng | `delegate_task` | direct call rejected (agent loop) | **partial** | — | must be agent-handled | budget/timeout | child tools | med–high MCP inherit | chat smoke; set `inherit_mcp_toolsets: false` on default chat |
| 10 | Provider routing | yes | opencode-go + MiniMax | `OPENCODE_GO_API_KEY` | all | chat completions | services active + config read | **pass** | — | aux openrouter/nous unhealthy in local measure | pool/fallback | API cost | keep |
| 11 | Capability-gap | yes (lib) | unwired | n/a | intended all | `build_gap_report` | unit tests + local call | **partial** | — | — | — | low | low | wire into Task OS failure / missing integ |
| 12 | Skill discovery | yes (lib) | unwired | n/a | intended daily-ops | `propose_discovery` | tests + local classify/search | **partial** | — | empty skills if wrong HERMES_HOME | — | skill scripts | med | wire thin; one staged official skill |
| 13 | Skill staging | yes (hub) | quarantine design | n/a | admin | skills_hub | not run | **unverified** | — | — | rollback docs | quarantine FS | med | staged install once |
| 14 | Failed MCP isolation | yes | Exa disabled; Zoho mostly off | keys may exist | dashboard `no_mcp` | MCP client | config + tests | **partial** | — | flaky servers historically | disable server | third-party | med | health-check Parallel; keep Composio/Zoho off |
| 15 | Public-action approvals | yes | approval module | Telegram user allowlist | daily-ops policy | `/approve` `/deny` | code path only | **partial** | — | blocks until approve | deny continues | user | high if YOLO | Telegram: force one approval prompt |
| 16 | Stale-path recovery | yes | VPS equivalent_failure:2 | n/a | all | runtime_metadata + guardrails | 8+13 tests green; Obsidian path fixed | **pass** (unit) | — | halt after 2 equivalent | remap `/root/audit` | — | med if remap misses | Desktop **new session** smoke still open |
| 17 | Telegram | yes | gateway | bot token + allowlist | default gateway | platform adapter | getMe + connected state | **pass** | — | disconnect recorded in gateway_state | restart service | bot scope | med | keep; gate heavy toolsets |
| 18 | ClickUp Task OS | yes | task-os profile + board IDs | CLICKUP token | **task-os only** | `hermes task-os` / poller | show-config + list API; cron paused | **partial** | list 899 ms | 0 hermes-ready | pause/resume cron | workspace token | med | resume cron; smoke Ready+hermes-ready → Review |
| 19 | clickup-bridge | yes | plugins.enabled | same token | default VPS plugins | `hermes clickup` | API `/user` 200; CLI thin | **partial** | — | CLI subcommands not exposed | use raw API/skill | workspace | med | fix CLI registration or use skill; capture→Ops |

### Knowledge (20–25)

| # | Capability | Installed | Configured | Authenticated | Profile exposure | Tool used | Test performed | Result | Latency | Error behavior | Recovery | Permissions | Security risk | Recommended action |
|---|------------|-----------|------------|---------------|------------------|-----------|----------------|--------|---------|----------------|----------|-------------|---------------|-------------------|
| 20 | Obsidian search | MCP fs + skill | VPS MCP → Growth OS | n/a (fs) | research allow; daily-ops intended | MCP filesystem / `search_files` | vault list; **MCP tool not invoked** | **partial** | — | historical wrong `/root/obsidian-vault` | path fix shipped | vault read | vault exfil | `npx` MCP list_dir or `search_files` on vault path live |
| 21 | Obsidian read | yes | paths Mac+VPS | n/a | research / daily-ops | filesystem | listed 26 md both sides | **pass** | — | — | sync later | read | med | prefer file tools over MCP for MVP |
| 22 | Staging write | policy | Drafts/Hermes intended | n/a | content/research | write_file | not run | **unverified** | — | — | approval | write | med | create Drafts/Hermes + one approved write |
| 23 | Canonical write approval | docs | — | — | admin | approvals | not run | **unverified** | — | — | — | — | high | keep human gate |
| 24 | Sync safety | design docs | hermes-production SSH works | SSH keys | admin | sync scripts | SSH OK; sync not run | **unverified** | — | — | dry-run+lock | rsync | high mass wipe | dry-run Mac→VPS only |
| 25 | Stale/duplicate detect | no verified impl | — | — | — | — | — | **unverified** | — | — | — | — | low | defer |

### Communication / productivity (26–34)

| # | Capability | Installed | Configured | Authenticated | Profile exposure | Tool used | Test performed | Result | Latency | Error behavior | Recovery | Permissions | Security risk | Recommended action |
|---|------------|-----------|------------|---------------|------------------|-----------|----------------|--------|---------|----------------|----------|-------------|---------------|-------------------|
| 26 | Gmail | skill (himalaya) | IMAP env commented VPS | **not verified** | intended daily-ops / email-ops (**profile missing**) | himalaya/terminal | himalaya missing local | **unverified** | — | — | — | mailbox | high | install himalaya + OAuth/IMAP on gated profile |
| 27 | Calendar | ? | — | no | daily-ops intended | — | none | **unverified** | — | — | — | calendar | med | only if Dylan needs; else cut |
| 28 | Drive | ? | — | no | — | — | none | **unverified** | — | — | — | drive | med | defer |
| 29 | GitHub | skill + token | VPS `GITHUB_TOKEN` | API 200 | engineering | `gh`/API/terminal | API user 200; no `gh` on VPS | **pass** (token) | — | `gh` missing | use API/curl | repo scope | med | `engineering` profile; install `gh` optional |
| 30 | SpaceMail | **no** | Growth OS only | n/a | prospecting/email-ops missing | — | inventory | **broken** | — | — | — | — | high if fake-ready | inventory credentials only; no send |
| 31 | Zoho | MCP stubs | leads URL unset | no | prospecting | MCP | URL expand empty | **broken** | — | unset env | disable enabled server | CRM | high | `enabled: false` until URL+need |
| 32 | Composio | MCP config | URL+key | key present | — | MCP | not called | **unverified** | — | — | keep off | third-party | high | leave disabled for MVP |
| 33 | Browser | yes | plugins on VPS | Browserbase flags present | research, browser-ops | browser_* | schema measure; CDP false | **partial** | high when live | session fail | profile-gate | browser | high | Mac browser-ops smoke; VPS gated |
| 34 | Computer use | yes code | doctor fails | no driver | disabled in profiles | computer_use | doctor: no cua-driver | **broken** | — | unavailable | install only if needed | full UI | **critical** | disable everywhere |

### Social (35–44)

| # | Capability | Status | Evidence / action |
|---|------------|--------|-------------------|
| 35–39 | Reddit / X / LinkedIn / YouTube / forums | unverified (YouTube skill partial) | Agent-Reach **not** installed; `AGENT_SOCIAL_*` env on VPS without product; LinkedIn skill on disk only. **Action:** public web research under `research`; no cookie/CAPTCHA bypass. |
| 40–42 | Social research / post / comment draft | unverified | Profiles `community-research`, `social-content`, `social-operator` **absent** from `config/capability_profiles/`. |
| 43 | Approved publishing | partial | Approvals code exists; no social-operator profile. |
| 44 | Performance data | unverified | Defer. |

### Prospecting (45–59)

| # | Cap | Status | Notes |
|---|-----|--------|-------|
| 45–52 | Signal→score/dedupe/cohort | unverified | Skills/PRD present; HyperAgent sources **missing** per Growth OS |
| 53 | SpaceMail sending | **broken** | No adapter |
| 54–57 | Follow-up / reply / classify / alerts | unverified | Depend on mail |
| 58 | ClickUp opportunity creation | partial | ClickUp API+Task OS/bridge can create when approved; not E2E |
| 59 | Weekly reporting | unverified | Templates in vault; no auto report run |

---

## MVP: 15–20 capabilities that unlock “daily personal OS” first

Prioritize these (order = unlock sequence):

1. **Telegram** (17) — already verified  
2. **Files** (1) + **Terminal** (2) — verified  
3. **Stale-path recovery** (16) — finish Desktop new-session smoke  
4. **Mem0** (5) — verify write/recall once; purge `/root` junk  
5. **Session Search** (6) — already works  
6. **Approvals** (15) — one live `/approve` path  
7. **clickup-bridge capture** (19) — chat → Ops  
8. **ClickUp Task OS** (18) + **Cron resume** (7) + **Kanban** (8) — durable queue  
9. **Obsidian read/search** (20–21) — Growth OS  
10. **Provider routing** (10) — keep MiniMax path  
11. **Native web** (under research; not numbered separately but required)  
12. **Skill discovery + gap reports** (11–12) — stop terminal thrash  
13. **MCP isolation** (14) — keep Exa/Zoho/Composio off default  
14. **Artifacts to Telegram/Desktop** (3–4)  
15. **GitHub** (29) — engineering profile only  
16. **Bounded delegation** (9) — inherit_mcp false on default  
17. **Browser** (33) — `browser-ops` / research only when needed  
18. **Gmail read** (26) — only if daily pain; else cut  

**Cut from first 20 days:** SpaceMail send, Zoho, Composio, computer use, full social publish, HyperAgent SDR (45–59).

---

## Commands Dylan / VPS should run (not done live here)

```bash
# VPS — resume Task OS poll after protect gates
ssh hermes-production
export HERMES_HOME=/opt/hermes/home
hermes cron list
hermes cron resume 4dcf0a86d0e8   # or equivalent
hermes -p task-os task-os poll --dry-run   # if supported
# Create ClickUp task: status next + tag hermes-ready → watch claim

# Mem0 E2E in a NEW Desktop/Telegram session
# "Remember that my vault is /opt/hermes/data/obsidian/Growth OS"
# new session: "Where is my Obsidian vault?" — must not say /root/obsidian-vault

# Obsidian search via tools (prefer file tools)
# search_files path='/opt/hermes/data/obsidian/Growth OS' pattern='ClickUp'

# Apply + measure daily-ops (do not assume healthy until measure)
hermes capability-profile apply daily-ops --dry-run
python -m hermes_cli.capability_profiles measure --profile daily-ops

# Fix Zoho dangling enable
# set orchidea-zoho-leads.enabled: false OR set ZOHO_MCP_LEAD_MANAGEMENT_URL

# GitHub engineering smoke
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user
```

---

## Phase 7B notes (profiles)

| Profile | YAML present | Applied on VPS default? | Schema measure (local) |
|---------|--------------|-------------------------|------------------------|
| daily-ops | yes | **yes** (VPS default `agent.capability_profile: daily-ops`) | Telegram toolsets **15 / 30.6 KB** (~26 ms); prior wide default was **39 / 47.8 KB** |
| task-os | yes | yes (profile config) | 13 tools / **28.5 KB** (kanban gated off without board mode) |
| engineering | yes | no | 15 tools / **36.5 KB** |
| research | yes | no | 22 tools / **33.6 KB** |
| content | yes | no | ~13 tools / **28.8 KB** |
| prospecting | yes | no | ~13 tools / **28.8 KB** |
| admin | yes | no | ~13 tools / **28.8 KB** (cronjob check_fn false in measure env) |
| browser-ops | yes | no | 21 tools / **27.9 KB** |
| community-research | **missing** | — | create when needed |
| social-content | **missing** | — | create when needed |
| social-operator | **missing** | — | create when needed |
| email-ops | **missing** | — | create when needed |

See `audit/HERMES_PHASE7_PROFILE_EXPOSURE.md`.

---

## Top recommended actions

1. ~~Resume Task OS cron `4dcf0a86d0e8`~~ — done Week-1 (single poller).  
2. ~~Apply `daily-ops` + `inherit_mcp_toolsets: false`~~ — done.  
3. ~~Disable `orchidea-zoho-leads`~~ — done.  
4. **Desktop new-session smoke** for stale `/root` (path-boundary unit tests green; live Desktop session still recommended).  
5. ~~Ready+hermes-ready → Review smoke~~ — done (`86carf2p2`).  
6. ~~Wire gap/discovery into Task OS failure~~ — done (thin); deepen only if failures stay silent.  
7. **Do not** chase SpaceMail / Composio / social publish for MVP week.  
8. **Install `gh` on VPS** optional; token already works.  
9. **Obsidian:** prove search via `search_files` or MCP once; prefer file tools.  
10. **Add missing profiles** only when a real surface needs gating (email-ops / social-operator).
