"""Tests for Knowledge OS mutation hooks / receipt wrapper."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.knowledge_os_mutation import (
    MutationSession,
    in_approved_lane,
    is_protected,
    parse_frontmatter,
)


@pytest.fixture
def growth(tmp_path: Path) -> Path:
    g = tmp_path / "Growth OS"
    (g / "brain" / "concepts").mkdir(parents=True)
    (g / "workspace" / "receipts").mkdir(parents=True)
    (g / "raw" / "exports").mkdir(parents=True)
    (g / "compile-log.md").write_text("# Compile log\n", encoding="utf-8")
    (g / "hot.md").write_text("# Hot\n", encoding="utf-8")
    (g / "AGENTS.md").write_text("---\nsource_of_truth: true\n---\n", encoding="utf-8")
    return g


def test_lanes_and_protected():
    assert is_protected("AGENTS.md")
    assert is_protected("SCHEMA.md")
    assert not in_approved_lane("AGENTS.md")
    assert in_approved_lane("brain/concepts/x.md")
    assert in_approved_lane("workspace/drafts/a.md")
    assert in_approved_lane("hot.md")
    assert in_approved_lane("compile-log.md")
    assert in_approved_lane("raw/exports/a.md")
    assert not in_approved_lane("Constitution/x.md")
    assert not in_approved_lane("Strategy/x.md")


def test_preflight_blocks_protected(growth: Path):
    s = MutationSession("t1", "wiki-ingest", growth)
    with pytest.raises(PermissionError, match="protected"):
        s.preflight_path("AGENTS.md", op="update")


def test_preflight_blocks_obsolete_trees(growth: Path):
    s = MutationSession("t1", "wiki-ingest", growth)
    with pytest.raises(PermissionError, match="approved"):
        s.preflight_path("Strategy/foo.md", op="create")


def test_blocks_canonical_status(growth: Path):
    s = MutationSession("t1", "wiki-ingest", growth)
    body = "---\ntitle: X\ntype: concept\nstatus: CANONICAL\n---\n\n# X\n"
    with pytest.raises(PermissionError, match="lifecycle blocked"):
        s.write_text("brain/concepts/x.md", body)


def test_raw_immutable_after_create(growth: Path):
    s = MutationSession("t1", "wiki-ingest", growth)
    s.write_text("raw/exports/a.md", "hello\n", op="create")
    with pytest.raises(PermissionError, match="immutable"):
        s.write_text("raw/exports/a.md", "mutated\n", op="update")


def test_append_only_compile_log(growth: Path):
    s = MutationSession("t1", "wiki-ingest", growth)
    s.append_text("compile-log.md", "## 2026-07-21 test\n")
    text = (growth / "compile-log.md").read_text(encoding="utf-8")
    assert text.startswith("# Compile log\n")
    assert "## 2026-07-21 test" in text
    with pytest.raises(PermissionError, match="append-only"):
        s.preflight_path("compile-log.md", op="update")


def test_finalize_requires_complete_receipt(growth: Path):
    s = MutationSession("t1", "wiki-ingest", growth)
    s.write_text(
        "brain/concepts/ep-test.md",
        "---\ntitle: T\ntype: concept\nstatus: DRAFT\n---\n\n# T\n",
    )
    s.append_text("compile-log.md", "- test\n")
    receipt = s.emit_receipt()
    doc = json.loads(receipt.read_text(encoding="utf-8"))
    assert doc["schema"] == "kos-touched-path-receipt/v1"
    paths = {p["path"] for p in doc["paths"]}
    assert "brain/concepts/ep-test.md" in paths
    assert "compile-log.md" in paths
    assert doc["skill"] == "wiki-ingest"


def test_postflight_fails_if_hash_drift(growth: Path):
    s = MutationSession("t1", "wiki-ingest", growth)
    s.write_text(
        "brain/concepts/ep-test.md",
        "---\ntitle: T\ntype: concept\nstatus: DRAFT\n---\n\n# T\n",
    )
    # corrupt recorded hash
    s.touched[0].sha256 = "0" * 64
    errs = s.postflight()
    assert any("hash mismatch" in e for e in errs)


def test_parse_frontmatter():
    fm = parse_frontmatter("---\nstatus: STRUCTURED\ntitle: Hi\n---\n\nBody\n")
    assert fm["status"] == "STRUCTURED"
