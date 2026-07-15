"""Authoritative runtime path/user metadata for agent sessions.

Keeps migration-stale paths (/root/.hermes, /usr/local/lib/hermes-agent, …)
from overriding the live deployment facts shown in the system prompt and used
when remapping recalled memory.
"""

from __future__ import annotations

import getpass
import os
import platform
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from hermes_constants import get_hermes_home

from agent.runtime_cwd import resolve_agent_cwd


# Legacy deployment prefixes that must never override live runtime facts.
STALE_ROOT_PREFIXES: tuple[str, ...] = (
    "/root",
    "/root/.git",
    "/root/.hermes",
    "/root/audit",
    "/root/obsidian-vault",
    "/usr/local/lib/hermes-agent",
)


@dataclass(frozen=True)
class RuntimeMetadata:
    """Snapshot of where this Hermes process is actually running."""

    app_root: str
    hermes_home: str
    cwd: str
    user: str
    platform: str
    writable_roots: tuple[str, ...]
    terminal_backend: str

    def as_prompt_block(self) -> str:
        roots = ", ".join(self.writable_roots) if self.writable_roots else "(none detected)"
        return (
            "Authoritative runtime (do not override with recalled/old paths):\n"
            f"- App root: {self.app_root}\n"
            f"- Hermes home (HERMES_HOME): {self.hermes_home}\n"
            f"- Current working directory: {self.cwd}\n"
            f"- Service user: {self.user}\n"
            f"- Platform: {self.platform}\n"
            f"- Terminal backend: {self.terminal_backend}\n"
            f"- Writable roots: {roots}\n"
            "- Stale paths such as /root/.hermes, /root/audit, /root/obsidian-vault, "
            "and /usr/local/lib/hermes-agent are migration leftovers. Prefer the roots "
            "above. On the first missing-path error, discover under Writable roots "
            "instead of retrying the stale path."
        )


def resolve_app_root() -> Path:
    """Resolve the Hermes application checkout directory."""
    env = (os.getenv("HERMES_APP_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()

    # This file lives at <app>/agent/runtime_metadata.py
    here = Path(__file__).resolve().parent.parent
    if (here / "run_agent.py").exists() or (here / "pyproject.toml").exists():
        return here

    for candidate in (
        Path("/opt/hermes/app"),
        Path("/usr/local/lib/hermes-agent"),
    ):
        if candidate.is_dir() and (candidate / "run_agent.py").exists():
            return candidate.resolve()

    return here


def list_writable_roots(
    *,
    app_root: Path | None = None,
    hermes_home: Path | None = None,
    cwd: str | None = None,
) -> tuple[str, ...]:
    """Return existing directories the agent can typically write under."""
    app_root = app_root or resolve_app_root()
    hermes_home = hermes_home or get_hermes_home()
    try:
        resolved_cwd = Path(cwd or resolve_agent_cwd()).resolve()
    except OSError:
        resolved_cwd = Path.cwd()

    candidates: list[Path] = [
        resolved_cwd,
        hermes_home,
        hermes_home / "audit",
        app_root,
        app_root / "audit",
        Path.home(),
        Path("/tmp"),
        Path("/var/tmp"),
    ]
    seen: set[str] = set()
    roots: list[str] = []
    for path in candidates:
        try:
            resolved = str(path.resolve())
        except OSError:
            continue
        if resolved in seen:
            continue
        if not path.is_dir():
            continue
        if not os.access(path, os.W_OK | os.X_OK):
            continue
        seen.add(resolved)
        roots.append(resolved)
    return tuple(roots)


def collect_runtime_metadata() -> RuntimeMetadata:
    """Collect live runtime facts for prompt injection and remaps."""
    app_root = resolve_app_root()
    hermes_home = get_hermes_home()
    try:
        cwd = resolve_agent_cwd()
    except OSError:
        cwd = os.getcwd()
    try:
        user = getpass.getuser()
    except Exception:
        user = os.getenv("USER") or os.getenv("LOGNAME") or "unknown"

    if sys.platform == "darwin":
        plat = f"macOS ({platform.mac_ver()[0] or platform.release()})"
    elif sys.platform == "win32":
        plat = f"Windows ({platform.release()})"
    else:
        plat = f"{platform.system()} ({platform.release()})"

    return RuntimeMetadata(
        app_root=str(app_root),
        hermes_home=str(hermes_home.resolve()),
        cwd=str(cwd),
        user=user,
        platform=plat,
        writable_roots=list_writable_roots(app_root=app_root, hermes_home=hermes_home, cwd=cwd),
        terminal_backend=(os.getenv("TERMINAL_ENV") or "local").strip().lower() or "local",
    )


def stale_path_rewrite_map(meta: RuntimeMetadata | None = None) -> list[tuple[str, str]]:
    """Ordered (old_prefix, new_prefix) rewrites for recalled memory/text."""
    meta = meta or collect_runtime_metadata()
    audit_target = _prefer_existing(
        (
            Path(meta.app_root) / "audit",
            Path(meta.hermes_home) / "audit",
            Path(meta.cwd) / "audit",
        ),
        fallback=str(Path(meta.app_root) / "audit"),
    )
    obsidian_target = _prefer_existing(
        (
            Path("/opt/hermes/data/obsidian/Growth OS"),
            Path("/opt/hermes/data/obsidian"),
            Path(meta.hermes_home) / "obsidian-vault",
            Path("/opt/hermes/obsidian-vault"),
            Path.home() / "obsidian-vault",
        ),
        fallback=str(Path("/opt/hermes/data/obsidian/Growth OS")),
    )
    return [
        ("/usr/local/lib/hermes-agent", meta.app_root),
        ("/root/.hermes", meta.hermes_home),
        ("/root/audit", audit_target),
        ("/root/obsidian-vault", obsidian_target),
        ("/root/.git", str(Path(meta.app_root) / ".git")),
    ]


def remap_stale_paths(text: str, meta: RuntimeMetadata | None = None) -> str:
    """Rewrite known stale deployment paths to the live deployment."""
    if not text or ("/root" not in text and "/usr/local/lib/hermes-agent" not in text):
        return text
    meta = meta or collect_runtime_metadata()
    rewritten = text
    for old, new in stale_path_rewrite_map(meta):
        if old != new:
            rewritten = rewritten.replace(old, new)
    # Cover bare /root cwd tokens and /root/.git left after prefix rewrites.
    from agent.path_boundary import remap_stale_path_text

    rewritten = remap_stale_path_text(
        rewritten,
        app_root=meta.app_root,
        hermes_home=meta.hermes_home,
    )
    return rewritten


def discover_under_roots(relative: str, roots: Iterable[str] | None = None) -> list[str]:
    """Return existing joins of *relative* under configured writable roots."""
    rel = relative.lstrip("/")
    results: list[str] = []
    for root in roots or list_writable_roots():
        candidate = Path(root) / rel
        if candidate.exists():
            results.append(str(candidate.resolve()))
    return results


def _prefer_existing(candidates: Iterable[Path], *, fallback: str) -> str:
    for path in candidates:
        try:
            if path.is_dir():
                return str(path.resolve())
        except OSError:
            continue
    return fallback
