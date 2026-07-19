"""Inspection policy analytics — when does Hermes stop exploring and act?

Metrics:
* Inspection turns before first mutation
* Inspection-to-mutation ratio
* Tool-choice: shell inspect/search that could have been structured tools

No runtime changes.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from agent.execution_plan import BatchClass, classify_tool
from agent.terminal_loop_analysis import classify_command


INSPECT_STRUCTURED = frozenset(
    {
        "read_file",
        "search_files",
        "session_search",
        "skill_view",
        "skills_list",
        "web_search",
        "web_extract",
        "vision_analyze",
    }
)
MUTATE_STRUCTURED = frozenset({"write_file", "patch"})


def _parse_json(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


@dataclass
class TurnKind:
    index: int
    kind: str  # inspect | mutate | other | mixed
    tools: list[str] = field(default_factory=list)
    shell_replaceable: int = 0  # terminal cmds that look like cat/grep/ls/find


def _classify_assistant_turn(tool_calls_raw: Any) -> TurnKind:
    raw = _parse_json(tool_calls_raw)
    if not isinstance(raw, list) or not raw:
        return TurnKind(index=0, kind="other", tools=[])

    tools: list[str] = []
    has_inspect = False
    has_mutate = False
    shell_replaceable = 0

    for tc in raw:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        if not isinstance(fn, dict):
            continue
        name = str(fn.get("name") or "")
        tools.append(name)
        if name in INSPECT_STRUCTURED:
            has_inspect = True
        elif name in MUTATE_STRUCTURED:
            has_mutate = True
        elif name == "terminal":
            args = _parse_json(fn.get("arguments")) or {}
            cmd = ""
            if isinstance(args, dict):
                cmd = str(args.get("command") or args.get("cmd") or "")
            cat = classify_command(cmd)
            if cat in {"inspect", "search", "git"}:
                has_inspect = True
                # git is less clearly replaceable; ls/cat/grep/find are
                if cat in {"inspect", "search"}:
                    shell_replaceable += 1
            elif cat == "mutate":
                has_mutate = True
            elif cat == "test":
                # verification — treat as neither pure inspect nor mutate
                pass
            else:
                pass
        elif classify_tool(name) is BatchClass.MUTATING:
            if name not in {"todo", "clarify", "delegate_task"}:
                has_mutate = True

    if has_inspect and has_mutate:
        kind = "mixed"
    elif has_mutate:
        kind = "mutate"
    elif has_inspect:
        kind = "inspect"
    else:
        kind = "other"

    return TurnKind(
        index=0, kind=kind, tools=tools, shell_replaceable=shell_replaceable
    )


@dataclass
class SessionInspectionReport:
    session_id: str
    model: str = ""
    api_call_count: int = 0
    cache_read_tokens: int = 0
    tool_turns: int = 0
    inspect_turns: int = 0
    mutate_turns: int = 0
    mixed_turns: int = 0
    other_turns: int = 0
    inspect_before_first_mutate: Optional[int] = None
    inspect_to_mutate_ratio: Optional[float] = None
    shell_replaceable_cmds: int = 0
    structured_inspect_calls: int = 0
    verification_after_last_mutate: int = 0  # inspect/test turns after last mutate

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InspectionPolicyReport:
    sessions: list[SessionInspectionReport] = field(default_factory=list)
    aggregate: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessions": [s.to_dict() for s in self.sessions],
            "aggregate": self.aggregate,
        }


def analyze_session_messages(
    messages: list[dict[str, Any]],
    *,
    session_meta: Optional[dict[str, Any]] = None,
) -> SessionInspectionReport:
    meta = session_meta or {}
    turns: list[TurnKind] = []
    structured_inspect = 0
    shell_repl = 0

    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        if not msg.get("tool_calls"):
            continue
        tk = _classify_assistant_turn(msg.get("tool_calls"))
        tk.index = len(turns)
        turns.append(tk)
        shell_repl += tk.shell_replaceable
        for name in tk.tools:
            if name in INSPECT_STRUCTURED:
                structured_inspect += 1

    inspect_n = sum(1 for t in turns if t.kind == "inspect")
    mutate_n = sum(1 for t in turns if t.kind == "mutate")
    mixed_n = sum(1 for t in turns if t.kind == "mixed")
    other_n = sum(1 for t in turns if t.kind == "other")

    first_mut_idx = next(
        (i for i, t in enumerate(turns) if t.kind in {"mutate", "mixed"}),
        None,
    )
    inspect_before = None
    if first_mut_idx is not None:
        inspect_before = sum(
            1 for t in turns[:first_mut_idx] if t.kind == "inspect"
        )

    ratio = None
    if mutate_n + mixed_n > 0:
        ratio = round(inspect_n / (mutate_n + mixed_n), 2)

    # Verification loops: turns after last mutate that are inspect/other(test)
    last_mut = None
    for i, t in enumerate(turns):
        if t.kind in {"mutate", "mixed"}:
            last_mut = i
    verify_after = 0
    if last_mut is not None:
        verify_after = sum(
            1
            for t in turns[last_mut + 1 :]
            if t.kind in {"inspect", "other"}
        )

    return SessionInspectionReport(
        session_id=str(meta.get("id") or ""),
        model=str(meta.get("model") or ""),
        api_call_count=int(meta.get("api_call_count") or 0),
        cache_read_tokens=int(meta.get("cache_read_tokens") or 0),
        tool_turns=len(turns),
        inspect_turns=inspect_n,
        mutate_turns=mutate_n,
        mixed_turns=mixed_n,
        other_turns=other_n,
        inspect_before_first_mutate=inspect_before,
        inspect_to_mutate_ratio=ratio,
        shell_replaceable_cmds=shell_repl,
        structured_inspect_calls=structured_inspect,
        verification_after_last_mutate=verify_after,
    )


def analyze_top_sessions(
    db_path: str | Path,
    *,
    limit: int = 20,
    order_by: str = "cache_read_tokens",
) -> InspectionPolicyReport:
    allowed = {
        "cache_read_tokens",
        "api_call_count",
        "tool_call_count",
        "input_tokens",
    }
    if order_by not in allowed:
        order_by = "cache_read_tokens"

    conn = sqlite3.connect(str(Path(db_path)))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT id, model, api_call_count, tool_call_count, "
            f"cache_read_tokens FROM sessions "
            f"ORDER BY COALESCE({order_by}, 0) DESC LIMIT ?",
            (limit,),
        ).fetchall()
        sessions = []
        for r in rows:
            meta = dict(r)
            msgs = [
                dict(m)
                for m in conn.execute(
                    "SELECT role, content, tool_calls, tool_name "
                    "FROM messages WHERE session_id = ? ORDER BY id ASC",
                    (meta["id"],),
                ).fetchall()
            ]
            sessions.append(
                analyze_session_messages(msgs, session_meta=meta)
            )
    finally:
        conn.close()

    return InspectionPolicyReport(
        sessions=sessions, aggregate=_aggregate(sessions)
    )


def _aggregate(sessions: list[SessionInspectionReport]) -> dict[str, Any]:
    if not sessions:
        return {"sessions": 0}

    inspect = sum(s.inspect_turns for s in sessions)
    mutate = sum(s.mutate_turns + s.mixed_turns for s in sessions)
    shell_repl = sum(s.shell_replaceable_cmds for s in sessions)
    structured = sum(s.structured_inspect_calls for s in sessions)
    befores = [
        s.inspect_before_first_mutate
        for s in sessions
        if s.inspect_before_first_mutate is not None
    ]
    avg_before = round(sum(befores) / len(befores), 1) if befores else None
    ratios = [
        s.inspect_to_mutate_ratio
        for s in sessions
        if s.inspect_to_mutate_ratio is not None
    ]
    avg_ratio = round(sum(ratios) / len(ratios), 2) if ratios else None
    shell_share = (
        round(
            100.0 * shell_repl / (shell_repl + structured),
            1,
        )
        if (shell_repl + structured)
        else 0.0
    )

    if avg_before is not None and avg_before >= 15:
        verdict = (
            "DEEP_INSPECTION — many inspect turns before first edit; "
            "candidate for inspection-policy tuning (measure more first)"
        )
    elif shell_share >= 70:
        verdict = (
            "SHELL_PREFERRED — inspect mostly via terminal; "
            "measure whether structured tools would shrink wake-ups"
        )
    elif avg_ratio is not None and avg_ratio >= 5:
        verdict = (
            "INSPECT_HEAVY — high inspect:mutate ratio; "
            "may be cautious exploration (not necessarily waste)"
        )
    else:
        verdict = (
            "BALANCED_OR_SPARSE — no clear over-exploration signal; "
            "avoid behavioural changes until clearer evidence"
        )

    return {
        "sessions": len(sessions),
        "inspect_turns": inspect,
        "mutate_turns": mutate,
        "inspect_to_mutate_ratio": round(inspect / mutate, 2) if mutate else None,
        "avg_inspect_before_first_mutate": avg_before,
        "avg_session_inspect_to_mutate_ratio": avg_ratio,
        "shell_replaceable_cmds": shell_repl,
        "structured_inspect_calls": structured,
        "shell_share_of_inspect_ops": shell_share,
        "verdict": verdict,
    }


def format_terminal(report: InspectionPolicyReport) -> str:
    a = report.aggregate
    lines = [
        "",
        "  ╔══════════════════════════════════════════════════════════╗",
        "  ║              🔍 Inspection Policy Analytics              ║",
        "  ╚══════════════════════════════════════════════════════════╝",
        "",
        f"  Sessions:                    {a.get('sessions', 0)}",
        f"  Inspect turns:               {a.get('inspect_turns', 0)}",
        f"  Mutate turns:                {a.get('mutate_turns', 0)}",
        f"  Inspect:mutate (aggregate):  {a.get('inspect_to_mutate_ratio')}",
        f"  Avg inspect before 1st edit: {a.get('avg_inspect_before_first_mutate')}",
        f"  Shell-replaceable cmds:      {a.get('shell_replaceable_cmds', 0)}",
        f"  Structured inspect calls:    {a.get('structured_inspect_calls', 0)}",
        f"  Shell share of inspect ops:  {a.get('shell_share_of_inspect_ops', 0)}%",
        "",
        f"  Verdict: {a.get('verdict', '')}",
        "",
    ]
    if report.sessions:
        lines.append("  Top sessions")
        lines.append("  " + "─" * 56)
        lines.append(
            f"  {'Session':<22} {'Insp':>5} {'Mut':>4} {'Before':>6} "
            f"{'Ratio':>6} {'Shell%':>6}"
        )
        for s in report.sessions[:15]:
            before = (
                s.inspect_before_first_mutate
                if s.inspect_before_first_mutate is not None
                else "-"
            )
            ratio = (
                s.inspect_to_mutate_ratio
                if s.inspect_to_mutate_ratio is not None
                else "-"
            )
            denom = s.shell_replaceable_cmds + s.structured_inspect_calls
            shell_pct = (
                round(100.0 * s.shell_replaceable_cmds / denom, 0)
                if denom
                else 0
            )
            lines.append(
                f"  {s.session_id[:22]:<22} {s.inspect_turns:>5} "
                f"{s.mutate_turns + s.mixed_turns:>4} {str(before):>6} "
                f"{str(ratio):>6} {shell_pct:>5.0f}%"
            )
        lines.append("")
    return "\n".join(lines)


def format_markdown(report: InspectionPolicyReport) -> str:
    a = report.aggregate
    lines = [
        "# Inspection Policy Analytics",
        "",
        f"**Verdict:** {a.get('verdict', '')}",
        "",
        "## Aggregate",
        "",
        f"- Inspect turns: **{a.get('inspect_turns', 0)}**",
        f"- Mutate turns: **{a.get('mutate_turns', 0)}**",
        f"- Inspect:mutate: **{a.get('inspect_to_mutate_ratio')}**",
        f"- Avg inspect before first mutate: **{a.get('avg_inspect_before_first_mutate')}**",
        f"- Shell share of inspect ops: **{a.get('shell_share_of_inspect_ops', 0)}%**",
        "",
        "## Per session",
        "",
        "| Session | Inspect | Mutate | Before 1st edit | Ratio | Shell% |",
        "|---------|---------|--------|-----------------|-------|--------|",
    ]
    for s in report.sessions:
        denom = s.shell_replaceable_cmds + s.structured_inspect_calls
        shell_pct = (
            round(100.0 * s.shell_replaceable_cmds / denom, 1) if denom else 0
        )
        lines.append(
            f"| `{s.session_id}` | {s.inspect_turns} | "
            f"{s.mutate_turns + s.mixed_turns} | "
            f"{s.inspect_before_first_mutate} | "
            f"{s.inspect_to_mutate_ratio} | {shell_pct}% |"
        )
    lines.append("")
    return "\n".join(lines)
