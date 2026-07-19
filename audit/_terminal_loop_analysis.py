#!/usr/bin/env python3
"""Terminal Loop Analysis — evidence for shell micro-loops / retries.

Usage:
  ./venv/bin/python audit/_terminal_loop_analysis.py
  ./venv/bin/python audit/_terminal_loop_analysis.py --session 20260619_092959_3be2c9

Writes:
  audit/HERMES_TERMINAL_LOOP_ANALYSIS.json
  audit/HERMES_TERMINAL_LOOP_ANALYSIS.md
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
    )
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--session", default=None, help="Analyze one session id")
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

    from agent.terminal_loop_analysis import (
        analyze_top_sessions,
        format_markdown,
        format_terminal,
    )

    db = Path(args.db).expanduser()
    if not db.exists():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1

    report = analyze_top_sessions(
        db,
        limit=args.limit,
        order_by=args.order_by,
        session_id=args.session,
    )
    print(format_terminal(report))

    out_json = ROOT / "audit" / "HERMES_TERMINAL_LOOP_ANALYSIS.json"
    out_md = ROOT / "audit" / "HERMES_TERMINAL_LOOP_ANALYSIS.md"
    out_json.write_text(json.dumps(report.to_dict(), indent=2) + "\n")
    out_md.write_text(format_markdown(report))
    print(f"  Wrote {out_json}")
    print(f"  Wrote {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
