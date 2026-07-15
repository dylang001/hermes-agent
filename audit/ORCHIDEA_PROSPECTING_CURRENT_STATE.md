# Orchidea Prospecting — Current State (Phase 7H)

**Date:** 2026-07-15  
**Sources:** Hermes live paths, `Orchidea_Prospector_Hermes_PRD.md` (2026-06-19), `~/orchidea-gtm`, ClickUp canonical IDs, capability inventory.  
**Non-goals:** Success.ai is **out of scope** and must not appear in tooling assumptions.

---

## One-line status

Signal-led Orchidea outbound is **designed and partially scaffolded**, but **not a connected Hermes MVP pipeline**. Live cold send remains blocked pending SpaceMail proof, state integrity, evidence scoring, and human approval.

---

## What exists where

### A. Hermes (operator OS)

| Asset | Path / ID | State |
|---|---|---|
| ClickUp Orchidea space | `901511216857` | Live |
| Prospecting list `Pipeline` | `901524109891` | Statuses prospecting → won/lost |
| Ops list (Task OS) | `901524109892` | Poller for `next` + `hermes-ready` |
| Capability profile `prospecting` | `config/capability_profiles/prospecting.yaml` | Toolsets trimmed; `outbound_email: required` |
| Proposal orchestration skill | `~/.hermes/skills/orchidea/orchidea-proposal-system-flow` | Present; depends on **missing** `saraev-direct-proposal-outreach` |
| Saraev skills | Downloads JSON only (`~/Downloads/skill-saraev-*.json`) | **Not installed** under `~/.hermes/skills` |
| Apollo / cold-email / cold-outreach | Symlinks into Hermes skills from `~/.agents/skills` | Draft/enrich helpers, not wired to SpaceMail |
| Zoho CRM MCP | Configued historically; Phase 6 **not** an active MCP child | Keep dormant until CRM mirror needed |
| Native SerpAPI/Serper keys in Hermes `.env` | Not in observed relevant key set | Unconfigured on Hermes home |
| Success.ai | — | **None — do not add** |

### B. Orchidea GTM repo (`~/orchidea-gtm`)

Standalone SDR codebase (LangGraph-oriented README; packages present):

| Area | Package / file | Notes |
|---|---|---|
| CLI entry | `~/.local/bin/orchidea-prospector` → `packages.cli` | **Broken locally** (`python: command not found`) |
| Collectors | `packages/collectors/ad_discovery.py` | Ads discovery scaffolding |
| Integrations | Apify, Brave, Resend, DB config | `.env.example` only — secrets not audited here |
| Delivery | `packages/delivery/smtp_sender.py` | SpaceMail SMTP JSON pattern in `.env.example` |
| Scoring | `packages/agents/scorer.py` + tests | Weighted score; README says threshold 70 |
| Detectors | Playwright-oriented (per README) | Demand-leakage / funnel checks |
| DB | Supabase migrations present; `data/` empty locally | Canonical Hermes Postgres from PRD **not** standing in Hermes home |
| Default sender domain in example | `SENDER_DOMAIN=orchidea.digital` | **Conflicts** with PRD cold-block on `orchidea.digital` |

Reported/example providers in GTM `.env.example` (capability presence, not live verification):

- Discovery: Google Places, Brave, Apify Google/Meta ads actors  
- Optional fallback: Hunter, Serper  
- Send: Resend **or** SpaceMail SMTP JSON  
- CRM: HubSpot (not Zoho)  
- **No Success.ai**

### C. HyperAgent / PRD reported state (June 2026 — treat as historical until re-exported)

Reported: Prospect Master, Sender Registry, Suppression, Signal Evidence, Campaign Event tables; Deliverability Governor; intent engine; hiring + HTTP triage + SerpAPI ads confirm dry-run finding three accounts. **Source scripts for several of those pieces were not in the Hermes pack** — still a migration gap.

Eight SpaceMail inboxes reported on `orchideas.digital` / `orchideas.agency`, week-1 cap 5 each (40/day). `orchidea.digital` cold-blocked. **No live enrichment/send approved** for the dry-run accounts at PRD time.

---

## Tooling map (what to use vs ignore)

| Tool | Role for Orchidea | Hermes today |
|---|---|---|
| **SpaceMail** | Cold send path | Spec + SMTP example in gtm; **not proven end-to-end in Hermes** |
| Serper / SerpAPI | Ad transparency / SERP confirm | Example keys in gtm; Hermes core web prefers native/Exa |
| Apify | Ads + Decision Maker Email Finder (primary enrich in PRD) | Client stub in gtm |
| Playwright | Shortlist funnel audit only | Available via system/Meet/gtm; not gated pipeline |
| Hunter | Enrich fallback | Example only |
| Apollo | Secondary enrich / list build | Skill present; paid credits discipline required |
| Email verify | Pre-send deliverability class | Policy in PRD; no Hermes-native verifier wired |
| Zoho | Legacy send/CRM | MCP dormant; **not** MVP send layer |
| Proposal engine | High-touch visual proposals | Skill flow present; APIs + copy skill incomplete |
| Suppression | Hard block list | Designed in PRD/gtm; must be fail-closed before send |
| Evidence gates | Claims ↔ artifact URLs | Required by proposal skill + Saraev copy rules; not automated |
| Success.ai | — | **Forbidden / unused** |

---

## MVP operating sequence (canonical)

```text
1. SpaceMail read (inbox health, replies, bounces) 
2. Signal collection (lean: hiring/domain/HTTP triage ± targeted ad confirm)
3. Scoring + evidence attach (tiers A/B/C)
4. Approval-gated 3-touch send via SpaceMail
5. Reply classify + alert (stop sequence on human reply)
```

Anything that adds collectors, CRM writes, or proposal-asset generation sits **after** this loop is dry-run proven.

---

## Evidence confidence

| Claim | Class |
|---|---|
| ClickUp Pipeline/Ops IDs | Live/canonical |
| Capability profile requires email approval | Code-inspected |
| Proposal skill references missing Saraev skill | Code-inspected |
| GTM SpaceMail SMTP pattern | Code-inspected (example) |
| Eight SpaceMail inboxes / 40-day cap | Reported in PRD — re-verify before send |
| `orchidea.digital` cold-blocked | PRD policy — keep |
| Intent engine / suppression.py in Hermes tree | Not present as live Hermes package |

---

## Biggest current blockers

1. **No sealed send path in Hermes** — SpaceMail ops unproven; Governor/suppression not imported as a Hermes service.  
2. **State store not canonical on Hermes** — PRD wants Postgres; gtm points at Supabase; HyperAgent tables are legacy.  
3. **Scoring/evidence not operationalized** as a single CLI Hermes agents can run with ClickUp handoff.  
4. **Copy/policy skills incomplete** — Saraev proposal/cold skills not installed; proposal flow cannot finish.  
5. **Sender domain conflict** — gtm example still defaults to blocked `orchidea.digital`.  
6. **`orchidea-prospector` CLI broken** locally (`python` missing on PATH in wrapper).

See also: `audit/ORCHIDEA_PROSPECTING_GAP_ANALYSIS.md`.
