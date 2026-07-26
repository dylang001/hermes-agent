# Hermes production upgrade audit — 2026-07-26

**Verdict: MIXED — modestly improved on peak-context and tool thrash; regressed / broken on Knowledge OS scheduled maintenance. Confidence: high (0.85) on metrics; high on cron root cause.**

Objective: better useful work per token — not fewer tokens at any cost.

---

## 1. Audit period, versions, environments

| Item | Value |
|------|--------|
| Window | 2026-07-10 → 2026-07-26 (UTC) |
| Cut | **2026-07-22** (post `upgrade/hermes-latest-upstream-20260722` catch-up merges + KOS L1) |
| Before | 2026-07-10 ≤ t < 2026-07-22 |
| After | 2026-07-22 ≤ t < 2026-07-27 |
| Mac code | `/Users/dylanangloher/.hermes/hermes-agent` · branch `upgrade/hermes-latest-upstream-20260722` · **pre-update** `984677565` · Hermes `v0.19.0 (2026.7.20)` · **438 commits behind** `origin/main` (`a97b6ff8`) |
| VPS code | `/opt/hermes/app` · branch `hermes-phase1-approved` · **same** `984677565` · HERMES_HOME `/opt/hermes/home` |
| Evidence DB | `/opt/hermes/home/state.db` (658MB production) |
| KOS authority | Unchanged Model B: Mac Growth OS + Git authoritative; VPS writable mirror |
| Baseline artifacts | `audit/baselines/hermes-upgrade-audit-20260726/` · script `audit/hermes_production_upgrade_audit.py` |

---

## 2. Comparable metrics (desktop-only, api_call_count > 0)

| Metric | Before | After | Δ |
|--------|--------|-------|---|
| Sessions | 115 | 7 | small after sample |
| Cache ratio | 0.926 | 0.889 | slightly better |
| Avg promptish (in+cache) / session | 6.06M | **12.07M** | worse |
| Avg cache_read / session | 5.61M | **10.74M** | worse |
| Max cache_read | **111.2M** | 39.8M | improved ceiling |
| Tools / session | 153.5 | **101.6** | improved |
| API calls / session | 29.8 | **64.9** | worse |
| Compress ends (all sources) | 96 | 3 | fewer (mix + volume) |

**All-sources note:** After window is cron-heavy (23 cron / 8 desktop). Desktop-only is the fairer task-quality comparator; sample size after is thin (n=7).

**Cost:** `actual_cost_usd` / `estimated_cost_usd` stored as **0** across the window — OpenCode/NVIDIA billing not mirrored into SessionDB. Token totals are the cost proxy.

### Representative samples

**Before (worst cache):** `20260717_195908_85759f` — desktop ultra — 111M cache_read, 404 API, compression end.

**After (worst cache):** `20260722_081922_5d7dc8` — “Hermes Revenue Intelligence OS Architecture” — 39.8M cache_read, 169 API, compression end.

**KOS daily productive:** `cron_675506b90337_20260722_070023` — 31 API / 49 tools — real orient + raw scan + compile-log append (useful, but terminal-heavy; `read_file` evidence compacted away).

**KOS daily broken:** `cron_675506b90337_20260724`…`20260726` — 0 API, FAILED — OpenCode **HTTP 401 Insufficient balance**.

---

## 3. What demonstrably improved

1. **Peak cache_read ceiling** down (~111M → ~40M on top desktop sessions).
2. **Tools per desktop session** down (~153 → ~102) — less thrash / fewer micro-loops on average.
3. **Compress race rate** lower by calendar day after Jul 22 (2/day → stopped appearing after Jul 22 in agent.log sample; races still occurred Jul 20–22).
4. **CKO / Model B architecture** present: charter CANONICAL on Mac+VPS; obsolete trees absent; L1 cron flags correct (daily+lint on; nightly/weekly/monthly off).
5. **Jul 22 daily** showed charter-aligned restraint (no speculative compile) and wrote a real compile-log entry.
6. **Pinned skills** = 0 — not a current pin bottleneck.
7. **Manual compress race fix** is in the carried branch history (`d89addeb4` attach-to-winner) — prior Jul 19 `/compress` no-op is in the before window.

---

## 4. What became worse or remains unresolved

| Issue | Status |
|-------|--------|
| **KOS daily + lint FAILED since ~Jul 23/24** | **Urgent operational regression** — OpenCode balance 401 |
| Avg desktop cache_read / promptish up | Unresolved — long sessions still dominate cost |
| API calls / desktop session up | Unresolved |
| `select_context` / layered-context hooks | **0 log hits** — not used in production path |
| Compress race | Recurred through Jul 22; quieter after (low volume) |
| Terminal result replay / compact_tool_evidence | Still forces re-reads via `terminal` in Jul 22 daily |
| USD cost telemetry | Still zero — cannot compute $ / outcome |
| Zero-API cron sessions marked `cron_complete` | Misleading health signal |
| Thin after-desktop sample (n=7) | Limits strength of quality claims |

