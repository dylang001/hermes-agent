# Hermes Composio Validation — updated 2026-07-20

## Problem (historical)

Production capability check marked Composio **pass** after listing 7 tools, but
stderr/response contained `404: This page could not be found`. Listing tools
alone is not operational health.

A second failure mode (2026-07-20): agents diagnosed Composio as "broken"
because `MCP_COMPOSIO_API_KEY` returned HTTP 401 from the Python SDK, while
Hermes MCP OAuth was healthy and Zoho Mail connections were ACTIVE.

## Auth model (source of truth)

| Surface | Auth | Used by Hermes agent? |
|---------|------|------------------------|
| `mcp_servers.composio` → `https://connect.composio.dev/mcp` | OAuth 2.1 PKCE (`auth: oauth`) | **Yes** |
| Python `composio` SDK + `COMPOSIO_API_KEY` / `MCP_COMPOSIO_API_KEY` | Server API key | **No** (misleading if keys are stale) |
| Local `composio` CLI login | OAuth session | Optional helper only |

## Updated status rules

| Status | Criteria |
|--------|----------|
| **pass** | MCP connects **and** at least one harmless read-only tool invocation succeeds (prefer `COMPOSIO_SEARCH_TOOLS` or `COMPOSIO_MANAGE_CONNECTIONS` list) |
| **degraded** | Connect + tool list OK, but tested invocation fails (404, route error, etc.) |
| **fail** | Cannot connect, authenticate, or list tools via **OAuth MCP** |
| **auth_required** | OAuth tokens missing — run `hermes mcp login composio` |
| **skip** | Explicitly disabled in config (`enabled: false`) |

**Do not** mark fail solely because `COMPOSIO_API_KEY` / `MCP_COMPOSIO_API_KEY` 401.

## Config traps

1. Listing any MCP server name (e.g. `obsidian`) in `platform_toolsets.<platform>`
   creates an MCP **allowlist** and excludes other servers (including `composio`).
2. `mcp_discovery_timeout` should be ≥10s when Composio is enabled.

## Agent path

See `~/.hermes/skills/integrations/composio/SKILL.md`.

Zoho Mail send: toolkit `zoho_mail`, slug `ZOHO_MAIL_MESSAGES_SEND_EMAIL`,
from `dylan@orchidea.digital`, `accountId` from `ZOHO_MAIL_ACCOUNTS_LIST_ACCOUNTS`.

## Verification

```bash
hermes mcp test composio
# Connected + 7 COMPOSIO_* tools

# Platform resolver must include composio for cli:
python3 -c "
from hermes_cli.config import load_config
from hermes_cli.tools_config import _get_platform_tools
print('composio' in _get_platform_tools(load_config(), 'cli'))
"
```
