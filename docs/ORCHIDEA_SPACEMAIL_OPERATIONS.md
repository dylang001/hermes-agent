# Orchidea SpaceMail Operations

Operational runbook for the MVP send/receive path. **Cold send stays blocked** until activation criteria pass.

## Inventory (reported — re-verify before go-live)

| Cluster | Domain | Inboxes (reported) | Cap (week 1) |
|---|---|---|---|
| A | `orchideas.digital` | 5 | 5/day each |
| B | `orchideas.agency` | 3 | 5/day each |
| Blocked | `orchidea.digital` | any | **Never cold-send** |

Total reported capacity: **40/day**. Do not chase 180/day.

GTM example env pattern:

```json
[{"address":"inbox1@orchideas.digital","password":"app-password","smtp_host":"smtp.spacemail.com","smtp_port":587}]
```

Store secrets only in profile `.env` / secret manager — never in skills or ClickUp comments.

## Daily MVP loop

```text
1. READ  — IMAP/poll each active inbox for replies, bounces, provider notices
2. CLASSIFY — apply reply taxonomy; suppress unsub/bounce immediately
3. HEALTH — note deferrals, spam folders reports, unexpected SMTP errors
4. PLAN  — Governor: remaining daily cap per inbox; no over-assign
5. SEND  — only drafts with approval_id + Governor pass
6. LOG   — campaign_events append-only (who/what/why/message-id)
```

## Activation criteria (all required)

1. Sender registry file/table matches real SpaceMail inventory  
2. SPF/DKIM/DMARC aligned on cold domains  
3. Seed tests to Gmail / Outlook / iCloud acceptable  
4. Suppression + duplicate + continuity checks fail-closed  
5. SMTP send of a **self-addressed** test succeeds  
6. IMAP/read path succeeds and alerts  
7. Dylan approves a **named** bounded batch  

## Governor checks (fail closed)

- Suppression hit  
- Duplicate active sequence  
- Prior human reply  
- Verification ≠ deliverable  
- Wrong domain (`orchidea.digital`)  
- Cap exceeded  
- Missing approval_id  
- Missing evidence_refs on claims  

## Cap policy

- Warm-up: stay at ≤5/inbox/day until placement stable  
- Never raise caps in code to “catch Success.ai volume” — that product is banned from planning  
- If spam complaint rate trends up, pause domain cluster first, not just one inbox  

## Hermes integration notes

- Prospecting profile already requires outbound approval  
- Prefer ClickUp Pipeline status transitions: draft → approved → sent  
- `orchidea-prospector` CLI wrapper must use a real Python (`python3`) before automation

## Incident actions

| Symptom | Action |
|---|---|
| Bounce storm | Freeze cluster; suppress addresses; inspect list quality |
| Auth failure | Rotate app password offline; do not paste into chat |
| Reply “stop” / legal | Immediate suppress + human ack |
| Provider throttle | Cut volume 50% same day |
