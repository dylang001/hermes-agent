"""Project context brief + section index (Phase 1 context-cost remediation)."""

from pathlib import Path

from agent.project_brief import (
    build_project_brief_and_index,
    parse_markdown_sections,
)


SAMPLE_AGENTS = """# Hermes Agent

Hermes is a personal AI agent that runs across CLI and messaging.

## What Hermes Is

Long body about the product that should NOT appear in the brief dump.

### Nested Detail

More nested content.

## Contribution Rubric

Rules for contributions that are huge in the real file.
"""


def test_parse_markdown_sections_finds_headings():
    sections = parse_markdown_sections(SAMPLE_AGENTS)
    titles = [s.title for s in sections]
    assert "Hermes Agent" in titles
    assert "What Hermes Is" in titles
    assert "Contribution Rubric" in titles


def test_brief_omits_full_section_bodies():
    brief = build_project_brief_and_index(
        SAMPLE_AGENTS,
        source_path="/proj/AGENTS.md",
        source_label="AGENTS.md",
    )
    assert "Project Context Brief" in brief or "project context brief" in brief.lower()
    assert "What Hermes Is" in brief  # index entry
    assert "Contribution Rubric" in brief
    assert "Long body about the product" not in brief
    assert "Rules for contributions that are huge" not in brief
    assert "read_file" in brief
    assert "/proj/AGENTS.md" in brief


def test_brief_includes_short_intro_when_present():
    brief = build_project_brief_and_index(
        SAMPLE_AGENTS,
        source_path="/proj/AGENTS.md",
        source_label="AGENTS.md",
    )
    assert "personal AI agent" in brief


def test_brief_stays_under_char_budget():
    huge = "# Title\n\nIntro paragraph.\n\n" + "\n\n".join(
        f"## Section {i}\n\n{'x' * 5000}" for i in range(40)
    )
    brief = build_project_brief_and_index(
        huge,
        source_path="/proj/AGENTS.md",
        source_label="AGENTS.md",
        max_chars=4000,
    )
    assert len(brief) <= 4000
    assert "Section index" in brief or "section index" in brief.lower()


def test_build_context_files_prompt_uses_brief_not_full_body(tmp_path, monkeypatch):
    agents = tmp_path / "AGENTS.md"
    agents.write_text(SAMPLE_AGENTS + ("\n\n## Extra\n\n" + ("y" * 20_000)), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / ".hermes"))
    (tmp_path / ".hermes").mkdir()
    monkeypatch.setattr(
        "hermes_cli.config.load_config",
        lambda: {
            "context_file_max_chars": 8000,
            "context_project_brief": True,
        },
    )
    from agent.prompt_builder import build_context_files_prompt

    prompt = build_context_files_prompt(cwd=str(tmp_path), skip_soul=True)
    assert prompt
    assert "y" * 100 not in prompt  # full body not dumped
    assert "Extra" in prompt  # section title in index
    assert str(agents) in prompt or "AGENTS.md" in prompt
