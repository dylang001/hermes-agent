"""Model Wake-up Analysis — measure unnecessary planner turns before Track B batching.

Evidence gate (see ``audit/HERMES_TRACK_B_PLAN.md``): do not implement SAFE/LOOKUP
batching until this report shows ≥ ~30% of wake-ups would disappear.

Classifies each assistant tool-turn from persisted session messages. Pure
analysis — no execution changes.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from agent.execution_plan import BatchClass, classify_tool


# ── Turn labels (what the planner asked for this wake-up) ─────────

TURN_SAFE_ONLY = "safe_only"
TURN_LOOKUP_ONLY = "lookup_only"
TURN_BATCHABLE = "batchable_mixed"  # SAFE+LOOKUP, no mutating
TURN_MUTATING = "mutating"
TURN_MIXED = "mixed_safe_mutating"
TURN_SUBAGENT = "subagent"
TURN_NO_TOOLS = "no_tools"
TURN_EMPTY = "empty"


@dataclass
class WakeupTurn:
    index: int
    label: str
    tools: list[str] = field(default_factory=list)
    duplicate_ops: int = 0
    total_ops: int = 0
    has_only_duplicates: bool = False


@dataclass
class SessionWakeupReport:
    session_id: str
    model: str = ""
    api_call_count: int = 0
    tool_call_count: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    assistant_turns: int = 0
    tool_turns: int = 0
    tools_per_tool_turn: float = 0.0

    turn_labels: dict[str, int] = field(default_factory=dict)
    # Estimated wake-ups removable if consecutive batchable turns coalesced
    batchable_streak_turns: int = 0
    batchable_wakeups_saved_estimate: int = 0
    batchable_save_pct_of_tool_turns: float = 0.0

    duplicate_ops: int = 0
    turns_only_duplicates: int = 0
    files_reread: int = 0
    greps_rerun: int = 0
    subagent_spawns: int = 0

    # Heuristic buckets answering "why did we wake up?"
    buckets: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WakeupAnalysisReport:
    sessions: list[SessionWakeupReport] = field(default_factory=list)
    aggregate: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessions": [s.to_dict() for s in self.sessions],
            "aggregate": self.aggregate,
        }


def _parse_tool_calls(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        if not raw.strip():
            return []
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(raw, list):
        return []
    out = []
    for tc in raw:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        if not isinstance(fn, dict):
            fn = {}
        name = fn.get("name") or tc.get("name") or ""
        args = fn.get("arguments") or tc.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args) if args.strip() else {}
            except (json.JSONDecodeError, TypeError):
                args = {"_raw": args}
        if not isinstance(args, dict):
            args = {}
        out.append({"name": str(name), "arguments": args, "id": tc.get("id")})
    return out


def _fingerprint(tool: str, args: dict[str, Any]) -> Optional[str]:
    """Stable key for duplicate detection (reads / greps)."""
    name = (tool or "").strip()
    if name == "read_file":
        path = args.get("path") or args.get("file") or args.get("filename")
        if path:
            return f"read_file:{path}"
    if name == "search_files":
        pattern = args.get("pattern") or args.get("query") or args.get("regex")
        target = args.get("path") or args.get("directory") or args.get("target") or ""
        if pattern:
            return f"search_files:{pattern}|{target}"
    if name in {"web_search", "web_extract"}:
        q = args.get("query") or args.get("url") or args.get("q")
        if q:
            return f"{name}:{q}"
    return None


def _label_turn(tools: list[dict[str, Any]]) -> str:
    if not tools:
        return TURN_NO_TOOLS
    names = [t["name"] for t in tools if t.get("name")]
    if not names:
        return TURN_EMPTY
    if any(n == "delegate_task" for n in names):
        return TURN_SUBAGENT
    classes = {classify_tool(n) for n in names}
    if classes == {BatchClass.SAFE}:
        return TURN_SAFE_ONLY
    if classes == {BatchClass.LOOKUP}:
        return TURN_LOOKUP_ONLY
    if classes <= {BatchClass.SAFE, BatchClass.LOOKUP}:
        return TURN_BATCHABLE
    if BatchClass.MUTATING in classes and classes & {BatchClass.SAFE, BatchClass.LOOKUP}:
        return TURN_MIXED
    return TURN_MUTATING


def _is_batchable_label(label: str) -> bool:
    return label in {TURN_SAFE_ONLY, TURN_LOOKUP_ONLY, TURN_BATCHABLE}


def analyze_messages(messages: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Classify wake-ups from an ordered message list (session transcript)."""
    seen_fps: set[str] = set()
    files_seen: set[str] = set()
    greps_seen: set[str] = set()
    files_reread = 0
    greps_rerun = 0
    duplicate_ops = 0
    turns_only_duplicates = 0
    subagent_spawns = 0
    label_counts: Counter[str] = Counter()
    turns: list[WakeupTurn] = []

    assistant_turns = 0
    tool_turns = 0
    total_tools_on_tool_turns = 0

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "assistant":
            continue
        assistant_turns += 1
        tools = _parse_tool_calls(msg.get("tool_calls"))
        label = _label_turn(tools)
        label_counts[label] += 1

        dup_in_turn = 0
        for t in tools:
            name = t["name"]
            if name == "delegate_task":
                subagent_spawns += 1
            fp = _fingerprint(name, t.get("arguments") or {})
            if fp:
                if fp in seen_fps:
                    dup_in_turn += 1
                    duplicate_ops += 1
                    if fp.startswith("read_file:"):
                        files_reread += 1
                    elif fp.startswith("search_files:"):
                        greps_rerun += 1
                else:
                    seen_fps.add(fp)
                    if fp.startswith("read_file:"):
                        files_seen.add(fp)
                    elif fp.startswith("search_files:"):
                        greps_seen.add(fp)

        if tools:
            tool_turns += 1
            total_tools_on_tool_turns += len(tools)
            only_dups = dup_in_turn == len(tools) and len(tools) > 0
            if only_dups:
                turns_only_duplicates += 1
            turns.append(
                WakeupTurn(
                    index=assistant_turns - 1,
                    label=label,
                    tools=[t["name"] for t in tools],
                    duplicate_ops=dup_in_turn,
                    total_ops=len(tools),
                    has_only_duplicates=only_dups,
                )
            )
        else:
            turns.append(
                WakeupTurn(index=assistant_turns - 1, label=label)
            )

    # Consecutive batchable tool-turns → coalesce estimate
    saved = 0
    streak = 0
    batchable_streak_turns = 0
    for t in turns:
        if t.total_ops > 0 and _is_batchable_label(t.label):
            streak += 1
            batchable_streak_turns += 1
        else:
            if streak > 1:
                saved += streak - 1
            streak = 0
    if streak > 1:
        saved += streak - 1

    # Bucket mapping for the user's report table
    buckets = {
        "new_reasoning_required": label_counts.get(TURN_NO_TOOLS, 0)
        + label_counts.get(TURN_MUTATING, 0)
        + label_counts.get(TURN_MIXED, 0),
        "waiting_for_tool_result": 0,  # implicit in loop; not separable in DB
        "re_reading_information": turns_only_duplicates,
        "planner_loop_batchable": batchable_streak_turns,
        "retry": 0,  # not persisted distinctly
        "subagent": label_counts.get(TURN_SUBAGENT, 0),
        "noop_duplicate_turn": turns_only_duplicates,
        # Primary evidence for Track B:
        "batchable_tool_turns": (
            label_counts.get(TURN_SAFE_ONLY, 0)
            + label_counts.get(TURN_LOOKUP_ONLY, 0)
            + label_counts.get(TURN_BATCHABLE, 0)
        ),
        "estimated_wakeups_saved_if_batched": saved,
    }

    tools_per = (
        (total_tools_on_tool_turns / tool_turns) if tool_turns else 0.0
    )
    save_pct = (100.0 * saved / tool_turns) if tool_turns else 0.0

    return {
        "assistant_turns": assistant_turns,
        "tool_turns": tool_turns,
        "tools_per_tool_turn": round(tools_per, 2),
        "turn_labels": dict(label_counts),
        "batchable_streak_turns": batchable_streak_turns,
        "batchable_wakeups_saved_estimate": saved,
        "batchable_save_pct_of_tool_turns": round(save_pct, 1),
        "duplicate_ops": duplicate_ops,
        "turns_only_duplicates": turns_only_duplicates,
        "files_reread": files_reread,
        "greps_rerun": greps_rerun,
        "subagent_spawns": subagent_spawns,
        "buckets": buckets,
        "turns": turns,
    }


