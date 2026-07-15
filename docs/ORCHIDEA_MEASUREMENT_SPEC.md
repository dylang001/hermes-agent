# Orchidea Measurement Spec

Optimize for **booked qualified calls** and learning quality — not vanity open rates.

## Primary metrics

| Metric | Definition | Target posture |
|---|---|---|
| Qualified bookings | Calls with ICP decision-maker that came from Orchidea sequence | North star |
| Positive reply rate | `positive_interest` + `meeting_request` / delivered | Leading indicator |
| Delivered rate | Accepted by recipient MX / not bounced | Hygiene |
| Complaint / unsub rate | Complaints + hard unsub / delivered | Stay far below Gmail 0.3% spam ceiling; internal pause earlier |
| Evidence coverage | % of sends with ≥1 evidence_ref | ≥95% |
| Approval latency | Draft ready → approval | Process health |

## Secondary (use carefully)

| Metric | Use |
|---|---|
| Overall reply rate | Debug copy/list — not vanity KPI |
| Tier A→booking conversion | Scoring calibration |
| Time-to-first-reply | Cadence tuning |
| Cost per A-tier enriched contact | Collector discipline |

## Explicit non-obsession

- **Do not** optimize daily for open rate, pixel opens, or bot-inflated opens.  
- Plain-text MVP may not even support opens — that is fine.  
- Do not buy tools (incl. Success.ai) to chase open-rate theater.

## Weekly learning packet

1. Top 5 winning observations (with evidence)  
2. Top 5 failures (wrong ICP, weak proof, tone)  
3. Suppression adds  
4. Score tier calibration notes  
5. Caps / domain health  

## Instrumentation

Append-only `campaign_events`: `draft_created`, `approved`, `sent`, `bounce`, `reply_classified`, `suppressed`, `booked`. Prefer event log over CRM as source of truth.
