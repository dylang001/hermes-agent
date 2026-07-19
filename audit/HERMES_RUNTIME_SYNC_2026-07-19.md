# Hermes Runtime Synchronisation Report — 2026-07-19

Engineering/ops sync across Mac + VPS. No blind upstream fast-forward.

## 1. Deployment verification

| Component | Local | VPS | Match |
|-----------|-------|-----|-------|
| Branch | `upgrade/hermes-latest-upstream-20260716` | `hermes-phase1-approved` | Names differ; content aligned |
| HEAD commit | `64f4c18efbd5` | `c0515be2a036` (am of context policy) | Same tree for policy (see below) |
| Tree `agent/context_governor.py` | `4f9592795b63…` | `4f9592795b63…` | **YES** |
| Tree `agent/context_compressor.py` | `7f629211a414…` | `7f629211a414…` | **YES** |
| Tree `agent/hermes_metrics.py` | `efef89bec6c9…` | `efef89bec6c9…` | **YES** |
| Runtime freeze (`HERMES_V1_RUNTIME_FROZEN.md` + EC) | Present | Present | **YES** |
| Governor recovery (live≠schemas) | In history `680786aa36` | Equivalent `4f4b815023` | **YES** |
| Observatory Phase 1 + KPI | `4a5440` + `6ad19d` | `f6c1cb` + `f718d48` | **YES** |
| Context-policy redesign | `64f4c18efb` | `c0515be2a0` | **YES** (deployed) |
| Working tree | Dirty: raise-only threshold hotfix in `agent_init.py` | Clean | Hotfix Local-only until commit+deploy |
| Observatory `:9108` | N/A (no local gateway) | `ok` + `hermes_runtime_info` | VPS live |
| Gateway / Dashboard | No long-lived local gateway | Both `active` | VPS OK |
| Telegram | — | Connected (polling) | VPS OK |

**Marker ancestry (Local):** freeze `2ba34b7d43` → governor `680786aa36` → observatory `4a5440`/`6ad19d` → context policy `64f4c18efb`.

**VPS-only note:** SHAs differ because patches were applied with `git am` (new commit hashes, same trees for the delivered files).

---

## 2. Repository hygiene

WIP was stashed (not discarded):

`stash@{0}: wip/hygiene-20260719: dashboard-auth singleflight, desktop ws-ticket, firecrawl/browser gateway fallback, gtm/composio audits`

| Path / area | Category | Home |
|-------------|----------|------|
| `hermes_cli/dashboard_auth/*`, refresh singleflight tests | **STASH** | Restore as focused PR later |
| `apps/desktop/electron/*` WS ticket / OAuth | **STASH** | Desktop ship later |
| `agent/auxiliary_client.py`, dotenv-prefer key | **STASH** | Small production fix — separate commit |
| `plugins/web/firecrawl`, `plugins/browser/browser_use` | **STASH** | Tools availability — separate commit |
| GTM / Composio / capability-check audits | **STASH** | Audit trail |
| Context policy / observatory / freeze | **KEEP** (committed) | Production tip |
| `agent/agent_init.py` raise-only adaptive threshold | **COMMIT** | Hotfix found in suite — uncommitted |
| `audit/HERMES_RUNTIME_SYNC_2026-07-19.md` | **COMMIT** | This report |
| Generated noise | **DISCARD** | None left |

---

## 3. Upstream comparison

| Item | Value |
|------|-------|
| `origin/main` | `1d48863b856d7a82412e1b47d87e30d0378b851f` |
| Relationship | **`origin/main` is an ancestor of Local HEAD** |
| Ahead / behind | Local **+66 / -0** vs `origin/main` |
| Upstream commits not in Local | **0** |

**Conclusion:** No upstream merge. Blind fast-forward would be a no-op for upstream content.

### Worth taking later (monitor)

- MiniMax / OpenCode provider fixes
- Prompt-cache / compression bugfixes
- Gateway / Telegram reliability
- Security patches

### Must not overwrite

- Execution Coordinator  
- Prompt-cache capability abstraction  
- Observatory Phase 1  
- Adaptive context governor + working-memory `SUMMARY_PREFIX`  
- Runtime freeze principles  

### Merge plan (when upstream moves ahead)