def analyze_session_row(
    conn: sqlite3.Connection,
    session: dict[str, Any],
) -> SessionWakeupReport:
    sid = session["id"]
    cur = conn.execute(
        "SELECT role, content, tool_calls, tool_name FROM messages "
        "WHERE session_id = ? ORDER BY id ASC",
        (sid,),
    )
    messages = [dict(r) for r in cur.fetchall()]
    stats = analyze_messages(messages)
    return SessionWakeupReport(
        session_id=sid,
        model=str(session.get("model") or ""),
        api_call_count=int(session.get("api_call_count") or 0),
        tool_call_count=int(session.get("tool_call_count") or 0),
        cache_read_tokens=int(session.get("cache_read_tokens") or 0),
        cache_write_tokens=int(session.get("cache_write_tokens") or 0),
        input_tokens=int(session.get("input_tokens") or 0),
        output_tokens=int(session.get("output_tokens") or 0),
        assistant_turns=stats["assistant_turns"],
        tool_turns=stats["tool_turns"],
        tools_per_tool_turn=stats["tools_per_tool_turn"],
        turn_labels=stats["turn_labels"],
        batchable_streak_turns=stats["batchable_streak_turns"],
        batchable_wakeups_saved_estimate=stats["batchable_wakeups_saved_estimate"],
        batchable_save_pct_of_tool_turns=stats["batchable_save_pct_of_tool_turns"],
        duplicate_ops=stats["duplicate_ops"],
        turns_only_duplicates=stats["turns_only_duplicates"],
        files_reread=stats["files_reread"],
        greps_rerun=stats["greps_rerun"],
        subagent_spawns=stats["subagent_spawns"],
        buckets=stats["buckets"],
    )


