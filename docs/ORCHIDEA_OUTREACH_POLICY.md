# Orchidea Outreach Policy (Nick Saraev–aligned)

Applies to **cold plain-text** MVP. Proposal-engine campaigns are a separate mode (see proposal skill) and must not blur into cold E1.

## Non-negotiables

1. **Human approval** before any send (`approvals.outbound_email: required`).  
2. **Evidence before language** — only verified facts.  
3. **3 touches max** (E1–E3). Stop forever on human reply, bounce, or unsubscribe.  
4. **Plain text only** — no HTML, pixels, tracking links in cold E1–E2.  
5. **No Success.ai** templates or purchased personalization spam.

## Nick Saraev rules (cold)

| Rule | Spec |
|---|---|
| Length E1 | **< 75 words** (target ≤55 when possible) |
| Format | Plain text; short lines; mobile-first |
| Subject | 2–5 words, lowercase, specific — no clickbait |
| Em dashes | **Banned** (also avoid “ - ” spam patterns and stacked hyphens) |
| Structure | One observation + why it might matter + one small CTA |
| CTA | Soft: “want me to send what I’d change?” — not calendar spam in E1 |
| Personalization | Real trigger only; no fake familiarity |
| Banned openers | “I noticed…”, “hope this finds you”, “quick question”, “touching base”, “just circling back”, “not selling” |
| Banned claims | Invented spend, ROI, “your agency is failing”, guaranteed lead volume |

## Cadence (MVP)

| Touch | When | Content |
|---|---|---|
| E1 | Day 0 | Observation + soft CTA — **no asset dump** |
| E2 | Day 3–5 | **Different** confirmed insight (not “bumping this”) |
| E3 | Day 7–10 | Offer one real free artifact if it exists; else polite close-loop |
| After E3 | — | Nurture/suppress; no E4/E5 in MVP |

Same SpaceMail identity for all three touches.

## Proposal mode exception

When `orchidea-proposal-system-flow` runs **after** a live proposal URL exists, E1 may include that **single** proposal link. Still: approval-gated, evidence-backed, no spam punctuation patterns, ≤3 touches unless Dylan expands policy.

## Lint checklist (pre-approval)

- [ ] Word count E1 < 75  
- [ ] No em dash characters  
- [ ] Every factual clause has `evidence_ref`  
- [ ] One CTA only  
- [ ] Prospect not on suppression  
- [ ] Sender not `*@orchidea.digital` for cold  
- [ ] Approval ID attached
