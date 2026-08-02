# Context Engineering V2 — Observation Mode

**Status:** Observation only. PR #2 (compress race) is deployed.  
**Do not deploy:** PR #3 (V2 restore), PR #4 (pin-cap / short-bypass shadow).  
**Do not change:** `context_engineering_v2.*` in production `config.yaml`.

## Live dashboard

Plugin: `plugins/ce_observatory` (also installable under `$HERMES_HOME/plugins/ce_observatory`).

- Dashboard tab: **CE Observatory** (`/ce-observatory`)
- API: `GET /api/plugins/ce_observatory/summary`
- CLI: `python plugins/ce_observatory/cli_summary.py`

Reads existing JSONL under `$HERMES_HOME/logs/` only.

## Observation window

Run Hermes normally for **3–5 days** (no synthetic soak conversations).

After that window, regenerate a fresh audit:

```bash
# On the machine with HERMES_HOME pointing at production data:
python plugins/ce_observatory/cli_summary.py --json > /tmp/ce_obs_$(date -u +%Y%m%d).json
# Plus any existing scorecard / soak analysis scripts once available.
```

Compare vs the Jul 22 baseline: L4 %, pin counts/tokens, epoch close rate, retrieve frequency, inspect/mutate savings, compression events, API cost, latency.

## Hold criteria for #3 / #4

Keep both PRs **open and undeployed** until explicit approval after the fresh audit.
