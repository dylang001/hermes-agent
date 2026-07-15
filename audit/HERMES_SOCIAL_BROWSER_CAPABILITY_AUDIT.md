# Hermes Social & Browser Capability Audit (Phase 7F / 7G)

**Date:** 2026-07-15  
**Scope:** Local workspace `~/.hermes` + repo `hermes-agent` + capability-lab + archived agent skills  
**Posture:** Minimal viable personal OS — prefer existing free / already-present tools; **approval-gated** publishing/outreach; **no** Success.ai; **no** cookie theft, CAPTCHA bypass, or stealth-evasion recommendations.

---

## Executive snapshot

| Need | Current best path | Status |
|---|---|---|
| Public social research (X/Reddit/YT) | Capability-lab `public-platform-research` + native `web_search`/`web_extract` + `yt-dlp` + bundled `youtube-content` | Staged / partial |
| Official X write path | Bundled `skills/social-media/xurl` (OAuth2 PKCE) | Skill present; **`xurl` binary not on PATH** |
| Authenticated tab assist (human-logged Chrome) | `opencli` (installed) | Daemon up; **Chrome extension not connected** |
| Interactive browser | Hermes browser toolset + cloud plugins (`browser-use`, `browserbase`, `firecrawl`) | Local engine `auto`; cloud keys incomplete |
| Desktop GUI | `computer_use` + skill | Present on Mac; high blast radius — profile-gate |
| Agent-Reach full installer | Not installed | Lab keeps **curated read-only skill only**, installer disabled |
| Composio social toolkits | Archived skills + `~/.composio` present | Not in live Hermes MCP config |

**Agent-Reach install check:** `agent-reach` CLI **not found**; `pip show agent-reach` **missing**. Upstream project in ecosystem notes is **Panniantong/Agent-Reach** (not a verified local `dylang001/Agent-Reach` checkout). Reddit/YouTube/Twitter channels from Agent-Reach are **not live** here. Safer equivalent already staged: `capability-lab/skills/public-platform-research` (read-only, no cookies).

---

## Per-capability matrix

Columns: **Source · Maintained? · Auth · Permissions · Platform rules · Risks · Restore? · Safer equivalent**

### 1. Agent-Reach / “Agents Have Eyes” (public-platform research)

| Field | Finding |
|---|---|
| **Source** | Capability-lab: `agent_reach` routing → `public-platform-research` skill (`~/.hermes/capability-lab/`). Upstream ecosystem: Panniantong/Agent-Reach. Branding overlap with “give agents eyes” tools (JS-Eyes / Eyebrowse / etc.) — **none of those are installed as Hermes plugins**. |
| **Maintained?** | Lab skill present, `enabled: false`. Full Agent-Reach package **not installed**. |
| **Auth** | Lab skill: none (public only). Full Agent-Reach upstream often wants OpenCLI login or cookies for Reddit/X — **do not restore cookie paths**. |
| **Permissions** | Read-only research in lab security model (`allow_credentials: false`, `allow_writes: false`). |
| **Platform rules** | Respect ToS / rate limits; public URLs only. |
| **Risks** | Upstream auto-installer; cookie CLIs; ToS violations if used for bulk engagement. |
| **Restore?** | **Partial yes:** enable curated skill + free upstreams (`yt-dlp`, `gh`, native web). **No** to Agent-Reach auto-install / cookie unlocks. |
| **Safer equivalent** | `web_search` + `web_extract` + `youtube-content` + `gh` + OpenCLI **read** after human login (extension connected). |

### 2. Browser-Use (cloud)

| Field | Finding |
|---|---|
| **Source** | `plugins/browser/browser_use/` (bundled). Registry preference: `browser-use` → `browserbase`. |
| **Maintained?** | Yes (in-tree plugin + tests). |
| **Auth** | `BROWSER_USE_API_KEY` (not observed in local `.env` key scan). |
| **Permissions** | Cloud browser sessions; navigates arbitrary public URLs when configured. |
| **Platform rules** | Provider ToS; no assumption of logged-in personal accounts. |
| **Risks** | Cost/latency; schema exposure if toolset always on. |
| **Restore?** | Optional when key present; profile-gate `browser`. |
| **Safer equivalent** | Local Hermes browser / CDP for public pages; Playwright for owned sites. |

### 3. Crawl4AI