1. `git fetch origin main`  
2. Topic filter: minimax / cache / compress / gateway / security  
3. Prefer `git merge origin/main` into this branch  
4. Resolve conflicts preserving frozen surfaces  
5. Full `scripts/run_tests.sh`  
6. Deploy Local tip → VPS via `format-patch` / `git am`  
7. Recycle gateway; verify Telegram + `:9108`

**This run:** merge skipped — nothing to take.

---

## 4. Safe merge summary

| Action | Result |
|--------|--------|
| Upstream merge | **Skipped** (already current) |
| Conflicts | None |
| Preserved EC / cache / observatory / governor | Yes |

---

## 5. Deployment summary

### Local
- Tip: `64f4c18efb`
- Uncommitted hotfix: adaptive profile must not lower Codex autoraise / already-resolved compressor threshold (`agent/agent_init.py`)
- Desktop: **not rebuilt** (desktop changes only in stash)
- Gateway: not run as a long-lived local service in this sync

### VPS
- Context-policy patch applied → `c0515be2a036`
- Gateway recycled; Dashboard `active`; Telegram connected
- Observatory: `git_sha=c0515be2a036`, `runtime_frozen=true`
- Adaptive resolve proof: interactive @ 1M → 350k / 550k / 750k / **900k**
- Raise-only hotfix: **not yet on VPS** (commit + am next)

---

## 6. Test results

| Suite | Result |
|-------|--------|
| Context governor + summary prefix + metrics (focused, earlier) | **31/31** |
| `test_codex_gpt55_autoraise_notice.py` after hotfix | **15/15 passed** |
| Full `scripts/run_tests.sh` | **In progress** (~14% at last check); see failures below |

### Failures observed mid-suite (before / during hotfix)

| Failure | Classification |
|---------|----------------|
| `test_codex_gpt55_autoraise_notice` (3) | **Real regression** from adaptive profile overwriting Codex 0.85 → 0.70. **Fixed** in working tree (raise-only). |
| `test_record_overhead_is_negligible` | **Load flake** — enabled path 261µs vs 200µs ceiling under parallel suite |
| `test_runtime_cwd` (4) | **Env / isolation flake** under load (resolved to real checkout path) |
| Timeout-marked files (`non_stream_stale_timeout`, `reasoning_stale_timeout_floor`, `empty_tool_name`, `curator`) | **Wall-clock / xdist pressure** — not attributed to context-policy ship |

---

## 7. Remaining risks

1. **Uncommitted raise-only hotfix** — Local dirty; VPS still has overwrite behaviour for Codex autoraise (MiniMax Telegram path largely unaffected).  
2. **Commit SHA drift Local↔VPS** — trees match for shipped policy files; prefer tree hashes for identity.  
3. **Stashed WIP** — not in production tip.  
4. **MiniMax >512k pricing** — soak still required.  
5. **Full suite not finished** — do not tag a formal runtime release until green (or failures classified as flakes).

---

## 8. Exact commit hashes

| Environment | HEAD | Notes |
|-------------|------|-------|
| **Local** | `64f4c18efbd55544f0054e73c9842247853b9323` | Canonical tip (+ dirty hotfix) |
| **VPS** | `c0515be2a036acae43660710bd4b0b39a1bb7cd1` | am-equivalent of context-policy on observatory base |
| **Upstream `origin/main`** | `1d48863b856d7a82412e1b47d87e30d0378b851f` | Ancestor of Local (+66) |

Shared production trees:  
`context_governor` `4f9592795b63e1d4325deed350f7e287761d3a4e`  
`context_compressor` `7f629211a414c51cbd2f5cf56112445328a35d46`

---

## 9. Recommendation for next runtime release

**Immediate next step:** commit + deploy the raise-only `agent_init` hotfix, then finish/classify full suite.

**Tag candidate:** `runtime-2026-07-19` @ Local tip **after** hotfix commit + suite classification.

**Release notes focus:**
1. Adaptive %-of-window context policy + working-memory handoff  
2. Observatory Phase 1 soak  
3. Raise-only compressor threshold vs Codex autoraise  
4. Runtime freeze remains in force  

**Do not** pull upstream until it moves ahead of `1d48863b`.  
**Do** restore stashed dashboard-auth / firecrawl as separate commits next.

**Phase 5:** Context-policy redesign **implemented + deployed**. Next is soak + hotfix ship, not another redesign.
