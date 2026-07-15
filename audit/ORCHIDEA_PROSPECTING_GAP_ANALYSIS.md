# Orchidea Prospecting — Gap Analysis (Phase 7H)

**Date:** 2026-07-15  
**MVP target:** SpaceMail read → lean signals → score+evidence → approval-gated 3-touch → reply classify/alert  
**Policy:** No Success.ai. No cookie theft / CAPTCHA bypass / stealth. Prefer free/existing tools.

---

## Gap matrix

| Capability | Need for MVP | Current | Gap | Minimal fix |
|---|---|---|---|---|
| SpaceMail inbox read | Required #1 | SMTP send example in gtm; no Hermes skill/runbook wired | No IMAP/API read + health check in operator loop | Add `docs/ORCHIDEA_SPACEMAIL_OPERATIONS.md` procedure + small read script using existing SMTP/IMAP creds; prove one inbox round-trip |
| Sender registry | Required | Reported HyperAgent inventory; gtm JSON example | Hermes has no live registry table/file | Postgres or SQLite registry under HERMES_HOME; import 8 inboxes; cap=5 until warmup proven |
| Suppression | Required | Designed / file I/O reported | Not fail-closed in Hermes send path | Import suppression store; Governor fail-closed |
| Lean signal collectors | Required #2 | Hiring/HTTP/ad-confirm reported; gtm Ad Discovery + Brave/Places | Not callable as one Hermes dry-run command | Port **one** discover path (hiring OR Places+HTTP); defer Meta library etc. |
| Serper/SerpAPI ad confirm | Optional confirm | Example `SERPER_API_KEY`; PRD SerpAPI ads confirm | Keys not in Hermes `.env` probe | Use only after shortlist; prefer Serper if already budgeted in gtm |
| Scoring + evidence | Required #3 | Dual models (PRD intent vs gtm 70-threshold) | No single Hermes scorer with A/B/C tiers | Adopt `docs/ORCHIDEA_PROSPECT_SCORING.md` (fit/ads/funnel/timing/proof) |
| Enrichment (Apify→Hunter→Apollo) | Post-qualify only | Skills/examples exist | Credits can burn pre-qualify | Enforce route=`ready_for_enrichment` gate |
| Email verify | Pre-send | Contract in PRD | No wired verifier | Add one verifier behind Governor; map deliverable/risky/undeliverable/unknown |
| Drafting (Nick Saraev) | Required | Downloads JSON + generic cold-email skill | Official Saraev skills not installed; length rules inconsistent | Install Saraev skills; enforce `<75` words E1 / 3 touches from outreach policy |
| Approval gate | Required #4 | `prospecting.yaml` approvals | No ClickUp/Hermes draft queue linked to SpaceMail send | Draft → ClickUp Pipeline status + explicit approval ID before send |
| 3-touch send | Required #4 | Resend/SMTP stubs | Policy conflict (PRD E1–E5 vs MVP 3) | Cap at **3** touches for MVP; stop on reply |
| Reply classify + alert | Required #5 | Classes in PRD; gtm Router agent concept | No inbox poller alerting Telegram/ClickUp | IMAP poll + classify + alert to Telegram chat from example |
| Proposal engine | Later | Skill flow + API contracts | Depends on missing services/skills; heavy asset path | Keep offline until 3-touch email MVP works |
| Zoho | Later | Dormant MCP | Would resurrect CRM sprawl | Skip; event log first, optional HubSpot/ClickUp mirror |
| Playwright audits | Shortlist only | Available | Can become scraping farm | Queue only for tier A research_more |
| Success.ai | Never | Absent | Must not re-enter requirements | Explicit ban in scoring/ops docs |

---

## Conflicts to resolve (do not “both”)

| Conflict | Choose for Hermes MVP |
|---|---|
| Ads-first gate vs signal clusters | **Signal clusters**; ads = strong evidence, not universal hard gate |
| PRD E1–E5 vs lean volume | **3 touches max** (E1–E3) |
| PRD E1 “no links” vs proposal engine “E1 has proposal URL” | Separate modes: **cold plain-text MVP** vs **proposal campaign** (only after proposal record exists) |
| Resend vs SpaceMail | **SpaceMail** for cold; park Resend |
| `orchidea.digital` senders | **Hard block** cold send |
| HubSpot (gtm) vs Zoho (legacy) | Neither required for MVP; ClickUp Pipeline is CRM-of-record |
| Intent-quality weights vs fit/ads/funnel/timing/proof | Use **fit/ads/funnel/timing/proof** for Hermes scorecard (see scoring doc); keep intent dimensions as research notes |

---

## Free-first stack (approved direction)

1. ClickUp Pipeline + Ops Task OS (already live)  
2. Hermes web + optional Crawl4AI public extract  
3. Brave / Google Places only if already keyed in gtm  
4. SpaceMail SMTP/IMAP already contracted  
5. Apollo People Search **free** phase before paid enrich  
6. OpenCLI / public research for social intent — **read only**

Paid second: Apify DMEF, Hunter verify, Serper/SerpAPI ad confirm, Browser-Use only if local browser insufficient.

---

## Definition of done (MVP)

- [ ] SpaceMail: read one inbox; parse a reply; record event  
- [ ] Discover ≥10 ICP domains dry-run with evidence URLs stored  
- [ ] Score to A/B/C with component breakdown  
- [ ] Produce 3 drafts that pass outreach policy lint  
- [ ] Send 0 live emails until Dylan approval of a named batch  
- [ ] After approval: ≤3 touches / prospect; auto-stop on reply  
- [ ] Alert on positive / unsubscribe / bounce  

---

## Explicit non-work

- Success.ai (any tier)  
- Cookie CLIs / Agent-Reach cookie unlocks  
- Scrapling stealth / CAPTCHA bypass  
- Mass Reddit DMs or LinkedIn automation  
- Autonomous weekday send cron before activation criteria
