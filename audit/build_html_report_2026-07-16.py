#!/usr/bin/env python3
"""Build HTML report from capability check JSON."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

STATUS_COLOR = {
    "pass": "#2e7d32",
    "degraded": "#ed6c02",
    "fail": "#c62828",
    "auth_required": "#1565c0",
    "skip": "#6d6d6d",
}


def build_html(data: dict) -> str:
    rows = []
    for c in data.get("checks", []):
        color = STATUS_COLOR.get(c.get("status", ""), "#333")
        rows.append(
            "<tr>"
            f"<td>{html.escape(c.get('name', ''))}</td>"
            f"<td style='color:{color};font-weight:bold'>{html.escape(c.get('status', ''))}</td>"
            f"<td><code>{html.escape(c.get('command', ''))}</code></td>"
            f"<td>{c.get('duration_ms', 0):.0f}</td>"
            f"<td>{html.escape(c.get('remediation') or c.get('notes', ''))}</td>"
            "</tr>"
        )
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<title>Hermes Capability Check {html.escape(data.get('date', ''))}</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #f5f5f5; }}
meta {{ display: block; margin-bottom: 1rem; }}
</style></head><body>
<h1>Hermes Production Capability Check</h1>
<p><strong>Date:</strong> {html.escape(data.get('date', ''))}<br/>
<strong>SHA:</strong> <code>{html.escape(data.get('git_sha', ''))}</code><br/>
<strong>HERMES_HOME:</strong> <code>{html.escape(data.get('hermes_home', ''))}</code><br/>
<strong>Profile:</strong> {html.escape(data.get('profile', ''))}<br/>
<strong>Duration:</strong> {data.get('total_duration_ms', 0):.0f} ms<br/>
<strong>Counts:</strong> {html.escape(str(data.get('counts', {})))}</p>
<table><thead><tr><th>Check</th><th>Status</th><th>Command</th><th>ms</th><th>Remediation</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("json_path", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args()
    data = json.loads(args.json_path.read_text(encoding="utf-8"))
    out = args.output or args.json_path.with_suffix(".html")
    out.write_text(build_html(data), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
