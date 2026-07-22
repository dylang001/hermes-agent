#!/usr/bin/env bash
# Hermes production deploy / rollback helpers (VPS: hermes-production).
#
# Verified 2026-07-22 on hermes90210:
#   Active unit: hermes-gateway.service
#   Also present (not assumed for compress rollback): hermes-dashboard.service
#   App tree:    /opt/hermes/app
#   HERMES_HOME: /opt/hermes/home
#   Config:      /opt/hermes/home/config.yaml
#
# Usage (on the VPS, as the deploy user):
#   ./scripts/ops/hermes_prod_rollback.sh record-predeploy
#   ./scripts/ops/hermes_prod_rollback.sh code-rollback
#   ./scripts/ops/hermes_prod_rollback.sh config-rollback
#   ./scripts/ops/hermes_prod_rollback.sh full-rollback
#   ./scripts/ops/hermes_prod_rollback.sh verify
#
# Or with explicit SHA:
#   PRE_DEPLOY_SHA=1393fdbe5 ./scripts/ops/hermes_prod_rollback.sh code-rollback
#
# This script does NOT deploy. It only records/rolls back/verifies.
set -euo pipefail

APP_DIR="${HERMES_APP_DIR:-/opt/hermes/app}"
HERMES_HOME_DIR="${HERMES_HOME:-/opt/hermes/home}"
CONFIG_PATH="${HERMES_CONFIG:-$HERMES_HOME_DIR/config.yaml}"
SERVICE_UNIT="${HERMES_SERVICE_UNIT:-hermes-gateway.service}"
DEPLOY_LOG_DIR="${HERMES_DEPLOY_LOG_DIR:-$HERMES_HOME_DIR/deploy-log}"
STAMP_FILE="$DEPLOY_LOG_DIR/predeploy.env"
CONFIG_BACKUP="$DEPLOY_LOG_DIR/config.yaml.predeploy"

die() { echo "ERROR: $*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || die "missing command: $1"; }

record_predeploy() {
  need_cmd git
  need_cmd systemctl
  mkdir -p "$DEPLOY_LOG_DIR"
  cd "$APP_DIR"
  local sha
  sha="$(git rev-parse HEAD)"
  local tag="predeploy-$(date -u +%Y%m%dT%H%M%SZ)-${sha:0:12}"
  git tag -f "$tag" "$sha" 2>/dev/null || true
  {
    echo "PRE_DEPLOY_SHA=$sha"
    echo "PRE_DEPLOY_TAG=$tag"
    echo "PRE_DEPLOY_RECORDED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "SERVICE_UNIT=$SERVICE_UNIT"
    echo "APP_DIR=$APP_DIR"
    echo "CONFIG_PATH=$CONFIG_PATH"
  } >"$STAMP_FILE"
  if [[ -f "$CONFIG_PATH" ]]; then
    cp -a "$CONFIG_PATH" "$CONFIG_BACKUP"
  fi
  echo "Recorded pre-deploy SHA=$sha tag=$tag"
  echo "Stamp: $STAMP_FILE"
}

_load_stamp() {
  [[ -f "$STAMP_FILE" ]] || die "missing $STAMP_FILE — run record-predeploy first (or set PRE_DEPLOY_SHA)"
  # shellcheck disable=SC1090
  source "$STAMP_FILE"
}

code_rollback() {
  need_cmd git
  need_cmd systemctl
  cd "$APP_DIR"
  local target="${PRE_DEPLOY_SHA:-}"
  if [[ -z "$target" && -f "$STAMP_FILE" ]]; then
    _load_stamp
    target="${PRE_DEPLOY_SHA:-}"
  fi
  [[ -n "$target" ]] || die "PRE_DEPLOY_SHA not set"
  echo "Checking out $target in $APP_DIR"
  git fetch --all --tags 2>/dev/null || true
  git checkout --force "$target"
  systemctl restart "$SERVICE_UNIT"
  verify
}

config_rollback() {
  [[ -f "$CONFIG_BACKUP" ]] || die "missing config backup $CONFIG_BACKUP"
  cp -a "$CONFIG_BACKUP" "$CONFIG_PATH"
  echo "Restored config from $CONFIG_BACKUP → $CONFIG_PATH"
  systemctl restart "$SERVICE_UNIT"
  verify
}

full_rollback() {
  config_rollback_soft() {
    if [[ -f "$CONFIG_BACKUP" ]]; then
      cp -a "$CONFIG_BACKUP" "$CONFIG_PATH"
      echo "Config restored"
    else
      echo "WARN: no config backup; skipping config restore"
    fi
  }
  config_rollback_soft
  code_rollback
}

verify() {
  need_cmd systemctl
  systemctl is-active --quiet "$SERVICE_UNIT" || die "$SERVICE_UNIT is not active"
  systemctl status "$SERVICE_UNIT" --no-pager -l | head -20
  # Basic health: process responds / unit active. Extend with HTTP probe if desired.
  if systemctl show "$SERVICE_UNIT" -p MainPID --value | grep -Eq '^[1-9]'; then
    echo "VERIFY OK: $SERVICE_UNIT active (MainPID=$(systemctl show "$SERVICE_UNIT" -p MainPID --value))"
  else
    die "VERIFY FAILED: no MainPID for $SERVICE_UNIT"
  fi
}

auto_rollback_on_health_fail() {
  # Intended post-deploy hook: if verify fails, restore stamp SHA + config.
  if verify; then
    echo "Health OK — no rollback"
    return 0
  fi
  echo "Health FAILED — running full-rollback"
  full_rollback
}

usage() {
  sed -n '1,40p' "$0"
}

cmd="${1:-}"
case "$cmd" in
  record-predeploy) record_predeploy ;;
  code-rollback) code_rollback ;;
  config-rollback) config_rollback ;;
  full-rollback) full_rollback ;;
  verify) verify ;;
  auto-rollback-on-health-fail) auto_rollback_on_health_fail ;;
  -h|--help|help|"") usage ;;
  *) die "unknown command: $cmd" ;;
esac
