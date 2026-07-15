"""Path-boundary guards for post-migration Hermes deployments.

Prevents local backends from treating inaccessible legacy roots (especially
``/root`` and ``/root/.git``) as valid session cwds or git-discovery walk
targets. Remote/container backends may still legitimately use ``/root``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

# Exact paths that must never be used as a local session cwd on a non-root
# service user after the /opt/hermes migration.
_BLOCKED_EXACT = frozenset({
    "/root",
    "/root/.git",
    "/root/.hermes",
    "/root/audit",
    "/root/obsidian-vault",
    "/usr/local/lib/hermes-agent",
})

# Prefixes blocked for local cwd / git walks (trailing slash required except
# for exact matches handled above).
_BLOCKED_PREFIXES = (
    "/root/",
    "/root/.hermes/",
    "/root/audit/",
    "/root/obsidian-vault/",
    "/usr/local/lib/hermes-agent/",
    "/root/.hermes/worktrees/",
)


def is_local_terminal_backend() -> bool:
    backend = (os.environ.get("TERMINAL_ENV") or "").strip().lower()
    return not backend or backend == "local"


def normalize_path_string(path: str | Path | None) -> str:
    raw = str(path or "").strip()
    if not raw:
        return ""
    try:
        return os.path.abspath(os.path.expanduser(raw))
    except Exception:
        return raw.rstrip("/") or raw


def is_blocked_legacy_path(path: str | Path | None) -> bool:
    """True for migration-stale /root (and related) locations."""
    resolved = normalize_path_string(path)
    if not resolved:
        return False
    if resolved in _BLOCKED_EXACT:
        return True
    # Bare "/root" already handled; anything under it is blocked too.
    if resolved == "/root" or resolved.startswith("/root/"):
        return True
    for prefix in _BLOCKED_PREFIXES:
        if resolved.startswith(prefix.rstrip("/")) or resolved.startswith(prefix):
            return True
    return False


def path_is_usable_dir(path: str | Path | None) -> bool:
    """Directory exists AND is traversable for this process (local backends)."""
    resolved = normalize_path_string(path)
    if not resolved:
        return False
    if is_local_terminal_backend() and is_blocked_legacy_path(resolved):
        return False
    try:
        if not os.path.isdir(resolved):
            return False
        # isdir("/root") is True for dylan, but access fails — reject early.
        if not os.access(resolved, os.R_OK | os.X_OK):
            return False
    except OSError:
        return False
    return True


def safe_exists(path: str | Path) -> bool:
    """``Path.exists()`` that never raises PermissionError."""
    try:
        return Path(path).exists()
    except OSError:
        return False


def preferred_fallback_cwd() -> str:
    """Authoritative fallback: app root → HERMES_HOME → home → cwd."""
    candidates: list[str] = []
    env_app = (os.getenv("HERMES_APP_ROOT") or "").strip()
    if env_app:
        candidates.append(env_app)
    candidates.extend(
        [
            "/opt/hermes/app",
            str(Path(__file__).resolve().parent.parent),
        ]
    )
    hermes_home = (os.getenv("HERMES_HOME") or "").strip()
    if hermes_home:
        candidates.append(hermes_home)
    candidates.extend(["/opt/hermes/home", str(Path.home())])
    try:
        candidates.append(os.getcwd())
    except OSError:
        pass

    for candidate in candidates:
        if path_is_usable_dir(candidate):
            return normalize_path_string(candidate)
    return str(Path.home())


def sanitize_cwd(path: str | Path | None, *, fallback: str | None = None) -> str:
    """Return *path* if usable, else a safe authoritative fallback."""
    resolved = normalize_path_string(path)
    if path_is_usable_dir(resolved):
        return resolved
    fb = fallback if fallback and path_is_usable_dir(fallback) else preferred_fallback_cwd()
    return normalize_path_string(fb)


def remap_stale_path_text(text: str, *, app_root: str | None = None, hermes_home: str | None = None) -> str:
    """Rewrite stale path strings in free text (memory, prompts, logs)."""
    if not text:
        return text
    app = app_root or preferred_fallback_cwd()
    home = hermes_home or (os.getenv("HERMES_HOME") or "").strip() or "/opt/hermes/home"
    audit = app.rstrip("/") + "/audit"
    if path_is_usable_dir("/opt/hermes/app/audit"):
        audit = "/opt/hermes/app/audit"
    obsidian = "/opt/hermes/data/obsidian/Growth OS"
    replacements = (
        ("/usr/local/lib/hermes-agent", app),
        ("/root/.hermes/worktrees", home.rstrip("/") + "/worktrees"),
        ("/root/.hermes", home),
        ("/root/audit", audit),
        ("/root/obsidian-vault", obsidian),
        ("/root/.git", app.rstrip("/") + "/.git"),
    )
    out = text
    for old, new in replacements:
        if old != new:
            out = out.replace(old, new)
    # Bare `/root` as a path token (cwd). Avoid replacing `/root` inside already
    # remapped longer paths by doing word-ish boundaries after longer rewrites.
    if "/root" in out:
        # Replace standalone "/root" directory references commonly used as cwd.
        for token in ("/root/", "/root"):
            # Only swap exact remaining "/root" leftovers that weren't longer prefixes.
            pass
        # Final pass: if text is just "/root" or ends with " cwd=/root"
        if out.strip() == "/root" or out.rstrip("/").endswith(":/root"):
            out = out.replace("/root", app)
        # Common JSON/cwd fields
        out = out.replace('"cwd": "/root"', f'"cwd": "{app}"')
        out = out.replace("cwd=/root\n", f"cwd={app}\n")
        out = out.replace("cwd=/root ", f"cwd={app} ")
        if out.rstrip() == "/root":
            out = app
    return out


def git_walk_parents(start: Path) -> Iterable[Path]:
    """Yield start + parents, skipping blocked/inaccessible nodes."""
    try:
        current = start.expanduser().resolve()
    except OSError:
        return
    for parent in [current, *current.parents]:
        parent_s = str(parent)
        if is_local_terminal_backend() and is_blocked_legacy_path(parent_s):
            break
        # Stop before filesystem root walks into unrelated privileged trees.
        if parent_s == "/":
            yield parent
            break
        yield parent
