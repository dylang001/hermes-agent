#!/usr/bin/env python3
"""Print CE Observatory summary from HERMES_HOME logs (read-only).

Usage:
  python plugins/ce_observatory/cli_summary.py
  python plugins/ce_observatory/cli_summary.py --json
  HERMES_HOME=/opt/hermes/home python plugins/ce_observatory/cli_summary.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit full JSON summary")
    parser.add_argument(
        "--home",
        type=Path,
        default=None,
        help="HERMES_HOME override (default: get_hermes_home())",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=0,
        help="If >0, only read the last N lines of each JSONL",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from aggregator import build_summary

    summary = build_summary(
        home=args.home,
        max_lines=args.max_lines or None,
    )
    if args.json:
        print(json.dumps(summary, indent=2, default=str))
        return 0

    print(f"CE Observatory — {summary['logs_dir']}")
    print(f"Generated: {summary['generated_at']}")
    print(f"Freshest log mtime: {summary.get('telemetry_freshest_mtime')}")
    print()
    sh = summary["shadow"]
    print(f"Shadow records: {sh.get('records')}  sessions: {sh.get('sessions')}")
    print(f"  legacy mean: {sh.get('legacy_mean')}")
    print(f"  savings % of legacy mean: {sh.get('savings_pct_of_legacy_mean')}")
    layers = sh.get("layers_mean") or {}
    print(f"  L4 pinned mean: {layers.get('l4_pinned_tokens')}")
    pins = summary["pins"]
    print(f"Pins open-epoch rate %: {pins.get('open_epoch_rate_pct')}")
    print(f"  pin_count mean/max: {pins.get('pin_count_mean')} / {pins.get('pin_count_max')}")
    soak = summary["soak"]
    print(f"Soak retrieve mean: {soak.get('retrieve_mean')}  arms: {soak.get('arms')}")
    comp = summary["compression"]
    print(f"Compression done/skip (agent.log window): {comp.get('dones')} / {comp.get('skips')}")
    print()
    print("Streams:")
    for name, meta in (summary.get("streams") or {}).items():
        mark = "yes" if meta.get("exists") else "no"
        print(f"  {name:14s} {mark:3s}  {meta.get('mtime') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
