from pathlib import Path

from agent.capability_gap import build_gap_report
from agent.skill_discovery import classify_task_tags, evaluate_skill_dir, propose_discovery
from hermes_cli.capability_profiles import apply_profile_to_config, list_profiles, load_profile


def test_capability_gap_report_markdown():
    report = build_gap_report(
        requested_outcome="Search Obsidian Growth OS",
        missing_capability="obsidian MCP mount path",
        alternatives_checked=["native filesystem under /opt/hermes/data/obsidian"],
        recommended=["mcp_servers.obsidian path fix", "obsidian skill"],
        installation_risk="low",
        engineering_required=False,
    )
    md = report.to_markdown()
    assert "Capability gap" in md
    assert "obsidian MCP" in md


def test_skill_discovery_classify_and_propose():
    assert "engineering" in classify_task_tags("fix the pytest regression and open a PR")
    proposal = propose_discovery("write Orchidea newsletter copy")
    assert "content" in proposal["task_tags"]
    assert proposal["next_steps"]


def test_evaluate_skill_dir_flags_scripts(tmp_path: Path):
    skill = tmp_path / "demo-skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "scripts" / "run.sh").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    (skill / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo skill.\n---\n\nUses `terminal`.\n",
        encoding="utf-8",
    )
    ev = evaluate_skill_dir(skill, source="official")
    assert ev.has_scripts
    assert ev.requires_approval
    assert ev.checksum


def test_capability_profiles_load_and_apply():
    names = list_profiles()
    assert "daily-ops" in names
    assert "task-os" in names
    profile = load_profile("daily-ops")
    merged = apply_profile_to_config({}, profile)
    assert "file" in merged["tools"]["cli"]["enabled"]
    assert merged["agent"]["capability_profile"] == "daily-ops"
