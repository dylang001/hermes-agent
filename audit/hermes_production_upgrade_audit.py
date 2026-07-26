#!/usr/bin/env python3
"""Repeatable Hermes production before/after upgrade audit.

Reads VPS (or local) ``state.db`` and emits a JSON baseline + CSV metrics
suitable for comparing useful-work-per-token across upgrade cut points.

Usage:
  python audit/hermes_production_upgrade_audit.py \\
    --db /opt/hermes/home/state.db \\
    --cut 2026-07-22 \\
    --start 2026-07-10 \\
    --end 2026-07-27 \\
    --out audit/baselines/hermes-upgrade-audit-YYYYMMDD

Does not call the network. Cost fields are reported as stored (often 0 when
provider billing is not mirrored into SessionDB).
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def epoch(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def q(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def period_metrics(conn: sqlite3.Connection, start: int, end: int, source: str | None) -> dict:
    where = "started_at >= ? AND started_at < ?"
    params: list = [start, end]
    if source:
        where += " AND source = ?"
        params.append(source)
    where += " AND COALESCE(api_call_count,0) > 0"
    rows = q(
        conn,
        f"""
        SELECT
          COUNT(*) AS sessions,
          SUM(COALESCE(input_tokens,0)) AS input_tokens,
          SUM(COALESCE(output_tokens,0)) AS output_tokens,
          SUM(COALESCE(cache_read_tokens,0)) AS cache_read_tokens,
          SUM(COALESCE(cache_write_tokens,0)) AS cache_write_tokens,
          SUM(COALESCE(input_tokens,0)+COALESCE(output_tokens,0)+COALESCE(cache_read_tokens,0)) AS totalish_tokens,
          SUM(COALESCE(api_call_count,0)) AS api_calls,
          SUM(COALESCE(tool_call_count,0)) AS tool_calls,
          SUM(COALESCE(actual_cost_usd, estimated_cost_usd, 0)) AS cost_usd,
          MAX(COALESCE(cache_read_tokens,0)) AS max_cache_read,
          SUM(CASE WHEN end_reason='compression' THEN 1 ELSE 0 END) AS compress_ends
        FROM sessions
        WHERE {where}
        """,
        tuple(params),
    )
    m = rows[0] if rows else {}
    sessions = int(m.get("sessions") or 0) or 0
    input_t = int(m.get("input_tokens") or 0)
    cache = int(m.get("cache_read_tokens") or 0)
    promptish = input_t + cache
    return {
        "sessions": sessions,
        "input_tokens": input_t,
        "output_tokens": int(m.get("output_tokens") or 0),
        "cache_read_tokens": cache,
        "cache_write_tokens": int(m.get("cache_write_tokens") or 0),
        "totalish_tokens": int(m.get("totalish_tokens") or 0),
        "api_calls": int(m.get("api_calls") or 0),
        "tool_calls": int(m.get("tool_calls") or 0),
        "cost_usd": float(m.get("cost_usd") or 0),
        "max_cache_read": int(m.get("max_cache_read") or 0),
        "compress_ends": int(m.get("compress_ends") or 0),
        "cache_ratio": round(cache / promptish, 3) if promptish else None,
        "avg_promptish": round(promptish / sessions) if sessions else None,
        "avg_cache_read": round(cache / sessions) if sessions else None,
        "tools_per_session": round(int(m.get("tool_calls") or 0) / sessions, 1) if sessions else None,
        "api_per_session": round(int(m.get("api_calls") or 0) / sessions, 1) if sessions else None,
        "tokens_per_api_call": round(int(m.get("totalish_tokens") or 0) / int(m.get("api_calls") or 1), 0)
        if int(m.get("api_calls") or 0)
        else None,
    }


def daily_series(conn: sqlite3.Connection, start: int, end: int) -> list[dict]:
    return q(
        conn,
        """
        SELECT date(started_at, 'unixepoch') AS day,
               COUNT(*) AS sessions,
               SUM(COALESCE(input_tokens,0)) AS input_tokens,
               SUM(COALESCE(output_tokens,0)) AS output_tokens,
               SUM(COALESCE(cache_read_tokens,0)) AS cache_read_tokens,
               SUM(COALESCE(api_call_count,0)) AS api_calls,
               SUM(COALESCE(tool_call_count,0)) AS tool_calls,
               SUM(CASE WHEN end_reason='compression' THEN 1 ELSE 0 END) AS compress_ends,
               SUM(CASE WHEN COALESCE(api_call_count,0)=0 THEN 1 ELSE 0 END) AS zero_api_sessions
        FROM sessions
        WHERE started_at >= ? AND started_at < ?
        GROUP BY 1 ORDER BY 1
        """,
        (start, end),
    )


def top_sessions(conn: sqlite3.Connection, start: int, end: int, limit: int = 15) -> list[dict]:
    return q(
        conn,
        """
        SELECT id, date(started_at,'unixepoch') AS day, source, model,
               COALESCE(input_tokens,0) AS input_tokens,
               COALESCE(cache_read_tokens,0) AS cache_read_tokens,
               COALESCE(output_tokens,0) AS output_tokens,
               COALESCE(api_call_count,0) AS api_calls,
               COALESCE(tool_call_count,0) AS tool_calls,
               end_reason,
               substr(COALESCE(title,''),1,80) AS title
        FROM sessions
        WHERE started_at >= ? AND started_at < ?
        ORDER BY cache_read_tokens DESC
        LIMIT ?
        """,
        (start, end, limit),
    )


def cron_kos(conn: sqlite3.Connection, start: int, end: int) -> list[dict]:
    return q(
        conn,
        """
        SELECT id, date(started_at,'unixepoch') AS day, title,
               COALESCE(api_call_count,0) AS api_calls,
               COALESCE(tool_call_count,0) AS tool_calls,
               COALESCE(cache_read_tokens,0) AS cache_read_tokens,
               COALESCE(input_tokens,0) AS input_tokens,
               end_reason
        FROM sessions
        WHERE source='cron'
          AND started_at >= ? AND started_at < ?
          AND (title LIKE '%knowledge-os%' OR id LIKE 'cron_675506%' OR id LIKE 'cron_bde6f%')
        ORDER BY started_at
        """,
        (start, end),
    )


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", required=True, help="Path to state.db")
    ap.add_argument("--cut", required=True, help="Upgrade cut date YYYY-MM-DD (after starts here)")
    ap.add_argument("--start", default="2026-07-10")
    ap.add_argument("--end", default="2026-07-27")
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--git-sha", default="")
    ap.add_argument("--env-label", default="")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.is_file():
        print(f"missing db: {db}", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    start_e, cut_e, end_e = epoch(args.start), epoch(args.cut), epoch(args.end)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)

    baseline = {
        "schema": "hermes-upgrade-audit/v1",
        "emitted_at": utc_now(),
        "db": str(db),
        "env_label": args.env_label,
        "git_sha": args.git_sha,
        "window": {"start": args.start, "cut": args.cut, "end": args.end},
        "objective": "useful_work_per_token (not minimize tokens)",
        "all_sources": {
            "before": period_metrics(conn, start_e, cut_e, None),
            "after": period_metrics(conn, cut_e, end_e, None),
        },
        "desktop_only": {
            "before": period_metrics(conn, start_e, cut_e, "desktop"),
            "after": period_metrics(conn, cut_e, end_e, "desktop"),
        },
        "daily_series": daily_series(conn, start_e, end_e),
        "top_cache_before": top_sessions(conn, start_e, cut_e),
        "top_cache_after": top_sessions(conn, cut_e, end_e),
        "knowledge_os_cron": cron_kos(conn, start_e, end_e),
    }

    # Derived deltas
    def delta(a: dict, b: dict, key: str):
        if a.get(key) is None or b.get(key) is None:
            return None
        return round(b[key] - a[key], 3) if isinstance(a[key], float) else b[key] - a[key]

    dbefore, dafter = baseline["desktop_only"]["before"], baseline["desktop_only"]["after"]
    baseline["desktop_deltas_after_minus_before"] = {
        k: delta(dbefore, dafter, k)
        for k in (
            "sessions",
            "cache_ratio",
            "avg_promptish",
            "avg_cache_read",
            "tools_per_session",
            "api_per_session",
            "max_cache_read",
            "tokens_per_api_call",
        )
    }

    kos = baseline["knowledge_os_cron"]
    baseline["knowledge_os_cron_summary"] = {
        "runs": len(kos),
        "zero_api_runs": sum(1 for r in kos if int(r.get("api_calls") or 0) == 0),
        "productive_runs": sum(1 for r in kos if int(r.get("api_calls") or 0) > 0),
    }

    (out / "baseline.json").write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    write_csv(out / "daily_series.csv", baseline["daily_series"])
    write_csv(out / "kos_cron.csv", kos)
    write_csv(out / "top_cache_before.csv", baseline["top_cache_before"])
    write_csv(out / "top_cache_after.csv", baseline["top_cache_after"])

    print(json.dumps({"ok": True, "out": str(out), "desktop_deltas": baseline["desktop_deltas_after_minus_before"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
