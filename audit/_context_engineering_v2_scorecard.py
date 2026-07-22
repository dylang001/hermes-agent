#!/usr/bin/env python3
"""Summarise Context Engineering V2 shadow profiler JSONL.

Usage:
  python audit/_context_engineering_v2_scorecard.py
  python audit/_context_engineering_v2_scorecard.py --path ~/.hermes/logs/context_engineering_v2_shadow.jsonl
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def _load_records(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="JSONL path (default: $HERMES_HOME/logs/context_engineering_v2_shadow.jsonl)",
    )
    args = parser.parse_args()
    if args.path is None:
        try:
            from hermes_constants import get_hermes_home

            path = get_hermes_home() / "logs" / "context_engineering_v2_shadow.jsonl"
        except Exception:
            path = Path.home() / ".hermes" / "logs" / "context_engineering_v2_shadow.jsonl"
    else:
        path = args.path

    rows = _load_records(path)
    if not rows:
        print(f"No shadow records at {path}")
        print("Enable with config.yaml:")
        print("  context_engineering_v2:")
        print("    shadow_profiler:")
        print("      enabled: true")
        return 1

    by_session: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_session[str(r.get("session_id") or "")].append(r)

    legacy = [int(r.get("legacy_attended_tokens") or 0) for r in rows]
    v2 = [int(r.get("v2_attended_tokens") or 0) for r in rows]
    v2_ex = [
        int(r.get("v2_attended_tokens_ex_wm") or r.get("v2_attended_tokens") or 0)
        for r in rows
    ]
    savings = [int(r.get("estimated_savings_tokens") or 0) for r in rows]
    safe_replay = [
        int((r.get("tool_trace") or {}).get("replay_char_x_calls_safe") or 0) for r in rows
    ]

    print(f"Shadow scorecard — {path}")
    print(f"Records: {len(rows)}  Sessions: {len(by_session)}")
    print()
    print("Attended tokens (est.)")
    print(f"  legacy mean: {statistics.mean(legacy):,.0f}  p50={statistics.median(legacy):,.0f}  max={max(legacy):,}")
    print(f"  v2_ex_wm mean: {statistics.mean(v2_ex):,.0f}  p50={statistics.median(v2_ex):,.0f}  max={max(v2_ex):,}")
    print(f"  v2+wm  mean: {statistics.mean(v2):,.0f}  p50={statistics.median(v2):,.0f}  max={max(v2):,}")
    print(f"  layering savings mean: {statistics.mean(savings):,.0f}  ({100 * statistics.mean(savings) / max(statistics.mean(legacy), 1):.1f}% of legacy mean)")
    print()
    print("SAFE replay pressure (char × later assistant msgs)")
    print(f"  mean: {statistics.mean(safe_replay):,.0f}  max={max(safe_replay):,}")
    print()
    print("Per session (last record):")
    for sid, recs in sorted(by_session.items(), key=lambda kv: -len(kv[1]))[:15]:
        last = recs[-1]
        print(
            f"  {sid or '(none)':24s} n={len(recs):3d}  "
            f"legacy={last.get('legacy_attended_tokens')}  "
            f"v2={last.get('v2_attended_tokens')}  "
            f"save%={last.get('estimated_savings_pct')}"
        )

    # P3 archive shadow log (real summaries) — optional sibling file.
    arch_path = path.parent / "context_engineering_v2_archive_shadow.jsonl"
    if args.path is not None and args.path.name != "context_engineering_v2_shadow.jsonl":
        arch_path = path.parent / "context_engineering_v2_archive_shadow.jsonl"
    arch_rows = _load_records(arch_path)
    if arch_rows:
        print()
        print(f"P3 SAFE archive shadow — {arch_path}")
        print(f"Records: {len(arch_rows)}")
        a_legacy = [int(r.get("legacy_attended_tokens") or 0) for r in arch_rows]
        a_v2 = [int(r.get("v2_attended_tokens_ex_wm") or 0) for r in arch_rows]
        a_new = [int(r.get("archived_new") or 0) for r in arch_rows]
        a_idx = [int(r.get("index_size") or 0) for r in arch_rows]
        a_save = [int(r.get("estimated_savings_tokens") or 0) for r in arch_rows]
        print(
            f"  legacy mean: {statistics.mean(a_legacy):,.0f}  "
            f"real-archive v2_ex_wm mean: {statistics.mean(a_v2):,.0f}"
        )
        print(
            f"  savings mean: {statistics.mean(a_save):,.0f}  "
            f"archived_new/call mean: {statistics.mean(a_new):.2f}  "
            f"index_size max: {max(a_idx)}"
        )

    pin_path = path.parent / "context_engineering_v2_pins_shadow.jsonl"
    pin_rows = _load_records(pin_path)
    if pin_rows:
        print()
        print(f"P4 pin epoch shadow — {pin_path}")
        print(f"Records: {len(pin_rows)}")
        open_e = [int(r.get("open_epoch") or 0) for r in pin_rows]
        pcounts = [int(r.get("pin_count") or 0) for r in pin_rows]
        ptoks = [int(r.get("pinned_tokens_est") or 0) for r in pin_rows]
        closes = sum(1 for r in pin_rows if r.get("last_close_reason"))
        print(
            f"  open_epoch>0 rate: {100 * sum(1 for x in open_e if x > 0) / len(open_e):.1f}%  "
            f"pin_count mean: {statistics.mean(pcounts):.2f}  "
            f"pinned_tokens mean: {statistics.mean(ptoks):,.0f}"
        )
        print(f"  records with close_reason set: {closes}")

    asm_path = path.parent / "context_engineering_v2_assemble.jsonl"
    asm_rows = _load_records(asm_path)
    if asm_rows:
        print()
        print(f"P5 assemble — {asm_path}")
        print(f"Records: {len(asm_rows)}")
        leg = [int(r.get("legacy_tokens_est") or 0) for r in asm_rows]
        lay = [int(r.get("layered_tokens_est") or 0) for r in asm_rows]
        save = [max(0, a - b) for a, b in zip(leg, lay)]
        print(
            f"  legacy tokens mean: {statistics.mean(leg):,.0f}  "
            f"layered mean: {statistics.mean(lay):,.0f}  "
            f"save mean: {statistics.mean(save):,.0f}"
        )

    soak_path = path.parent / "context_engineering_v2_soak.jsonl"
    soak_rows = _load_records(soak_path)
    if soak_rows:
        print()
        print(f"P6 A/B soak — {soak_path}")
        print(f"Records: {len(soak_rows)}")
        by_arm: dict[str, list] = defaultdict(list)
        for r in soak_rows:
            by_arm[str(r.get("arm") or "?")].append(r)
        for arm, rows in sorted(by_arm.items()):
            leg = [int(r.get("legacy_tokens_est") or 0) for r in rows]
            lay = [int(r.get("layered_tokens_est") or 0) for r in rows]
            ret = [int(r.get("retrieve_count") or 0) for r in rows]
            print(
                f"  arm={arm:8s} n={len(rows):4d}  "
                f"legacy_mean={statistics.mean(leg):,.0f}  "
                f"final_mean={statistics.mean(lay):,.0f}  "
                f"retrieve_mean={statistics.mean(ret):.2f}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
