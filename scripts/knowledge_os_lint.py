#!/usr/bin/env python3
"""Read-only Knowledge OS lint for Growth OS.

Detects broken/ambiguous wikilinks, missing brain frontmatter, duplicate stems,
and CANONICAL without promoted_by. Never mutates the vault.

Usage:
  python scripts/knowledge_os_lint.py [/path/to/Growth OS]
  HERMES_GROWTH_OS=/path python scripts/knowledge_os_lint.py

Exit codes: 0 = no CRITICAL, 1 = CRITICAL findings, 2 = usage/path error.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

LINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
STATUS_RE = re.compile(r"(?m)^status:\s*(\S+)")
TYPE_RE = re.compile(r"(?m)^type:\s*(\S+)")
PROMOTED_RE = re.compile(r"(?m)^promoted_by:\s*(.+)$")

PLACEHOLDERS = {"wikilink", "wikilinks", "related note", "canonical doc"}
PARA_SUBS = ("00 Inbox", "01 Projects", "02 Areas", "03 Decisions", "04 Runbooks", "05 Receipts")


def resolve_growth_os(argv: list[str]) -> Path:
    if len(argv) > 1:
        return Path(argv[1]).expanduser().resolve()
    env = os.environ.get("HERMES_GROWTH_OS")
    if env:
        return Path(env).expanduser().resolve()
    return (Path.home() / "Documents/Obsidian Vault/Growth OS").resolve()


def has_frontmatter(text: str) -> bool:
    return text.startswith("---\n")


def parse_fm_field(text: str, pattern: re.Pattern[str]) -> str | None:
    m = pattern.search(text)
    return m.group(1).strip() if m else None


def under_raw(path: Path, growth: Path) -> bool:
    try:
        return path.resolve().is_relative_to((growth / "raw").resolve())
    except Exception:
        return "raw/" in str(path)


def collect_md(growth: Path, vault_root: Path) -> tuple[list[Path], list[Path]]:
    """Return (growth_os_md, all_md_for_stems)."""
    skip = {".git", ".obsidian", ".trash", "node_modules"}
    growth_md: list[Path] = []
    for p in growth.rglob("*.md"):
        if any(part in skip for part in p.parts):
            continue
        growth_md.append(p)

    stems_md = list(growth_md)
    stems_md.extend(vault_root.glob("*.md"))
    for sub in PARA_SUBS:
        d = vault_root / sub
        if d.is_dir():
            stems_md.extend(d.rglob("*.md"))
    return growth_md, stems_md


def main() -> int:
    growth = resolve_growth_os(sys.argv)
    if not growth.is_dir():
        print(f"ERROR: Growth OS path not found: {growth}", file=sys.stderr)
        return 2

    vault_root = growth.parent
    md_files, all_for_stems = collect_md(growth, vault_root)

    by_stem: dict[str, list[Path]] = defaultdict(list)
    for p in all_for_stems:
        by_stem[p.stem].append(p)

    findings: list[dict] = []

    def add(sev: str, kind: str, path: Path, detail: str) -> None:
        findings.append(
            {
                "severity": sev,
                "kind": kind,
                "path": str(path.relative_to(vault_root) if path.is_relative_to(vault_root) else path),
                "detail": detail,
            }
        )

    for stem, paths in sorted(by_stem.items()):
        uniq = {p.resolve() for p in paths}
        if len(uniq) < 2 or stem == "README":
            continue
        # Ignore collisions entirely inside raw/exports (evidence copies)
        if all(under_raw(p, growth) for p in uniq):
            continue
        rels = [str(p.relative_to(vault_root)) for p in sorted(uniq)]
        add("CRITICAL", "duplicate_stem", next(iter(uniq)), f"{stem} => {rels}")

    for p in md_files:
        # Skip generated lint reports (self-referential noise)
        if "workspace/drafts" in str(p) and "wiki-lint" in p.name:
            continue
        text = p.read_text(errors="replace")
        rel = p.relative_to(growth)
        in_raw = under_raw(p, growth)

        if (
            str(rel).startswith("brain/")
            and "_indexes" not in str(rel)
            and p.suffix == ".md"
        ):
            if not has_frontmatter(text):
                add("WARN", "missing_frontmatter", p, "brain page lacks YAML frontmatter")
            else:
                status = parse_fm_field(text, STATUS_RE)
                if not status:
                    add("WARN", "missing_status", p, "brain page missing status:")
                elif status.upper() == "CANONICAL":
                    promo = parse_fm_field(text, PROMOTED_RE)
                    if not promo or promo in ("null", "None", "~", ""):
                        add(
                            "CRITICAL",
                            "canonical_without_promoted_by",
                            p,
                            "CANONICAL requires promoted_by",
                        )
                if not parse_fm_field(text, TYPE_RE):
                    add("WARN", "missing_type", p, "brain page missing type:")

        for m in LINK_RE.finditer(text):
            target = m.group(1).strip()
            low = target.lower()
            if "yyyy" in low or low in PLACEHOLDERS:
                add("WARN", "placeholder_link", p, f"[[{target}]]")
                continue
            stem = Path(target).name
            candidates: list[Path] = []
            for base in (p.parent, growth, vault_root):
                for cand in (base / f"{target}.md", base / target):
                    if cand.is_file():
                        candidates.append(cand)
            if stem in by_stem:
                candidates.extend(by_stem[stem])
            uniq = {c.resolve() for c in candidates if c.exists()}
            if not uniq:
                if (growth / target).exists() or (p.parent / target).exists():
                    add("INFO", "non_md_link", p, f"[[{target}]] exists but is not .md")
                elif in_raw:
                    add("INFO", "broken_link_in_raw", p, f"[[{target}]]")
                else:
                    add("CRITICAL", "broken_link", p, f"[[{target}]]")
            elif len(uniq) > 1:
                # Prefer treating raw/exports collisions as INFO when one side is live SoT
                live = [u for u in uniq if not under_raw(u, growth)]
                if len(live) == 1 and any(under_raw(u, growth) for u in uniq):
                    continue  # resolved to live page; export copy ignored
                rels = sorted(
                    str(u.relative_to(vault_root)) if u.is_relative_to(vault_root) else str(u)
                    for u in uniq
                )
                add("CRITICAL", "ambiguous_link", p, f"[[{target}]] => {rels}")

    crit = [f for f in findings if f["severity"] == "CRITICAL"]
    warn = [f for f in findings if f["severity"] == "WARN"]
    info = [f for f in findings if f["severity"] == "INFO"]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "growth_os": str(growth),
        "md_files_scanned": len(md_files),
        "counts": {"CRITICAL": len(crit), "WARN": len(warn), "INFO": len(info)},
        "findings": findings,
    }

    out_dir = growth / "workspace" / "drafts"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    json_path = out_dir / f"{stamp}-wiki-lint.json"
    md_path = out_dir / f"{stamp}-wiki-lint.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        f"# Wiki lint — {stamp}",
        "",
        f"Growth OS: `{growth}`",
        f"CRITICAL: {len(crit)} · WARN: {len(warn)} · INFO: {len(info)}",
        "",
        "## CRITICAL",
        "",
    ]
    if not crit:
        lines.append("_None._")
    for f in crit:
        lines.append(f"- `{f['path']}` — **{f['kind']}**: {f['detail']}")
    lines += ["", "## WARN", ""]
    if not warn:
        lines.append("_None._")
    for f in warn:
        lines.append(f"- `{f['path']}` — **{f['kind']}**: {f['detail']}")
    lines.append("")
    md_path.write_text("\n".join(lines))

    print(f"Lint wrote {md_path}")
    print(f"CRITICAL={len(crit)} WARN={len(warn)} INFO={len(info)}")
    for f in crit[:40]:
        print(f"  CRITICAL {f['kind']}: {f['path']} :: {f['detail']}")
    return 1 if crit else 0


if __name__ == "__main__":
    raise SystemExit(main())