| Field | Finding |
|---|---|
| **Source** | User plugin `~/.hermes/plugins/web/crawl4ai/` + capability-lab mirror; isolated venv helper. |
| **Maintained?** | Staged operator plugin (`kind: standalone`); **enabled: false** in capability-config. |
| **Auth** | None (public extract). |
| **Permissions** | `supports_extract` only; subprocess isolation. |
| **Platform rules** | Public read-only. |
| **Risks** | SSRF if private URLs allowed (lab forces `allow_private_urls: false`). |
| **Restore?** | **Yes — low risk** as opt-in extract backend after benchmark. |
| **Safer equivalent** | Native `web_extract` / Firecrawl when keyed. |

### 4. Playwright

| Field | Finding |
|---|---|
| **Source** | System `playwright` on PATH; Google Meet plugin; orchidea-gtm Detector README; archived `playwright-skill`. Hermes venv: `playwright` package **not** installed in `.venv`. |
| **Maintained?** | Upstream Playwright yes; Hermes Meet plugin maintained. |
| **Auth** | Ephemeral contexts by default; Meet uses explicit auth file path for Google session. |
| **Permissions** | Full browser automation when run via terminal/plugin. |
| **Platform rules** | Use on owned sites / public triage; avoid anti-bot evasion framing. |
| **Risks** | Agent scripting can become scraping-at-scale; stealth skills exist in optional/archive — **do not restore those**. |
| **Restore?** | Keep Meet path; for Orchidea, queue Playwright only for **shortlisted** public funnel audits. |
| **Safer equivalent** | Hermes `browser_*` tools + HTTP triage first. |

### 5. Chrome DevTools / CDP

| Field | Finding |
|---|---|
| **Source** | `tools/browser_cdp_tool.py`; `browser.cdp_url` config; Camofox REST/CDP bridge; skill `node-inspect-debugger` (Node V8 inspect — not social). |
| **Maintained?** | Yes in Hermes core. |
| **Auth** | Attaches to a browser you already control; can expose cookies via CDP methods. |
| **Permissions** | High — Network.getAllCookies etc. documented. |
| **Platform rules** | Operator-owned debug sessions only. |
| **Risks** | Cookie/session exfiltration into LLM context if agent calls cookie CDP methods. |
| **Restore?** | Keep for engineering debug. **Do not** use as social login bypass. |
| **Safer equivalent** | `opencli browser bind` to a human-prepared tab; never dump cookies to chat. |

### 6. Computer Use

| Field | Finding |
|---|---|
| **Source** | `tools/computer_use/` + skill `skills/computer-use`; cua-driver. |
| **Maintained?** | Yes. |
| **Auth** | Host Accessibility / desktop control. |
| **Permissions** | Click/type/capture across apps; CLI approval callback. |
| **Platform rules** | Local Mac only in practice; VPS N/A. |
| **Risks** | Highest blast radius (can operate any visible UI). |
| **Restore?** | Keep local, **disabled** on VPS / messaging profiles (`prospecting.yaml` already disables). |
| **Safer equivalent** | Browser toolset for web-only tasks. |

### 7. Authenticated browser profiles

| Field | Finding |
|---|---|
| **Source** | Camofox `managed_persistence` / adopt tab; Browserbase sessions; OpenCLI bind to logged-in Chrome; archived `setup-browser-cookies`. |
| **Maintained?** | Camofox + OpenCLI paths yes; cookie-setup skill **archived**. |
| **Auth** | Human login first, then reuse profile/tab. Local `.env` has `BROWSERBASE_*` knobs including `BROWSERBASE_ADVANCED_STEALTH` — treat as **vendor knob to leave off / ignore** for policy (no stealth-evasion playbook). |
| **Permissions** | Full account power of the logged-in user. |
| **Platform rules** | Publishing/outreach require explicit approval; research may use read-only. |
| **Risks** | Session theft if agents export cookies; ToS/ban risk for automated engagement. |
| **Restore?** | Prefer OpenCLI bind + Camofox adopt **without** cookie export skills. **Do not** restore `setup-browser-cookies`. |
| **Safer equivalent** | Official OAuth CLIs (`xurl`, `gh`) for write; public extract for read. |

### 8. Cookie CLIs / archived cookie skills

| Field | Finding |
|---|---|
| **Source** | Archived `~/.agents/skills/.archived/setup-browser-cookies`; Agent-Reach cookie unlock docs (external). |
| **Maintained?** | Archived / external. |
| **Auth** | Cookie jar reuse. |
| **Permissions** | Equivalent to stolen session. |
| **Platform rules** | Violates many platform ToS; high ban risk. |
| **Risks** | Account loss, credential leakage into logs/LLM. |
| **Restore?** | **No.** |
| **Safer equivalent** | OAuth CLIs; human SSO then OpenCLI bind. |

