# Hermes Production Capability Check — 2026-07-16

- **SHA:** `a477cd04a50c5709b3e3fea3cc5935ed7e978ac6`
- **HERMES_HOME:** `/Users/dylanangloher/.hermes`
- **Profile:** `default`
- **Duration:** 13784 ms
- **Counts:** {'pass': 3, 'degraded': 1, 'fail': 1, 'auth_required': 4, 'skip': 0}

| Check | Status | Tested | Command | ms | Remediation |
|-------|--------|--------|---------|-----|-------------|
| ClickUp CLI (clickup-bridge) | **pass** | yes | `hermes clickup workspaces` | 1117 |  |
| Obsidian MCP (Growth OS filesystem) | **pass** | yes | `hermes mcp test obsidian` | 3097 | tools=['create_directory', 'directory_tree', 'edit_file', 'get_file_info', 'list_allowed_directories', 'list_directory'] |
| Composio MCP | **fail** | no | `hermes mcp test composio + tool invoke` | 7023 | Cannot connect to Composio MCP — verify URL and API key |
| Gmail (Himalaya) | **auth_required** | no | `himalaya accounts list` | 3 | Install himalaya + configure IMAP on gated profile when needed |
| GitHub API | **auth_required** | no | `GET /user + GET /user/repos?per_page=1` | 0 | Set GITHUB_TOKEN in HERMES_HOME/.env |
| Cron scheduler | **pass** | yes | `hermes cron list` | 474 |  |
| Mem0 memory | **auth_required** | no | `GET /v1/memories/` | 2 | Set MEM0_API_KEY |
| Web search + extract | **auth_required** | no | `web_search + web_extract (smoke)` | 1 | Set a web search API key (TAVILY/FIRECRAWL/BRAVE/EXA) |
| Delegation / subagents | **degraded** | yes | `delegate_task schema present` | 1873 | Run one bounded delegate_task in chat to reach pass |

