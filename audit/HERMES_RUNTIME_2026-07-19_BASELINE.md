# Baseline: `runtime-2026-07-19`

**Program:** Hermes Reliability Program (post–runtime-architecture phase)  
**Tag:** `runtime-2026-07-19` → `acdeb2f955f2c79ffb07a63a6344a23312a77566`  
**Runtime tip inside tag (hotfix):** `b66356363562efa6d6bb63f8ad4a7bad6ef39f1d`  
**Declared:** 2026-07-19

This is the known-good reference for the frozen runtime + adaptive context policy + Observatory Phase 1 + raise-only compressor alignment. Compare future reliability work against this baseline, not against “whichever commit felt good.”

## Environment identity

| Field | Local | VPS (at tag declaration) |
|-------|-------|--------------------------|
| Branch | `upgrade/hermes-latest-upstream-20260716` | `hermes-phase1-approved` |
| HEAD | `acdeb2f955f2…` (tag) / runtime `b663563635…` | `4a322dcd084a1a3dc1032fe8511896bc3e7a21e0` |
| Relationship | Canonical tip | `git am` of runtime patches → **same trees**, different SHAs |
| Runtime version | `0.18.2` | `0.18.2` (`hermes_runtime_info`) |
| Upstream base | `1d48863b856d7a82412e1b47d87e30d0378b851f` | same lineage |
| Working tree | clean | clean |
| Observatory | N/A (no long-lived local gateway) | enabled, `:9108`, `runtime_frozen=true` |

## Shared production trees (authoritative identity until SHA parity)

| Path | Tree OID |
|------|----------|
| `agent/context_governor.py` | `4f9592795b63e1d4325deed350f7e287761d3a4e` |
| `agent/context_compressor.py` | `7f629211a414c51cbd2f5cf56112445328a35d46` |
| `agent/agent_init.py` | `271df112c508735e34d09d3158332856cb28c80c` |
| `agent/hermes_metrics.py` | `efef89bec6c99270a2ca298f09202a3dcc844b74` |
| Full commit tree (Local tip) | `9bad3e75384434bdb512a68cc082b9b0951cffef` |

## What’s in the box

| Capability | Status |
|------------|--------|
| Runtime freeze / Execution Coordinator | Frozen |
| Prompt-cache capability abstraction | Present |
| Recovery-first governor | Present |
| Adaptive %-of-window context policy + working-memory `SUMMARY_PREFIX` | Present |
| Raise-only adaptive threshold (Codex autoraise safe) | Present |
| Observatory Phase 1 (loopback Prometheus text) | Live on VPS |
| Dashboard / Telegram gateway | Healthy on VPS |

## Benchmark baselines attached to this tag

| Benchmark | Artefact | Notes |
|-----------|----------|-------|
| Context policy P0 (token/stage) | `audit/HERMES_CONTEXT_POLICY_BENCHMARK.*` | Offline; proves adaptive vs absolute 28k |
| Memory reliability (continuity) | `audit/HERMES_MEMORY_RELIABILITY_BENCHMARK.*` | Offline scaffold; primary reliability metric going forward |

## Observatory

Leave Phase 1 collecting for 1–2 weeks. Do not expand metric surface until soak data shows a gap.

## Next program step

See `audit/HERMES_RELIABILITY_PROGRAM.md` — memory reliability first, then long-session evaluation. Deploy SHA parity tracked in `audit/HERMES_DEPLOYMENT_MODEL.md`.
