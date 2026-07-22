#!/usr/bin/env python3
"""Shadow-mode reference-cost report over session_model_usage.

Recomputes reference token costs from the versioned registry. Does **not**
overwrite ``actual_cost_usd`` or ``estimated_cost_usd``.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from agent.reference_pricing import (  # noqa: E402
    reference_cost_from_counters,
    round_usd,
    summarize_reference_coverage,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")) + "/state.db",
        help="Path to state.db (default: $HERMES_HOME/state.db)",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"missing db: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT billing_provider, model, billing_base_url,
               SUM(input_tokens) AS input_tokens,
               SUM(output_tokens) AS output_tokens,
               SUM(cache_read_tokens) AS cache_read_tokens,
               SUM(cache_write_tokens) AS cache_write_tokens,
               SUM(reasoning_tokens) AS reasoning_tokens,
               SUM(api_call_count) AS api_calls,
               COALESCE(SUM(actual_cost_usd), 0) AS actual_cost_usd,
               COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
        FROM session_model_usage
        GROUP BY billing_provider, model, billing_base_url
        ORDER BY SUM(input_tokens) + SUM(output_tokens) DESC
        """
    ).fetchall()
    conn.close()

    report = []
    for row in rows:
        ref = reference_cost_from_counters(
            billing_provider=row["billing_provider"],
            model_id=row["model"],
            input_tokens=row["input_tokens"] or 0,
            output_tokens=row["output_tokens"] or 0,
            cache_read_tokens=row["cache_read_tokens"] or 0,
            cache_write_tokens=row["cache_write_tokens"] or 0,
            reasoning_tokens=row["reasoning_tokens"] or 0,
            base_url=row["billing_base_url"] or "",
        )
        item = {
            "billing_provider": row["billing_provider"],
            "model": row["model"],
            "billing_base_url": row["billing_base_url"],
            "api_calls": row["api_calls"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "cache_read_tokens": row["cache_read_tokens"],
            "actual_cost_usd": float(row["actual_cost_usd"] or 0),
            "estimated_cost_usd": float(row["estimated_cost_usd"] or 0),
            "reference_cost_usd": (
                float(ref.reference_cost_usd) if ref.reference_cost_usd is not None else None
            ),
            "reference_rounded_usd": (
                float(round_usd(ref.reference_cost_usd))
                if ref.reference_cost_usd is not None
                else None
            ),
            "pricing_type": ref.pricing_type,
            "pricing_source": ref.pricing_source,
            "pricing_effective_date": ref.pricing_effective_date,
            "cost_confidence": ref.cost_confidence,
            "breakdown": {
                "input_usd": float(ref.input_usd) if ref.input_usd is not None else None,
                "cache_read_usd": (
                    float(ref.cache_read_usd) if ref.cache_read_usd is not None else None
                ),
                "output_usd": float(ref.output_usd) if ref.output_usd is not None else None,
            },
            "notes": list(ref.notes),
        }
        report.append(item)

    coverage = summarize_reference_coverage(report)
    payload = {"models": report, "coverage": coverage}

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("Reference cost backfill (shadow mode — actual_cost untouched)")
        print("-" * 72)
        for item in report:
            ref = item["reference_rounded_usd"]
            print(
                f"{item['billing_provider'] or '-':<14} {item['model']:<40} "
                f"actual=${item['actual_cost_usd']:.4f}  "
                f"ref={('$' + format(ref, '.2f')) if ref is not None else 'n/a':>8}  "
                f"({item['pricing_type']})"
            )
        print("-" * 72)
        print(
            f"priced={coverage['priced_rows']}/{coverage['rows']}  "
            f"unknown_pct={coverage['unknown_price_coverage_pct']}%  "
            f"total_ref=${coverage['total_reference_cost_usd']:.2f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
