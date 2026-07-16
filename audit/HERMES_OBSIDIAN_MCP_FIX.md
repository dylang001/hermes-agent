# Hermes Obsidian MCP Fix — 2026-07-16

## Context from operator (Mac)

Obsidian Local REST API + MCP exposes:

| Transport | URL |
|-----------|-----|
| HTTPS MCP | `https://127.0.0.1:27124/mcp/` |
| HTTP MCP | `http://127.0.0.1:27123/mcp/` |
| Auth | `Authorization: Bearer <OBSIDIAN_API_TOKEN>` |

This only works when Hermes runs **on the same machine as the Obsidian app**. It does **not** work from `hermes-production` VPS — nothing listens on VPS `127.0.0.1:27124`, causing ~8s connect timeouts and `Connection closed`.

## Intended production architecture (MVP)

**One path:** stdio `@modelcontextprotocol/server-filesystem` scoped to Growth OS only.

| Host | Vault path |
|------|------------|
| VPS | `/opt/hermes/data/obsidian/Growth OS` |
| Mac (optional local) | `~/Documents/Obsidian Vault/Growth OS` |

Default tool include: `read_file`, `list_directory`, `search_grep`, `get_file_info`.

Default writes: `Growth OS/Drafts/Hermes/` only (policy — not enforced by MCP mount; skill + approvals).

**Remove / disable:**

- `OBSIDIAN_MCP_URL` pointing at localhost HTTP(S)
- `/root/obsidian-vault` mount args
- Parallel filesystem + unreachable HTTP bridge

## Code changes

- `hermes_cli/obsidian_mcp_normalize.py` — detect localhost HTTP / stale `/root/obsidian-vault`, emit filesystem config.
- Config migration **v34** — auto-rewrite `mcp_servers.obsidian` on `hermes update` / migrate.

## Mac vs VPS

| Surface | Obsidian MCP |
|---------|----------------|
| Mac desktop beside Obsidian | HTTP MCP to `127.0.0.1:27124` is valid **only for local Hermes** |
| VPS / Telegram / Task OS | Filesystem MCP on synced Growth OS — **never** localhost HTTP |

## Verification

```bash
hermes mcp test obsidian          # connect <15s, tools listed
# Vault INDEX.md readable
# search_grep / list_directory under Growth OS only
# no access outside Growth OS mount
```

Capability check: `audit/capability_check_2026-07-16.py` → `obsidian_mcp` check.

## Operator actions (VPS)

1. `hermes update` or run config migrate (v34).
2. Confirm `mcp_servers.obsidian` has `command` + `args` ending in `/opt/hermes/data/obsidian/Growth OS` — no `url`.
3. Remove `OBSIDIAN_MCP_URL` from `.env` if present (secrets file only; not needed for filesystem MCP).
4. `sudo systemctl restart hermes-gateway` after config change.