---

## 5. Token / waste breakdown

**Main waste sources (evidence):**

1. **Mega-session cache_read** on desktop (multi-million to tens of millions per session) — dominant share of totalish tokens.
2. **Tool evidence compaction hiding useful content** → model re-invokes `terminal` to re-read the same files (Jul 22 daily).
3. **Failed cron skill injection** still materializes full SKILL.md into the user message (~8.5KB) with **zero API** — wasted scheduling + confusing FAILED/complete dual signal.
4. **OpenCode billing outage** → total loss of L1 Knowledge OS maintenance outcomes since Jul 24.

Not counted as “waste”: legitimate large research sessions (Upwork / Revenue OS) if they produce decisions — those need quality scoring, not raw token minimization.

---

## 6. Mac vs VPS discrepancies

| Area | Finding |
|------|---------|
| Code SHA | Aligned at `984677565` pre-update |
| HERMES_HOME | Mac `~/.hermes` vs VPS `/opt/hermes/home` — expected |
| Production traffic | **VPS only** for Desktop/Telegram/cron |
| KOS vault | Mac Git authority; VPS mirror — charter/hash parity verified earlier in Model B work |
| Cron model | VPS cron uses `minimax-m3` via OpenCode — **broken on billing** |
| Desktop models | NVIDIA nemotron paths still produce tokens after cut |

---

## 7. Root causes

1. **KOS cron dead:** `RuntimeError: HTTP 401: Insufficient balance` (OpenCode workspace billing). Not a Hermes code bug.
2. **High avg cache after cut:** Fewer but still-long desktop sessions on large NVIDIA models; compression creates children but cache_read remains high within a session.
3. **`select_context` unused:** Hooks exist in upstream/carried code; production loop not emitting / not selecting a context-engine plugin that logs usage.
4. **Tool replay:** Evidence compaction + model distrust of compact payloads → terminal re-reads.
5. **Historical `/compress` no-op:** Documented Jul 19 when rotation did not occur and in-place mode off (`#44794`); race skips when another compressor holds the lock.

---

## 8. Prioritised fixes

### Urgent (regressions / broken L1)

1. **Restore OpenCode balance** or **repoint cron/default model** to a funded provider (Dylan decision — billing/secrets).
2. **Surface cron FAILED in ops alerts** when `api_call_count=0` + Error footer (do not treat as healthy `cron_complete` alone).
3. After billing restore: **manual `hermes cron run knowledge-os-daily`** and confirm receipt + compile-log.

### High (quality / useful-work-per-token)

4. Ensure production context-engine path actually calls `select_context` (or document intentional off).
5. Reduce compact_tool_evidence false-negatives for `read_file` / short markdown (stop forcing terminal re-reads).
6. Continue compress race hardening validation on live desktop long sessions.

### Optional

7. Populate SessionDB cost fields from provider invoices for true $/outcome.
8. Weekly Knowledge Health dashboard automation (charter metric) once cron is healthy.
9. Enable nightly (L2) only after 30 clean L1 days — unchanged policy.

---

## 9. Verdict

**Improved on infrastructure and peak-context control; regressed on Knowledge OS L1 reliability due to provider billing — overall MIXED / slight net regression for the executive charter mission until cron is restored.**

- Engineering upgrades (context engine hooks, compress race fix, KOS Model B) are real and partly visible.
- The **CKO daily loop is currently non-functional** — that dominates the executive-quality score.

Confidence: **high** on cron failure cause; **medium-high** on desktop token trends (small after-n).

---

## 10. Repeatable baseline

```bash
# On VPS
python3 /opt/hermes/app/audit/hermes_production_upgrade_audit.py \
  --db /opt/hermes/home/state.db \
  --cut YYYY-MM-DD \
  --start YYYY-MM-DD --end YYYY-MM-DD \
  --git-sha "$(git -C /opt/hermes/app rev-parse HEAD)" \
  --env-label vps-production \
  --out /opt/hermes/home/audit/baselines/hermes-upgrade-audit-YYYYMMDD
```

Compare `baseline.json` → `desktop_only` and `knowledge_os_cron_summary` across cuts.

Canvas: `~/.cursor/projects/Users-dylanangloher-hermes-hermes-agent/canvases/hermes-upgrade-audit-2026-07-26.canvas.tsx`