### 9. Social skills (live)

| Skill | Source | Auth | Restore? | Notes |
|---|---|---|---|---|
| `xurl` | Bundled `skills/social-media/xurl` | X OAuth2 PKCE via `~/.xurl` (user setup) | **Yes** after installing binary + user auth | Approval before posts/DMs |
| `youtube-content` | Bundled media skill | Public transcript API | Keep | Read-only |
| Composio Twitter/Reddit/YouTube | `.archived/*-automation` via Rube MCP | Composio connections | Optional later | Critical risk skills — **approval + read-first** |
| `x-twitter-scraper` (Xquik) | Archived | Third-party API | Prefer **no** | Paid/third-party scrape surface |
| cold-outreach / cold-email | `~/.agents/skills` symlinked into Hermes skills | N/A (copy) | Use for drafting only | Must align Nick Saraev / Orchidea policies |

### 10. Composio social

| Field | Finding |
|---|---|
| **Source** | `~/.composio/` + archived `composio-cli` / `*-automation` skills. Not listed as active Hermes MCP child in Phase 6 (Exa + Obsidian only). |
| **Maintained?** | Composio product maintained; Hermes wiring inactive. |
| **Auth** | Composio OAuth link per toolkit. |
| **Permissions** | Toolkit-scoped (Twitter/Reddit/YouTube can write). |
| **Platform rules** | Provider + platform ToS. |
| **Risks** | Schema bloat; accidental posts; third-party token sprawl. |
| **Restore?** | Only if OAuth app is intentional and **write tools require approval**. Prefer `xurl` for X. |
| **Safer equivalent** | Official CLIs + public research skill. |

### 11. Firecrawl / Browserbase (adjacent)

| Capability | Status | Notes |
|---|---|---|
| Firecrawl plugin | Bundled `plugins/browser/firecrawl` | Extract-oriented cloud |
| Browserbase | Plugin present; local env has Browserbase knobs | Prefer public sessions; do not build cookie/stealth workflows |

### 12. Scrapling (optional-skill)

| Field | Finding |
|---|---|
| **Source** | `optional-skills/research/scrapling` — advertises stealth / Cloudflare bypass. |
| **Restore?** | **No** for this OS phase (conflicts with no-CAPTCHA-bypass / no-stealth policy). |
| **Safer equivalent** | Crawl4AI public extract or native `web_extract`. |

---

## Installation facts (2026-07-15 local probe)

| Binary / package | Present? |
|---|---|
| `agent-reach` | No |
| `xurl` | No (skill exists) |
| `opencli` | Yes v1.8.6 — extension **not connected** |
| `yt-dlp` | Yes |
| `gh` | Yes |
| `playwright` (system) | Yes |
| Hermes `.venv` playwright/crawl4ai/browser_use | No |
| Capability-lab `agent_reach` flag | `enabled: false` |
| Crawl4AI user plugin | Present, staged off |

---

## Top restore candidates (social) — ordered for MVP OS

1. **`xurl` install + user OAuth** — official X read/write with approval gate (replaces Composio Twitter for most needs).  
2. **Connect OpenCLI Chrome extension** — authenticated **human** sessions for rare logged-in research; read-first; no cookie export.  
3. **Enable capability-lab `public-platform-research` (+ optional Crawl4AI extract)** — free public signal research without Agent-Reach installer.  
4. **Keep `youtube-content` + `yt-dlp`** — YT transcripts without Agent-Reach.  
5. **Do not restore:** cookie CLIs, Scrapling stealth, Agent-Reach cookie unlocks, archived mass automation skills, Success.ai.

---

## Approval gates (mandatory)

| Action | Gate |
|---|---|
| Post / reply / DM / like / follow | Explicit human approval per action or bounded batch ID |
| Publish from authenticated browser | Approval + Prefer official API over automation |
| Research / extract public pages | Allowed without per-URL approval under rate limits |
| Export cookies / CDP cookie dumps | Forbidden |

---

## Related files

- `audit/HERMES_CAPABILITY_INVENTORY.md`
- `~/.hermes/capability-lab/README.md` + `capability-config.json`
- `config/capability_profiles/prospecting.yaml`
- `skills/social-media/xurl/SKILL.md`
- `plugins/browser/{browser_use,browserbase,firecrawl}/`
