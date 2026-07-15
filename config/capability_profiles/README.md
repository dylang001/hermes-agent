# Capability profiles (tool routing)

Lightweight **toolset / skill surface** presets for Hermes profiles.  
These are **not** a new runtime — they map onto existing `tools.<platform>.enabled/disabled` and `plugins.enabled` knobs.

## Profiles

| Profile | Intent | Notes |
|---------|--------|-------|
| `daily-ops` | Default chat (capture, status, approvals) | Core files/terminal/memory/skills/web; no MCP bloat |
| `task-os` | ClickUp poller workers | `clickup_task_os` + kanban; concurrency 2 |
| `engineering` | Code / git / tests | Terminal+files+gh; no outreach |
| `research` | Search / reading | web + optional browser; write tools careful |
| `content` | Orchidea writing | skills + files; no publish without approval |
| `prospecting` | Outreach pipeline | gated marketing skills; approval wall |
| `admin` | Platform/config | setup, cron, plugins — human session |
| `browser-ops` | Explicit browser automation | browser toolset on |

## Apply

```bash
# Preview
python -m hermes_cli.capability_profiles show daily-ops

# Write into a Hermes profile's config.yaml (merges tools/plugins keys)
hermes -p <profile> capability-profile apply daily-ops --dry-run
hermes -p <profile> capability-profile apply daily-ops
```

Measure schema size before/after with:

```bash
python -m hermes_cli.capability_profiles measure --profile daily-ops
```
