"""Load ClickUp Task OS configuration without hardcoding IDs in call sites."""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional

import yaml

from hermes_constants import get_hermes_home

_PLUGIN_DIR = Path(__file__).resolve().parent
_DEFAULTS_PATH = _PLUGIN_DIR / "defaults.yaml"

CONFIG_KEY = "clickup_task_os"


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Expected mapping in {path}")
    return raw


def _deep_merge(base: MutableMapping[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = deepcopy(dict(base))
    for key, value in overlay.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, Mapping)
        ):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def load_task_os_config(
    *,
    hermes_home: Optional[Path] = None,
    overlay: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge defaults ← HERMES_HOME/clickup_task_os.yaml ← config.yaml section ← overlay."""
    home = Path(hermes_home) if hermes_home else get_hermes_home()
    cfg = _read_yaml(_DEFAULTS_PATH)

    standalone = home / "clickup_task_os.yaml"
    cfg = _deep_merge(cfg, _read_yaml(standalone))

    user_cfg_path = home / "config.yaml"
    user_cfg = _read_yaml(user_cfg_path)
    section = user_cfg.get(CONFIG_KEY) or {}
    if isinstance(section, Mapping):
        cfg = _deep_merge(cfg, section)

    if overlay:
        cfg = _deep_merge(cfg, overlay)

    _validate(cfg)
    return cfg


def _validate(cfg: Mapping[str, Any]) -> None:
    required = ("workspace_id", "space_id", "list_id", "statuses", "tags")
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        raise ValueError(f"clickup_task_os config missing keys: {missing}")
    for name in ("ready", "in_progress", "waiting", "review"):
        if name not in (cfg.get("statuses") or {}):
            raise ValueError(f"clickup_task_os.statuses.{name} is required")
    if "hermes_ready" not in (cfg.get("tags") or {}):
        raise ValueError("clickup_task_os.tags.hermes_ready is required")


def resolve_api_token(*, environ: Optional[Mapping[str, str]] = None) -> str:
    env = environ if environ is not None else os.environ
    token = (env.get("CLICKUP_API_TOKEN") or env.get("CLICKUP_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "CLICKUP_API_TOKEN is not set. Add it to the task-os profile .env "
            "(secrets only — never commit)."
        )
    return token


def status_name(cfg: Mapping[str, Any], logical: str) -> str:
    statuses = cfg["statuses"]
    try:
        return str(statuses[logical])
    except KeyError as exc:
        raise KeyError(f"Unknown logical status {logical!r}") from exc


def tag_name(cfg: Mapping[str, Any], logical: str) -> str:
    tags = cfg["tags"]
    try:
        return str(tags[logical])
    except KeyError as exc:
        raise KeyError(f"Unknown logical tag {logical!r}") from exc


def clickup_idempotency_key(task_id: str) -> str:
    return f"clickup:{task_id}"
