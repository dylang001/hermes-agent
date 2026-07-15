# Hermes Production Acceptance — Phase 7.1

**Accepted:** 2026-07-15 (tag `production-2026-07-16`)  
**Scope:** Deployment finalization & baseline only (Week 1 already accepted).  
**Production:** `hermes-production` / `hermes90210` / `138.128.247.49` only.

## Deployment

| Item | Value |
|------|--------|
| Desktop / local SHA | `881f1cf4790507d2b4416e90ab0117a1f37546e0` |
| VPS `/opt/hermes/app` SHA | `881f1cf4790507d2b4416e90ab0117a1f37546e0` (matches Desktop) |
| Tag | `production-2026-07-16` |
| `.deployed-sha` | same as tip |
| Deploy commands | documented below |

### Exact SHA deploy (preferred path used)

```bash
# On Mac (repo root), after commit:
SHA=$(git rev-parse HEAD)
BUNDLE="/tmp/hermes-production-${SHA:0:12}.bundle"
git bundle create "$BUNDLE" "$SHA"

# Copy bundle to VPS
ssh hermes-production "mkdir -p /opt/hermes/deploy"
ssh hermes-production "cat > /opt/hermes/deploy/hermes-production-${SHA:0:12}.bundle" < "$BUNDLE"

# On VPS: immutable checkout + restart
ssh hermes-production "bash -s" <<REMOTE
set -euo pipefail
SHA='$SHA'
cd /opt/hermes/app
git fetch /opt/hermes/deploy/hermes-production-\${SHA:0:12}.bundle "\$SHA"
git checkout -B hermes-phase1-approved "\$SHA"
git reset --hard "\$SHA"
git clean -fd
printf '%s\n' "\$SHA" > .deployed-sha
test "\$(git rev-parse HEAD)" = "\$SHA"
test -z "\$(git status --porcelain)"
sudo -n /usr/bin/systemctl restart hermes-gateway hermes-dashboard
sudo -n /usr/bin/systemctl is-active hermes-gateway hermes-dashboard
REMOTE
```

## Services & health (at acceptance)

| Service | Status |
|---------|--------|
| hermes-gateway | active |
| hermes-dashboard | active |
| caddy | active |
| Task OS cron `4dcf0a86d0e8` | active, last_status ok |
| Mem0 | configured (`memory.provider: mem0`) |
| Obsidian MCP | enabled (may retry connect) |
| Desktop path / capability wire | from tagged SHA (no dirty overlays) |
| Telegram daily-ops footprint | ~15 tools (prior Week-1 measure ~26 ms) |

Soak health confirmed by Dylan 2026-07-15 — Desktop / Telegram / Task OS / Obsidian / Mem0 healthy on new VPS.

## Latency / footprint

| Measure | Value |
|---------|--------|
| Telegram tool schema (Week-1) | ~15 tools / ~30.6 KB / ~26 ms |
| Task OS | single poller every 5m |

## Privilege cleanup

- Removed `/etc/sudoers.d/hermes-migration-temp` after deploy restart  
- Final model: Dylan password sudo via `sudo` group; no Hermes migration NOPASSWD  
- Validated: migration file absent; `sudo -l` still shows password `ALL` for dylan

## Old VPS destroy

- Archive captured under `audit/old-vps-retire-20260715/` (config secrets omitted)  
- Host `212.86.105.178` decommissioned per Dylan hard-gate lift  
- SSH Host `hermes-production-old` removed from local SSH config  
- Docs point only at `138.128.247.49`

## Rollback simulation

Performed: documented restore steps executed as dry-run (verify tag + bundle object exists, `git rev-parse` / `git cat-file -t` for tagged SHA, confirm restart commands) **without** leaving production on a bad SHA. Production remains on tip SHA after simulation.

```bash
# Rollback to this baseline
TAG=production-2026-07-16
SHA=$(git rev-parse "$TAG")
# reuse bundle path or recreate: git bundle create /tmp/hermes-rollback.bundle "$SHA"
# then same VPS reset --hard "$SHA" + systemctl restart as above
```

## Known issues

- Obsidian MCP intermittent initial connection failures (parked retry)
- skill_finder_hook under `/root/.hermes` not allowlisted (warning only)
- Dirty overlay deploys forbidden going forward — always exact SHA

## Remaining roadmap

**Phase 8 = business capabilities** (not more infrastructure).  
Do not enable SpaceMail send / LinkedIn automation / social publishing in this phase.  
Do not add a second Task OS poller.
