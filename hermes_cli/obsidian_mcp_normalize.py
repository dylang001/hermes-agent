"""Normalize Obsidian MCP entries to scoped filesystem Growth OS mounts.

VPS agents cannot reach Obsidian Local REST API on the operator Mac
(``https://127.0.0.1:27124/mcp/``). Production posture: one stdio
``@modelcontextprotocol/server-filesystem`` mount on the Growth OS vault only.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

STALE_MOUNT_FRAGMENTS = ("/root/obsidian-vault",)
FILESYSTEM_MCP_PACKAGE = "@modelcontextprotocol/server-filesystem@2026.7.10"
DEFAULT_TOOL_INCLUDE = (
    "read_text_file",
    "list_directory",
    "search_files",
    "get_file_info",
)


def _growth_os_candidates() -> list[Path]:
    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser()
    return [
        Path("/opt/hermes/data/obsidian/Growth OS"),
        Path.home() / "Documents/Obsidian Vault/Growth OS",
        home / "data/obsidian/Growth OS",
    ]


def resolve_growth_os_vault_path() -> str | None:
    for candidate in _growth_os_candidates():
        try:
            if candidate.is_dir():
                return str(candidate.resolve())
        except OSError:
            continue
    return None


def _is_local_http_obsidian_url(url: str) -> bool:
    stripped = (url or "").strip()
    if not stripped:
        return False
    try:
        parsed = urlparse(stripped)
    except Exception:
        return False
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return False
    return parsed.scheme.lower() in {"http", "https"}


def obsidian_mcp_needs_normalize(entry: dict[str, Any] | None) -> bool:
    if not isinstance(entry, dict):
        return False
    url = entry.get("url")
    if isinstance(url, str) and _is_local_http_obsidian_url(url):
        return True
    args = entry.get("args") or []
    if not isinstance(args, list):
        args = [args]
    for arg in args:
        text = str(arg)
        if any(stale in text for stale in STALE_MOUNT_FRAGMENTS):
            return True
        if text == "@modelcontextprotocol/server-filesystem":
            return True
    return False


def _resolve_npx_command() -> str:
    for candidate in (
        shutil.which("npx"),
        "/usr/local/bin/npx",
        "/opt/homebrew/bin/npx",
        os.path.expanduser("~/.local/bin/npx"),
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return "npx"


def normalize_obsidian_mcp_entry(
    entry: dict[str, Any] | None,
    *,
    vault_path: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Return a filesystem MCP entry and human-readable change notes."""
    changes: list[str] = []
    vault = vault_path or resolve_growth_os_vault_path()
    if not vault:
        raise ValueError(
            "Growth OS vault directory not found — expected one of: "
            + ", ".join(str(p) for p in _growth_os_candidates())
        )

    prior = dict(entry) if isinstance(entry, dict) else {}
    if prior.get("url"):
        changes.append(f"removed unreachable HTTP url={prior.get('url')!r}")
    if prior.get("headers"):
        changes.append("removed HTTP Authorization headers (filesystem MCP)")
    if prior.get("auth"):
        changes.append(f"removed auth={prior.get('auth')!r}")

    normalized: dict[str, Any] = {
        "command": prior.get("command") or _resolve_npx_command(),
        "args": [
            "-y",
            FILESYSTEM_MCP_PACKAGE,
            vault,
        ],
        "enabled": prior.get("enabled", True),
        "connect_timeout": min(float(prior.get("connect_timeout", 15) or 15), 15),
        "tools": {
            "include": list(
                (prior.get("tools") or {}).get("include") or DEFAULT_TOOL_INCLUDE
            ),
        },
    }
    if str(prior.get("args", [""])[-1] if prior.get("args") else "") != vault:
        changes.append(f"mount scoped to Growth OS at {vault}")
    return normalized, changes
