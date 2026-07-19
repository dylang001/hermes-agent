"""Project context brief + section index for lean system prompts.

Replaces dumping full AGENTS.md / CLAUDE.md / .hermes.md / .cursorrules into
the cached system prompt. The model gets a short intro + section TOC and is
directed to ``read_file`` the source path when a section is needed.

Cache-safe: the brief is byte-stable for the session (same as the previous
full-file inject). Mid-session file edits do not rebuild the system prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)

# Soft defaults — config may tighten further via context_file_max_chars.
_DEFAULT_MAX_CHARS = 4_000
_DEFAULT_INTRO_CHARS = 900
_MAX_INDEX_ENTRIES = 60


@dataclass(frozen=True)
class MarkdownSection:
    """One markdown heading and its location in the source text."""

    level: int
    title: str
    start_char: int
    line_number: int  # 1-based


def parse_markdown_sections(content: str) -> List[MarkdownSection]:
    """Return heading entries in document order."""
    sections: List[MarkdownSection] = []
    # Precompute line starts for line-number lookup.
    line_starts = [0]
    for i, ch in enumerate(content):
        if ch == "\n":
            line_starts.append(i + 1)

    def _line_for(pos: int) -> int:
        # Binary search would be fine; linear is fine for typical AGENTS.md.
        line = 1
        for idx, start in enumerate(line_starts):
            if start > pos:
                return max(1, idx)
            line = idx + 1
        return line

    for match in _HEADING_RE.finditer(content):
        level = len(match.group(1))
        title = match.group(2).strip()
        if not title:
            continue
        sections.append(
            MarkdownSection(
                level=level,
                title=title,
                start_char=match.start(),
                line_number=_line_for(match.start()),
            )
        )
    return sections


def _extract_intro(content: str, sections: List[MarkdownSection], max_chars: int) -> str:
    """Text before the first H2+ heading (or after H1), capped."""
    if not content.strip():
        return ""
    # Prefer body after the first H1 until the next heading of any level.
    if sections and sections[0].level == 1:
        start = 0
        # Skip the H1 line itself for the intro body.
        nl = content.find("\n", sections[0].start_char)
        start = nl + 1 if nl != -1 else sections[0].start_char
        end = sections[1].start_char if len(sections) > 1 else len(content)
        intro = content[start:end].strip()
    elif sections:
        intro = content[: sections[0].start_char].strip()
    else:
        intro = content.strip()

    # Collapse excess blank lines.
    intro = re.sub(r"\n{3,}", "\n\n", intro).strip()
    if len(intro) <= max_chars:
        return intro
    cut = intro[: max_chars - 20].rsplit(" ", 1)[0]
    return cut + " …"


def build_project_brief_and_index(
    content: str,
    *,
    source_path: str,
    source_label: str,
    max_chars: int = _DEFAULT_MAX_CHARS,
    intro_chars: int = _DEFAULT_INTRO_CHARS,
) -> str:
    """Build a short project brief + section index for system-prompt injection.

    Full section bodies are intentionally omitted — the model recovers them
    with ``read_file`` on ``source_path`` near the listed line numbers.
    """
    sections = parse_markdown_sections(content)
    intro = _extract_intro(content, sections, intro_chars)

    lines: List[str] = [
        f"# Project Context Brief (from {source_label})",
        "",
        f"Source file: `{source_path}`",
        "Full project instructions are NOT inlined. When a section below is "
        "relevant to the current task, load it with `read_file` "
        f"(path=`{source_path}`, use offset near the listed line).",
        "",
    ]
    if intro:
        lines.extend(["## Overview", "", intro, ""])

    lines.append("## Section index")
    lines.append("")
    if not sections:
        lines.append("(No markdown headings found — read the full source file if needed.)")
    else:
        for i, sec in enumerate(sections[:_MAX_INDEX_ENTRIES], start=1):
            indent = "  " * max(0, sec.level - 1)
            lines.append(f"{indent}{i}. {sec.title}  (line {sec.line_number})")
        if len(sections) > _MAX_INDEX_ENTRIES:
            lines.append(
                f"… +{len(sections) - _MAX_INDEX_ENTRIES} more sections — "
                f"open `{source_path}` for the complete outline."
            )

    brief = "\n".join(lines).strip() + "\n"
    if len(brief) <= max_chars:
        return brief

    # Hard cap: keep header + overview + as many index lines as fit.
    header_end = brief.find("## Section index")
    if header_end == -1:
        return brief[: max_chars - 20] + "\n… [brief truncated]\n"
    head = brief[:header_end]
    index_block = brief[header_end:]
    budget = max_chars - len(head) - 40
    if budget < 80:
        return head[: max_chars - 20] + "\n… [brief truncated]\n"
    trimmed_index = index_block[:budget].rsplit("\n", 1)[0]
    return (
        head
        + trimmed_index
        + "\n… [section index truncated — open source file for full TOC]\n"
    )


def maybe_brief_project_context(
    content: str,
    *,
    source_path: str,
    source_label: str,
    use_brief: bool,
    max_chars: Optional[int] = None,
) -> str:
    """Return brief+index when enabled, else the original content (caller truncates)."""
    if not use_brief:
        return content
    return build_project_brief_and_index(
        content,
        source_path=source_path,
        source_label=source_label,
        max_chars=max_chars or _DEFAULT_MAX_CHARS,
    )