def analyze_top_sessions(
    db_path: str | Path,
    *,
    limit: int = 20,
    order_by: str = "cache_read_tokens",
) -> WakeupAnalysisReport:
    """Analyze the top-N sessions by cost proxy (default: cache reads)."""
    allowed = {
        "cache_read_tokens",
        "api_call_count",
        "tool_call_count",
        "input_tokens",
    }
    if order_by not in allowed:
        order_by = "cache_read_tokens"

    path = Path(db_path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT id, model, api_call_count, tool_call_count, "
            f"cache_read_tokens, cache_write_tokens, input_tokens, output_tokens "
            f"FROM sessions ORDER BY COALESCE({order_by}, 0) DESC LIMIT ?",
            (limit,),
        ).fetchall()
        sessions = [analyze_session_row(conn, dict(r)) for r in rows]
    finally:
        conn.close()

    agg = _aggregate(sessions)
    return WakeupAnalysisReport(sessions=sessions, aggregate=agg)


def _aggregate(sessions: list[SessionWakeupReport]) -> dict[str, Any]:
    if not sessions:
        return {"sessions": 0}

    total_api = sum(s.api_call_count for s in sessions)
    total_tools = sum(s.tool_call_count for s in sessions)
    total_tool_turns = sum(s.tool_turns for s in sessions)
    total_saved = sum(s.batchable_wakeups_saved_estimate for s in sessions)
    total_batchable = sum(s.buckets.get("batchable_tool_turns", 0) for s in sessions)
    total_dups = sum(s.duplicate_ops for s in sessions)
    total_reread = sum(s.files_reread for s in sessions)
    total_sub = sum(s.subagent_spawns for s in sessions)
    label_sum: Counter[str] = Counter()
    for s in sessions:
        label_sum.update(s.turn_labels)

    save_pct_tool_turns = (
        100.0 * total_saved / total_tool_turns if total_tool_turns else 0.0
    )
    save_pct_api = (
        100.0 * total_saved / total_api if total_api else 0.0
    )

    verdict = "unknown"
    if save_pct_tool_turns >= 30:
        verdict = "BUILD_BATCHING — estimated save ≥ 30% of tool turns"
    elif save_pct_tool_turns >= 15:
        verdict = "MAYBE — moderate; compare vs duplicate-read / subagent waste"
    else:
        verdict = "DEFER_BATCHING — look at duplicates / subagents / retries first"

    return {
        "sessions": len(sessions),
        "total_api_calls": total_api,
        "total_tool_calls": total_tools,
        "total_tool_turns": total_tool_turns,
        "tools_per_api_call": round(total_tools / total_api, 2) if total_api else 0,
        "batchable_tool_turns": total_batchable,
        "estimated_wakeups_saved_if_batched": total_saved,
        "estimated_save_pct_of_tool_turns": round(save_pct_tool_turns, 1),
        "estimated_save_pct_of_api_calls": round(save_pct_api, 1),
        "duplicate_ops": total_dups,
        "files_reread": total_reread,
        "subagent_spawns": total_sub,
        "turn_labels": dict(label_sum),
        "verdict": verdict,
    }


