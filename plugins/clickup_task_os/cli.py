"""Operator CLI: hermes task-os …"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from hermes_constants import display_hermes_home, get_hermes_home
from plugins.clickup_task_os.config import (
    CONFIG_KEY,
    load_task_os_config,
    resolve_api_token,
    status_name,
    tag_name,
)


def register_cli(subparser: argparse.ArgumentParser) -> None:
    subs = subparser.add_subparsers(dest="task_os_action")

    poll_p = subs.add_parser("poll", help="Poll Orchidea Ops for Ready+hermes-ready tasks")
    poll_p.add_argument("--dry-run", action="store_true", help="Scan only; do not claim or execute")
    poll_p.add_argument(
        "--deterministic-worker",
        action="store_true",
        help="Operator smoke: execute without LLM; write a real artifact file",
    )

    subs.add_parser("show-config", help="Print resolved Task OS board mapping (no secrets)")

    setup_p = subs.add_parser(
        "setup",
        help="Create task-os profile, enable plugin, install cron poll script",
    )
    setup_p.add_argument("--skip-cron", action="store_true")
    setup_p.add_argument("--skip-profile", action="store_true")

    verify_p = subs.add_parser(
        "verify-board",
        help="Read-only verify Ops list statuses/tags against config",
    )

    subparser.set_defaults(func=task_os_command)


def task_os_command(args: argparse.Namespace) -> int:
    action = getattr(args, "task_os_action", None)
    if not action:
        print(
            "Usage: hermes task-os {poll|show-config|setup|verify-board}\n"
            "ClickUp-specific logic lives in plugins/clickup_task_os (not core tools)."
        )
        return 2

    if action == "poll":
        return _cmd_poll(
            dry_run=bool(getattr(args, "dry_run", False)),
            deterministic_worker=bool(getattr(args, "deterministic_worker", False)),
        )
    if action == "show-config":
        return _cmd_show_config()
    if action == "setup":
        return _cmd_setup(
            skip_cron=bool(getattr(args, "skip_cron", False)),
            skip_profile=bool(getattr(args, "skip_profile", False)),
        )
    if action == "verify-board":
        return _cmd_verify_board()
    print(f"Unknown action: {action}")
    return 2


def _cmd_poll(*, dry_run: bool, deterministic_worker: bool = False) -> int:
    from plugins.clickup_task_os.client import ClickUpAPIError
    from plugins.clickup_task_os.poller import format_poll_result, poll_once

    # Resolve token early for a clear error.
    try:
        resolve_api_token()
    except RuntimeError as exc:
        print(str(exc))
        return 2

    try:
        result = poll_once(
            dry_run=dry_run,
            deterministic_worker=deterministic_worker,
        )
    except ClickUpAPIError as exc:
        print(f"ClickUp API error {exc.status}: {exc.payload}")
        return 1
    print(format_poll_result(result))
    return 1 if result.errors else 0


def _cmd_show_config() -> int:
    cfg = load_task_os_config()
    public = {
        k: cfg[k]
        for k in (
            "workspace_id",
            "space_id",
            "folder_id",
            "list_id",
            "statuses",
            "tags",
            "max_concurrent",
            "max_repair_attempts",
            "worker_profile",
            "models",
        )
        if k in cfg
    }
    print(json.dumps(public, indent=2))
    print(
        f"\nOverride via {display_hermes_home()}/clickup_task_os.yaml "
        f"or config.yaml `{CONFIG_KEY}:`"
    )
    print("Secret: CLICKUP_API_TOKEN in profile .env (never git).")
    return 0


def _cmd_verify_board() -> int:
    from plugins.clickup_task_os.client import ClickUpClient

    cfg = load_task_os_config()
    client = ClickUpClient(resolve_api_token())
    list_id = str(cfg["list_id"])
    data = client._request("GET", f"/list/{list_id}")  # noqa: SLF001 — operator verify
    statuses = [s.get("status") for s in (data.get("statuses") or [])]
    print("list:", data.get("name"), data.get("id"))
    folder = data.get("folder") or {}
    space = data.get("space") or {}
    print("space:", space.get("id"), space.get("name"))
    print("folder:", folder.get("id"), folder.get("name"), "hidden=", folder.get("hidden"))
    print("statuses:", statuses)

    ready = status_name(cfg, "ready")
    in_progress = status_name(cfg, "in_progress")
    waiting = status_name(cfg, "waiting")
    review = status_name(cfg, "review")
    ok = True
    for label, name in (
        ("ready", ready),
        ("in_progress", in_progress),
        ("waiting", waiting),
        ("review", review),
    ):
        present = any((s or "").casefold() == name.casefold() for s in statuses)
        mark = "OK" if present else "MISSING"
        if not present:
            ok = False
        print(f"  map {label} -> {name!r}: {mark}")

    if review.casefold() == waiting.casefold():
        print(
            "  note: Review is mapped to status "
            f"{waiting!r} + tag {tag_name(cfg, 'hermes_review')!r} "
            "(no native Review column on Ops yet)."
        )

    tags = client._request("GET", f"/space/{cfg['space_id']}/tag")  # noqa: SLF001
    names = {t.get("name") for t in (tags.get("tags") or [])}
    for logical in ("hermes_ready", "hermes_review", "waiting_on_dylan", "approval_required"):
        name = tag_name(cfg, logical)
        mark = "OK" if name in names else "MISSING"
        if name not in names:
            ok = False
        print(f"  tag {logical} -> {name!r}: {mark}")

    return 0 if ok else 1


def _cmd_setup(*, skip_cron: bool, skip_profile: bool) -> int:
    home = get_hermes_home()
    cfg = load_task_os_config()
    profile = str(cfg.get("worker_profile") or "task-os")

    if not skip_profile:
        _ensure_profile(profile)

    # Enable plugin in current HERMES_HOME config AND the worker profile home.
    _ensure_plugin_enabled(home)
    profile_home = Path.home() / ".hermes" / "profiles" / profile
    if profile_home.is_dir():
        _ensure_plugin_enabled(profile_home)

    # Install poll script under worker profile scripts (and current home).
    script_path = _install_poll_script(profile_home if profile_home.is_dir() else home)
    if profile_home.is_dir() and home.resolve() != profile_home.resolve():
        _install_poll_script(home)

    # Profile model hints (best-effort)
    _write_profile_model_hints(profile, cfg)

    if not skip_cron:
        _ensure_cron_job(profile, script_path.name)

    print(
        textwrap.dedent(
            f"""
            Task OS setup complete.
            - Profile: {profile}
            - Board list: Orchidea Ops ({cfg.get('list_id')})
            - Ready status: {status_name(cfg, 'ready')}
            - Trigger tag: {tag_name(cfg, 'hermes_ready')}
            - Poll script: {script_path}
            - Ensure CLICKUP_API_TOKEN is in ~/.hermes/profiles/{profile}/.env
              (or the active profile .env).

            Rollback:
              hermes plugins disable clickup_task_os
              hermes -p {profile} cron pause <job-id>   # or remove the job
              # Optional: hermes profile delete {profile}
            """
        ).strip()
    )
    return 0


def _ensure_profile(profile: str) -> None:
    try:
        subprocess.run(
            ["hermes", "profile", "create", profile, "--description", "Hermes ClickUp Task OS worker"],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print("warn: hermes not on PATH; create profile manually: hermes profile create task-os")


def _ensure_plugin_enabled(home: Path) -> None:
    import yaml

    path = home / "config.yaml"
    data: dict[str, Any] = {}
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    plugins = data.setdefault("plugins", {})
    enabled = list(plugins.get("enabled") or [])
    if "clickup_task_os" not in enabled:
        enabled.append("clickup_task_os")
    plugins["enabled"] = enabled
    # Bound Kanban concurrency for Task OS board usage.
    kanban = data.setdefault("kanban", {})
    kanban.setdefault("failure_limit", 2)
    kanban.setdefault("max_spawn", 2)
    kanban.setdefault("max_in_progress", 2)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    print(f"Enabled plugin in {path}")


def _install_poll_script(home: Path) -> Path:
    scripts = home / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    dest = scripts / "clickup-task-os-poll.sh"
    src = Path(__file__).resolve().parent / "scripts" / "clickup-task-os-poll.sh"
    if src.is_file():
        shutil.copyfile(src, dest)
    else:
        dest.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nhermes task-os poll\n",
            encoding="utf-8",
        )
    dest.chmod(0o755)
    return dest


def _write_profile_model_hints(profile: str, cfg: dict) -> None:
    import yaml

    models = cfg.get("models") or {}
    profile_home = Path.home() / ".hermes" / "profiles" / profile
    if not profile_home.is_dir():
        return
    path = profile_home / "config.yaml"
    data: dict[str, Any] = {}
    if path.is_file():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    model = data.setdefault("model", {})
    # Primary executor for Phase 1 one-shot runs.
    model.setdefault("default", models.get("executor") or "minimax-m3")
    data[CONFIG_KEY] = {
        k: cfg[k]
        for k in (
            "workspace_id",
            "space_id",
            "folder_id",
            "list_id",
            "statuses",
            "tags",
            "max_concurrent",
            "max_repair_attempts",
            "worker_profile",
            "models",
        )
        if k in cfg
    }
    # Smart routing hints (ignored if unsupported).
    smr = data.setdefault("smart_model_routing", {})
    smr.setdefault("enabled", True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    print(f"Wrote model/board hints to {path}")


def _ensure_cron_job(profile: str, script_name: str) -> None:
    try:
        proc = subprocess.run(
            [
                "hermes",
                "-p",
                profile,
                "cron",
                "create",
                "every 2m",
                "--no-agent",
                "--script",
                script_name,
                "--deliver",
                "local",
                "--name",
                "clickup-task-os-poll",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            print(proc.stdout.strip() or "cron job created")
        else:
            print(
                "warn: cron create failed (create manually):\n"
                f"  hermes -p {profile} cron create \"every 2m\" --no-agent "
                f"--script {script_name} --name clickup-task-os-poll\n"
                f"{(proc.stderr or proc.stdout)[:500]}"
            )
    except FileNotFoundError:
        print("warn: hermes not on PATH; skip cron create")
