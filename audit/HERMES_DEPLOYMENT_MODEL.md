# Hermes Deployment Model — Why `git am`, and how to leave it

**Date:** 2026-07-19  
**Status:** Recommendation (no infra change in this commit)

## Why Local SHA ≠ VPS SHA today

| Fact | Detail |
|------|--------|
| Local tip | Annotated production work on `upgrade/hermes-latest-upstream-20260716` |
| VPS tip | Same *trees* applied via `git am` onto `hermes-phase1-approved` |
| VPS `origin` | **Not GitHub** — a local bundle: `/opt/hermes/deploy/hermes-phase1-approved-07bdd098.bundle` |
| Nous `origin/main` | Upstream only; our runtime branch is **not** pushed there |
| `fork` remote | `https://github.com/dylang001/hermes-agent.git` — available but unused for VPS pulls |

`git am` was the path of least resistance when VPS cannot fetch the branch that Local is on. Functionally correct (matching trees), operationally noisy (divergent `git_sha` in Observatory).

## Can we move to push → pull → fast-forward?

**Yes.** There is no architectural reason to keep `git am` as the normal path. The blockers are operational, not runtime:

1. **VPS has no live remote** that contains Local’s tip.  
2. **We must not push private runtime tips to NousResearch/hermes-agent** as the default (upstream is shared).  
3. Bundle-based `origin` on VPS was a one-shot migration artifact, not a CI remote.

### Recommended model

```
Local tip (canonical)
    ↓  git push fork <deploy-branch>
fork (or private bare mirror)
    ↓  git fetch + git merge --ff-only
VPS /opt/hermes/app
    ↓  recycle hermes-gateway
Observatory git_sha == Local HEAD
```

Concrete options (pick one):

| Option | Pros | Cons |
|--------|------|------|
| **A. Push deploy branch to `fork`** | Already configured; simple | Branch is on a personal GitHub fork (ACL/visibility) |
| **B. Bare mirror on VPS** (`/opt/hermes/deploy/hermes.git`) | No GitHub required; `scp`/`rsync` or `git push` over SSH | Need a small push script from Mac |
| **C. Private deploy remote** | Cleanest for multi-machine | Extra hosting |

Prefer **B** if the tip must stay off public GitHub; prefer **A** if the fork is already private or acceptable.

### Deployment script contract (target)

```bash
# Local
git push deploy HEAD:hermes-production   # deploy = fork or ssh://vps/…/hermes.git

# VPS
cd /opt/hermes/app
git fetch deploy
git merge --ff-only deploy/hermes-production
# refuse non-FF; never reset --hard unless operator override
systemctl kill -s TERM hermes-gateway   # or documented recycle
```

Identity rule: **Observatory `git_sha` must equal the Local tagged tip** after every production deploy. Tree-hash fallback remains a diagnostic, not the primary identity.

### What stays

- `git am` / format-patch: emergency / air-gapped / one-off only  
- Bundle snapshots: backup / rollback archives, not day-to-day origin  

### What this does *not* require

- Changing Execution Coordinator, governor, or Observatory  
- Fast-forwarding onto Nous `main` (still audit-first for upstream)

## Decision needed

Approve Option A or B (or C). After approval, rewire VPS `origin`/`deploy` remote once, push Local tip, FF VPS, confirm `hermes_runtime_info{git_sha=…}` matches Local `HEAD`.