def format_terminal(report: WakeupAnalysisReport) -> str:
    lines: list[str] = []
    a = report.aggregate
    lines.append("")
    lines.append("  ╔══════════════════════════════════════════════════════════╗")
    lines.append("  ║              🔎 Model Wake-up Analysis                   ║")
    lines.append("  ╚══════════════════════════════════════════════════════════╝")
    lines.append("")
    lines.append(f"  Sessions analyzed:     {a.get('sessions', 0)}")
    lines.append(f"  API calls (model):     {a.get('total_api_calls', 0):,}")
    lines.append(f"  Tool calls:            {a.get('total_tool_calls', 0):,}")
    lines.append(f"  Tools / API call:      {a.get('tools_per_api_call', 0)}")
    lines.append(f"  Tool-turns (assistant with tools): {a.get('total_tool_turns', 0):,}")
    lines.append("")
    lines.append("  Track B evidence (SAFE/LOOKUP coalesce)")
    lines.append("  " + "─" * 56)
    lines.append(
        f"  Batchable tool-turns:  {a.get('batchable_tool_turns', 0):,}"
    )
    lines.append(
        f"  Est. wake-ups saved:   {a.get('estimated_wakeups_saved_if_batched', 0):,}  "
        f"({a.get('estimated_save_pct_of_tool_turns', 0)}% of tool-turns / "
        f"{a.get('estimated_save_pct_of_api_calls', 0)}% of API calls)"
    )
    lines.append("")
    lines.append("  Other waste signals")
    lines.append("  " + "─" * 56)
    lines.append(f"  Duplicate ops:         {a.get('duplicate_ops', 0):,}")
    lines.append(f"  Files re-read:         {a.get('files_reread', 0):,}")
    lines.append(f"  Subagent spawns:       {a.get('subagent_spawns', 0):,}")
    labels = a.get("turn_labels") or {}
    if labels:
        lines.append("")
        lines.append("  Turn labels")
        lines.append("  " + "─" * 56)
        for k, v in sorted(labels.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {k:<28} {v:>8}")
    lines.append("")
    lines.append(f"  Verdict: {a.get('verdict', '')}")
    lines.append("")

    if report.sessions:
        lines.append("  Top sessions")
        lines.append("  " + "─" * 56)
        lines.append(
            f"  {'Session':<22} {'API':>5} {'Tools':>6} "
            f"{'Batch%':>7} {'Saved':>6} {'Dup':>5}"
        )
        for s in report.sessions[:20]:
            lines.append(
                f"  {s.session_id[:22]:<22} {s.api_call_count:>5} "
                f"{s.tool_call_count:>6} "
                f"{s.batchable_save_pct_of_tool_turns:>6.1f}% "
                f"{s.batchable_wakeups_saved_estimate:>6} "
                f"{s.duplicate_ops:>5}"
            )
        lines.append("")
    return "\n".join(lines)


def format_markdown(report: WakeupAnalysisReport) -> str:
    a = report.aggregate
    lines = [
        "# Model Wake-up Analysis",
        "",
        "Evidence gate for Track B execution batching.",
        "",
        "## Aggregate",
        "",
        f"- Sessions: **{a.get('sessions', 0)}**",
        f"- API calls: **{a.get('total_api_calls', 0):,}**",
        f"- Tool calls: **{a.get('total_tool_calls', 0):,}**",
        f"- Tools / API call: **{a.get('tools_per_api_call', 0)}**",
        f"- Batchable tool-turns: **{a.get('batchable_tool_turns', 0):,}**",
        f"- Est. wake-ups saved if SAFE/LOOKUP coalesced: "
        f"**{a.get('estimated_wakeups_saved_if_batched', 0):,}** "
        f"({a.get('estimated_save_pct_of_tool_turns', 0)}% of tool-turns, "
        f"{a.get('estimated_save_pct_of_api_calls', 0)}% of API calls)",
        f"- Duplicate ops: **{a.get('duplicate_ops', 0):,}**",
        f"- Files re-read: **{a.get('files_reread', 0):,}**",
        f"- Subagent spawns: **{a.get('subagent_spawns', 0):,}**",
        "",
        f"**Verdict:** {a.get('verdict', '')}",
        "",
        "## Method",
        "",
        "For consecutive assistant turns that only requested SAFE and/or LOOKUP "
        "tools, estimate that a perfect batching planner would need **1** wake-up "
        "per streak instead of **N** (save = N−1). Mutating / mixed / subagent "
        "turns break streaks. This is an upper bound on wake-ups removable by "
        "batching alone — it does not change reasoning quality assumptions.",
        "",
        "## Per-session",
        "",
        "| Session | API | Tools | Save% tool-turns | Saved | Dup ops | Subagents |",
        "|---------|-----|-------|------------------|-------|---------|-----------|",
    ]
    for s in report.sessions:
        lines.append(
            f"| `{s.session_id}` | {s.api_call_count} | {s.tool_call_count} | "
            f"{s.batchable_save_pct_of_tool_turns}% | "
            f"{s.batchable_wakeups_saved_estimate} | {s.duplicate_ops} | "
            f"{s.subagent_spawns} |"
        )
    lines.append("")
    return "\n".join(lines)
