"""Tests for Obsidian MCP normalization."""

from __future__ import annotations

import pytest

from hermes_cli.obsidian_mcp_normalize import (
    normalize_obsidian_mcp_entry,
    obsidian_mcp_needs_normalize,
)


def test_needs_normalize_local_http_url():
    entry = {"url": "https://127.0.0.1:27124/mcp/", "headers": {"Authorization": "Bearer x"}}
    assert obsidian_mcp_needs_normalize(entry) is True


def test_needs_normalize_stale_mount():
    entry = {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/root/obsidian-vault"],
    }
    assert obsidian_mcp_needs_normalize(entry) is True


def test_needs_normalize_filesystem_growth_os_false():
    entry = {
        "command": "npx",
        "args": [
            "-y",
            "@modelcontextprotocol/server-filesystem@2026.7.10",
            "/opt/hermes/data/obsidian/Growth OS",
        ],
    }
    assert obsidian_mcp_needs_normalize(entry) is False


def test_normalize_removes_http_and_scopes_mount(tmp_path):
    vault = tmp_path / "Growth OS"
    vault.mkdir()
    (vault / "INDEX.md").write_text("# Index\n", encoding="utf-8")

    entry = {
        "url": "https://127.0.0.1:27124/mcp/",
        "headers": {"Authorization": "Bearer secret"},
        "enabled": True,
    }
    normalized, changes = normalize_obsidian_mcp_entry(entry, vault_path=str(vault))
    assert "url" not in normalized
    assert "headers" not in normalized
    assert normalized["args"][-1] == str(vault)
    assert "read_text_file" in normalized["tools"]["include"]
    assert any("removed unreachable HTTP" in c for c in changes)
