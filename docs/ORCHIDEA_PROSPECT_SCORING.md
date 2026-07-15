# Orchidea Prospect Scoring

Hermes scorecard for MVP. Persist **raw components** so weights can change without re-scraping.

## Weights (100)

| Component | Weight | What it measures |
|---|---|---|
| **Fit** | **30** | ICP match (multi-location med spa preferred), US service business, size, not franchise/hospital |
| **Ads** | **25** | Credible paid demand (Transparency confirm or strong proxy). Missing ads ≠ auto-zero if other cluster is strong, but caps tier |
| **Funnel** | **25** | Booking/capture friction evidenced (mobile CTA, form, phone-only, broken path) |
| **Timing** | **15** | Recency of hire, launch, review spike, ads change |
| **Proof** | **5** | Can we truthfully attach a give-first artifact this week? |

```text
score = 0.30*fit + 0.25*ads + 0.25*funnel + 0.15*timing + 0.05*proof
```

Each component is 0–100 before weighting.

## Tiers

| Tier | Score | Action |
|---|---|---|
| **A** | ≥ 75 | Enrich after batch approval; priority draft |
| **B** | 55–74 | `research_more` or light enrich if one confirm lands |
| **C** | 40–54 | Nurture / cheap re-scan only |
| Discard | < 40 or hard DQ | Suppress or archive learning only |

Hard disqualifiers override score: non-US, franchise/PE chain, hospital system, suppressed, competitor, no contactable angle, `orchidea.digital` self-domains.

## Component rubrics (abbrev)

### Fit (30)

- 90–100: Multi-location med spa / aesthetics, independent, clear commercial site  
- 70–89: Single-location high-ticket med spa / dental / dermatology  
- 40–69: Adjacent wellness (chiro, PT, TMJ) needing clear angle  
- 0–39: Poor vertical or unclear business

### Ads (25)

- 90–100: Confirmed active Google/Meta ads  
- 60–89: Strong proxy (paid landing params, remarketing pixels) without full confirm  
- 20–59: Unknown  
- 0–19: Explicitly no paid + no demand proxy (still allow other clusters, but tier usually ≤ B)

### Funnel (25)

- 90–100: Multiple evidenced leaks (mobile CTA buried + booking broken + review mentions)  
- 60–89: One clear leak with screenshot/URL  
- 20–59: Suspected only  
- 0–19: Clean book path (often nurture even if ads strong)

### Timing (15)

- Recency windows: ≤30d strong; 30–90d medium; >180d weak unless continuous ads

### Proof (5)

- 100 if screenshot/asset brief ready; 50 if briefable this week; 0 if not

## Evidence gate

A tier **A** draft may only cite facts with `evidence_ref` URLs. Claims without evidence are deleted in lint, not softened into spam.

## Relationship to intent dimensions

Keep PRD’s seven intent dimensions as **analyst notes** under each prospect. They do not replace this scorecard for Hermes MVP routing.
