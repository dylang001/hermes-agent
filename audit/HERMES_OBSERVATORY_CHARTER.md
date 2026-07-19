# Hermes Observatory — Charter

**Status:** Phase 1 live on VPS (soak 1–2 weeks before Phase 2 scrape stack)  
**Date:** 2026-07-19  
**Constraint:** Prometheus/Grafana/exporters are **VPS ops** under `/opt/hermes/observatory/`. They do **not** land as new third-party product plugins under `plugins/` (AGENTS.md). Hermes core only exposes a scrapeable metrics surface + weekly report. Do **not** build dashboards until soak data shows which metrics are useful.

## Philosophy

Monitor Hermes itself, not just the host.

Recover-first context governor (backpack metaphor) is the product UX; Observatory measures whether that UX stays healthy.

## Architecture

```
Hermes gateway/dashboard
  └─ localhost :9108/metrics   (Prometheus text)
         ↑ scrape
Prometheus (+ node_exporter, systemd_exporter)
         ↑
Grafana dashboards + alertmanager
         ↑
Weekly health report (cron → Telegram / file)
```

## Phases

### Phase 1 — Hermes metrics surface (in-repo)
- Process-local counters/histograms (no external SaaS)
- `GET /metrics` on loopback only
- Config: `observatory.enabled` in `config.yaml` (default off; enable on VPS for soak)
- Emit: requests, success/fail, latency, model/tool calls, live tokens, compressions (auto/emergency), cache read share when known
- Runtime identity: `hermes_runtime_info{git_sha,runtime_version,runtime_frozen,build_time}`
- Primary KPI: `hermes_engineering_tasks_*` + aggregate `hermes_engineering_task_cost_usd_total` (cost per successful engineering task)

### Phase 2 — VPS stack (ops, not git plugins/)
- docker-compose: prometheus, grafana, node_exporter, systemd_exporter
- Scrape Hermes `:9108`, node, systemd units `hermes-gateway` / `hermes-dashboard`
- Alert rules: telegram down, gateway restarts >3/h, compression every request, cache hit collapse, latency 2×, credit spike proxy

### Phase 3 — Weekly health report
- Sunday cron: requests, success rate, latency, avg live tokens, auto/emergency compressions (target emergency=0), cache hit %, uptime, restarts, WoW deltas
- Deliver via Telegram + `/opt/hermes/home/reports/`

## Non-goals
- Shipping Grafana/Langfuse/Datadog as new in-tree product plugins
- Optimizing raw token spend as the north star (use Engineering Scorecard)

## Acceptance
- Dashboard + gateway scrapeable
- One Grafana board with runtime/context/cache panels
- Zero emergency-compaction alerts in a quiet week
- Sunday report lands without manual steps
