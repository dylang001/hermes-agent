#!/usr/bin/env python3
"""Agent behavior analytics suite — measure before changing policy.

Runs:
  1. Delegation ROI
  2. Inspection policy (+ tool-choice shell vs structured)

Usage:
  ./venv/bin/python audit/_agent_behavior_analytics.py
  ./venv/bin/python audit/_agent_behavior_analytics.py --limit 20

Writes under audit/:
  HERMES_DELEGATION_ROI.{json,md}
  HERMES_INSPECTION_POLICY.{json,md}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--db", default=str(Path.home() / ".hermes" / "state.db")
    )
    p.add_argument("--limit", type=int, default=20)
    args = p.parse_args()

    db = Path(args.db).expanduser()
    if not db.exists():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1

    from agent.delegation_roi_analysis import (
        analyze_delegation_roi,
        format_markdown as fmt_deleg_md,
        format_terminal as fmt_deleg,
    )
    from agent.inspection_policy_analysis import (
        analyze_top_sessions as analyze_inspection,
        format_markdown as fmt_insp_md,
        format_terminal as fmt_insp,
    )

    print("\n=== 1) Delegation ROI ===")
    deleg = analyze_delegation_roi(db, limit_parents=args.limit)
    print(fmt_deleg(deleg))
    (ROOT / "audit" / "HERMES_DELEGATION_ROI.json").write_text(
        json.dumps(deleg.to_dict(), indent=2) + "\n"
    )
    (ROOT / "audit" / "HERMES_DELEGATION_ROI.md").write_text(
        fmt_deleg_md(deleg)
    )

    print("\n=== 2) Inspection policy + tool-choice ===")
    insp = analyze_inspection(db, limit=args.limit)
    print(fmt_insp(insp))
    (ROOT / "audit" / "HERMES_INSPECTION_POLICY.json").write_text(
        json.dumps(insp.to_dict(), indent=2) + "\n"
    )
    (ROOT / "audit" / "HERMES_INSPECTION_POLICY.md").write_text(
        fmt_insp_md(insp)
    )

    print("  Wrote audit/HERMES_DELEGATION_ROI.{json,md}")
    print("  Wrote audit/HERMES_INSPECTION_POLICY.{json,md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
