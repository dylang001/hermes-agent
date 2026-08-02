"""Unit tests for CE Observatory read-only aggregator."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.ce_observatory.aggregator import build_summary, summarize_pins, summarize_shadow


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_build_summary_from_temp_home(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    _write_jsonl(
        logs / "context_engineering_v2_shadow.jsonl",
        [
            {
                "session_id": "s1",
                "legacy_attended_tokens": 1000,
                "v2_attended_tokens": 700,
                "v2_attended_tokens_ex_wm": 650,
                "estimated_savings_tokens": 350,
                "estimated_savings_pct": 35.0,
                "layers": {
                    "l1_system_tokens": 100,
                    "l1_tools_tokens": 50,
                    "l2_working_memory_tokens": 40,
                    "l3_recent_tokens": 200,
                    "l4_pinned_tokens": 400,
                    "l5_summary_tokens": 10,
                },
            }
        ],
    )
    _write_jsonl(
        logs / "context_engineering_v2_pins_shadow.jsonl",
        [
            {
                "session_id": "s1",
                "open_epoch": 2,
                "pin_count": 12,
                "pinned_tokens_est": 400,
                "events": ["pinned", "epoch_opened"],
            }
        ],
    )
    summary = build_summary(home=tmp_path)
    assert summary["observation"]["mode"] == "observation"
    assert summary["shadow"]["records"] == 1
    assert summary["shadow"]["legacy_mean"] == 1000
    assert summary["pins"]["pin_count_mean"] == 12
    assert summary["pin_caps"]["status"] == "pending_no_file_or_empty"
    assert summary["short_bypass"]["status"] == "pending_no_file_or_empty"


def test_summarize_helpers_empty() -> None:
    assert summarize_shadow([])["records"] == 0
    assert summarize_pins([])["records"] == 0
