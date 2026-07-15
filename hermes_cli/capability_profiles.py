"""Apply / inspect capability profile YAML presets (tool routing).

Presets live in ``config/capability_profiles/*.yaml`` relative to the app root.
They merge into an existing Hermes profile ``config.yaml`` under
``tools.<platform>.enabled`` / ``disabled`` and ``plugins.enabled``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from hermes_constants import get_hermes_home


def profiles_dir() -> Path:
    here = Path(__file__).resolve().parent.parent / "config" / "capability_profiles"
    if here.is_dir():
        return here
    return Path(__file__).resolve().parent.parent / "capability_profiles"


def list_profiles() -> list[str]:
    return sorted(p.stem for p in profiles_dir().glob("*.yaml") if p.stem != "README")


def load_profile(name: str) -> dict[str, Any]:
    path = profiles_dir() / f"{name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Unknown capability profile: {name} ({path})")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid capability profile YAML: {path}")
    return data


def apply_profile_to_config(config: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow-copied config with profile tool/plugin routing merged."""
    out = dict(config)
    tools = dict(out.get("tools") or {})
    platforms = profile.get("platforms") or {}
    for platform, spec in platforms.items():
        if not isinstance(spec, dict):
            continue
        plat = dict(tools.get(platform) or {})
        if "enabled_toolsets" in spec:
            plat["enabled"] = list(spec["enabled_toolsets"])
        if "disabled_toolsets" in spec:
            plat["disabled"] = list(spec["disabled_toolsets"])
        tools[platform] = plat
    out["tools"] = tools

    plugins_spec = profile.get("plugins") or {}
    if plugins_spec.get("enabled") is not None or plugins_spec.get("disabled") is not None:
        plugins = dict(out.get("plugins") or {})
        if plugins_spec.get("enabled") is not None:
            plugins["enabled"] = list(plugins_spec["enabled"])
        if plugins_spec.get("disabled") is not None:
            plugins["disabled"] = list(plugins_spec["disabled"])
        out["plugins"] = plugins

    out.setdefault("agent", {})
    if isinstance(out["agent"], dict):
        agent = dict(out["agent"])
        agent["capability_profile"] = profile.get("name")
        out["agent"] = agent
    return out


def measure_schema_size(enabled_toolsets: list[str] | None = None) -> dict[str, Any]:
    """Approximate tool-schema payload size for the given toolsets."""
    try:
        from model_tools import get_tool_definitions
    except Exception as exc:
        return {"error": str(exc)}

    defs = get_tool_definitions(
        enabled_toolsets=enabled_toolsets,
    ) if enabled_toolsets is not None else get_tool_definitions()
    payload = json.dumps(defs, ensure_ascii=False, separators=(",", ":"))
    return {
        "tool_count": len(defs) if isinstance(defs, list) else 0,
        "schema_chars": len(payload),
        "schema_kb": round(len(payload) / 1024, 2),
        "enabled_toolsets": enabled_toolsets,
    }


def cmd_show(name: str) -> int:
    profile = load_profile(name)
    print(yaml.safe_dump(profile, sort_keys=False))
    return 0


def cmd_list() -> int:
    for name in list_profiles():
        print(name)
    return 0


def cmd_apply(name: str, *, dry_run: bool) -> int:
    from hermes_cli.config import load_config, save_config

    profile = load_profile(name)
    current = load_config()
    merged = apply_profile_to_config(current, profile)
    if dry_run:
        print(yaml.safe_dump({"tools": merged.get("tools"), "plugins": merged.get("plugins")}, sort_keys=False))
        print(f"(dry-run) would write capability profile '{name}' into {get_hermes_home() / 'config.yaml'}")
        return 0
    save_config(merged)
    print(f"Applied capability profile '{name}' → {get_hermes_home() / 'config.yaml'}")
    return 0


def cmd_measure(name: str | None) -> int:
    enabled = None
    if name:
        profile = load_profile(name)
        cli = (profile.get("platforms") or {}).get("cli") or {}
        enabled = list(cli.get("enabled_toolsets") or [])
    result = measure_schema_size(enabled)
    print(json.dumps(result, indent=2))
    return 0 if "error" not in result else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="capability-profiles")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List available capability profiles")

    show_p = sub.add_parser("show", help="Print a profile YAML")
    show_p.add_argument("name")

    apply_p = sub.add_parser("apply", help="Merge profile into current HERMES_HOME config.yaml")
    apply_p.add_argument("name")
    apply_p.add_argument("--dry-run", action="store_true")

    measure_p = sub.add_parser("measure", help="Measure tool schema size for a profile")
    measure_p.add_argument("--profile", dest="name", default=None)

    args = parser.parse_args(argv)
    if args.cmd == "list":
        return cmd_list()
    if args.cmd == "show":
        return cmd_show(args.name)
    if args.cmd == "apply":
        return cmd_apply(args.name, dry_run=args.dry_run)
    if args.cmd == "measure":
        return cmd_measure(args.name)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
