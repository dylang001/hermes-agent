# Orchidea Signal Taxonomy

Operational glossary for collectors and scoring. A signal is a **clue**, not intent.

## Principles

1. Store raw evidence (URL, timestamp, snippet hash) before interpretation.  
2. Every signal gets a hypothesis **and** a counter-hypothesis.  
3. Prefer cheap public HTTP checks before paid APIs.  
4. Social/Reddit: research first; never mass-DM.

## Signal families

| Family | Code | Example | Confirm with |
|---|---|---|---|
| Hiring / capacity | `SIG_HIRE_*` | Front-desk / intake / marketing coordinator | Domain resolve + booking/HTTP triage |
| Paid demand | `SIG_ADS_*` | Google/Meta ads live or recently active | Ads Transparency / Serper confirm (positive-only) |
| Funnel leakage | `SIG_FUNNEL_*` | Phone-only CTA, broken book flow, slow LCP | Playwright or browser shortlist |
| Reputation friction | `SIG_REV_*` | Reviews mentioning booking/wait/response | Public GBP/maps extract |
| Expansion | `SIG_EXPAND_*` | New location / service page | HTTP + optional geo |
| Competitive pressure | `SIG_COMP_*` | Competitor easier book/find | Manual note + URL |
| Direct pain language | `SIG_SOCIAL_*` | Owner post about leads/agency | Identity resolution required before enrich |
| Contactability | `SIG_CONTACT_*` | Named owner email pattern found | Enrichment only after qualify |

## Intent clusters (qualification shapes)

| Cluster | Required mix | Typical angle |
|---|---|---|
| Demand + leakage | Ads **or** strong demand proxy + funnel issue | Fix post-click path |
| Growth + weak infra | Hiring/expansion + weak booking/tracking | Capture growth |
| Operational pressure | Intake hire + review/booking pain | Reduce front-desk pressure |
| Competitive pressure | Competitor ease + own friction | Outside conversion view |
| Direct pain | Attributed operator statement | Answer stated pain only |

## Safe claim classes

| Class | Agent may say | Agent must not say |
|---|---|---|
| Observed | “Hiring front desk”, “CTA is phone-only on mobile” | “Team overwhelmed”, “wasting ad spend” |
| Inferred (hedged) | “This **may** create friction before booking” | Absolute revenue/ROI claims |
| Forbidden without human | Agency performance, invented spend | |

## Routing labels

| Route | Meaning |
|---|---|
| `ready_for_enrichment` | Cluster + ICP + proof opportunity |
| `research_more` | Missing one cheap confirmation |
| `nurture` | Good fit, weak timing |
| `discard` | Bad fit / suppressed / no angle |
| `ready_for_draft` | Verified contact + approved angle |
| `ready_for_send` | Draft + Governor + approval ID |

## Lean collector order (MVP)

1. Dedupe + suppression  
2. Discovery (one surface)  
3. Domain resolve  
4. HTTP triage  
5. Score  
6. Optional ad confirm / Playwright on shortlist only  
7. Enrich → verify → draft (approval)

Deferred until proven need: Meta library bulk, PageSpeed API every lead, LinkedIn scrape, new-location spider.
