# Hermes Observatory (Phase 1)

Process-local Prometheus **text** metrics for the gateway. No third-party
observability products are shipped in core. Prometheus/Grafana scrape stacks
belong on the VPS under `/opt/hermes/observatory/` (Phase 2 — not built yet).

## Enable

In `config.yaml`:

```yaml
observatory:
  enabled: true
  bind_host: 127.0.0.1   # non-loopback hosts are refused
  port: 9108
```

Restart `hermes-gateway`. Scrape only from the host:

```bash
curl -sS http://127.0.0.1:9108/metrics
curl -sS http://127.0.0.1:9108/health
```

Default is **`enabled: false`**.

## Security

| Guarantee | How |
|-----------|-----|
| Loopback-only bind | `bind_host` must be `127.0.0.1` / `::1` / `localhost`; `0.0.0.0` refused |
| Loopback-only clients | Handler returns **403** for non-loopback peer addresses |
| Not on dashboard/Caddy | Separate daemon thread — **not** mounted on `:9119` |
| No PII / secrets | Metrics never include prompts, tool arguments, credentials, session IDs, user IDs, chat IDs, or model names |

## Metrics collected

| Metric | Type | Labels (low cardinality) |
|--------|------|---------------------------|
| `hermes_process_uptime_seconds` | gauge | — |
| `hermes_gateway_turns_total` | counter | `outcome=success\|failure` |
| `hermes_gateway_turn_duration_seconds` | histogram | — |
| `hermes_model_calls_total` | counter | `status=ok\|error` |
| `hermes_model_call_duration_seconds` | histogram | — |
| `hermes_tool_calls_total` | counter | `category=…`, `status=ok\|error` |
| `hermes_tool_call_duration_seconds` | histogram | `category=…` |
| `hermes_compression_total` | counter | `kind=auto\|emergency\|hygiene\|overflow\|manual\|governor\|other` |
| `hermes_context_governor_events_total` | counter | `kind=pass\|soft_warning\|compact\|emergency\|blocked\|other` |
| `hermes_context_live_tokens` | gauge | last observed live-transcript estimate |
| `hermes_tokens_prompt_total` | counter | — |
| `hermes_tokens_completion_total` | counter | — |
| `hermes_tokens_cache_read_total` | counter | — |
| `hermes_tokens_cache_write_total` | counter | — |
| `hermes_errors_total` | counter | `kind=api\|tool\|governor_blocked\|compression\|other` |
| `hermes_runtime_info` | gauge (=1) | `git_sha`, `runtime_version`, `runtime_frozen`, `build_time` |
| `hermes_engineering_tasks_total` | counter | `outcome=success\|failure\|aborted\|intervention`, `source=agent_turn\|gateway_turn\|benchmark\|manual` |
| `hermes_engineering_task_duration_seconds` | histogram | `outcome=…` |
| `hermes_engineering_task_cost_usd_total` | counter | `outcome=…` (aggregate USD only) |

**Primary KPI (PromQL sketch):**

```
hermes_engineering_task_cost_usd_total{outcome="success"}
  / hermes_engineering_tasks_total{outcome="success"}
```

Benchmark harnesses should call `record_engineering_task(..., source="benchmark")`
so lab runs stay separable from live `agent_turn` traffic.

**Tool `category` allow-list:** `terminal`, `code`, `file`, `web`, `browser`,
`delegation`, `session`, `skills`, `memory`, `todo`, `mcp`, `kanban`, `other`.
Raw tool names are never exported.

Histogram buckets (seconds): `0.5, 1, 2, 5, 10, 30, 60, 120, +Inf`.

## Explicitly excluded (Phase 1)

- Prompt / message / tool-argument content
- API keys, tokens, cookies, OAuth material
- Session / user / chat / thread IDs
- Model or provider names (cardinality + fingerprinting)
- Per-skill or per-MCP tool names
- Per-session or per-user dollar amounts (aggregate by outcome only)
- Weekly reports, alerts, Grafana, exporters (Phase 2+)

## Code map

| Piece | Path |
|-------|------|
| Registry + HTTP server | `agent/hermes_metrics.py` |
| Gateway start/stop | `gateway/run.py` (`start_gateway`) |
| Turn outcome | `gateway/run.py` (`_handle_message_with_agent`) |
| Engineering-task KPI | `agent/turn_finalizer.py` |
| Model + tokens | `agent/conversation_loop.py` |
| Governor / compression | `agent/conversation_loop.py` |
| Tools | `model_tools.py` |
| Config defaults | `hermes_cli/config.py` → `observatory` |
| Tests | `tests/agent/test_hermes_metrics.py` |

## Overhead

Record helpers are fail-open. When `enabled: false`, each call is a boolean
check only. When enabled, updates are in-process under a lock — no network I/O
on the agent hot path (HTTP is scrape-driven on another thread).
