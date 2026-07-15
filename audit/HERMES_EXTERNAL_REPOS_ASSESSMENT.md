# Hermes Phase 7 — External Repo Assessment

**Date:** 2026-07-15  
**Lens:** Minimal viable Hermes personal OS (social / browser / marketing / LinkedIn)  
**Stance:** Ruthless reuse. Prefer on-demand optional-skills / CLIs that can be deactivated. Reject brittle ToS-evasion and always-on MCP bloat.  
**Local inventory sources:** `~/.hermes`, hermes-agent tree, capability-lab, VPS `hermes-production` (`/opt/hermes/home`).

---

## Executive verdict

| Artifact | Verdict | Why |
|---|---|---|
| `dylang001/agent-browser` | **SKIP** | Fork of `vercel-labs/agent-browser`; Hermes already pins/uses upstream `agent-browser@0.26.0` as native browser CLI |
| `dylang001/ai-marketing-claude` | **FORK (cherry-pick)** | Useful marketing *prompt* suite for Claude Code; too heavy as full install; adapt 1–3 skills into Hermes `optional-skills` |
| `dylang001/Agent-Reach` | **HARDEN → optional adopt** | User belief “already installed with Reddit/YouTube/Twitter” is **false** for working backends; VPS has orphan skill stub only |
| `charlesdove977/linkedin-automator` | **SKIP** | Browser-driven LinkedIn outreach; autonomous mode; ToS/account-ban risk; wrong shape for approval-gated Personal OS |

