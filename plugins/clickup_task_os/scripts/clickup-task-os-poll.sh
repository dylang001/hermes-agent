#!/usr/bin/env bash
# Hermes Task OS Phase 1 cron entrypoint (no-agent).
# Installed to $HERMES_HOME/scripts/ by `hermes task-os setup`.
set -euo pipefail
# Prefer the dedicated worker profile when invoked outside `hermes -p`.
if [[ -z "${HERMES_HOME:-}" || "${HERMES_HOME}" == "${HOME}/.hermes" ]]; then
  exec hermes -p task-os task-os poll
fi
exec hermes task-os poll
