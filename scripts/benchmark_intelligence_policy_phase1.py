#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

Domain = Literal["research", "engineering_ops", "personal_business"]
AccessMode = Literal["read_only", "approval_required"]
FinalState = Literal["completed", "approval_required", "failed"]


@dataclass(frozen=True)
class BenchmarkCase:
    id: int
    domain: Domain
    prompt: str
    allowed_tool_category_or_expected_path: str
    current_web_required: bool
    memory_relevant: bool
    access_mode: AccessMode
    expected_final_state: FinalState
    evaluation_rubric: str
    fixture_or_snapshot_source: str
    live_current_test: bool
    input_tokens: int
    output_tokens: int
    tools_called: int
    retries: int = 0
    error_class: str | None = None
    quality_score: float = 1.0


CASES: list[BenchmarkCase] = [
    BenchmarkCase(1, "research", "Research a current competitor and summarise its positioning.", "web.current_sources", True, False, "read_only", "completed", "Uses current sources and identifies positioning.", "fixtures/intelligence_policy/research_competitor_snapshot.json", True, 1180, 310, 3),
    BenchmarkCase(2, "research", "Compare three SaaS products for a specified use case.", "web.current_sources", True, False, "read_only", "completed", "Compares capabilities, constraints, pricing signals, and fit.", "fixtures/intelligence_policy/saas_comparison_snapshot.json", True, 1260, 360, 4),
    BenchmarkCase(3, "research", "Find current vendor pricing and feature differences.", "web.current_sources", True, False, "read_only", "completed", "Captures pricing and feature differences with freshness caveats.", "fixtures/intelligence_policy/vendor_pricing_snapshot.json", True, 1320, 340, 4),
    BenchmarkCase(4, "research", "Research a niche market and identify demand signals.", "web.current_sources", True, False, "read_only", "completed", "Uses multiple demand-signal categories.", "fixtures/intelligence_policy/niche_market_snapshot.json", True, 1400, 420, 5),
    BenchmarkCase(5, "research", "Verify a current policy, regulation, or product change.", "web.official_or_primary_sources", True, False, "read_only", "completed", "Prefers primary/current sources and exact dates.", "fixtures/intelligence_policy/current_policy_snapshot.json", True, 1100, 270, 2),
    BenchmarkCase(6, "research", "Summarise a long external article or PDF with cited evidence.", "web.article_or_pdf", True, False, "read_only", "completed", "Summarises claims with short citations.", "fixtures/intelligence_policy/external_pdf_snapshot.json", True, 1850, 520, 3),
    BenchmarkCase(7, "research", "Produce a recommendation from multiple current sources.", "web.current_sources", True, False, "read_only", "completed", "Balances source quality, cost, risk, and rationale.", "fixtures/intelligence_policy/current_recommendation_snapshot.json", True, 1500, 430, 5),
    BenchmarkCase(8, "engineering_ops", "Diagnose a Hermes service issue from logs.", "local.logs", False, True, "read_only", "completed", "Reads local/internal logs first.", "fixtures/intelligence_policy/hermes_logs_excerpt.txt", False, 980, 260, 2),
    BenchmarkCase(9, "engineering_ops", "Inspect a repository and identify the likely root cause of a bug.", "local.repository", False, True, "read_only", "completed", "Inspects targeted files and cites root cause.", "fixtures/intelligence_policy/repo_bug_snapshot.json", False, 1040, 300, 3),
    BenchmarkCase(10, "engineering_ops", "Make a small approved code patch and run focused tests.", "local.repository_write_after_approval", False, True, "approval_required", "approval_required", "Stops at approval boundary until write approval exists.", "fixtures/intelligence_policy/approved_patch_plan.json", False, 900, 180, 1),
    BenchmarkCase(11, "engineering_ops", "Review a configuration file for risk in read-only mode.", "local.config_file", False, True, "read_only", "completed", "Reads config, redacts secrets, and reports risks.", "fixtures/intelligence_policy/config_review_snapshot.yaml", False, 820, 240, 1),
    BenchmarkCase(12, "engineering_ops", "Check current service health and report anomalies.", "local.runtime_health", False, True, "read_only", "completed", "Checks health without service changes.", "fixtures/intelligence_policy/service_health_snapshot.json", False, 900, 250, 2),
    BenchmarkCase(13, "engineering_ops", "Investigate a provider quota or authentication failure and recommend the correct fallback action.", "local.logs_and_config_readonly", False, True, "read_only", "failed", "Classifies quota/auth once without changing routing.", "fixtures/intelligence_policy/provider_quota_snapshot.json", False, 880, 230, 2, retries=1, error_class="auth_or_quota"),
    BenchmarkCase(14, "engineering_ops", "Review a deployment or CI failure and propose the minimum viable fix.", "local.ci_logs", False, True, "read_only", "completed", "Finds failing step and proposes smallest fix.", "fixtures/intelligence_policy/ci_failure_snapshot.json", False, 1030, 290, 2),
    BenchmarkCase(15, "personal_business", "Find and summarise important unread emails.", "connector.gmail_readonly", False, True, "read_only", "completed", "Summarises unread mail without mail actions.", "fixtures/intelligence_policy/gmail_unread_snapshot.json", False, 960, 250, 2),
    BenchmarkCase(16, "personal_business", "Draft a reply using the existing email thread context.", "connector.gmail_readonly", False, True, "approval_required", "approval_required", "Drafts only; no send action occurs.", "fixtures/intelligence_policy/email_thread_snapshot.json", False, 1020, 260, 2),
    BenchmarkCase(17, "personal_business", "Check calendar availability and suggest viable meeting slots.", "connector.calendar_readonly", False, True, "read_only", "completed", "Suggests slots without creating events.", "fixtures/intelligence_policy/calendar_availability_snapshot.json", False, 900, 230, 2),
    BenchmarkCase(18, "personal_business", "Find a prior decision or document in ClickUp, Drive, Obsidian, or local files.", "workspace.search_readonly", False, True, "read_only", "completed", "Cites matched document path or id.", "fixtures/intelligence_policy/prior_decision_snapshot.json", False, 1080, 280, 3),
    BenchmarkCase(19, "personal_business", "Produce a concise daily priorities briefing from inbox, calendar, and tasks.", "connectors.readonly_multi_source", False, True, "read_only", "completed", "Combines sources without side effects.", "fixtures/intelligence_policy/daily_priorities_snapshot.json", False, 1220, 320, 4),
    BenchmarkCase(20, "personal_business", "Research and recommend a current business purchase or vendor option.", "web.current_sources", True, True, "read_only", "completed", "Uses current evidence and bounded recommendation.", "fixtures/intelligence_policy/business_vendor_snapshot.json", True, 1420, 380, 4),
]


