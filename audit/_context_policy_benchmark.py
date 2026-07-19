#!/usr/bin/env python3
"""Before/after Context Policy P0 benchmark (offline, no API calls).

Compares legacy absolute 28k governor vs adaptive %-of-window + profiles
on synthetic long engineering transcripts.

Usage:
  ./venv/bin/python audit/_context_policy_benchmark.py

Writes:
  audit/HERMES_CONTEXT_POLICY_BENCHMARK.json
  audit/HERMES_CONTEXT_POLICY_BENCHMARK.md
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.context_governor import ContextGovernorConfig, govern_request


def _msg(role: str, content: str, **extra):
    m = {"role": role, "content": content}
    m.update(extra)
    return m


def build_engineering_transcript(turns: int) -> list:
    """Synthetic long engineering chat with tool traces + decisions."""
    messages = [
        _msg(
            "system",
            "You are Hermes. Architecture: hexagonal services, Postgres, "
            "MiniMax M3. Decisions: use recover-first governor; keep EC frozen.",
        )
    ]
    for i in range(turns):
        messages.append(
            _msg(
                "user",
                f"Turn {i}: continue the auth refactor. Remember we chose "
                f"JWT + refresh cookies and the dashboard singleflight fix. "
                f"Open files: auth/middleware.py, cookies.py. TODO: tests.",
            )
        )
        messages.append(
            _msg(
                "assistant",
                None,
                tool_calls=[
                    {
                        "id": f"c{i}",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": '{"path":"auth/middleware.py"}',
                        },
                    }
                ],
            )
        )
        # Verbose tool result (low-value for continuity once read).
        messages.append(
            _msg(
                "tool",
                tool_call_id=f"c{i}",
                content=("LINE " * 800) + f" middleware chunk {i}\n",
            )
        )
        messages.append(
            _msg(
                "assistant",
                f"Decision {i}: keep singleflight; extend cookie path; "
                f"tests still pending for refresh race. "
                f"Architecture note: hexagonal boundary stays frozen; "
                f"do not rewrite Execution Coordinator. " * 3,
            )
        )
    return messages


def run_scenario(label: str, cfg: ContextGovernorConfig, messages: list) -> dict:
    t0 = time.perf_counter()
    result = govern_request(messages, tools=None, memory_prefetch="", config=cfg)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        "label": label,
        "profile": cfg.profile,
        "budget_mode": cfg.budget_mode,
        "context_length": cfg.context_length,
        "max_live_tokens": cfg.max_live_tokens,
        "auto_compact_tokens": cfg.auto_compact_tokens,
        "optimization_tokens": cfg.optimization_tokens,
        "tokens_before": result.tokens_before,
        "tokens_after": result.tokens_after,
        "stage": result.stage,
        "recovery": result.recovery,
        "blocked": result.blocked,
        "actions": result.actions,
        "pruned_tool_results": sum(1 for a in result.actions if "tool_result" in a),
        "elapsed_ms": round(elapsed_ms, 3),
        # Continuity proxy: did we keep assistant decision text?
        "kept_decision_markers": sum(
            1
            for m in result.messages
            if m.get("role") == "assistant"
            and isinstance(m.get("content"), str)
            and "Decision" in (m.get("content") or "")
        ),
        "input_decision_markers": sum(
            1
            for m in messages
            if m.get("role") == "assistant"
            and isinstance(m.get("content"), str)
            and "Decision" in (m.get("content") or "")
        ),
    }


def main() -> int:
    # Sized so live transcript exceeds legacy 28k but stays in Stage 1
    # under adaptive interactive @ 1M (continuity win).
    turns = 120
    messages = build_engineering_transcript(turns)
    legacy = ContextGovernorConfig(
        enabled=True,
        budget_mode="absolute",
        profile="legacy_absolute",
        max_live_tokens=28_000,
        target_tokens=24_000,
        soft_warning_tokens=26_000,
        auto_compact_tokens=27_000,
        max_retrieval_tokens=5_000,
        max_tool_result_tokens=6_000,
        max_memory_prefetch_tokens=1_500,
        informational_tokens=26_000,
        optimization_tokens=24_000,
        compaction_tokens=27_000,
        emergency_tokens=28_000,
        resolved=True,
    )
    adaptive_m3 = ContextGovernorConfig(budget_mode="adaptive").resolve(
        context_length=1_000_000, profile="interactive"
    )
    adaptive_128k = ContextGovernorConfig(budget_mode="adaptive").resolve(
        context_length=128_000, profile="interactive"
    )
    batch_m3 = ContextGovernorConfig(budget_mode="adaptive").resolve(
        context_length=1_000_000, profile="batch"
    )

    rows = [
        run_scenario("legacy_absolute_28k", legacy, messages),
        run_scenario("adaptive_interactive_1M", adaptive_m3, messages),
        run_scenario("adaptive_interactive_128k", adaptive_128k, messages),
        run_scenario("adaptive_batch_1M", batch_m3, messages),
    ]

    legacy_row = rows[0]
    m3_row = rows[1]
    summary = {
        "turns": turns,
        "primary_kpi": "conversation_continuity_vs_premature_compaction",
        "findings": {
            "legacy_requests_compact": legacy_row["recovery"] == "compact",
            "adaptive_1M_requests_compact": m3_row["recovery"] == "compact",
            "adaptive_1M_stage": m3_row["stage"],
            "legacy_stage": legacy_row["stage"],
            "continuity_decisions_kept_adaptive": m3_row["kept_decision_markers"],
            "continuity_decisions_kept_legacy": legacy_row["kept_decision_markers"],
            "live_budget_1M_vs_legacy": {
                "adaptive_emergency": adaptive_m3.max_live_tokens,
                "legacy_max_live": legacy.max_live_tokens,
                "ratio": round(
                    adaptive_m3.max_live_tokens / legacy.max_live_tokens, 1
                ),
            },
        },
        "scenarios": rows,
        "notes": [
            "Offline proxy — no model API, no real cache hit rates.",
            "Engineering task completion / UX require a live soak on MiniMax M3.",
            "Cache efficiency should improve with longer stable prefixes under "
            "adaptive interactive (fewer mid-session system rebuilds).",
            "Cost: adaptive may send larger prompts; prompt caching makes that "
            "practical. Measure hermes_engineering_task_cost_usd_total in soak.",
        ],
    }

    out_json = ROOT / "audit" / "HERMES_CONTEXT_POLICY_BENCHMARK.json"
    out_md = ROOT / "audit" / "HERMES_CONTEXT_POLICY_BENCHMARK.md"
    out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Hermes Context Policy P0 — Before/After Benchmark",
        "",
        f"**Turns in synthetic transcript:** {turns}",
        "",
        "## Verdict",
        "",
    ]
    if legacy_row["recovery"] == "compact" and m3_row["recovery"] != "compact":
        lines.append(
            "Legacy absolute 28k **requests compaction** on this engineering "
            "transcript; adaptive interactive @ 1M stays in "
            f"**`{m3_row['stage']}`** without compaction — continuity preserved."
        )
    else:
        lines.append(
            f"Legacy stage=`{legacy_row['stage']}` recovery=`{legacy_row['recovery']}`; "
            f"adaptive 1M stage=`{m3_row['stage']}` recovery=`{m3_row['recovery']}`."
        )
    lines.extend(
        [
            "",
            "## Budgets",
            "",
            "| Scenario | Window | Opt | Compact | Emergency | Stage | Recovery |",
            "|----------|--------|-----|---------|-----------|-------|----------|",
        ]
    )
    for r in rows:
        lines.append(
            f"| {r['label']} | {r['context_length'] or 'n/a'} | "
            f"{r['optimization_tokens']:,} | {r['auto_compact_tokens']:,} | "
            f"{r['max_live_tokens']:,} | {r['stage']} | {r['recovery']} |"
        )
    lines.extend(
        [
            "",
            "## Continuity proxy",
            "",
            f"- Decision markers in input: {m3_row['input_decision_markers']}",
            f"- Kept under legacy: {legacy_row['kept_decision_markers']}",
            f"- Kept under adaptive 1M: {m3_row['kept_decision_markers']}",
            "",
            "## What this does **not** measure (live soak)",
            "",
            "- Real engineering task completion rate",
            "- Prompt-cache hit % / cost USD",
            "- End-to-end latency with MiniMax",
            "- Subjective UX vs ChatGPT/Claude",
            "",
            "Use Observatory (`hermes_engineering_tasks_*`, compression counters) "
            "during a 1–2 week interactive soak on MiniMax M3.",
            "",
        ]
    )
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(out_md.read_text(encoding="utf-8"))
    print(f"Wrote {out_json} and {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
