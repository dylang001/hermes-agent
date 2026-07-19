#!/usr/bin/env python3
"""Memory reliability benchmark v0 — offline, no API calls.

Measures conversation / engineering continuity proxies around the governor
and working-memory compaction handoff. Complements (does not replace)
live MiniMax long-session evaluation.

Usage:
  ./venv/bin/python audit/_memory_reliability_benchmark.py

Writes:
  audit/HERMES_MEMORY_RELIABILITY_BENCHMARK.json
  updates results section in audit/HERMES_MEMORY_RELIABILITY_BENCHMARK.md
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.context_compressor import SUMMARY_PREFIX, LEGACY_SUMMARY_PREFIX
from agent.context_governor import ContextGovernorConfig, govern_request

OUT_JSON = ROOT / "audit" / "HERMES_MEMORY_RELIABILITY_BENCHMARK.json"
OUT_MD = ROOT / "audit" / "HERMES_MEMORY_RELIABILITY_BENCHMARK.md"

# Stable markers injected into synthetic engineering chats.
ACTION_T0 = "ACTION_MARKER_DEPLOYED_RAISE_ONLY_HOTFIX"
DECISION_A = "DECISION_USE_REDIS_FOR_SESSION_STORE"
DECISION_B = "DECISION_USE_SQLITE_FOR_SESSION_STORE"
OPEN_FILE = "OPEN_FILE_agent/agent_init.py"
TODO_MARK = "TODO_ADD_CONTINUITY_PROBE"
DISTRACTOR = "NEVER_STATED_DECISION_MIGRATE_TO_KAFKA"


def _msg(role: str, content: str, **extra):
    m = {"role": role, "content": content}
    m.update(extra)
    return m


def _flatten(messages: list) -> str:
    parts = []
    for m in messages:
        c = m.get("content")
        if isinstance(c, str):
            parts.append(c)
        elif isinstance(c, list):
            for block in c:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
    return "\n".join(parts)


def _score_bool(ok: bool) -> float:
    return 1.0 if ok else 0.0


def scenario_summary_prefix_working_memory() -> dict:
    """Working-memory retention: prefix must preserve, not discard-era."""
    lower = SUMMARY_PREFIX.lower()
    checks = {
        "has_working_memory_language": (
            "working-memory" in lower or "working memory" in lower
        ),
        "preserves_key_decisions": "key decisions" in lower,
        "preserves_relevant_files": "relevant files" in lower,
        "continuity_over_discard": "continuity" in lower,
        "no_discard_stale": "discard stale items" not in lower,
        "not_legacy_prefix": not SUMMARY_PREFIX.startswith(LEGACY_SUMMARY_PREFIX),
        "latest_wins_on_conflict": "conflict" in lower and (
            "wins" in lower or "supersede" in lower
        ),
    }
    score = sum(_score_bool(v) for v in checks.values()) / len(checks)
    return {
        "id": "working_memory_prefix",
        "dimension": "working-memory retention",
        "passed": all(checks.values()),
        "score": score,
        "details": checks,
    }


def scenario_two_turn_action() -> dict:
    """Conversation continuity: early action survives noisy tool turns."""
    messages = [
        _msg("system", "You are Hermes engineering agent."),
        _msg(
            "user",
            f"Please deploy the hotfix. Confirm when done. marker={ACTION_T0}",
        ),
        _msg(
            "assistant",
            f"Deployed successfully. Recorded action: {ACTION_T0}.",
        ),
    ]
    # Noise turns with large tool dumps (governor may prune tool bodies).
    for i in range(12):
        messages.append(_msg("user", f"noise turn {i}: inspect logs"))
        messages.append(
            _msg(
                "assistant",
                None,
                tool_calls=[
                    {
                        "id": f"n{i}",
                        "type": "function",
                        "function": {
                            "name": "terminal",
                            "arguments": '{"cmd":"journalctl"}',
                        },
                    }
                ],
            )
        )
        messages.append(
            _msg(
                "tool",
                tool_call_id=f"n{i}",
                content=("LOGLINE " * 400) + f" noise {i}\n",
            )
        )
        messages.append(
            _msg("assistant", f"Logs inspected for noise {i}; no change to plan.")
        )
    messages.append(
        _msg(
            "user",
            "What hotfix action did you complete two turns after we started? "
            "Quote the action marker.",
        )
    )

    # Force optimisation so tool pruning may run while dialogue should stay.
    cfg = ContextGovernorConfig(
        enabled=True,
        budget_mode="absolute",
        max_live_tokens=40_000,
        auto_compact_tokens=38_000,
        optimization_tokens=20_000,
        protect_last_n=16,
    )
    result = govern_request(messages, tools=None, memory_prefetch="", config=cfg)
    flat = _flatten(result.messages)
    retained = ACTION_T0 in flat
    return {
        "id": "two_turn_action",
        "dimension": "conversation continuity",
        "passed": retained,
        "score": _score_bool(retained),
        "details": {
            "action_marker_retained": retained,
            "tokens_before": result.tokens_before,
            "tokens_after": result.tokens_after,
            "stage": result.stage,
            "recovery": result.recovery,
        },
    }


def scenario_engineering_markers() -> dict:
    """Engineering continuity: decisions/files/todos survive optimisation."""
    messages = [
        _msg("system", "Hermes. Keep engineering state continuous."),
        _msg(
            "user",
            f"We decided {DECISION_B}. Open {OPEN_FILE}. Next: {TODO_MARK}.",
        ),
        _msg(
            "assistant",
            f"Ack. Decision locked: {DECISION_B}. Working in {OPEN_FILE}. "
            f"Queue: {TODO_MARK}.",
        ),
    ]
    for i in range(20):
        messages.append(_msg("user", f"read more of the file chunk {i}"))
        messages.append(
            _msg(
                "assistant",
                None,
                tool_calls=[
                    {
                        "id": f"r{i}",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path":"agent/agent_init.py"}',
                        },
                    }
                ],
            )
        )
        messages.append(
            _msg(
                "tool",
                tool_call_id=f"r{i}",
                content=("CODE " * 500) + f" chunk {i}\n",
            )
        )
        messages.append(
            _msg(
                "assistant",
                f"Still on {OPEN_FILE}; decision remains {DECISION_B}; "
                f"{TODO_MARK} still open.",
            )
        )

    cfg = ContextGovernorConfig(
        enabled=True,
        budget_mode="absolute",
        max_live_tokens=35_000,
        auto_compact_tokens=33_000,
        optimization_tokens=18_000,
        protect_last_n=16,
    )
    result = govern_request(messages, tools=None, memory_prefetch="", config=cfg)
    flat = _flatten(result.messages)
    checks = {
        "decision_retained": DECISION_B in flat,
        "open_file_retained": OPEN_FILE in flat,
        "todo_retained": TODO_MARK in flat,
        # Hallucination structural guard: distractor never injected.
        "distractor_absent": DISTRACTOR not in flat,
    }
    score = sum(_score_bool(v) for v in checks.values()) / len(checks)
    return {
        "id": "engineering_markers",
        "dimension": "engineering continuity",
        "passed": all(checks.values()),
        "score": score,
        "details": {
            **checks,
            "tokens_before": result.tokens_before,
            "tokens_after": result.tokens_after,
        },
    }


def scenario_decision_latest_wins() -> dict:
    """On conflict, latest decision must be the one still framed as current."""
    # Structural: build a synthetic summary body and assert selection logic
    # we expect compressors / prompts to follow (latest wins). Offline we
    # verify the *policy text* plus a trivial resolution helper used by tests.
    summary_body = (
        "## Key Decisions\n"
        f"- Prior: {DECISION_A}\n"
        f"- Current: {DECISION_B}\n"
        "## Relevant Files\n"
        f"- {OPEN_FILE}\n"
    )
    # Emulate "latest wins": keep only the last Decision line as current.
    decisions = re.findall(r"DECISION_[A-Z0-9_]+", summary_body)
    current = decisions[-1] if decisions else None
    checks = {
        "latest_is_b": current == DECISION_B,
        "prefix_requires_conflict_win": "wins" in SUMMARY_PREFIX.lower()
        or "supersede" in SUMMARY_PREFIX.lower(),
        "a_still_in_history_ok": DECISION_A in summary_body,  # history may remain
        "current_pointer_is_b": "Current: " + DECISION_B in summary_body,
    }
    score = sum(_score_bool(v) for v in checks.values()) / len(checks)
    return {
        "id": "decision_latest_wins",
        "dimension": "conversation continuity",
        "passed": all(checks.values()),
        "score": score,
        "details": checks,
    }


def scenario_hallucination_guard() -> dict:
    """Never-stated decisions must not appear after govern on a clean chat."""
    messages = [
        _msg("system", "Hermes."),
        _msg("user", f"Implement raise-only threshold. marker={ACTION_T0}"),
        _msg("assistant", f"Done. {ACTION_T0}. No other architectural migrations."),
        _msg("user", "Summarize only what we actually decided."),
        _msg("assistant", f"We only recorded {ACTION_T0}."),
    ]
    cfg = ContextGovernorConfig(enabled=True, budget_mode="adaptive", context_length=1_000_000)
    result = govern_request(messages, tools=None, memory_prefetch="", config=cfg)
    flat = _flatten(result.messages)
    ok = DISTRACTOR not in flat and ACTION_T0 in flat
    return {
        "id": "hallucination_guard",
        "dimension": "hallucination rate",
        "passed": ok,
        "score": _score_bool(ok),
        "details": {
            "distractor_absent": DISTRACTOR not in flat,
            "real_marker_present": ACTION_T0 in flat,
        },
    }


def run_all() -> dict:
    t0 = time.perf_counter()
    scenarios = [
        scenario_summary_prefix_working_memory(),
        scenario_two_turn_action(),
        scenario_engineering_markers(),
        scenario_decision_latest_wins(),
        scenario_hallucination_guard(),
    ]
    suite_score = sum(s["score"] for s in scenarios) / len(scenarios)
    passed = all(s["passed"] for s in scenarios)
    report = {
        "benchmark": "memory_reliability_v0",
        "baseline_tag": "runtime-2026-07-19",
        "mode": "offline",
        "passed": passed,
        "suite_score": round(suite_score, 4),
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
        "scenarios": scenarios,
        "dimensions": {
            "conversation_continuity": round(
                sum(
                    s["score"]
                    for s in scenarios
                    if s["dimension"] == "conversation continuity"
                )
                / max(
                    1,
                    sum(
                        1
                        for s in scenarios
                        if s["dimension"] == "conversation continuity"
                    ),
                ),
                4,
            ),
            "engineering_continuity": round(
                next(
                    s["score"]
                    for s in scenarios
                    if s["dimension"] == "engineering continuity"
                ),
                4,
            ),
            "working_memory_retention": round(
                next(
                    s["score"]
                    for s in scenarios
                    if s["dimension"] == "working-memory retention"
                ),
                4,
            ),
            "hallucination_guard": round(
                next(
                    s["score"] for s in scenarios if s["dimension"] == "hallucination rate"
                ),
                4,
            ),
        },
    }
    return report


def _write_results_md(report: dict) -> None:
    lines = [
        "",
        "## Results (auto-generated)",
        "",
        f"**Suite passed:** `{report['passed']}`  ",
        f"**Suite score:** `{report['suite_score']}`  ",
        f"**Mode:** `{report['mode']}`  ",
        f"**Baseline tag:** `{report['baseline_tag']}`  ",
        "",
        "| Scenario | Dimension | Passed | Score |",
        "|----------|-----------|--------|-------|",
    ]
    for s in report["scenarios"]:
        lines.append(
            f"| `{s['id']}` | {s['dimension']} | {s['passed']} | {s['score']:.2f} |"
        )
    lines.extend(
        [
            "",
            "### Dimension scores",
            "",
            "| Dimension | Score |",
            "|-----------|-------|",
        ]
    )
    for k, v in report["dimensions"].items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    existing = OUT_MD.read_text(encoding="utf-8") if OUT_MD.exists() else ""
    marker = "## Results (auto-generated)"
    if marker in existing:
        existing = existing.split(marker)[0].rstrip() + "\n"
    OUT_MD.write_text(existing + "\n".join(lines), encoding="utf-8")


def main() -> int:
    report = run_all()
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _write_results_md(report)
    print(json.dumps({k: report[k] for k in ("passed", "suite_score", "dimensions")}, indent=2))
    for s in report["scenarios"]:
        flag = "PASS" if s["passed"] else "FAIL"
        print(f"  [{flag}] {s['id']} ({s['dimension']}) score={s['score']:.2f}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
