# Hermes local and VPS latest-upstream parity

## Verified baseline

- Upstream `main`: `7b5ba2054721dde998ed47fd4a0f031955278e99`
- Local checkout: `190cef7e02d5e7a3742dc069146e08e0ba2516d7` on `codex/hermes-latest-main-integration-20260710`, with the verified Desktop startup fix still uncommitted
- VPS checkout: `2b33f66ab134b272708aeace9100123383f739fe` on the same protected integration branch, with only an existing untracked audit directory
- VPS disk: 77% used; dashboard and gateway services active
- Public dashboard: healthy `0.18.2`; root correctly redirects to OAuth

## Plan

- [x] Create rollback-safe local and VPS backup refs/artifacts before changing either checkout.
- [x] Commit the verified local Desktop startup and packaging fix on the protected integration branch.
- [x] Fetch upstream and merge `origin/main` into the protected local integration branch; resolve only evidence-backed conflicts while preserving carried commits and routing/config behavior.
- [x] Run focused Desktop tests, type checks, the relevant broader suite, and production builds against the merged commit.
- [x] Transfer/fetch the exact tested integration commit to the VPS, back up its current head, and fast-forward the VPS protected branch to that exact commit without generic `hermes update`.
- [x] Refresh required runtime/workspace dependencies, rebuild the dashboard if required, and restart only the services touched by the update.
- [x] Verify local and VPS `HEAD` equality, Hermes versions, provider/model invariants, service state, localhost dashboard/gateway health, public `/api/status`, OAuth redirect, and authenticated-path readiness where available.

## Success criteria

Local and `/usr/local/lib/hermes-agent` end on the same tested integration commit containing upstream `main` `7b5ba205` plus all protected carried work and the Desktop connection fix; both services and the public endpoint are healthy; provider/model routing remains OpenCode Go + MiniMax M3; rollback refs/artifacts are recorded.