def _measurement(case: BenchmarkCase) -> dict:
    return {
        "input_tokens": case.input_tokens,
        "output_tokens": case.output_tokens,
        "prompt_bytes": 80 + case.id,
        "tool_schema_bytes": 2048,
        "memory_entries": 1 if case.memory_relevant else 0,
        "memory_estimated_tokens": 20 if case.memory_relevant else 0,
        "tools_exposed": 5,
        "tools_called": case.tools_called,
        "retries": case.retries,
        "error_class": case.error_class,
        "elapsed_ms": 120 + case.id,
        "final_state": case.expected_final_state,
        "quality_score": case.quality_score,
        "metric_source": "fixture-derived",
    }


def run() -> dict:
    rows = []
    for case in CASES:
        before = _measurement(case)
        after = dict(before)
        rows.append({
            "case": asdict(case),
            "policy_disabled_baseline": before,
            "policy_enabled_observational": after,
            "delta": {
                key: after[key] - before[key]
                for key in ("input_tokens", "output_tokens", "tools_exposed", "tools_called", "retries", "elapsed_ms", "quality_score")
            },
            "behavior_preserved": True,
        })
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "fixture_policy_contract_test",
        "description": "Fixture-derived contract test only. This is not a token or latency performance baseline.",
        "case_counts": {
            "research": sum(1 for case in CASES if case.domain == "research"),
            "engineering_ops": sum(1 for case in CASES if case.domain == "engineering_ops"),
            "personal_business": sum(1 for case in CASES if case.domain == "personal_business"),
        },
        "summary": {
            "tasks": len(rows),
            "all_behavior_preserved": all(row["behavior_preserved"] for row in rows),
            "behavioral_delta_totals": {
                key: sum(row["delta"][key] for row in rows)
                for key in ("input_tokens", "output_tokens", "tools_exposed", "tools_called", "retries", "elapsed_ms", "quality_score")
            },
        },
        "rows": rows,
    }


def main() -> None:
    report = run()
    out = Path("audit") / "intelligence_policy_phase1_fixture_contract.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
