#!/usr/bin/env python3
"""Model Wake-up Analysis — evidence gate before Track B batching.

Usage:
  ./venv/bin/python audit/_wakeup_analysis.py
  ./venv/bin/python audit/_wakeup_analysis.py --limit 20 --db ~/.hermes/state.db

Writes:
  audit/HERMES_WAKEUP_ANALYSIS.json
  audit/HERMES_WAKEUP_ANALYSIS.md
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
        "--db",
        default=str(Path.home() / ".hermes" / "state.db"),
        help="Path to Hermes state.db",
    )
    p.add_argument("--limit", type=int, default=20, help="Top-N sessions")
    p.add_argument(
        "--order-by",
        default="cache_read_tokens",
        choices=[
            "cache_read_tokens",
            "api_call_count",
            "tool_call_count",
            "input_tokens",
        ],
    )
    args = p.parse_args()

    from agent.wakeup_analysis import (
        analyze_top_sessions,
        format_markdown,
        format_terminal,
    )

    db = Path(args.db).expanduser()
    if not db.exists():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1

    report = analyze_top_sessions(
        db, limit=args.limit, order_by=args.order_by
    )
    print(format_terminal(report))

    out_json = ROOT / "audit" / "HERMES_WAKEUP_ANALYSIS.json"
    out_md = ROOT / "audit" / "HERMES_WAKEUP_ANALYSIS.md"
    # Drop per-turn detail from JSON sessions (too large); keep aggregates.
    payload = report.to_dict()
    out_json.write_text(json.dumps(payload, indent=2) + "\n")
    out_md.write_text(format_markdown(report))
    print(f"  Wrote {out_json}")
    print(f"  Wrote {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
