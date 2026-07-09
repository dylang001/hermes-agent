# Phase 6 Read-Only VPS Parity Audit

Generated: 2026-07-09

Scope: read-only audit only. No files, services, credentials, MCP configuration, schedules, memory, or provider routing were changed.

## Local Hermes

- path: `/Users/dylanangloher/.hermes/hermes-agent`
- branch: `main`
- HEAD: `7d23fad2c25968aa5ebb694e7de36ab33c281002`
- upstream relation: `behind 41, ahead 12` relative to `origin/main`
- working tree: dirty from local staged-progress work; no deployment performed
- intelligence env flags in current shell: none set
- sanitized provider config:
  - primary provider: `opencode-go`
  - fallback providers: `opencode-go` only
  - fallback models: `glm-5.2`, `deepseek-v4-pro`, `deepseek-v4-flash`, `kimi-k2.7-code`, `qwen3.7-max`
  - external memory provider: empty / unset in local config
  - Telegram config present
- Desktop connection:
  - mode: `remote`
  - url: `https://hermes.meetlyra.live`
  - token redacted

## VPS Hermes

- host: `hermes-agent-2025`
- production path: `/usr/local/lib/hermes-agent`
- branch: `main`
- HEAD: `58f22c2f1069d651b75ab90a52901c5cf1f8a192`
- upstream relation: `behind 41, ahead 12` relative to `origin/main`
- working tree: no dirty files were shown by the audited short status beyond the branch relation
- enabled intelligence flags in `hermes-gateway.service` / `hermes-dashboard.service` environments: none found
- active Hermes services:
  - `hermes-dashboard.service`: active/running
  - `hermes-gateway.service`: active/running
- active Hermes processes:
  - dashboard: `/usr/local/lib/hermes-agent/venv/bin/hermes dashboard --port 9119 --no-open --skip-build`
  - gateway: `/usr/local/lib/hermes-agent/venv/bin/python -m hermes_cli.main gateway run`
  - slash workers: `tui_gateway.slash_worker --model minimax-m3`
- active MCP child processes:
  - `exa-mcp-server`
  - `@modelcontextprotocol/server-filesystem /root/obsidian-vault`
  - no active Zoho MCP child process observed
- sanitized VPS config highlights:
  - primary provider: `opencode-go`
  - fallback provider: `opencode-go`
  - fallback model: `minimax-m3`
  - memory provider: `mem0`
  - mcp discovery timeout: `30`
  - configured MCP server URLs include Composio, Exa, Parallel, filesystem/Obsidian, and Zoho entries, but active child processes were Exa and Obsidian only

## Parity Notes

- Local and VPS are not on the same commit:
  - local: `7d23fad2c25968aa5ebb694e7de36ab33c281002`
  - VPS: `58f22c2f1069d651b75ab90a52901c5cf1f8a192`
- Both report the same upstream relation (`behind 41, ahead 12`), so a deployment plan must validate lineage before applying patches.
- Local config and VPS config differ materially:
  - local fallback chain contains several OpenCode Go models
  - VPS fallback chain observed in sanitized config is OpenCode Go / `minimax-m3`
  - local external memory provider is empty/unset
  - VPS external memory provider is `mem0`
- No Phase 1-6 intelligence flags were enabled on the VPS services.
- No MCP startup regression was observed during the audit; this was a read-only process listing, not a service restart.

## Rollback Path For A Future Approved VPS Application

No rollback was needed in this audit because nothing was changed. For a future approved application:

1. Capture `git rev-parse HEAD`, `git status --short --branch`, service environment, and a tar/git bundle backup before touching `/usr/local/lib/hermes-agent`.
2. Apply the approved patch only.
3. Keep all intelligence flags disabled unless explicitly approved.
4. Run the approved VPS test commands.
5. If rollback is required, restore the previous commit or backup snapshot and restart only the explicitly approved service(s).
