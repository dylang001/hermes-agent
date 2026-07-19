"""Terminal Loop Analysis — measure shell micro-loops before changing runtime.

Evidence follow-up to wake-up analysis: the heavy session was ~272 ``terminal``
calls, not SAFE reads. This report classifies each command and detects
duplicates / retries / inspect-vs-mutate mix.

See ``audit/HERMES_TRACK_B_PLAN.md`` (batching archived; terminal is next).
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional


# ── Categories ────────────────────────────────────────────────────

CAT_BUILD = "build"
CAT_TEST = "test"
CAT_GIT = "git"
CAT_SEARCH = "search"
CAT_INSPECT = "inspect"
CAT_INSTALL = "install"
CAT_FORMAT = "formatting"
CAT_MUTATE = "mutate"
CAT_SSH = "ssh"
CAT_HERMES = "hermes_cli"
CAT_RETRY = "retry"  # assigned as flag, not exclusive category
CAT_OTHER = "other"

_TEST_RE = re.compile(
    r"(?:^|[\s;&|])(?:pytest|py\.test|scripts/run_tests\.sh|npm\s+test|vitest|"
    r"cargo\s+test|go\s+test|unittest)\b",
    re.I,
)
_BUILD_RE = re.compile(
    r"(?:^|[\s;&|])(?:make\b|cmake\b|ninja\b|cargo\s+build|npm\s+run\s+build|"
    r"tsc\b|webpack|vite\s+build|uv\s+build|python\s+-m\s+build)\b",
    re.I,
)
_INSTALL_RE = re.compile(
    r"(?:^|[\s;&|])(?:pip\d*\s+install|uv\s+pip\s+install|npm\s+i(?:nstall)?|"
    r"yarn\s+add|brew\s+install|apt(?:-get)?\s+install|cargo\s+install)\b",
    re.I,
)
_FORMAT_RE = re.compile(
    r"(?:^|[\s;&|])(?:black|ruff\s+format|prettier|isort|gofmt|rustfmt|"
    r"clang-format)\b",
    re.I,
)
_SEARCH_RE = re.compile(
    r"(?:^|[\s;&|])(?:grep\b|rg\b|ag\b|find\b|fd\b|ack\b)\b",
    re.I,
)
_INSPECT_RE = re.compile(
    r"(?:^|[\s;&|])(?:ls\b|cat\b|head\b|tail\b|wc\b|pwd\b|which\b|type\b|"
    r"file\b|stat\b|du\b|df\b|ps\b|tree\b|realpath\b|dirname\b|basename\b|"
    r"echo\b|date\b|env\b|printenv\b|whoami\b)\b",
    re.I,
)
_MUTATE_RE = re.compile(
    r"(?:^|[\s;&|])(?:rm\b|mv\b|cp\b|mkdir\b|touch\b|chmod\b|chown\b|"
    r"sed\s+-i|tee\b|truncate\b|dd\b|>\s*\S)",
    re.I,
)
_GIT_RE = re.compile(r"(?:^|[\s;&|])git\b", re.I)
_SSH_RE = re.compile(r"(?:^|[\s;&|])(?:ssh|scp|rsync)\b", re.I)
_HERMES_RE = re.compile(r"(?:^|[\s;&|])hermes\b", re.I)


def normalize_command(cmd: str) -> str:
    """Collapse whitespace for duplicate detection."""
    return re.sub(r"\s+", " ", (cmd or "").strip())


def classify_command(cmd: str) -> str:
    """Primary category for a shell command string."""
    c = cmd or ""
    # Order matters: more specific first
    if _TEST_RE.search(c):
        return CAT_TEST
    if _BUILD_RE.search(c):
        return CAT_BUILD
    if _INSTALL_RE.search(c):
        return CAT_INSTALL
    if _FORMAT_RE.search(c):
        return CAT_FORMAT
    if _SSH_RE.search(c):
        return CAT_SSH
    if _HERMES_RE.search(c):
        return CAT_HERMES
    if _GIT_RE.search(c):
        return CAT_GIT
    if _SEARCH_RE.search(c):
        return CAT_SEARCH
    if _MUTATE_RE.search(c) and not _INSPECT_RE.search(c):
        return CAT_MUTATE
    # Pipelines that are mostly inspect (ls && cat && …)
    if _INSPECT_RE.search(c) and not _MUTATE_RE.search(c):
        return CAT_INSPECT
    if _MUTATE_RE.search(c):
        return CAT_MUTATE
    if _INSPECT_RE.search(c):
        return CAT_INSPECT
    return CAT_OTHER


def _parse_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {"_raw": raw}
    return {}


def _parse_result(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if not isinstance(content, str) or not content.strip():
        return {}
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {"output": content}
    except (json.JSONDecodeError, TypeError):
        # Some rows append trailing text — take first JSON object
        try:
            dec = json.JSONDecoder()
            parsed, _ = dec.raw_decode(content.strip())
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}


@dataclass
class TerminalEvent:
    command: str
    normalized: str
    category: str
    exit_code: Optional[int] = None
    is_duplicate: bool = False
    is_retry: bool = False  # same normalized cmd after non-zero exit


@dataclass
class SessionTerminalReport:
    session_id: str
    model: str = ""
    api_call_count: int = 0
    cache_read_tokens: int = 0
    terminal_calls: int = 0
    unique_commands: int = 0
    duplicate_commands: int = 0
    duplicate_rate: float = 0.0
    retry_events: int = 0
    retry_rate: float = 0.0
    non_zero_exits: int = 0
    exit_zero: int = 0
    exit_unknown: int = 0
    categories: dict[str, int] = field(default_factory=dict)
    top_commands: list[dict[str, Any]] = field(default_factory=list)
    inspect_search_git_share: float = 0.0  # % of terminal that is read-ish
    median_extra_runs_for_repeated_cmds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TerminalLoopReport:
    sessions: list[SessionTerminalReport] = field(default_factory=list)
    aggregate: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessions": [s.to_dict() for s in self.sessions],
            "aggregate": self.aggregate,
        }


def extract_terminal_events(messages: list[dict[str, Any]]) -> list[TerminalEvent]:
    """Pair assistant terminal tool_calls with subsequent tool results."""
    # Map tool_call_id → result
    results: dict[str, dict[str, Any]] = {}
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        if (msg.get("tool_name") or "") not in {"terminal", "", None}:
            # Still accept if content looks like terminal JSON
            pass
        tid = msg.get("tool_call_id")
        if tid:
            results[str(tid)] = _parse_result(msg.get("content"))

    events: list[TerminalEvent] = []
    seen_norm: set[str] = set()
    last_fail_norm: Optional[str] = None

    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        raw = msg.get("tool_calls")
        if isinstance(raw, str) and raw.strip():
            try:
                tcs = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
        elif isinstance(raw, list):
            tcs = raw
        else:
            continue

        for tc in tcs or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            if not isinstance(fn, dict):
                continue
            if (fn.get("name") or "") != "terminal":
                continue
            args = _parse_args(fn.get("arguments"))
            cmd = str(args.get("command") or args.get("cmd") or "")
            norm = normalize_command(cmd)
            cat = classify_command(cmd)
            tid = str(tc.get("id") or "")
            res = results.get(tid) or {}
            exit_code = res.get("exit_code")
            if exit_code is None:
                exit_code = res.get("exit")
            try:
                exit_code = int(exit_code) if exit_code is not None else None
            except (TypeError, ValueError):
                exit_code = None

            is_dup = bool(norm) and norm in seen_norm
            is_retry = bool(
                norm
                and last_fail_norm
                and norm == last_fail_norm
                and exit_code is not None
            )
            # retry: re-running same cmd after a previous failure of that cmd
            if last_fail_norm and norm == last_fail_norm:
                is_retry = True

            if norm:
                seen_norm.add(norm)

            events.append(
                TerminalEvent(
                    command=cmd,
                    normalized=norm,
                    category=cat,
                    exit_code=exit_code,
                    is_duplicate=is_dup,
                    is_retry=is_retry,
                )
            )

            if exit_code is not None and exit_code != 0 and norm:
                last_fail_norm = norm
            elif exit_code == 0:
                if norm == last_fail_norm:
                    last_fail_norm = None

    return events


def analyze_terminal_events(events: list[TerminalEvent]) -> dict[str, Any]:
    cats: Counter[str] = Counter()
    cmd_counts: Counter[str] = Counter()
    exit_zero = exit_nz = exit_unk = 0
    dups = retries = 0

    for e in events:
        cats[e.category] += 1
        if e.normalized:
            cmd_counts[e.normalized] += 1
        if e.is_duplicate:
            dups += 1
        if e.is_retry:
            retries += 1
        if e.exit_code is None:
            exit_unk += 1
        elif e.exit_code == 0:
            exit_zero += 1
        else:
            exit_nz += 1

    n = len(events)
    unique = len(cmd_counts)
    inspectish = (
        cats.get(CAT_INSPECT, 0)
        + cats.get(CAT_SEARCH, 0)
        + cats.get(CAT_GIT, 0)
    )
    top = [
        {"command": c[:160], "count": n}
        for c, n in cmd_counts.most_common(15)
    ]
    # Median retries: for commands run >1 time after a failure — approximate
    # as mean (count-1) for commands with count>=2 that had a non-zero at some point
    # Simpler: median of (count - 1) for all commands with count >= 2
    extras = sorted([cnt - 1 for cnt in cmd_counts.values() if cnt >= 2])
    median_extra = 0.0
    if extras:
        mid = len(extras) // 2
        median_extra = (
            float(extras[mid])
            if len(extras) % 2
            else (extras[mid - 1] + extras[mid]) / 2.0
        )

    return {
        "terminal_calls": n,
        "unique_commands": unique,
        "duplicate_commands": dups,
        "duplicate_rate": round(100.0 * dups / n, 1) if n else 0.0,
        "retry_events": retries,
        "retry_rate": round(100.0 * retries / n, 1) if n else 0.0,
        "non_zero_exits": exit_nz,
        "exit_zero": exit_zero,
        "exit_unknown": exit_unk,
        "categories": dict(cats),
        "top_commands": top,
        "inspect_search_git_share": round(100.0 * inspectish / n, 1) if n else 0.0,
        "median_extra_runs_for_repeated_cmds": median_extra,
    }


def analyze_session_messages(
    messages: list[dict[str, Any]],
    *,
    session_meta: Optional[dict[str, Any]] = None,
) -> SessionTerminalReport:
    meta = session_meta or {}
    events = extract_terminal_events(messages)
    stats = analyze_terminal_events(events)
    return SessionTerminalReport(
        session_id=str(meta.get("id") or meta.get("session_id") or ""),
        model=str(meta.get("model") or ""),
        api_call_count=int(meta.get("api_call_count") or 0),
        cache_read_tokens=int(meta.get("cache_read_tokens") or 0),
        **stats,
    )


def analyze_top_sessions(
    db_path: str | Path,
    *,
    limit: int = 20,
    order_by: str = "cache_read_tokens",
    session_id: Optional[str] = None,
) -> TerminalLoopReport:
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
        if session_id:
            rows = conn.execute(
                "SELECT id, model, api_call_count, tool_call_count, "
                "cache_read_tokens, input_tokens, output_tokens "
                "FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT id, model, api_call_count, tool_call_count, "
                f"cache_read_tokens, input_tokens, output_tokens "
                f"FROM sessions ORDER BY COALESCE({order_by}, 0) DESC LIMIT ?",
                (limit,),
            ).fetchall()

        sessions: list[SessionTerminalReport] = []
        for r in rows:
            meta = dict(r)
            msgs = [
                dict(m)
                for m in conn.execute(
                    "SELECT role, content, tool_calls, tool_name, tool_call_id "
                    "FROM messages WHERE session_id = ? ORDER BY id ASC",
                    (meta["id"],),
                ).fetchall()
            ]
            sessions.append(analyze_session_messages(msgs, session_meta=meta))
    finally:
        conn.close()

    return TerminalLoopReport(sessions=sessions, aggregate=_aggregate(sessions))


def _aggregate(sessions: list[SessionTerminalReport]) -> dict[str, Any]:
    if not sessions:
        return {"sessions": 0}

    total = sum(s.terminal_calls for s in sessions)
    dups = sum(s.duplicate_commands for s in sessions)
    retries = sum(s.retry_events for s in sessions)
    nz = sum(s.non_zero_exits for s in sessions)
    z = sum(s.exit_zero for s in sessions)
    cats: Counter[str] = Counter()
    for s in sessions:
        cats.update(s.categories)

    inspectish = (
        cats.get(CAT_INSPECT, 0)
        + cats.get(CAT_SEARCH, 0)
        + cats.get(CAT_GIT, 0)
    )

    # Verdict for next engineering focus
    if total == 0:
        verdict = "NO_TERMINAL — look elsewhere"
    elif (100.0 * inspectish / total) >= 50:
        verdict = (
            "TERMINAL_AS_CHAT — majority inspect/search/git via shell; "
            "consider read_file/search_files or terminal macros"
        )
    elif (100.0 * retries / total) >= 20:
        verdict = "RETRY_STORM — high same-command retries after failure"
    elif (100.0 * dups / total) >= 25:
        verdict = "DUPLICATE_SHELL — many exact command repeats"
    elif cats.get(CAT_TEST, 0) / total >= 0.3:
        verdict = "TEST_LOOP — heavy pytest / run_tests churn"
    else:
        verdict = "MIXED — dig into per-session top_commands"

    return {
        "sessions": len(sessions),
        "terminal_calls": total,
        "duplicate_commands": dups,
        "duplicate_rate": round(100.0 * dups / total, 1) if total else 0.0,
        "retry_events": retries,
        "retry_rate": round(100.0 * retries / total, 1) if total else 0.0,
        "exit_zero": z,
        "non_zero_exits": nz,
        "success_rate": round(100.0 * z / (z + nz), 1) if (z + nz) else 0.0,
        "categories": dict(cats),
        "inspect_search_git_share": round(100.0 * inspectish / total, 1)
        if total
        else 0.0,
        "verdict": verdict,
    }


def format_terminal(report: TerminalLoopReport) -> str:
    a = report.aggregate
    lines = [
        "",
        "  ╔══════════════════════════════════════════════════════════╗",
        "  ║              🐚 Terminal Loop Analysis                   ║",
        "  ╚══════════════════════════════════════════════════════════╝",
        "",
        f"  Sessions analyzed:     {a.get('sessions', 0)}",
        f"  Terminal calls:        {a.get('terminal_calls', 0):,}",
        f"  Duplicate rate:        {a.get('duplicate_rate', 0)}%",
        f"  Retry rate:            {a.get('retry_rate', 0)}%",
        f"  Exit success rate:     {a.get('success_rate', 0)}% "
        f"(zero={a.get('exit_zero', 0)}, nonzero={a.get('non_zero_exits', 0)})",
        f"  Inspect+search+git:    {a.get('inspect_search_git_share', 0)}%",
        "",
        "  Categories",
        "  " + "─" * 56,
    ]
    for k, v in sorted(
        (a.get("categories") or {}).items(), key=lambda kv: -kv[1]
    ):
        lines.append(f"  {k:<20} {v:>8}")
    lines.append("")
    lines.append(f"  Verdict: {a.get('verdict', '')}")
    lines.append("")
    if report.sessions:
        lines.append("  Top sessions (by terminal volume in this set)")
        lines.append("  " + "─" * 56)
        ranked = sorted(
            report.sessions, key=lambda s: -s.terminal_calls
        )[:15]
        lines.append(
            f"  {'Session':<22} {'Term':>5} {'Dup%':>6} {'Retry%':>7} "
            f"{'Insp%':>6} {'OK%':>5}"
        )
        for s in ranked:
            ok = (
                round(
                    100.0
                    * s.exit_zero
                    / (s.exit_zero + s.non_zero_exits),
                    0,
                )
                if (s.exit_zero + s.non_zero_exits)
                else 0
            )
            lines.append(
                f"  {s.session_id[:22]:<22} {s.terminal_calls:>5} "
                f"{s.duplicate_rate:>5.1f}% {s.retry_rate:>6.1f}% "
                f"{s.inspect_search_git_share:>5.1f}% {ok:>4.0f}%"
            )
        lines.append("")
        # Spotlight monster session top commands
        heavy = max(report.sessions, key=lambda s: s.terminal_calls)
        if heavy.top_commands:
            lines.append(f"  Top commands in `{heavy.session_id[:22]}`")
            lines.append("  " + "─" * 56)
            for item in heavy.top_commands[:10]:
                lines.append(
                    f"  ×{item['count']:<3} {item['command'][:70]}"
                )
            lines.append("")
    return "\n".join(lines)


def format_markdown(report: TerminalLoopReport) -> str:
    a = report.aggregate
    lines = [
        "# Terminal Loop Analysis",
        "",
        "Follow-up to Model Wake-up Analysis. SAFE batching archived; "
        "terminal micro-loops are the measured bottleneck candidate.",
        "",
        "## Aggregate",
        "",
        f"- Sessions: **{a.get('sessions', 0)}**",
        f"- Terminal calls: **{a.get('terminal_calls', 0):,}**",
        f"- Duplicate rate: **{a.get('duplicate_rate', 0)}%**",
        f"- Retry rate: **{a.get('retry_rate', 0)}%**",
        f"- Exit success rate: **{a.get('success_rate', 0)}%**",
        f"- Inspect+search+git share: **{a.get('inspect_search_git_share', 0)}%**",
        "",
        f"**Verdict:** {a.get('verdict', '')}",
        "",
        "### Categories",
        "",
        "| Category | Count |",
        "|----------|------:|",
    ]
    for k, v in sorted(
        (a.get("categories") or {}).items(), key=lambda kv: -kv[1]
    ):
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "## Method",
        "",
        "- Pair each `terminal` tool_call with its tool result (`exit_code`).",
        "- Classify command text (test/build/git/search/inspect/…).",
        "- **Duplicate:** exact normalized command seen earlier in the session.",
        "- **Retry:** same normalized command re-run after a prior non-zero exit "
        "of that command.",
        "",
        "## Per-session",
        "",
        "| Session | Terminal | Dup% | Retry% | Insp+git+search% | OK% |",
        "|---------|----------|------|--------|------------------|-----|",
    ]
    for s in sorted(report.sessions, key=lambda x: -x.terminal_calls):
        ok = (
            round(
                100.0 * s.exit_zero / (s.exit_zero + s.non_zero_exits), 1
            )
            if (s.exit_zero + s.non_zero_exits)
            else 0
        )
        lines.append(
            f"| `{s.session_id}` | {s.terminal_calls} | {s.duplicate_rate}% | "
            f"{s.retry_rate}% | {s.inspect_search_git_share}% | {ok}% |"
        )
    lines.append("")
    return "\n".join(lines)
