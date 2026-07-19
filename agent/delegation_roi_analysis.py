"""Delegation ROI — measure whether subagents pay for themselves.

Does **not** change runtime. Reports credits/proxy tokens spent in child
sessions vs parent, completion outcomes, and mutation productivity.

Child sessions are linked via ``sessions.parent_session_id`` /
``model_config._delegate_from``.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from agent.terminal_loop_analysis import classify_command


def _parse_json(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            try:
                dec = json.JSONDecoder()
                obj, _ = dec.raw_decode(raw.strip())
                return obj
            except (json.JSONDecodeError, TypeError, ValueError):
                return None
    return None


def _tool_names_from_assistant(msg: dict[str, Any]) -> list[str]:
    raw = _parse_json(msg.get("tool_calls"))
    if not isinstance(raw, list):
        return []
    names = []
    for tc in raw:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        if isinstance(fn, dict) and fn.get("name"):
            names.append(str(fn["name"]))
    return names


def count_mutations(messages: list[dict[str, Any]]) -> dict[str, int]:
    """Count mutating tool uses in a transcript."""
    writes = patches = terminal_mutate = 0
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        raw = _parse_json(msg.get("tool_calls"))
        if not isinstance(raw, list):
            continue
        for tc in raw:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            if not isinstance(fn, dict):
                continue
            name = fn.get("name") or ""
            if name == "write_file":
                writes += 1
            elif name == "patch":
                patches += 1
            elif name == "terminal":
                args = _parse_json(fn.get("arguments")) or {}
                if isinstance(args, dict):
                    cmd = str(args.get("command") or args.get("cmd") or "")
                    if classify_command(cmd) == "mutate":
                        terminal_mutate += 1
    return {
        "write_file": writes,
        "patch": patches,
        "terminal_mutate": terminal_mutate,
        "total_mutations": writes + patches + terminal_mutate,
    }


def parse_delegate_outcomes(messages: list[dict[str, Any]]) -> dict[str, int]:
    """Classify parent-side delegate_task tool results."""
    outcomes: Counter[str] = Counter()
    spawns = 0
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        names = _tool_names_from_assistant(msg)
        spawns += names.count("delegate_task")

    for msg in messages:
        if msg.get("role") != "tool":
            continue
        if (msg.get("tool_name") or "") != "delegate_task":
            # Some paths omit tool_name — sniff content
            content = msg.get("content") or ""
            if "delegation_id" not in str(content) and "delegate" not in str(content)[:80]:
                continue
        data = _parse_json(msg.get("content"))
        if not isinstance(data, dict):
            outcomes["unknown"] += 1
            continue
        if data.get("error"):
            err = str(data["error"])
            if "capacity" in err.lower():
                outcomes["capacity_error"] += 1
            else:
                outcomes["error"] += 1
            continue
        status = str(data.get("status") or "")
        if status == "dispatched":
            outcomes["dispatched"] += 1
        elif status == "completed":
            outcomes["completed"] += 1
        elif "results" in data:
            results = data.get("results") or []
            if isinstance(results, list):
                for r in results:
                    if isinstance(r, dict):
                        outcomes[str(r.get("status") or "result")] += 1
                    else:
                        outcomes["result"] += 1
            else:
                outcomes["results_blob"] += 1
        else:
            outcomes["other"] += 1

    return {"spawn_calls": spawns, **dict(outcomes)}


@dataclass
class ChildSessionROI:
    session_id: str
    api_call_count: int = 0
    tool_call_count: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    mutations: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ParentDelegationROI:
    session_id: str
    model: str = ""
    parent_api_calls: int = 0
    parent_cache_read: int = 0
    parent_tool_calls: int = 0
    children: list[ChildSessionROI] = field(default_factory=list)
    child_api_calls: int = 0
    child_cache_read: int = 0
    child_tool_calls: int = 0
    child_mutations: int = 0
    parent_mutations: int = 0
    outcomes: dict[str, int] = field(default_factory=dict)
    # Rough proxies — not counterfactuals
    child_share_of_family_cache: float = 0.0
    child_share_of_family_api: float = 0.0
    mutations_per_child_api: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class DelegationROIReport:
    parents: list[ParentDelegationROI] = field(default_factory=list)
    aggregate: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "parents": [p.to_dict() for p in self.parents],
            "aggregate": self.aggregate,
        }


def _load_messages(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT role, content, tool_calls, tool_name, tool_call_id "
            "FROM messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
    ]


def analyze_delegation_roi(
    db_path: str | Path,
    *,
    limit_parents: int = 30,
) -> DelegationROIReport:
    """Analyze parents that have at least one delegated child session."""
    conn = sqlite3.connect(str(Path(db_path)))
    conn.row_factory = sqlite3.Row
    try:
        # Parents = sessions that are targets of _delegate_from / parent_session_id
        parent_ids = [
            r[0]
            for r in conn.execute(
                """
                SELECT DISTINCT COALESCE(
                    json_extract(model_config, '$._delegate_from'),
                    parent_session_id
                ) AS pid
                FROM sessions
                WHERE parent_session_id IS NOT NULL
                   OR json_extract(model_config, '$._delegate_from') IS NOT NULL
                """
            ).fetchall()
            if r[0]
        ]
        # Prefer parents ordered by their own cache reads
        parents_meta = []
        for pid in parent_ids:
            row = conn.execute(
                "SELECT id, model, api_call_count, tool_call_count, "
                "cache_read_tokens, cache_write_tokens, input_tokens, output_tokens "
                "FROM sessions WHERE id = ?",
                (pid,),
            ).fetchone()
            if row:
                parents_meta.append(dict(row))
        parents_meta.sort(
            key=lambda s: int(s.get("cache_read_tokens") or 0), reverse=True
        )
        parents_meta = parents_meta[:limit_parents]

        reports: list[ParentDelegationROI] = []
        for pm in parents_meta:
            pid = pm["id"]
            child_rows = conn.execute(
                """
                SELECT id, model, api_call_count, tool_call_count,
                       cache_read_tokens, cache_write_tokens,
                       input_tokens, output_tokens, model_config, parent_session_id
                FROM sessions
                WHERE parent_session_id = ?
                   OR json_extract(model_config, '$._delegate_from') = ?
                """,
                (pid, pid),
            ).fetchall()

            children: list[ChildSessionROI] = []
            for cr in child_rows:
                cm = dict(cr)
                msgs = _load_messages(conn, cm["id"])
                mut = count_mutations(msgs)
                children.append(
                    ChildSessionROI(
                        session_id=cm["id"],
                        api_call_count=int(cm.get("api_call_count") or 0),
                        tool_call_count=int(cm.get("tool_call_count") or 0),
                        cache_read_tokens=int(cm.get("cache_read_tokens") or 0),
                        cache_write_tokens=int(cm.get("cache_write_tokens") or 0),
                        input_tokens=int(cm.get("input_tokens") or 0),
                        output_tokens=int(cm.get("output_tokens") or 0),
                        mutations=mut,
                    )
                )

            parent_msgs = _load_messages(conn, pid)
            parent_mut = count_mutations(parent_msgs)
            outcomes = parse_delegate_outcomes(parent_msgs)

            child_api = sum(c.api_call_count for c in children)
            child_cache = sum(c.cache_read_tokens for c in children)
            child_tools = sum(c.tool_call_count for c in children)
            child_mut_n = sum(c.mutations.get("total_mutations", 0) for c in children)
            parent_api = int(pm.get("api_call_count") or 0)
            parent_cache = int(pm.get("cache_read_tokens") or 0)
            family_api = parent_api + child_api
            family_cache = parent_cache + child_cache

            reports.append(
                ParentDelegationROI(
                    session_id=pid,
                    model=str(pm.get("model") or ""),
                    parent_api_calls=parent_api,
                    parent_cache_read=parent_cache,
                    parent_tool_calls=int(pm.get("tool_call_count") or 0),
                    children=children,
                    child_api_calls=child_api,
                    child_cache_read=child_cache,
                    child_tool_calls=child_tools,
                    child_mutations=child_mut_n,
                    parent_mutations=parent_mut.get("total_mutations", 0),
                    outcomes=outcomes,
                    child_share_of_family_cache=round(
                        100.0 * child_cache / family_cache, 1
                    )
                    if family_cache
                    else 0.0,
                    child_share_of_family_api=round(
                        100.0 * child_api / family_api, 1
                    )
                    if family_api
                    else 0.0,
                    mutations_per_child_api=round(
                        child_mut_n / child_api, 3
                    )
                    if child_api
                    else 0.0,
                )
            )
    finally:
        conn.close()

    return DelegationROIReport(
        parents=reports, aggregate=_aggregate(reports)
    )


def _aggregate(parents: list[ParentDelegationROI]) -> dict[str, Any]:
    if not parents:
        return {"parents": 0, "verdict": "NO_DELEGATION_DATA"}

    n_children = sum(len(p.children) for p in parents)
    child_api = sum(p.child_api_calls for p in parents)
    child_cache = sum(p.child_cache_read for p in parents)
    parent_api = sum(p.parent_api_calls for p in parents)
    parent_cache = sum(p.parent_cache_read for p in parents)
    child_mut = sum(p.child_mutations for p in parents)
    parent_mut = sum(p.parent_mutations for p in parents)
    outcomes: Counter[str] = Counter()
    for p in parents:
        outcomes.update(p.outcomes)

    family_cache = parent_cache + child_cache
    family_api = parent_api + child_api
    capacity = outcomes.get("capacity_error", 0)
    completed = (
        outcomes.get("completed", 0) + outcomes.get("result", 0)
    )
    dispatched = outcomes.get("dispatched", 0)

    # Heuristic verdict — not a counterfactual
    child_cache_share = (
        100.0 * child_cache / family_cache if family_cache else 0.0
    )
    mut_per_child_api = child_mut / child_api if child_api else 0.0

    if n_children == 0:
        verdict = "NO_CHILD_SESSIONS"
    elif capacity > completed and capacity > 0:
        verdict = (
            "CAPACITY_THRASH — many async capacity errors; "
            "delegation may be burning parent turns waiting"
        )
    elif child_cache_share >= 40 and mut_per_child_api < 0.05:
        verdict = (
            "EXPENSIVE_LOW_OUTPUT — children take large cache share "
            "with few mutations; investigate worker scope"
        )
    elif mut_per_child_api >= 0.15:
        verdict = (
            "PRODUCTIVE_WORKERS — children mutate at a healthy rate; "
            "delegation may be earning its keep"
        )
    elif child_cache_share >= 50:
        verdict = (
            "CACHE_HEAVY_CHILDREN — majority of family cache in workers; "
            "measure whether parent loops shrank"
        )
    else:
        verdict = "MIXED — inspect per-parent child tables"

    return {
        "parents": len(parents),
        "children": n_children,
        "parent_api_calls": parent_api,
        "child_api_calls": child_api,
        "parent_cache_read": parent_cache,
        "child_cache_read": child_cache,
        "child_share_of_family_api": round(
            100.0 * child_api / family_api, 1
        )
        if family_api
        else 0.0,
        "child_share_of_family_cache": round(child_cache_share, 1),
        "child_mutations": child_mut,
        "parent_mutations": parent_mut,
        "mutations_per_child_api_call": round(mut_per_child_api, 3),
        "outcomes": dict(outcomes),
        "verdict": verdict,
        "note": (
            "Parent turns avoided is not observable from the DB "
            "(counterfactual). ROI uses child cost share + mutation "
            "productivity as proxies."
        ),
    }


def format_terminal(report: DelegationROIReport) -> str:
    a = report.aggregate
    lines = [
        "",
        "  ╔══════════════════════════════════════════════════════════╗",
        "  ║                 👥 Delegation ROI                        ║",
        "  ╚══════════════════════════════════════════════════════════╝",
        "",
        f"  Parents with children: {a.get('parents', 0)}",
        f"  Child sessions:        {a.get('children', 0)}",
        f"  Parent API calls:      {a.get('parent_api_calls', 0):,}",
        f"  Child API calls:       {a.get('child_api_calls', 0):,}  "
        f"({a.get('child_share_of_family_api', 0)}% of family)",
        f"  Parent cache reads:    {a.get('parent_cache_read', 0):,}",
        f"  Child cache reads:     {a.get('child_cache_read', 0):,}  "
        f"({a.get('child_share_of_family_cache', 0)}% of family)",
        f"  Child mutations:       {a.get('child_mutations', 0)}  "
        f"({a.get('mutations_per_child_api_call', 0)} per child API call)",
        f"  Parent mutations:      {a.get('parent_mutations', 0)}",
        "",
        "  Outcomes (parent tool results)",
        "  " + "─" * 56,
    ]
    for k, v in sorted(
        (a.get("outcomes") or {}).items(), key=lambda kv: -kv[1]
    ):
        lines.append(f"  {k:<28} {v:>8}")
    lines.append("")
    lines.append(f"  Verdict: {a.get('verdict', '')}")
    lines.append(f"  Note: {a.get('note', '')}")
    lines.append("")
    if report.parents:
        lines.append("  Per parent")
        lines.append("  " + "─" * 56)
        lines.append(
            f"  {'Parent':<22} {'Kids':>4} {'ChAPI':>6} {'ChCache%':>8} "
            f"{'ChMut':>5}"
        )
        for p in report.parents:
            lines.append(
                f"  {p.session_id[:22]:<22} {len(p.children):>4} "
                f"{p.child_api_calls:>6} {p.child_share_of_family_cache:>7.1f}% "
                f"{p.child_mutations:>5}"
            )
        lines.append("")
    return "\n".join(lines)


def format_markdown(report: DelegationROIReport) -> str:
    a = report.aggregate
    lines = [
        "# Delegation ROI",
        "",
        "Agent-behavior analytics (not a runtime change).",
        "",
        f"**Verdict:** {a.get('verdict', '')}",
        "",
        f"> {a.get('note', '')}",
        "",
        "## Aggregate",
        "",
        f"- Parents: **{a.get('parents', 0)}**",
        f"- Children: **{a.get('children', 0)}**",
        f"- Child share of family API: **{a.get('child_share_of_family_api', 0)}%**",
        f"- Child share of family cache: **{a.get('child_share_of_family_cache', 0)}%**",
        f"- Mutations / child API call: **{a.get('mutations_per_child_api_call', 0)}**",
        "",
        "## Per parent",
        "",
        "| Parent | Children | Child API | Child cache % | Child mut |",
        "|--------|----------|-----------|---------------|-----------|",
    ]
    for p in report.parents:
        lines.append(
            f"| `{p.session_id}` | {len(p.children)} | {p.child_api_calls} | "
            f"{p.child_share_of_family_cache}% | {p.child_mutations} |"
        )
    lines.append("")
    return "\n".join(lines)
