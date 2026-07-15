"""Single source of truth for the agent working directory.

`TERMINAL_CWD` is the runtime carrier for the configured working directory
(design #19214/#19242: `terminal.cwd` is bridged once to `TERMINAL_CWD` at
gateway/cron startup). The local-CLI backend deliberately leaves it unset and
relies on the launch dir. Reading it in one place keeps the system prompt, the
tool surfaces, and context-file discovery agreeing on where the agent lives.

Multi-session gateways can pin a logical cwd via the `_SESSION_CWD`
contextvar; CLI/cron fall through to `TERMINAL_CWD`/launch cwd.
"""

import os
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any

_UNSET: Any = object()

_SESSION_CWD: ContextVar = ContextVar("HERMES_SESSION_CWD", default=_UNSET)


def set_session_cwd(cwd: str | None) -> Token:
    """Pin the logical cwd for the current context."""
    return _SESSION_CWD.set((cwd or "").strip())


def clear_session_cwd() -> None:
    _SESSION_CWD.set("")


def _session_cwd_override() -> str:
    value = _SESSION_CWD.get()
    if value is _UNSET:
        return ""
    return str(value).strip()


def resolve_agent_cwd() -> Path:
    from agent.path_boundary import path_is_usable_dir, sanitize_cwd

    override = _session_cwd_override()
    if override:
        p = Path(override).expanduser()
        if path_is_usable_dir(p):
            return p
        return Path(sanitize_cwd(p))
    raw = os.environ.get("TERMINAL_CWD", "").strip()
    if raw:
        p = Path(raw).expanduser()
        if path_is_usable_dir(p):
            return p
        return Path(sanitize_cwd(p))
    try:
        cwd = Path(os.getcwd())
    except OSError:
        return Path(sanitize_cwd(None))
    if path_is_usable_dir(cwd):
        return cwd
    return Path(sanitize_cwd(cwd))


def resolve_context_cwd() -> Path | None:
    # None means "no configured cwd": build_context_files_prompt then falls back
    # to the launch dir (os.getcwd()) — correct for the local CLI. The gateway
    # avoids slurping its install dir by setting TERMINAL_CWD (see system_prompt.py)
    # or, per session, the _SESSION_CWD contextvar above.
    from agent.path_boundary import path_is_usable_dir, sanitize_cwd

    override = _session_cwd_override()
    if override:
        p = Path(override).expanduser()
        return Path(sanitize_cwd(p)) if not path_is_usable_dir(p) else p
    raw = os.environ.get("TERMINAL_CWD", "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return Path(sanitize_cwd(p)) if not path_is_usable_dir(p) else p
