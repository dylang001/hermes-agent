# Hermes Latest-Upstream Upgrade Report

**Date (UTC):** 2026-07-16  
**Upgrade branch:** `upgrade/hermes-latest-upstream-20260716`  
**Preservation:** `preserve/hermes-pre-upstream-20260716T0958Z` @ `18b78dd1f`  
**Bundle:** `/tmp/preserve-hermes-pre-upstream-20260716T0958Z.bundle`

## Outcome

| Item | Result |
|------|--------|
| Upstream merge | **Clean** — `origin/main` (`1d48863b8`) into fork tip |
| Conflicts | **None** |
| Obsolete skill_finder shell hook | **Removed** from live VPS config; archived; not allowlisted |
| Stale `/root/.hermes` runtime config keys | **Cleared** (tirith_path, memory_store.db_path, hooks) |
| Focused Python tests | **283 passed** (obsidian, clickup, path_boundary, config, input_sanitize, telegram policy, skill discovery, WAL, MCP catalog, codex ttfb) |
| Desktop typecheck | **pass** (after typing fix for `buildPosixPinArgs`) |
| Desktop vitest (merge-touched) | **33 passed** |
| Approved SHA | `db265696d4b7adf2e19258d7daecc69d6ea99401` |
| Immutable tag | `production-2026-07-16-upstream` (annotated) |

## Runtime cleanup evidence

- Backup: `/opt/hermes/home/config.yaml.bak-root-cleanup-20260716T095853Z`
- `hooks:` → `None`
- Hook archived: `/opt/hermes/home/agent-hooks/.archive/skill_finder_hook.sh.obsolete`
- Only remaining `/root/.hermes` string in live config is `environment_hint` (instructional)

## Local smokes (post-merge)

| Check | Result |
|-------|--------|
| `hermes --version` | `v0.18.2 (2026.7.7.2)` · upstream `1d48863b` · local merge tip |
| ClickUp CLI workspaces | workspace `90152507264` |
| Obsidian MCP test | tools listed (filesystem Growth OS) |

## Deploy / parity

| Surface | Expected after deploy |
|---------|----------------------|
| Local git SHA | approved tip |
| VPS `/opt/hermes/app` + `.deployed-sha` | same tip |
| Desktop build | same tip (package version may still read `0.17.0`) |
| Gateway / dashboard | active after password sudo restart |

## What was not done

- Dashboard “Update” button (forbidden)
- `git pull` on production (forbidden — bundle + reset --hard only)
- Auto-allowlisting the obsolete skill_finder hook
- Claiming SpaceMail read until credentials/adapter verified on this tip

## Rollback

```bash
# Restore preservation tip locally
git checkout preserve/hermes-pre-upstream-20260716T0958Z

# Or from bundle
git fetch /tmp/preserve-hermes-pre-upstream-20260716T0958Z.bundle \
  preserve/hermes-pre-upstream-20260716T0958Z
```

VPS: redeploy prior SHA `18b78dd1f` via the same bundle deploy path documented in `audit/HERMES_PRODUCTION_ACCEPTANCE.md`.
