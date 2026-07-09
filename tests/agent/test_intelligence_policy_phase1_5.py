from __future__ import annotations

from scripts.benchmark_intelligence_policy_phase1 import CASES, run as run_fixture_contract
from scripts.benchmark_intelligence_memory_policy_phase2 import run as run_phase2_memory_benchmark
from scripts.benchmark_intelligence_evidence_compaction_phase4 import run as run_phase4_evidence_benchmark
from scripts.benchmark_intelligence_tool_policy_phase3 import run as run_phase3_tool_benchmark
from scripts.collect_intelligence_policy_runtime_samples import collect_samples


def test_fixture_contract_benchmark_is_labeled_not_performance_baseline():
    report = run_fixture_contract()
    assert report["mode"] == "fixture_policy_contract_test"
    assert "not a token or latency performance baseline" in report["description"]
    assert len(CASES) == 20
    assert report["case_counts"] == {"research": 7, "engineering_ops": 7, "personal_business": 6}
    assert report["summary"]["all_behavior_preserved"] is True
    assert all(row["policy_disabled_baseline"]["metric_source"] == "fixture-derived" for row in report["rows"])
    assert all(row["policy_enabled_observational"]["metric_source"] == "fixture-derived" for row in report["rows"])


def test_mocked_real_runtime_samples_capture_actual_request_sizes(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    report = collect_samples()
    assert report["mode"] == "phase3_mocked_real_runtime_tool_samples"
    domains = {row["sample_domain"] for row in report["reports"]}
    assert domains == {"research", "engineering_ops", "personal_business"}
    modes = {row["sample_mode"] for row in report["reports"]}
    assert modes == {"phase1_5_observational_only", "memory_policy_enabled", "tool_policy_enabled"}

    for row in report["reports"]:
        assert row["runtime_request_bytes"] > 0
        assert row["runtime_request_estimated_tokens"] > 0
        assert row["system_prompt_bytes"] > 1000
        assert row["tool_schema_bytes"] > 1000
        assert row["volatile_context_bytes"] > 0
        assert row["measurement_labels"]["runtime_request_bytes"] == "real_runtime_derived"
        assert row["sample_metric_source"]["prompt_and_schema"] == "real-runtime-derived"
        assert row["sample_metric_source"]["provider_response"] == "mock-runtime-derived"
        assert row["final_state"] == "completed"

    by_id_mode = {(row["sample_id"], row["sample_mode"]): row for row in report["reports"]}
    assert by_id_mode[("research-runtime", "memory_policy_enabled")]["runtime_request_bytes"] <= by_id_mode[("research-runtime", "phase1_5_observational_only")]["runtime_request_bytes"]
    assert by_id_mode[("engineering-runtime", "memory_policy_enabled")]["memory_decision"] in {"project", "light", "user", "full"}
    tool_enabled = by_id_mode[("research-runtime", "tool_policy_enabled")]
    observational = by_id_mode[("research-runtime", "phase1_5_observational_only")]
    if tool_enabled.get("tool_policy_fallback_reason"):
        assert tool_enabled["tool_policy_fallback_reason"] in {
            "required_tool_group_missing",
            "uncertain_classifier",
            "unknown_connector",
        }
        assert tool_enabled["tool_schema_bytes"] <= observational["tool_schema_bytes"]
    else:
        assert tool_enabled["tool_schema_bytes"] < observational["tool_schema_bytes"]
    if tool_enabled.get("tool_policy_fallback_reason"):
        assert tool_enabled["runtime_request_bytes"] <= observational["runtime_request_bytes"]
    else:
        assert tool_enabled["runtime_request_bytes"] < observational["runtime_request_bytes"]
    assert len(tool_enabled["tools_exposed"]) == len(observational["tools_exposed"])
    assert tool_enabled["tools_exposed_after_policy"] <= observational["tools_exposed_after_policy"]


def test_phase2_memory_policy_benchmark_reports_three_modes():
    report = run_phase2_memory_benchmark()
    assert report["mode"] == "phase2_memory_policy_fixture_benchmark"
    assert report["summary"]["cases"] == 20
    assert report["summary"]["modes"] == ["baseline_disabled", "phase1_5_observational_only", "memory_policy_enabled"]
    assert report["summary"]["memory_token_savings"] > 0
    assert report["summary"]["quality_regressions"] == 0
    assert report["summary"]["tool_exposure_unchanged"] is True
    assert report["summary"]["provider_model_unchanged"] is True
    assert len(report["rows"]) == 60


def test_phase3_tool_policy_benchmark_reports_four_modes():
    report = run_phase3_tool_benchmark()
    assert report["mode"] == "phase3_tool_policy_fixture_benchmark"
    assert report["summary"]["cases"] == 20
    assert report["summary"]["modes"] == [
        "baseline_disabled",
        "phase1_5_observational_only",
        "memory_policy_enabled",
        "tool_policy_enabled",
    ]
    assert report["summary"]["schema_bytes_saved_total"] > 0
    assert report["summary"]["request_bytes_saved_total"] > 0
    assert report["summary"]["quality_regressions"] == 0
    assert report["summary"]["provider_model_unchanged"] is True
    assert report["summary"]["approval_state_unchanged"] is True
    assert report["summary"]["mcp_startup_regressions"] == 0
    assert report["summary"]["needed_tool_group_available"] is True
    assert len(report["rows"]) == 80


def test_phase4_evidence_compaction_benchmark_reports_five_modes():
    report = run_phase4_evidence_benchmark()
    assert report["mode"] == "phase4_evidence_compaction_fixture_benchmark"
    assert report["summary"]["cases"] == 20
    assert report["summary"]["modes"] == [
        "baseline_disabled",
        "phase1_5_observational_only",
        "memory_policy_enabled",
        "tool_policy_enabled",
        "evidence_compaction_enabled",
    ]
    assert report["summary"]["evidence_savings_bytes"] > 0
    assert report["summary"]["compaction_failure_count"] == 0
    assert report["summary"]["quality_regressions"] == 0
    assert report["summary"]["provider_model_unchanged"] is True
    assert report["summary"]["approval_state_unchanged"] is True
    assert report["summary"]["mcp_startup_regressions"] == 0
    assert report["summary"]["memory_decisions_unchanged"] is True
    assert report["summary"]["tool_exposure_groups_unchanged"] is True
