# Hermes Composio Validation — 2026-07-16

## Problem

Production capability check marked Composio **pass** after listing 7 tools, but stderr/response contained `404: This page could not be found`. Listing tools alone is not operational health.

## Updated status rules

| Status | Criteria |
|--------|----------|
| **pass** | MCP connects **and** at least one harmless read-only tool invocation succeeds |
| **degraded** | Connect + tool list OK, but tested invocation fails (404, route error, etc.) |
| **fail** | Cannot connect, authenticate, or list tools |
| **auth_required** | Credentials / interactive auth missing by design |
| **skip** | Explicitly disabled in config (`enabled: false`) |

## Implementation

`audit/capability_check_2026-07-16.py` → `check_composio()`:

1. `_probe_single_server("composio")` — connection + list (15s cap).
2. Pick read-only tool (`list*`, `get*`, `search*`, else first tool).
3. `call_tool` with `{}` — classify 404 as **degraded**, not pass.
4. Record exact command, duration, stderr summary, remediation.

## MVP posture

Composio remains **off default chat** (`daily-ops`). Capability check reports truthfully; broken Composio must not block unrelated profiles (MCP per-server isolation + `mcp_discovery_timeout`).

## Verification

```bash
python audit/capability_check_2026-07-16.py
# composio row: pass | degraded | fail — never pass on list-only with 404 body
```