**LinkedIn winner (when API publish is needed):** [`anubisalpha/linkedin-mcp`](https://github.com/anubisalpha/linkedin-mcp) — official API + preview/approve write gates.  
**LinkedIn winner for MVP this week:** Hermes **draft-only optional skill + Obsidian queue** (already designed under `~/.hermes/sandboxes/linkedin-jobs/`) — no LinkedIn automation until Dylan explicitly upgrades.

---

## Recommendation table (adopt / skip / harden)

| Item | Adopt | Harden | Skip | Hermes integration path |
|---|:-:|:-:|:-:|---|
| Upstream `vercel-labs/agent-browser` (already in Hermes) | ✅ keep | — | — | **Built-in** browser toolset (`agent-browser` npm) — not a new repo |
| Dylan fork `agent-browser` | — | — | ✅ | None |
| Agent-Reach upstream (`Panniantong/Agent-Reach`) | — | ✅ optional CLI + curated skill | — | **optional-skill** + terminal CLI; never always-on MCP; never auto-installer |
| Dylan fork `Agent-Reach` | — | — | ✅ follow upstream | None (track `Panniantong/Agent-Reach`) |
| `zubair-trabzada/ai-marketing-claude` (Dylan fork) | — | ✅ cherry-pick | full suite | **optional-skills** only (`market-audit`, `market-copy`, maybe `market-social`) |
| `charlesdove977/linkedin-automator` | — | — | ✅ | None |
| Hermes Obsidian LinkedIn draft queue | ✅ MVP | — | — | **optional-skill** + cron + Obsidian markdown (no LinkedIn network) |
| `anubisalpha/linkedin-mcp` | ✅ phase 7.1 | pin + disable when unused | — | **MCP** opt-in on CLI/content profile only; secrets in `.env` |
| `octoryn/octopus-linkedin` | alt | — | if anubisalpha wins | MCP/CLI governor (`draft→approve→publish`) |
| `stickerdaniel/linkedin-mcp-server` | — | — | ✅ scraper | ToS risk despite popularity |
| Browser-use cloud plugin | keep gated | — | as default | Already a Hermes browser *backend* plugin; leave off until needed |
| Crawl4AI plugin | — | keep disabled | as default | Present under `~/.hermes/plugins/web/crawl4ai`; config **disabled** (SSRF/telemetry) |
| Composio social | — | re-evaluate old VPS stack | as Phase 7 default | Historical LinkedIn tools on old host; not MVP-first vs official LinkedIn MCP |
| “Agents Have Eyes” / Agent Eyes / JS Eyes | — | — | ✅ | Redundant with Hermes browser + agent-browser; AGPL/extension complexity |

---

## Local / VPS presence verify (Agent-Reach + siblings)

### Agent-Reach — claim vs reality

| Check | Local Mac | VPS `hermes-production` |
|---|---|---|
| `agent-reach` CLI on PATH | **Missing** | **Missing** |
| `~/.agent-reach` / install dir | **Missing** | **Missing** |
| PyPI/runtime package | Not installed (`pip` find fails) | Not present |
| Skill file | Not under `~/.hermes/skills/research/` | **Present:** `/opt/hermes/home/skills/research/agent-reach/SKILL.md` only |
| `references/*.md` companion docs | N/A | **Missing** (skill links to them; directory has only SKILL.md) |
| Cookie backends (`twitter`, `rdt`, OpenCLI) | `twitter`/`rdt` missing; OpenCLI shim path exists under BrowserBridge | `twitter`/`rdt`/`opencli`/`yt-dlp`/`mcporter` all **missing** |
| Capability-lab posture | `agent_reach.enabled: false`, `mode: curated_skill_only` | N/A |
| Curated substitute | `capability-lab` / `skills/capability-lab/public-platform-research` (read-only; forbids Agent-Reach auto-installer) | Orphan full Agent-Reach skill text (expects CLI that isn’t installed) |

**Verdict:** Agent-Reach is **not** installed as a working Reddit/YouTube/Twitter stack. VPS has a **skill stub that will fail or invent commands** if invoked. Local intentionally uses a safer public-only research skill with Agent-Reach installer blocked.

### Sibling inventory (already discoverable)

| Tool / surface | Present? | Notes |
|---|---|---|
| `agent-browser` | **Yes** | PATH + hermes-agent `package.json` dep `^0.26.0` (upstream Vercel Labs) |
| Hermes `browser_*` toolset | **Yes** | Local Chromium / CDP / optional Browser Use / Camofox |
| Playwright | **Yes** (system Python) | Used by ecosystem; not the Hermes primary drive path |
| Crawl4AI | **Plugin present, disabled** | `config.yaml` → `plugins.disabled: web/crawl4ai` |
| Browser-use | **Plugin present, gated** | `plugins/browser/browser_use`; capability-lab `enabled: false` |
| `yt-dlp` | Local yes / VPS no | Local Homebrew; not wired via Agent-Reach on VPS |
| `gh` | Local yes | Official GitHub CLI |
| Hermes `xurl` skill | **Yes** | Official X API CLI path (preferred for *write* Twitter vs cookie scrapers) |
| Hermes `youtube-content` skill | **Yes** | Transcripts via `youtube-transcript-api` |
| Social-media skills | Minimal | Essentially `xurl` + DESCRIPTION |
| Composio | Historical | Migration notes + retired-host archaeology (pre-cutover; production is `138.128.247.49` only) show LinkedIn+Composio; not Phase 7 default on current local config MCP list |
| Cookie CLIs | Partial | OpenCLI shim under `~/Library/Application Support/BrowserBridge/opencli-shim`; no twitter-cli/rdt-cli |
| “Agents Have Eyes” | **Not found** | No local install matching that name |

---

## Repo-by-repo assessments

### 1. `dylang001/agent-browser` → skip

| Field | Assessment |
|---|---|
| **Purpose** | Browser automation CLI for AI agents |
| **Maturity** | Dylan fork of mature upstream [`vercel-labs/agent-browser`](https://github.com/vercel-labs/agent-browser) (~38k★, actively pushed). Fork itself has 0★ / no independent value |
| **Auth model** | Cookie/profile/`--state` / CDP connect; optionally reuses Chrome profile |
| **Security risk** | High blast radius if pointed at logged-in personal profiles (session theft, unintended clicks). Hermes already mitigates via tool approvals + host/SSRF guards — do not add a second browser stack |
| **Integration path** | **None new.** Hermes already drives browser via this CLI (`tools/browser_*.py`, docs, npm dep) |
| **Recommend** | **SKIP fork.** Keep pinning upstream via Hermes install/setup. Do not mirror Dylan fork into plugins/skills |

**Better alternative:** Already won — Hermes native browser toolset + optional `/browser connect` to an approved Chrome profile for interactive sessions.

---

### 2. `dylang001/ai-marketing-claude` → harden / cherry-pick

| Field | Assessment |
|---|---|
| **Purpose** | Claude Code marketing suite: `/market audit|copy|emails|social|ads|…`, 14 skills + 5 parallel subagents + Python helpers + PDF reports |
| **Maturity** | Fork of [`zubair-trabzada/ai-marketing-claude`](https://github.com/zubair-trabzada/ai-marketing-claude) (~2.1k★, MIT). Dylan fork adds no unique commits of note. Promotional Skool CTA is packaging noise, not runtime risk |
| **Auth model** | None required (prompt+script analysis). Uses page fetch / scraping scripts — depends on network + HTML quality |
| **Security risk** | Medium operational: `curl \| bash` installer into `~/.claude`; parallel subagents inflate cost; PDF/script deps; not a credential store. Prompt-injection surface if audits ingest competitor HTML without treating content as untrusted |
| **Integration path** | **optional-skills**, not core, not MCP. Do **not** dump all 15 skills into always-loaded `~/.hermes/skills` |
| **Recommend** | **FORK/cherry-pick:** port 1–3 Hermes-native skills (`market-audit`, `market-copy`, optional `market-social`) under `optional-skills/…`, require `hermes skills install`, deactivate when unused. Prefer Hermes `web_extract` / browser over suite’s ad-hoc scrapers |

**Better alternatives (ranked for Hermes):**

1. **Cherry-picked optional-skills** from this suite (MVP) — on-demand, curator-friendly  
2. [`coreyhaines31/marketingskills`](https://github.com/coreyhaines31/marketingskills) — more modular Agent Skills spec; still cherry-pick, don’t install whole marketplace  
3. Existing Hermes growth skills (`cold-outreach`, `cold-email`, Obsidian Growth OS voice) — reuse first for Personal OS copy  
4. Full `claude-marketing` 56-skill packs — **too heavy** for MVP

---

### 3. `dylang001/Agent-Reach` → harden, then optional adopt (not “already working”)

| Field | Assessment |
|---|---|
| **Purpose** | Capability router skill+CLI: read/search web + social (Twitter, Reddit, YouTube, GitHub, ZH platforms…) via backend CLIs; `agent-reach doctor` health |
| **Maturity** | Fork of [`Panniantong/Agent-Reach`](https://github.com/Panniantong/Agent-Reach) (very large star count; active docs). Genuine product-market fit for agents that need social *read* without paid APIs |
| **Auth model** | Mixed: zero-config (Jina, yt-dlp, gh public); **cookie / OpenCLI browser session** for Twitter/Reddit/etc. Docs warn of ban risk — recommend secondary accounts |
| **Security risk** | **High if enabled carelessly:** (1) cookies on disk for primary accounts; (2) installer mutates agent environments; (3) LinkedIn channel points at **scraper MCP** (`stickerdaniel/linkedin-mcp-server`) — ToS risk; (4) VPS orphan skill causes hallucinated CLI use; (5) write tooling may creep in via twitter-cli |
| **Integration path** | **Terminal CLI + optional-skill**, profile-gated (`research` / CLI only). Never core tool schema. Never auto-run upstream install.md on VPS chat profile. Prefer curated public-only skill until doctor is green |
| **Recommend** | **HARDEN:** delete or quarantine VPS orphan skill until CLI+backends exist; keep local `public-platform-research` as default; if Dylan wants full social read, install upstream CLI on **Mac only**, secondary cookies only, strip LinkedIn scraper channel, and wrap as optional skill |

**Adopt shape (if/when):**

```text
optional-skills/research/agent-reach-read/
  SKILL.md          # doctor-first, read-only, secondary-account cookies only
  # no curl|bash installer; pin version; list exact backends
```

**Already better partial substitutes in Hermes:**

| Need | Prefer |
|---|---|
| Web read/search | Native `web` toolset (+ fix/disable flaky Exa MCP) |
| YouTube | `skills/media/youtube-content` (+ local `yt-dlp` if needed) |
| Twitter **write**/API | `skills/social-media/xurl` (official) |
| Twitter/Reddit **read** cheaply | Agent-Reach *after* harden — or Hermes browser on public pages |
| GitHub | `gh` + GitHub skills |

---

### 4. `charlesdove977/linkedin-automator` — assess first → **skip**

| Field | Assessment |
|---|---|
| **Purpose** | Claude Code + Claude-in-Chrome LinkedIn outreach: DMs, reply DMs, posts, connection requests |
| **Maturity** | Thin (Shell + slash command markdown). ~30★. Install via `curl \| bash` into `~/.claude/commands`. Single-author, ~1 day of push history (Jan 2026). Not a durable platform integration |
| **Auth model** | Reuses live Chrome LinkedIn session via Claude-in-Chrome (`claude --chrome`) |
| **Security / compliance risk** | **Unacceptable for Personal OS:** LinkedIn User Agreement forbids this class of automation; account restriction risk; “Fully Autonomous” mode sends without approval; rates/limits tracked in markdown, not hard gates; primary identity riding extension automation |
| **Integration path** | Would require Hermes browser + custom skill mimicking slash commands — **do not** |
| **Recommend** | **SKIP.** Even the human-in-the-loop mode is still browser automation against LinkedIn UI |

---

## LinkedIn alternatives (ranked)

Goal: **research + drafting with approval gates**, not mass automation / evasion.

| Rank | Option | Fit | Auth | Risk | Hermes path | Notes |
|---|---|---|---|---|---|---|
| **1 (MVP)** | Obsidian `linkedin-engagement-queue` skill + cron drafts | ★★★★★ | None | Low | **optional-skill** | Already audited/designed in `~/.hermes/sandboxes/linkedin-jobs/` — drafts only, Dylan executes in LinkedIn app |
| **2** | [`anubisalpha/linkedin-mcp`](https://github.com/anubisalpha/linkedin-mcp) | ★★★★★ | Official OAuth (`w_member_social`…) | Low–med (token store) | **MCP** opt-in | Preview→approve publish; audit log; 229 tests; ToS-aligned **winner for API publish** |
| **3** | [`octoryn/octopus-linkedin`](https://github.com/octoryn/octopus-linkedin) | ★★★★☆ | Official API | Low–med | MCP + CLI | Explicit `draft→approve→publish`; strong governor model; smaller/newer star count |
| **4** | Hermes browser + **approved dedicated Chrome profile** (read public / help compose; human posts) | ★★★☆☆ | Profile cookies | Med | Built-in browser | OK for research UX; still ToS-grey if agent clicks send — policy must forbid submit without Dylan click |
| **5** | Composio LinkedIn tools | ★★☆☆☆ | Vendor OAuth | Med–high | MCP/HTTP | Proven on **old** VPS archaeology; couples Hermes to vendor surface; OK later for multi-app glue, not LinkedIn MVP |
| **6** | [`southleft/linkedin-mcp`](https://github.com/southleft/linkedin-mcp) | ★★☆☆☆ | Mixed official + some unofficial (DM cookies) | Med–high | MCP | Content-intelligence pitch; DMs via cookies undermine the ToS story |
| **7** | [`raaaaaif/linkedin-research-agent-mcp`](https://github.com/raaaaaif/linkedin-research-agent-mcp) | ★☆☆☆☆ | Scrape/session style | High | MCP | Research UX + connect/message tools — wrong threat model for personal account |
| **8** | [`stickerdaniel/linkedin-mcp-server`](https://github.com/stickerdaniel/linkedin-mcp-server) | ★☆☆☆☆ | Cookie scrape | High | MCP | Popular; Agent-Reach’s LinkedIn default; **reject for primary account** |
| **9** | charlesdove / yennanliu / Easy-Apply Playwright agents | ☆ | Browser session | Critical | — | Mass automation / evasion class — **hard skip** |

### LinkedIn winner

| Phase | Winner | Rationale |
|---|---|---|
| **Phase 7 MVP (now)** | Hermes optional **draft queue skill** + Obsidian Growth OS | Matches Personal OS approval rules; zero LinkedIn ToS exposure; reuses existing inventory |
| **Phase 7.1 (publish)** | **`anubisalpha/linkedin-mcp`** | Official API, human-in-the-loop writes, audit log, disable-when-unused MCP — aligns with optional surface pattern |

`octopus-linkedin` is the runner-up if Dylan prefers a local draft kanban with a single `publish_draft` gate.

---

## Phase 7 pragmatic MVP blueprint (minimal)

1. **Browser:** keep Hermes native `agent-browser` stack; profile-gate on VPS chat; do not adopt Dylan fork.  
2. **Social read:** keep `public-platform-research`; do **not** restore full Agent-Reach until `agent-reach doctor` is green on Mac with secondary cookies; **remove/quarantine** VPS orphan skill. Prefer `xurl` + `youtube-content` + `gh` + native web.  
3. **Marketing:** cherry-pick 1–2 optional-skills from `ai-marketing-claude`; leave rest uninstalled.  
4. **LinkedIn:** ship draft-only queue skill; later add `anubisalpha/linkedin-mcp` behind MCP enable + content profile.  
5. **Explicit rejects:** linkedin-automator, stickerdaniel scraper, crawl4ai-on-by-default, Agents-Have-Eyes stack, always-on marketing/Agent-Reach MCP.

---

## Evidence footnotes

- Hermes already depends on upstream agent-browser: `package.json` → `"agent-browser": "^0.26.0"`; CLI `agent-browser 0.26.0` on PATH.  
- Local plugins: only `clickup-bridge` enabled; `web/crawl4ai` and opik staged disabled.  
- VPS Agent-Reach skill exists without backends (SSH `hermes-production`, 2026-07-15).  
- LinkedIn Personal OS audit: `~/.hermes/sandboxes/linkedin-jobs/audit.md` (no LinkedIn automation in that cycle).  
- Capability-lab already coded the hard line: `agent_reach` curated only + `public_read_only: true`.
