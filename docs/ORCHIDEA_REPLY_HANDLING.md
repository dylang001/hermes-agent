# Orchidea Reply Handling

## Classes

```text
positive_interest
meeting_request
send_info
objection_existing_agency
objection_budget
objection_timing
not_interested
unsubscribe
bounce
out_of_office
other_human_reply
```

**Any human reply stops automated touches immediately.**

## Actions

| Class | Hermes action | Human |
|---|---|---|
| `positive_interest` / `meeting_request` | Draft reply + approved Cal.com; alert | Send / book |
| `send_info` | Deliver promised artifact only | Confirm |
| `objection_existing_agency` | Soft outside-view angle draft | Approve tone |
| `objection_budget` / `timing` | Log re-entry date only if new future signal | Optional |
| `not_interested` | Suppress soft (90d) | — |
| `unsubscribe` | Hard suppress | — |
| `bounce` | Hard suppress; verify path audit | — |
| `out_of_office` | Pause sequence; resume once after end date | — |
| `other_human_reply` | Alert; no auto-send | Classify |

## Alerting

- Primary: Telegram chat id from ops config (gtm example `ORCHIDEA_TELEGRAM_CHAT_ID`)  
- Secondary: ClickUp Pipeline comment + status `waiting` / tag for review  
- Include: prospect, inbox, class, snippet (redact PII beyond need), suggested next action  

## SLA

- Positive / meeting: alert within 15 minutes of poll  
- Unsubscribe / bounce: suppress within same poll cycle  
- Poll interval MVP: ≤30 minutes during send weeks; daily off-weeks  

## Call prep (booked only)

Brief must include: company, contact, originating signals + evidence URLs, hypothesis/counter, funnel issue, safe claims, ask. No invented metrics.
