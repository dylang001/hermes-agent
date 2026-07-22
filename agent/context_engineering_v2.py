"""Context Engineering V2 — measurement, dark stores, and layered assemble.

P1 — **shadow prompt profiler** (log-only)

P2 — **Working Memory store** (dark / fail-open)

P3 — **SAFE summarise→archive** (shadow; blobs + index)

P4 — **MUTATING pin/unpin epoch** (dark pin set)

P5 — **Layered assemble for inspect steps** (opt-in wire change)

P6 — **Retrieval helper + A/B soak** (opt-in):

* ``context_archive`` tool (service-gated) for list/get of SAFE archives
* Budgeted raw segments appended at end of API messages (cache-friendly)
* Pending retrieve queue + optional auto-retrieve on verify failure
* Soak JSONL comparing legacy vs layered arms per call

P1–P4 helpers never mutate the wire prompt. P5/P6 do only when their
config flags are enabled.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shlex
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Rough char→token divisor used elsewhere in Hermes rough estimators.
_CHARS_PER_TOKEN = 4

# SessionDB state_meta key prefix for Working Memory (P2).
_WM_META_PREFIX = "context_wm_v2:"
_WM_SCHEMA_VERSION = 1
_DEFAULT_WM_BUDGET_TOKENS = 2_000
_MAX_OBJECTIVE_CHARS = 240
_MAX_ACTIVE_FILES = 12
_MAX_DECISIONS = 24

# SAFE archive (P3) — index in state_meta, blobs under HERMES_HOME/context_archive/.
_ARCHIVE_META_PREFIX = "context_archive_v2:"
_DEFAULT_ARCHIVE_MIN_CHARS = 400
_DEFAULT_ARCHIVE_SUMMARY_MAX_CHARS = 256
_PATHISH = re.compile(
    r"(?:^|[\s`\"'(])("
    r"(?:[A-Za-z]:)?(?:\./|\.\./|/)?[\w./+-]+\.[A-Za-z0-9]{1,8}"
    r")(?:$|[\s`\"'):,])"
)
_ERRORISH = re.compile(
    r"(?i)\b(error|failed|failure|traceback|exception|not found|enoent)\b"
)

# Pin epoch (P4) — state_meta index of open MUTATING/VERIFY pins.
_PIN_META_PREFIX = "context_pins_v2:"
_PIN_SCHEMA_VERSION = 1

# Retrieve queue (P6) — pending archive injects for next assemble.
_RETRIEVE_META_PREFIX = "context_retrieve_v2:"
_DEFAULT_RETRIEVE_MAX_TOKENS = 4_000
_DEFAULT_SOAK_LOG = "context_engineering_v2_soak.jsonl"
_USER_ABANDON = re.compile(
    r"(?i)\b("
    r"never\s*mind|nevermind|cancel\s+that|scratch\s+that|"
    r"forget\s+(?:it|that)|abandon(?:\s+that)?|undo\s+that|"
    r"don'?t\s+(?:do|bother)|stop\s+that"
    r")\b"
)
# Text fallback only when no trustworthy exit_code is present (legacy /
# non-terminal tools). Prefer exit_code via ``detect_verify_outcome``.
_VERIFY_PASS = re.compile(
    r"(?i)(\b\d+\s+passed\b|\ball\s+tests?\s+passed\b|\bok\b.*\bpassed\b|"
    r"\"success\"\s*:\s*true|\berror_count\s*[:=]\s*0\b)"
)
_VERIFY_FAIL = re.compile(
    r"(?i)(\bFAILED\b|\b\d+\s+failed\b|\berrors?\s*[:=]\s*[1-9]|"
    r"\"success\"\s*:\s*false|Traceback \(most recent call last\))"
)

# Pipeline stages that only format/slice output — never demote VERIFY.
_PIPELINE_FORMATTERS = frozenset(
    {
        "head",
        "tail",
        "grep",
        "egrep",
        "fgrep",
        "rg",
        "wc",
        "sort",
        "uniq",
        "tee",
        "less",
        "more",
        "cat",  # often used as passthrough at end of pipes
        "cut",
        "awk",
        "sed",
        "tr",
        "column",
        "jq",
        "python3",  # only when `-m json.tool` — handled in formatter check
        "python",
    }
)
_NODE_PKG_MANAGERS = frozenset({"npm", "pnpm", "yarn", "bun"})
_NODE_VERIFY_SCRIPTS = frozenset(
    {"test", "lint", "typecheck", "types", "build", "check", "verify", "ci"}
)
_MAKE_VERIFY_TARGETS = frozenset(
    {"test", "check", "lint", "typecheck", "verify", "build", "ci"}
)
_DEFAULT_VERIFY_SCRIPT_BASENAMES = frozenset(
    {
        "knowledge_os_lint.py",
        "run_tests.sh",
        "run_tests.py",
    }
)
_PYTHON_EXES = frozenset(
    {"python", "python3", "python3.10", "python3.11", "python3.12", "python3.13"}
)

# git subcommands that are inspect-only for evidence classification.
_GIT_SAFE_SUB = re.compile(
    r"\bgit\s+(?:status|diff|log|show|branch|tag|remote|stash\s+list|"
    r"rev-parse|describe|blame|shortlog)\b",
    re.I,
)
_GIT_MUTATE_SUB = re.compile(
    r"\bgit\s+(?:commit|add|push|pull|merge|rebase|checkout|switch|"
    r"reset|clean|cherry-pick|stash(?:\s+pop|\s+apply|\s+drop)?|"
    r"rm|mv|restore|fetch|clone|init)\b",
    re.I,
)


class EvidenceClass(str, Enum):
    SAFE = "safe"
    VERIFY = "verify"
    MUTATING = "mutating"
    DELEGATE = "delegate"
    OTHER = "other"


_STRUCTURED_SAFE = frozenset(
    {
        "ha_get_state",
        "ha_list_entities",
        "ha_list_services",
        "read_file",
        "search_files",
        "session_search",
        "skill_view",
        "skills_list",
        "vision_analyze",
        "web_extract",
        "web_search",
        "todo",  # checklist state — not bulk evidence; treat as cheap/safe
    }
)
_STRUCTURED_MUTATING = frozenset(
    {
        "write_file",
        "patch",
        "memory",
        "skill_manage",
        "browser_click",
        "browser_type",
        "browser_press",
        "browser_scroll",
        "browser_navigate",
        "send_message",
        "cronjob",
        "process",
        "execute_code",
    }
)


def _load_verify_command_config() -> Dict[str, Any]:
    """Optional registry extensions from config.yaml."""
    defaults: Dict[str, Any] = {
        "script_basenames": [],
        "extra_executables": [],
    }
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        section = cfg.get("context_engineering_v2") or {}
        vc = section.get("verify_commands") or {}
        if not isinstance(vc, dict):
            return defaults
        out = dict(defaults)
        for key in defaults:
            if key in vc and isinstance(vc[key], list):
                out[key] = [str(x) for x in vc[key] if str(x).strip()]
        return out
    except Exception:
        return defaults


def _strip_shell_comments(cmd: str) -> str:
    """Remove ``#`` comments so English like 'make sure' cannot classify."""
    lines: List[str] = []
    for line in (cmd or "").splitlines():
        in_single = False
        in_double = False
        cut = len(line)
        i = 0
        while i < len(line):
            ch = line[i]
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "#" and not in_single and not in_double:
                cut = i
                break
            i += 1
        stripped = line[:cut].rstrip()
        if stripped.strip():
            lines.append(stripped)
    return "\n".join(lines)


def _split_pipeline_stages(cmd: str) -> List[str]:
    """Split on top-level ``|`` (not inside quotes)."""
    stages: List[str] = []
    buf: List[str] = []
    in_single = False
    in_double = False
    for ch in cmd or "":
        if ch == "'" and not in_double:
            in_single = not in_single
            buf.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            buf.append(ch)
        elif ch == "|" and not in_single and not in_double:
            stage = "".join(buf).strip()
            if stage:
                stages.append(stage)
            buf = []
        else:
            buf.append(ch)
    stage = "".join(buf).strip()
    if stage:
        stages.append(stage)
    return stages or [""]


def _strip_redirects(stage: str) -> str:
    """Drop ``2>&1``, ``>file``, ``<file`` tokens for argv parsing."""
    # Remove common redirect forms before shlex so they don't become argv.
    s = re.sub(r"(?:^|\s)\d*>&\d+", " ", stage or "")
    s = re.sub(r"(?:^|\s)\d*[<>]+\s*\S+", " ", s)
    return s.strip()


def _tokenize_stage(stage: str) -> List[str]:
    cleaned = _strip_redirects(stage)
    if not cleaned:
        return []
    try:
        return shlex.split(cleaned, posix=True)
    except ValueError:
        return cleaned.split()


def _exe_basename(token: str) -> str:
    t = (token or "").strip().strip("'\"")
    if not t:
        return ""
    # env/wrappers: take last path component
    base = Path(t).name
    return base.lower()


def _is_formatter_stage(argv: List[str]) -> bool:
    if not argv:
        return True
    exe = _exe_basename(argv[0])
    if exe in {"xargs"}:
        return True
    if exe in _PYTHON_EXES and len(argv) >= 3 and argv[1] == "-m" and argv[2] in {
        "json.tool",
        "json",
    }:
        return True
    if exe in _PIPELINE_FORMATTERS and exe not in _PYTHON_EXES:
        return True
    # bare `python3 -m json.tool` already handled; other python ≠ formatter
    if exe in _PIPELINE_FORMATTERS and exe in _PYTHON_EXES:
        return False
    return False


def _verify_script_basenames() -> frozenset[str]:
    cfg = _load_verify_command_config()
    extra = {str(x).lower() for x in (cfg.get("script_basenames") or [])}
    return frozenset({b.lower() for b in _DEFAULT_VERIFY_SCRIPT_BASENAMES} | extra)


def _extra_verify_executables() -> frozenset[str]:
    cfg = _load_verify_command_config()
    return frozenset(
        str(x).lower() for x in (cfg.get("extra_executables") or []) if str(x).strip()
    )


def _stage_is_verify(argv: List[str]) -> bool:
    """Return True if this pipeline stage is an allowlisted verify invocation."""
    if not argv or _is_formatter_stage(argv):
        return False

    # Skip leading env assignments: FOO=bar cmd …
    i = 0
    while i < len(argv) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[i]):
        i += 1
    # Skip common wrappers
    while i < len(argv) and _exe_basename(argv[i]) in {
        "env",
        "sudo",
        "nice",
        "nohup",
        "command",
        "time",
        "timeout",
    }:
        # timeout 15 cmd …  / env VAR=x cmd
        exe = _exe_basename(argv[i])
        i += 1
        if exe == "timeout" and i < len(argv) and re.match(r"^\d", argv[i]):
            i += 1
        while i < len(argv) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[i]):
            i += 1
        if exe == "env":
            continue
        break

    if i >= len(argv):
        return False

    exe = _exe_basename(argv[i])
    rest = argv[i + 1 :]

    if exe in _extra_verify_executables():
        return True

    # pytest / unittest entrypoints
    if exe in {"pytest", "py.test", "vitest", "unittest"}:
        return True
    if exe in _PYTHON_EXES and rest:
        if rest[0] == "-m" and len(rest) >= 2 and rest[1] in {
            "pytest",
            "unittest",
            "mypy",
            "pyright",
            "ruff",
        }:
            # python -m ruff check …
            if rest[1] == "ruff":
                return len(rest) >= 3 and rest[2] == "check"
            return True
        # python path/to/knowledge_os_lint.py
        script = _exe_basename(rest[0])
        if script in _verify_script_basenames():
            return True

    # bare /path/knowledge_os_lint.py or ./scripts/run_tests.sh
    if exe in _verify_script_basenames():
        return True

    # ruff check …
    if exe == "ruff":
        return bool(rest) and rest[0] == "check"

    if exe in {"mypy", "pyright", "basedpyright", "eslint", "tsc"}:
        return True

    if exe in {"cargo"} and rest and rest[0] in {"test", "build", "check", "clippy"}:
        return True
    if exe == "go" and rest and rest[0] == "test":
        return True

    # node package managers
    if exe in _NODE_PKG_MANAGERS:
        if not rest:
            return False
        if rest[0] == "test":
            return True
        if rest[0] == "run" and len(rest) >= 2:
            script = rest[1].split(":")[0]  # lint:fix → lint
            return script in _NODE_VERIFY_SCRIPTS
        if exe == "bun" and rest[0] in _NODE_VERIFY_SCRIPTS:
            return True

    # make <verify-target> — executable must be make, not English "make sure"
    if exe == "make":
        if not rest:
            return False
        # skip make options (-j, --jobs, VAR=val)
        targets = [
            t
            for t in rest
            if not t.startswith("-") and "=" not in t
        ]
        if not targets:
            return False
        return targets[0] in _MAKE_VERIFY_TARGETS

    # npx tsc / npx eslint …
    if exe == "npx" and rest:
        # npx -y tsc --noEmit
        j = 0
        while j < len(rest) and rest[j].startswith("-"):
            j += 1
        if j < len(rest) and _exe_basename(rest[j]) in {
            "tsc",
            "eslint",
            "vitest",
            "pyright",
        }:
            return True

    return False


def is_verify_command(command: str | None) -> bool:
    """True when any non-formatter pipeline stage is an allowlisted VERIFY cmd."""
    cleaned = _strip_shell_comments(command or "")
    if not cleaned.strip():
        return False
    # Also split on && / ; and require any segment's pipeline to verify
    # (cd x && pytest → verify).
    segments = re.split(r"(?:&&|;|\n)", cleaned)
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        stages = _split_pipeline_stages(seg)
        substantive = False
        for stage in stages:
            argv = _tokenize_stage(stage)
            if not argv:
                continue
            if _is_formatter_stage(argv):
                continue
            substantive = True
            if _stage_is_verify(argv):
                return True
        # If the only stages were formatters, ignore.
        _ = substantive
    return False


def classify_evidence(tool_name: str, command: str | None = None) -> EvidenceClass:
    """Classify a tool result for V2 SAFE-archive vs pin policy.

    VERIFY is allowlist-based structured classification (not whole-command
    regex). Other terminal categories reuse ``terminal_loop_analysis``.
    """
    name = (tool_name or "").strip()
    if not name:
        return EvidenceClass.OTHER
    if name == "delegate_task":
        return EvidenceClass.DELEGATE
    if name in _STRUCTURED_SAFE:
        return EvidenceClass.SAFE
    if name in _STRUCTURED_MUTATING:
        return EvidenceClass.MUTATING
    if name == "terminal":
        return _classify_terminal_command(command or "")
    # Unknown tools: conservative — treat as mutating so we never archive
    # evidence that might be load-bearing.
    return EvidenceClass.MUTATING


def _classify_terminal_command(cmd: str) -> EvidenceClass:
    from agent.terminal_loop_analysis import (
        CAT_FORMAT,
        CAT_GIT,
        CAT_INSPECT,
        CAT_INSTALL,
        CAT_MUTATE,
        CAT_SEARCH,
        classify_command,
    )

    # VERIFY first — structured allowlist; ignores comment text / formatters.
    if is_verify_command(cmd):
        return EvidenceClass.VERIFY

    # Classify on comment-stripped text so analytics categories are cleaner.
    cleaned = _strip_shell_comments(cmd)
    # Use the first substantive pipeline stage for SAFE/MUTATING (not tail/head).
    primary = cleaned
    for seg in re.split(r"(?:&&|;|\n)", cleaned):
        seg = seg.strip()
        if not seg:
            continue
        for stage in _split_pipeline_stages(seg):
            argv = _tokenize_stage(stage)
            if argv and not _is_formatter_stage(argv):
                primary = stage
                break
        else:
            continue
        break

    cat = classify_command(primary)
    # CAT_TEST / CAT_BUILD no longer map to VERIFY — allowlist only.
    if cat in {CAT_INSPECT, CAT_SEARCH}:
        return EvidenceClass.SAFE
    if cat == CAT_GIT:
        if _GIT_MUTATE_SUB.search(primary):
            return EvidenceClass.MUTATING
        if _GIT_SAFE_SUB.search(primary) or primary.strip().lower() in {
            "git",
            "git status",
        }:
            return EvidenceClass.SAFE
        return EvidenceClass.MUTATING
    if cat in {CAT_MUTATE, CAT_INSTALL, CAT_FORMAT}:
        return EvidenceClass.MUTATING
    return EvidenceClass.MUTATING


def _content_chars(content: Any) -> int:
    if content is None:
        return 0
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict):
                total += len(str(part.get("text") or ""))
            else:
                total += len(str(part))
        return total
    return len(str(content))


def _tokens_from_chars(chars: int) -> int:
    if chars <= 0:
        return 0
    return max(1, chars // _CHARS_PER_TOKEN)


def _message_chars(msg: Mapping[str, Any]) -> int:
    n = _content_chars(msg.get("content"))
    tcs = msg.get("tool_calls")
    if tcs:
        try:
            n += len(json.dumps(tcs, ensure_ascii=False, default=str))
        except Exception:
            n += len(str(tcs))
    return n


def _parse_args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            val = json.loads(raw)
            return val if isinstance(val, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _index_tool_calls(
    messages: Sequence[Mapping[str, Any]],
) -> Dict[str, Tuple[str, Optional[str]]]:
    """Map tool_call_id → (tool_name, command|None)."""
    out: Dict[str, Tuple[str, Optional[str]]] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        tcs = msg.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            tc_id = str(tc.get("id") or "")
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = str((fn or {}).get("name") or "")
            args = _parse_args((fn or {}).get("arguments"))
            cmd = None
            if name == "terminal":
                cmd = str(args.get("command") or args.get("cmd") or "") or None
            if tc_id:
                out[tc_id] = (name, cmd)
    return out


def profile_api_request_shadow(
    messages: Sequence[Mapping[str, Any]],
    *,
    tools: Optional[Sequence[Mapping[str, Any]]] = None,
    session_id: str = "",
    api_call_index: int = 0,
    recent_turn_budget_tokens: int = 20_000,
    working_memory_budget_tokens: int = 2_000,
    safe_summary_tokens: int = 64,
) -> Dict[str, Any]:
    """Estimate legacy vs V2 attended tokens without mutating ``messages``.

    V2 estimate (P1 heuristic — no real WM/archive yet):

    * L1 = system + tool schemas
    * L2 = working_memory_budget (assumed filled)
    * L3 = messages kept while walking from the end until recent budget fills
    * L4 = VERIFY/MUTATING tool bodies not already counted in L3 (pins)
    * SAFE tool bodies outside L3 count as ``safe_summary_tokens`` only
    * DELEGATE outside L3 counts as summary (raw archived)
    """
    from agent.model_metadata import _estimate_tools_tokens_rough

    call_index = _index_tool_calls(messages)

    system_chars = 0
    rest: List[Tuple[int, Mapping[str, Any], int]] = []  # (idx, msg, chars)
    for i, msg in enumerate(messages):
        chars = _message_chars(msg)
        if msg.get("role") == "system" and system_chars == 0:
            system_chars = chars
            continue
        rest.append((i, msg, chars))

    tools_list = list(tools or [])
    tools_tokens = _estimate_tools_tokens_rough(tools_list) if tools_list else 0
    system_tokens = _tokens_from_chars(system_chars)

    legacy_msg_tokens = system_tokens + sum(_tokens_from_chars(c) for _, _, c in rest)
    legacy_attended = legacy_msg_tokens + tools_tokens

    # Classify tool rows
    safe_count = verify_count = mutating_count = delegate_count = 0
    safe_chars = verify_chars = mutating_chars = delegate_chars = 0
    tool_rows: List[Dict[str, Any]] = []

    assistant_indices = [
        idx for idx, msg, _ in rest if msg.get("role") == "assistant"
    ]

    for pos, (idx, msg, chars) in enumerate(rest):
        if msg.get("role") != "tool":
            continue
        tc_id = str(msg.get("tool_call_id") or "")
        name = str(msg.get("tool_name") or "")
        cmd = None
        if tc_id and tc_id in call_index:
            name = name or call_index[tc_id][0]
            cmd = call_index[tc_id][1]
        ev = classify_evidence(name, cmd)
        subsequent = sum(1 for aidx in assistant_indices if aidx > idx)
        row = {
            "index": idx,
            "tool_name": name,
            "evidence_class": ev.value,
            "chars": chars,
            "tokens_est": _tokens_from_chars(chars),
            "subsequent_assistant_msgs": subsequent,
            "replay_char_x_calls": chars * subsequent,
        }
        tool_rows.append(row)
        if ev is EvidenceClass.SAFE:
            safe_count += 1
            safe_chars += chars
        elif ev is EvidenceClass.VERIFY:
            verify_count += 1
            verify_chars += chars
        elif ev is EvidenceClass.MUTATING:
            mutating_count += 1
            mutating_chars += chars
        elif ev is EvidenceClass.DELEGATE:
            delegate_count += 1
            delegate_chars += chars

    # Walk from end for L3 recent window
    recent_idxs: set[int] = set()
    recent_tokens = 0
    for idx, msg, chars in reversed(rest):
        tok = _tokens_from_chars(chars)
        if recent_tokens + tok > recent_turn_budget_tokens and recent_idxs:
            break
        recent_idxs.add(idx)
        recent_tokens += tok

    l3_tokens = 0
    l4_tokens = 0
    l5_summary_tokens = 0
    safe_chars_archived = 0
    archived_safe_count = 0

    for idx, msg, chars in rest:
        tok = _tokens_from_chars(chars)
        if idx in recent_idxs:
            l3_tokens += tok
            continue
        if msg.get("role") != "tool":
            # Old dialogue outside recent window — not attended in V2 estimate
            continue
        tc_id = str(msg.get("tool_call_id") or "")
        name = str(msg.get("tool_name") or "")
        cmd = None
        if tc_id and tc_id in call_index:
            name = name or call_index[tc_id][0]
            cmd = call_index[tc_id][1]
        ev = classify_evidence(name, cmd)
        if ev in {EvidenceClass.MUTATING, EvidenceClass.VERIFY}:
            l4_tokens += tok
        elif ev in {EvidenceClass.SAFE, EvidenceClass.DELEGATE}:
            l5_summary_tokens += safe_summary_tokens
            safe_chars_archived += chars
            archived_safe_count += 1
        else:
            # OTHER → pin conservatively
            l4_tokens += tok

    l2 = max(0, int(working_memory_budget_tokens))
    # Layered attend set before the WM placeholder. On short transcripts WM
    # alone can make full v2 > legacy; layering savings are still real.
    v2_ex_wm = (
        system_tokens
        + tools_tokens
        + l3_tokens
        + l4_tokens
        + l5_summary_tokens
    )
    v2_attended = v2_ex_wm + l2

    layering_savings = max(0, legacy_attended - v2_ex_wm)
    layering_savings_pct = (
        round(100.0 * layering_savings / legacy_attended, 1)
        if legacy_attended
        else 0.0
    )
    net_vs_legacy = legacy_attended - v2_attended  # may be negative early on

    return {
        "ts": time.time(),
        "session_id": session_id or "",
        "api_call_index": api_call_index,
        "message_count": len(messages),
        "legacy_attended_tokens": legacy_attended,
        "v2_attended_tokens": v2_attended,
        "v2_attended_tokens_ex_wm": v2_ex_wm,
        "estimated_savings_tokens": layering_savings,
        "estimated_savings_pct": layering_savings_pct,
        "net_vs_legacy_tokens": net_vs_legacy,
        "layers": {
            "l1_system_tokens": system_tokens,
            "l1_tools_tokens": tools_tokens,
            "l2_working_memory_tokens": l2,
            "l3_recent_tokens": l3_tokens,
            "l4_pinned_tokens": l4_tokens,
            "l5_summary_tokens": l5_summary_tokens,
        },
        "tool_trace": {
            "safe_count": safe_count,
            "verify_count": verify_count,
            "mutating_count": mutating_count,
            "delegate_count": delegate_count,
            "safe_chars": safe_chars,
            "verify_chars": verify_chars,
            "mutating_chars": mutating_chars,
            "delegate_chars": delegate_chars,
            "safe_chars_archived_est": safe_chars_archived,
            "safe_archived_count": archived_safe_count,
            "replay_char_x_calls_total": sum(
                r["replay_char_x_calls"] for r in tool_rows
            ),
            "replay_char_x_calls_safe": sum(
                r["replay_char_x_calls"]
                for r in tool_rows
                if r["evidence_class"] == EvidenceClass.SAFE.value
            ),
        },
        "budgets": {
            "recent_turn_budget_tokens": recent_turn_budget_tokens,
            "working_memory_budget_tokens": working_memory_budget_tokens,
            "safe_summary_tokens": safe_summary_tokens,
        },
        "shadow": True,
        "mutates_prompt": False,
    }


def write_shadow_profile_record(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(dict(record), ensure_ascii=False, default=str) + "\n")


def _load_shadow_config() -> Dict[str, Any]:
    """Read ``context_engineering_v2.shadow_profiler`` from user config."""
    defaults = {
        "enabled": False,
        "recent_turn_budget_tokens": 20_000,
        "working_memory_budget_tokens": 2_000,
        "safe_summary_tokens": 64,
        "log_filename": "context_engineering_v2_shadow.jsonl",
    }
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        section = cfg.get("context_engineering_v2") or {}
        shadow = section.get("shadow_profiler") or {}
        if not isinstance(shadow, dict):
            return defaults
        out = dict(defaults)
        out.update({k: shadow[k] for k in defaults if k in shadow})
        return out
    except Exception:
        return defaults


def shadow_log_path(log_filename: str | None = None) -> Path:
    from hermes_constants import get_hermes_home

    name = log_filename or "context_engineering_v2_shadow.jsonl"
    return get_hermes_home() / "logs" / name


def maybe_log_shadow_profile(
    *,
    api_messages: Sequence[Mapping[str, Any]],
    tools: Optional[Sequence[Mapping[str, Any]]],
    session_id: str,
    api_call_index: int,
    config: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """If enabled, write one shadow profile line. Never raises. Never mutates."""
    try:
        cfg = dict(config) if config is not None else _load_shadow_config()
        if not cfg.get("enabled"):
            return None
        record = profile_api_request_shadow(
            api_messages,
            tools=tools,
            session_id=session_id,
            api_call_index=api_call_index,
            recent_turn_budget_tokens=int(cfg.get("recent_turn_budget_tokens") or 20_000),
            working_memory_budget_tokens=int(
                cfg.get("working_memory_budget_tokens") or 2_000
            ),
            safe_summary_tokens=int(cfg.get("safe_summary_tokens") or 64),
        )
        path = shadow_log_path(str(cfg.get("log_filename") or ""))
        write_shadow_profile_record(path, record)
        return record
    except Exception:
        logger.debug("context_engineering_v2 shadow profiler failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# P2 — Working Memory (dark store + fail-open assemble stub)
# ---------------------------------------------------------------------------


@dataclass
class WorkingMemory:
    """Live engineering state for the current objective (Layer 2).

    Hard budget is enforced by ``trim_working_memory_to_budget``. Never put
    this object into the stable system prefix (Layer 1).
    """

    objective: str = ""
    hypothesis: str = ""
    decisions: List[str] = field(default_factory=list)
    active_files: List[Dict[str, str]] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    branch: str = ""
    open_questions: List[str] = field(default_factory=list)
    mutation_epoch: int = 0
    last_updated_api_call: int = 0
    schema_version: int = _WM_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, default=str)

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> "WorkingMemory":
        if not data:
            return cls()
        active = data.get("active_files") or []
        files: List[Dict[str, str]] = []
        if isinstance(active, list):
            for item in active:
                if isinstance(item, Mapping) and item.get("path"):
                    files.append(
                        {
                            "path": str(item.get("path") or ""),
                            "intent": str(item.get("intent") or ""),
                        }
                    )
                elif isinstance(item, str) and item.strip():
                    files.append({"path": item.strip(), "intent": ""})
        return cls(
            objective=str(data.get("objective") or ""),
            hypothesis=str(data.get("hypothesis") or ""),
            decisions=[str(x) for x in (data.get("decisions") or []) if str(x).strip()],
            active_files=files,
            blockers=[str(x) for x in (data.get("blockers") or []) if str(x).strip()],
            branch=str(data.get("branch") or ""),
            open_questions=[
                str(x) for x in (data.get("open_questions") or []) if str(x).strip()
            ],
            mutation_epoch=int(data.get("mutation_epoch") or 0),
            last_updated_api_call=int(data.get("last_updated_api_call") or 0),
            schema_version=int(data.get("schema_version") or _WM_SCHEMA_VERSION),
        )

    @classmethod
    def from_json(cls, raw: str) -> "WorkingMemory":
        return cls.from_dict(json.loads(raw))


def working_memory_meta_key(session_id: str) -> str:
    return f"{_WM_META_PREFIX}{session_id}"


def estimate_working_memory_tokens(wm: WorkingMemory) -> int:
    return max(1, len(wm.to_json()) // _CHARS_PER_TOKEN) if wm.to_json() else 0


def trim_working_memory_to_budget(
    wm: WorkingMemory,
    budget_tokens: int = _DEFAULT_WM_BUDGET_TOKENS,
) -> WorkingMemory:
    """Drop lowest-priority fields first; never drop objective or open pins."""
    out = WorkingMemory.from_dict(wm.to_dict())
    budget = max(64, int(budget_tokens or _DEFAULT_WM_BUDGET_TOKENS))

    def _ok() -> bool:
        return estimate_working_memory_tokens(out) <= budget

    if _ok():
        return out

    # 1) open_questions
    while out.open_questions and not _ok():
        out.open_questions.pop()

    # 2) verbose hypothesis
    while len(out.hypothesis) > 80 and not _ok():
        out.hypothesis = out.hypothesis[: max(40, len(out.hypothesis) // 2)].rstrip()

    # 3) oldest decisions
    while len(out.decisions) > 2 and not _ok():
        out.decisions.pop(0)

    # 4) blockers (keep newest)
    while len(out.blockers) > 1 and not _ok():
        out.blockers.pop(0)

    # 5) trim active_files intents / drop oldest files last (never all if epoch open)
    for af in out.active_files:
        if _ok():
            break
        if len(af.get("intent") or "") > 40:
            af["intent"] = (af.get("intent") or "")[:40]
    while len(out.active_files) > 1 and not _ok():
        out.active_files.pop(0)

    # 6) last resort — truncate objective (keep non-empty)
    while len(out.objective) > 40 and not _ok():
        out.objective = out.objective[: max(40, len(out.objective) // 2)].rstrip()

    return out


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, Mapping):
                if block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                elif "text" in block:
                    parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def _tool_args(tc: Mapping[str, Any]) -> Dict[str, Any]:
    fn = tc.get("function") if isinstance(tc.get("function"), Mapping) else tc
    raw = ""
    if isinstance(fn, Mapping):
        raw = fn.get("arguments") or ""
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _tool_name(tc: Mapping[str, Any]) -> str:
    fn = tc.get("function") if isinstance(tc.get("function"), Mapping) else None
    if isinstance(fn, Mapping):
        return str(fn.get("name") or "")
    return str(tc.get("name") or "")


def _path_from_tool_args(name: str, args: Mapping[str, Any]) -> str:
    for key in ("path", "file_path", "filepath", "filename", "target"):
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    if name == "patch":
        # common patch shapes
        for key in ("file", "files"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, list) and val:
                first = val[0]
                if isinstance(first, str):
                    return first
                if isinstance(first, Mapping) and first.get("path"):
                    return str(first["path"])
    return ""


def fold_working_memory_from_messages(
    wm: WorkingMemory,
    messages: Sequence[Mapping[str, Any]],
    *,
    api_call_index: int = 0,
) -> WorkingMemory:
    """Deterministic fold of recent transcript into Working Memory.

    Primary author for P2 (architecture §12 #1). No aux-LLM calls.
    """
    out = WorkingMemory.from_dict(wm.to_dict())
    out.last_updated_api_call = int(api_call_index or out.last_updated_api_call)

    # Seed / refresh objective from the latest non-empty user turn.
    for msg in reversed(list(messages)):
        if msg.get("role") != "user":
            continue
        text = _message_text(msg.get("content")).strip()
        if not text:
            continue
        # Skip synthetic / slash-noise that is not an objective.
        if text.startswith("/") and len(text.split()) == 1:
            continue
        candidate = text.splitlines()[0].strip()
        if len(candidate) > _MAX_OBJECTIVE_CHARS:
            candidate = candidate[:_MAX_OBJECTIVE_CHARS].rstrip() + "…"
        if candidate and (
            not out.objective
            or (
                candidate.lower() not in out.objective.lower()
                and out.objective.lower() not in candidate.lower()
            )
        ):
            # On clear topic shift, keep prior objective as a decision crumb.
            if out.objective and out.objective != candidate:
                note = f"prior objective: {out.objective}"
                if note not in out.decisions:
                    out.decisions.append(note)
                    if len(out.decisions) > _MAX_DECISIONS:
                        out.decisions = out.decisions[-_MAX_DECISIONS:]
            out.objective = candidate
        elif not out.objective:
            out.objective = candidate
        break

    # Track mutating file paths from assistant tool_calls.
    saw_mutate = False
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        tcs = msg.get("tool_calls") or []
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            if not isinstance(tc, Mapping):
                continue
            name = _tool_name(tc)
            args = _tool_args(tc)
            cmd = args.get("command") if isinstance(args.get("command"), str) else None
            ev = classify_evidence(name, command=cmd)
            if ev != EvidenceClass.MUTATING:
                continue
            saw_mutate = True
            path = _path_from_tool_args(name, args)
            if not path:
                continue
            intent = f"{name}"
            # Upsert by path.
            updated = False
            for af in out.active_files:
                if af.get("path") == path:
                    af["intent"] = intent
                    updated = True
                    break
            if not updated:
                out.active_files.append({"path": path, "intent": intent})
            if len(out.active_files) > _MAX_ACTIVE_FILES:
                out.active_files = out.active_files[-_MAX_ACTIVE_FILES:]

    if saw_mutate and out.mutation_epoch <= 0:
        out.mutation_epoch = 1
    elif saw_mutate:
        # Bump only when we observe a new mutate after a quiet gap is hard
        # without pin state (P4). Keep epoch sticky at >=1 for P2 dark.
        out.mutation_epoch = max(1, out.mutation_epoch)

    if not out.objective:
        out.objective = "(unspecified)"

    return out


def load_working_memory(
    session_id: str,
    *,
    session_db: Any = None,
) -> Optional[WorkingMemory]:
    if not session_id or session_db is None:
        return None
    try:
        raw = session_db.get_meta(working_memory_meta_key(session_id))
    except Exception:
        logger.debug("working_memory get_meta failed", exc_info=True)
        return None
    if not raw:
        return None
    try:
        return WorkingMemory.from_json(raw)
    except Exception:
        logger.debug("working_memory parse failed", exc_info=True)
        return None


def save_working_memory(
    session_id: str,
    wm: WorkingMemory,
    *,
    session_db: Any = None,
) -> bool:
    if not session_id or session_db is None or wm is None:
        return False
    try:
        session_db.set_meta(working_memory_meta_key(session_id), wm.to_json())
        return True
    except Exception:
        logger.debug("working_memory set_meta failed", exc_info=True)
        return False


def assemble_layered_messages_dark(
    legacy_messages: Sequence[Mapping[str, Any]],
    *,
    working_memory: Optional[WorkingMemory] = None,
) -> List[Dict[str, Any]]:
    """P2 dark assemble stub — always returns a shallow copy of legacy."""
    _ = working_memory
    return [dict(m) for m in legacy_messages]


def _load_working_memory_config() -> Dict[str, Any]:
    defaults = {
        "enabled": False,
        "budget_tokens": _DEFAULT_WM_BUDGET_TOKENS,
        "persist": True,
    }
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        section = cfg.get("context_engineering_v2") or {}
        wm = section.get("working_memory") or {}
        if not isinstance(wm, dict):
            return defaults
        out = dict(defaults)
        out.update({k: wm[k] for k in defaults if k in wm})
        return out
    except Exception:
        return defaults


def maybe_touch_working_memory(
    *,
    api_messages: Sequence[Mapping[str, Any]],
    session_id: str,
    api_call_index: int,
    session_db: Any = None,
    config: Optional[Mapping[str, Any]] = None,
) -> Optional[WorkingMemory]:
    """Load → fold → trim → persist WM. Never mutates ``api_messages``.

    Fail-open: any exception returns None. Dark assemble is a no-op on the
    live prompt (callers may still stash the returned WM on the agent).
    """
    try:
        cfg = dict(config) if config is not None else _load_working_memory_config()
        if not cfg.get("enabled"):
            return None
        budget = int(cfg.get("budget_tokens") or _DEFAULT_WM_BUDGET_TOKENS)
        existing = load_working_memory(session_id, session_db=session_db)
        base = existing or WorkingMemory()
        folded = fold_working_memory_from_messages(
            base,
            api_messages,
            api_call_index=api_call_index,
        )
        trimmed = trim_working_memory_to_budget(folded, budget_tokens=budget)
        # Prove dark assemble path is wired without changing the prompt.
        _ = assemble_layered_messages_dark(api_messages, working_memory=trimmed)
        if cfg.get("persist", True) and session_db is not None and session_id:
            save_working_memory(session_id, trimmed, session_db=session_db)
        return trimmed
    except Exception:
        logger.debug("context_engineering_v2 working_memory touch failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# P3 — SAFE summarise → archive (shadow; wire prompt unchanged)
# ---------------------------------------------------------------------------


@dataclass
class ArchiveEntry:
    archive_id: str
    kind: str
    evidence_class: str
    created_api_call: int
    summary: str
    raw_ref: str
    tokens_raw: int
    tokens_summary: int
    tool_name: str = ""
    tool_call_id: str = ""
    message_index: int = -1
    command: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ArchiveEntry":
        return cls(
            archive_id=str(data.get("archive_id") or ""),
            kind=str(data.get("kind") or ""),
            evidence_class=str(data.get("evidence_class") or EvidenceClass.SAFE.value),
            created_api_call=int(data.get("created_api_call") or 0),
            summary=str(data.get("summary") or ""),
            raw_ref=str(data.get("raw_ref") or ""),
            tokens_raw=int(data.get("tokens_raw") or 0),
            tokens_summary=int(data.get("tokens_summary") or 0),
            tool_name=str(data.get("tool_name") or ""),
            tool_call_id=str(data.get("tool_call_id") or ""),
            message_index=int(data.get("message_index") or -1),
            command=str(data.get("command") or ""),
        )


def archive_meta_key(session_id: str) -> str:
    return f"{_ARCHIVE_META_PREFIX}{session_id}"


def archive_blob_dir(session_id: str, hermes_home: Optional[Path] = None) -> Path:
    if hermes_home is None:
        from hermes_constants import get_hermes_home

        hermes_home = get_hermes_home()
    return Path(hermes_home) / "context_archive" / session_id


def make_archive_id(session_id: str, tool_call_id: str, content: str) -> str:
    seed = f"{session_id}|{tool_call_id}|{hashlib.sha1(content.encode('utf-8', errors='replace')).hexdigest()[:12]}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    return f"tr_{digest}"


def summarise_safe_tool_result(
    *,
    tool_name: str,
    command: Optional[str],
    content: Any,
    max_chars: int = _DEFAULT_ARCHIVE_SUMMARY_MAX_CHARS,
) -> str:
    """Deterministic SAFE summary — crumbs only, never the raw dump."""
    text = _message_text(content)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    line_count = len(lines)
    findings: List[str] = []

    label = (command or tool_name or "tool").strip()
    if len(label) > 80:
        label = label[:77] + "…"

    paths: List[str] = []
    for ln in lines[:80]:
        for m in _PATHISH.finditer(ln):
            p = m.group(1)
            if p not in paths and len(p) < 120:
                paths.append(p)
            if len(paths) >= 5:
                break
        if len(paths) >= 5:
            break
    if paths:
        findings.append("paths: " + ", ".join(paths[:5]))

    err_hits = [ln.strip() for ln in lines if _ERRORISH.search(ln)]
    if err_hits:
        findings.append("signal: " + err_hits[0][:100])

    # Lightweight listing / JSON cues
    joined_lower = "\n".join(lines[:30]).lower()
    for cue in ("package.json", "src/", "pyproject.toml", "cargo.toml", "go.mod"):
        if cue in joined_lower and cue not in " ".join(findings).lower():
            findings.append(f"found {cue.rstrip('/')}")

    if not findings and lines:
        preview = lines[0].strip()
        if len(preview) > 100:
            preview = preview[:97] + "…"
        findings.append(f"first line: {preview}")

    findings.append(f"{line_count} lines / {len(text)} chars")

    body = f"{label} inspected.\nKey findings:\n" + "\n".join(f"- {f}" for f in findings[:6])
    if len(body) > max_chars:
        body = body[: max(0, max_chars - 1)].rstrip() + "…"
    return body


def build_archive_summary(
    *,
    archive_id: str,
    tool_name: str,
    command: Optional[str],
    content: Any,
    max_chars: int = _DEFAULT_ARCHIVE_SUMMARY_MAX_CHARS,
) -> str:
    inner_budget = max(64, int(max_chars) - len(archive_id) - 24)
    crumbs = summarise_safe_tool_result(
        tool_name=tool_name,
        command=command,
        content=content,
        max_chars=inner_budget,
    )
    text = (
        f"[archived:{archive_id}] {crumbs}\n"
        f"Retrieve with context_archive(id={archive_id}) if raw needed."
    )
    if len(text) > max_chars:
        text = text[: max(0, max_chars - 1)].rstrip() + "…"
    return text


def load_archive_index(
    session_id: str,
    *,
    session_db: Any = None,
) -> List[ArchiveEntry]:
    if not session_id or session_db is None:
        return []
    try:
        raw = session_db.get_meta(archive_meta_key(session_id))
    except Exception:
        return []
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out: List[ArchiveEntry] = []
    for item in data:
        if isinstance(item, Mapping):
            try:
                out.append(ArchiveEntry.from_dict(item))
            except Exception:
                continue
    return out


def save_archive_index(
    session_id: str,
    entries: Sequence[ArchiveEntry],
    *,
    session_db: Any = None,
) -> bool:
    if not session_id or session_db is None:
        return False
    try:
        payload = json.dumps([e.to_dict() for e in entries], ensure_ascii=False)
        session_db.set_meta(archive_meta_key(session_id), payload)
        return True
    except Exception:
        logger.debug("archive index set_meta failed", exc_info=True)
        return False


def _recent_message_indices(
    messages: Sequence[Mapping[str, Any]],
    recent_turn_budget_tokens: int,
) -> set[int]:
    """Mirror P1 L3 walk: indices kept in the recent-turn window."""
    rest: List[Tuple[int, int]] = []
    seen_system = False
    for i, msg in enumerate(messages):
        if msg.get("role") == "system" and not seen_system:
            seen_system = True
            continue
        rest.append((i, _message_chars(msg)))
    recent: set[int] = set()
    used = 0
    budget = max(0, int(recent_turn_budget_tokens))
    for idx, chars in reversed(rest):
        tok = _tokens_from_chars(chars)
        if used + tok > budget and recent:
            break
        recent.add(idx)
        used += tok
    return recent


def shadow_archive_safe_tools(
    messages: Sequence[Mapping[str, Any]],
    *,
    session_id: str,
    api_call_index: int = 0,
    session_db: Any = None,
    recent_turn_budget_tokens: int = 20_000,
    min_chars: int = _DEFAULT_ARCHIVE_MIN_CHARS,
    summary_max_chars: int = _DEFAULT_ARCHIVE_SUMMARY_MAX_CHARS,
    hermes_home: Optional[Path] = None,
) -> Dict[str, Any]:
    """Create SAFE/DELEGATE archive entries for tool bodies outside L3.

    Shadow only: does not mutate ``messages``. Idempotent on tool_call_id.
    """
    existing = load_archive_index(session_id, session_db=session_db)
    by_tc = {e.tool_call_id: e for e in existing if e.tool_call_id}
    call_index = _index_tool_calls(messages)
    recent = _recent_message_indices(messages, recent_turn_budget_tokens)

    blob_root = archive_blob_dir(session_id, hermes_home=hermes_home)
    blob_root.mkdir(parents=True, exist_ok=True)

    new_entries: List[ArchiveEntry] = []
    reused = 0
    skipped_small = 0
    skipped_class = 0

    for idx, msg in enumerate(messages):
        if msg.get("role") != "tool":
            continue
        if idx in recent:
            continue
        tc_id = str(msg.get("tool_call_id") or "")
        name = str(msg.get("tool_name") or "")
        cmd = None
        if tc_id and tc_id in call_index:
            name = name or call_index[tc_id][0]
            cmd = call_index[tc_id][1]
        ev = classify_evidence(name, cmd)
        if ev not in {EvidenceClass.SAFE, EvidenceClass.DELEGATE}:
            skipped_class += 1
            continue
        raw_text = _message_text(msg.get("content"))
        if len(raw_text) < int(min_chars):
            skipped_small += 1
            continue
        if tc_id and tc_id in by_tc:
            reused += 1
            continue

        archive_id = make_archive_id(session_id or "none", tc_id or str(idx), raw_text)
        summary = build_archive_summary(
            archive_id=archive_id,
            tool_name=name,
            command=cmd,
            content=raw_text,
            max_chars=int(summary_max_chars),
        )
        blob_path = blob_root / f"{archive_id}.txt"
        if not blob_path.exists():
            blob_path.write_text(raw_text, encoding="utf-8")
        entry = ArchiveEntry(
            archive_id=archive_id,
            kind=name or "tool",
            evidence_class=ev.value,
            created_api_call=int(api_call_index),
            summary=summary,
            raw_ref=str(blob_path),
            tokens_raw=_tokens_from_chars(len(raw_text)),
            tokens_summary=_tokens_from_chars(len(summary)),
            tool_name=name,
            tool_call_id=tc_id,
            message_index=idx,
            command=cmd or "",
        )
        new_entries.append(entry)
        if tc_id:
            by_tc[tc_id] = entry

    if new_entries and session_db is not None and session_id:
        merged = list(existing) + new_entries
        save_archive_index(session_id, merged, session_db=session_db)

    all_entries = list(existing) + new_entries
    return {
        "archived_new": len(new_entries),
        "archived_existing": reused,
        "skipped_small": skipped_small,
        "skipped_class": skipped_class,
        "entries": new_entries,
        "index_size": len(all_entries),
        "archives_by_tool_call_id": {
            e.tool_call_id: e for e in all_entries if e.tool_call_id
        },
    }


def estimate_attended_with_real_archives(
    messages: Sequence[Mapping[str, Any]],
    *,
    tools: Optional[Sequence[Mapping[str, Any]]] = None,
    archives_by_tool_call_id: Optional[Mapping[str, ArchiveEntry]] = None,
    recent_turn_budget_tokens: int = 20_000,
    working_memory_budget_tokens: int = 0,
) -> Dict[str, Any]:
    """Attended estimate using real archive summary lengths for SAFE outside L3."""
    from agent.model_metadata import _estimate_tools_tokens_rough

    archives = archives_by_tool_call_id or {}
    call_index = _index_tool_calls(messages)
    recent = _recent_message_indices(messages, recent_turn_budget_tokens)

    system_chars = 0
    rest: List[Tuple[int, Mapping[str, Any], int]] = []
    for i, msg in enumerate(messages):
        chars = _message_chars(msg)
        if msg.get("role") == "system" and system_chars == 0:
            system_chars = chars
            continue
        rest.append((i, msg, chars))

    tools_list = list(tools or [])
    tools_tokens = _estimate_tools_tokens_rough(tools_list) if tools_list else 0
    system_tokens = _tokens_from_chars(system_chars)
    legacy = system_tokens + sum(_tokens_from_chars(c) for _, _, c in rest) + tools_tokens

    l3 = l4 = l5 = 0
    archived_safe = 0
    raw_chars_archived = 0
    for idx, msg, chars in rest:
        tok = _tokens_from_chars(chars)
        if idx in recent:
            l3 += tok
            continue
        if msg.get("role") != "tool":
            continue
        tc_id = str(msg.get("tool_call_id") or "")
        name = str(msg.get("tool_name") or "")
        cmd = None
        if tc_id and tc_id in call_index:
            name = name or call_index[tc_id][0]
            cmd = call_index[tc_id][1]
        ev = classify_evidence(name, cmd)
        if ev in {EvidenceClass.MUTATING, EvidenceClass.VERIFY, EvidenceClass.OTHER}:
            l4 += tok
            continue
        # SAFE / DELEGATE → summary tokens if archived, else full (fail-open)
        entry = archives.get(tc_id) if tc_id else None
        if entry is not None:
            l5 += int(entry.tokens_summary)
            archived_safe += 1
            raw_chars_archived += chars
        else:
            l4 += tok  # not yet archived — keep full (conservative)

    l2 = max(0, int(working_memory_budget_tokens))
    v2_ex = system_tokens + tools_tokens + l3 + l4 + l5
    return {
        "legacy_attended_tokens": legacy,
        "v2_attended_tokens_ex_wm": v2_ex,
        "v2_attended_tokens": v2_ex + l2,
        "estimated_savings_tokens": max(0, legacy - v2_ex),
        "l3_recent_tokens": l3,
        "l4_pinned_tokens": l4,
        "l5_summary_tokens": l5,
        "archived_safe_count": archived_safe,
        "raw_chars_archived": raw_chars_archived,
        "mutates_prompt": False,
        "shadow": True,
        "real_summaries": True,
    }


def _fold_archive_crumbs_into_wm(
    wm: WorkingMemory,
    entries: Sequence[ArchiveEntry],
) -> WorkingMemory:
    """Fold brief SAFE findings into WM without pasting raw logs."""
    out = WorkingMemory.from_dict(wm.to_dict())
    for entry in entries:
        crumb = entry.summary.splitlines()
        # Prefer a single "Key findings" bullet if present.
        bullet = ""
        for ln in crumb:
            if ln.strip().startswith("- "):
                bullet = ln.strip()[2:].strip()
                break
        if not bullet:
            continue
        note = f"SAFE {entry.tool_name or entry.kind}: {bullet}"
        if len(note) > 160:
            note = note[:157] + "…"
        if note not in out.decisions:
            out.decisions.append(note)
            if len(out.decisions) > _MAX_DECISIONS:
                out.decisions = out.decisions[-_MAX_DECISIONS:]
    return out


def _load_safe_archive_config() -> Dict[str, Any]:
    defaults = {
        "shadow_enabled": False,
        "min_chars": _DEFAULT_ARCHIVE_MIN_CHARS,
        "summary_max_chars": _DEFAULT_ARCHIVE_SUMMARY_MAX_CHARS,
        "recent_turn_budget_tokens": 20_000,
        "working_memory_budget_tokens": 0,
        "fold_into_wm": True,
        "log_filename": "context_engineering_v2_archive_shadow.jsonl",
    }
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        section = cfg.get("context_engineering_v2") or {}
        arch = section.get("safe_archive") or {}
        if not isinstance(arch, dict):
            return defaults
        out = dict(defaults)
        out.update({k: arch[k] for k in defaults if k in arch})
        # Inherit recent budget from shadow_profiler when unset in safe_archive.
        if "recent_turn_budget_tokens" not in arch:
            shadow = section.get("shadow_profiler") or {}
            if isinstance(shadow, dict) and "recent_turn_budget_tokens" in shadow:
                out["recent_turn_budget_tokens"] = shadow["recent_turn_budget_tokens"]
        return out
    except Exception:
        return defaults


def archive_shadow_log_path(log_filename: str | None = None) -> Path:
    from hermes_constants import get_hermes_home

    name = log_filename or "context_engineering_v2_archive_shadow.jsonl"
    return get_hermes_home() / "logs" / name


def maybe_run_safe_archive_shadow(
    *,
    api_messages: Sequence[Mapping[str, Any]],
    session_id: str,
    api_call_index: int,
    session_db: Any = None,
    tools: Optional[Sequence[Mapping[str, Any]]] = None,
    working_memory: Optional[WorkingMemory] = None,
    config: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Shadow SAFE archive pass. Never mutates ``api_messages``. Fail-open."""
    try:
        cfg = dict(config) if config is not None else _load_safe_archive_config()
        if not cfg.get("shadow_enabled"):
            return None
        result = shadow_archive_safe_tools(
            api_messages,
            session_id=session_id,
            api_call_index=api_call_index,
            session_db=session_db,
            recent_turn_budget_tokens=int(cfg.get("recent_turn_budget_tokens") or 20_000),
            min_chars=int(cfg.get("min_chars") or _DEFAULT_ARCHIVE_MIN_CHARS),
            summary_max_chars=int(
                cfg.get("summary_max_chars") or _DEFAULT_ARCHIVE_SUMMARY_MAX_CHARS
            ),
        )
        archives = result["archives_by_tool_call_id"]
        attended = estimate_attended_with_real_archives(
            api_messages,
            tools=tools,
            archives_by_tool_call_id=archives,
            recent_turn_budget_tokens=int(cfg.get("recent_turn_budget_tokens") or 20_000),
            working_memory_budget_tokens=int(
                cfg.get("working_memory_budget_tokens") or 0
            ),
        )
        wm_out = working_memory
        if (
            cfg.get("fold_into_wm")
            and working_memory is not None
            and result["entries"]
            and session_db is not None
            and session_id
        ):
            wm_out = _fold_archive_crumbs_into_wm(working_memory, result["entries"])
            wm_out = trim_working_memory_to_budget(
                wm_out,
                budget_tokens=_DEFAULT_WM_BUDGET_TOKENS,
            )
            save_working_memory(session_id, wm_out, session_db=session_db)

        record = {
            "ts": time.time(),
            "session_id": session_id or "",
            "api_call_index": api_call_index,
            "archived_new": result["archived_new"],
            "archived_existing": result["archived_existing"],
            "index_size": result["index_size"],
            "skipped_small": result["skipped_small"],
            "mutates_prompt": False,
            "shadow": True,
            **attended,
            "new_archive_ids": [e.archive_id for e in result["entries"]],
        }
        path = archive_shadow_log_path(str(cfg.get("log_filename") or ""))
        write_shadow_profile_record(path, record)
        record["_working_memory"] = wm_out
        return record
    except Exception:
        logger.debug("context_engineering_v2 safe_archive shadow failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# P4 — MUTATING pin / unpin epoch (dark; wire prompt unchanged)
# ---------------------------------------------------------------------------


@dataclass
class PinnedEvidence:
    tool_call_id: str
    tool_name: str
    evidence_class: str
    mutation_epoch: int
    message_index: int
    chars: int
    tokens_est: int
    path: str = ""
    command: str = ""
    verify_outcome: str = ""  # success | failure | ""
    pinned_at_api_call: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PinnedEvidence":
        return cls(
            tool_call_id=str(data.get("tool_call_id") or ""),
            tool_name=str(data.get("tool_name") or ""),
            evidence_class=str(data.get("evidence_class") or ""),
            mutation_epoch=int(data.get("mutation_epoch") or 0),
            message_index=int(data.get("message_index") or -1),
            chars=int(data.get("chars") or 0),
            tokens_est=int(data.get("tokens_est") or 0),
            path=str(data.get("path") or ""),
            command=str(data.get("command") or ""),
            verify_outcome=str(data.get("verify_outcome") or ""),
            pinned_at_api_call=int(data.get("pinned_at_api_call") or 0),
        )


@dataclass
class PinSet:
    """Open mutation-epoch pin set (Layer 4 state)."""

    open_epoch: int = 0
    mutation_epoch_counter: int = 0
    pins: List[PinnedEvidence] = field(default_factory=list)
    last_closed_epoch: int = 0
    last_close_reason: str = ""
    last_updated_api_call: int = 0
    schema_version: int = _PIN_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "open_epoch": self.open_epoch,
            "mutation_epoch_counter": self.mutation_epoch_counter,
            "pins": [p.to_dict() for p in self.pins],
            "last_closed_epoch": self.last_closed_epoch,
            "last_close_reason": self.last_close_reason,
            "last_updated_api_call": self.last_updated_api_call,
            "schema_version": self.schema_version,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Optional[Mapping[str, Any]]) -> "PinSet":
        if not data:
            return cls()
        pins_raw = data.get("pins") or []
        pins: List[PinnedEvidence] = []
        if isinstance(pins_raw, list):
            for item in pins_raw:
                if isinstance(item, Mapping):
                    try:
                        pins.append(PinnedEvidence.from_dict(item))
                    except Exception:
                        continue
        return cls(
            open_epoch=int(data.get("open_epoch") or 0),
            mutation_epoch_counter=int(data.get("mutation_epoch_counter") or 0),
            pins=pins,
            last_closed_epoch=int(data.get("last_closed_epoch") or 0),
            last_close_reason=str(data.get("last_close_reason") or ""),
            last_updated_api_call=int(data.get("last_updated_api_call") or 0),
            schema_version=int(data.get("schema_version") or _PIN_SCHEMA_VERSION),
        )

    @classmethod
    def from_json(cls, raw: str) -> "PinSet":
        return cls.from_dict(json.loads(raw))

    @property
    def pinned_tokens(self) -> int:
        return sum(int(p.tokens_est) for p in self.pins)

    def pinned_tool_call_ids(self) -> set[str]:
        return {p.tool_call_id for p in self.pins if p.tool_call_id}


def pin_meta_key(session_id: str) -> str:
    return f"{_PIN_META_PREFIX}{session_id}"


def load_pin_set(session_id: str, *, session_db: Any = None) -> Optional[PinSet]:
    if not session_id or session_db is None:
        return None
    try:
        raw = session_db.get_meta(pin_meta_key(session_id))
    except Exception:
        return None
    if not raw:
        return None
    try:
        return PinSet.from_json(raw)
    except Exception:
        logger.debug("pin_set parse failed", exc_info=True)
        return None


def save_pin_set(session_id: str, pins: PinSet, *, session_db: Any = None) -> bool:
    if not session_id or session_db is None or pins is None:
        return False
    try:
        session_db.set_meta(pin_meta_key(session_id), pins.to_json())
        return True
    except Exception:
        logger.debug("pin_set set_meta failed", exc_info=True)
        return False


def _parse_tool_result_payload(content: Any) -> Dict[str, Any]:
    """Best-effort parse of terminal/tool JSON result bodies."""
    if isinstance(content, dict):
        return content
    text = _message_text(content).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        try:
            parsed, _ = json.JSONDecoder().raw_decode(text)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}


def _extract_exit_code(content: Any) -> Optional[int]:
    """Return integer exit_code when the tool result carries a trustworthy one."""
    payload = _parse_tool_result_payload(content)
    if "exit_code" not in payload:
        return None
    raw = payload.get("exit_code")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def detect_verify_outcome(tool_name: str, content: Any) -> Optional[str]:
    """Return ``success`` / ``failure`` for a VERIFY-class tool result.

    When a reliable ``exit_code`` is present (terminal JSON), it is the sole
    signal: ``0`` → success, anything else → failure. Missing exit_code on
    terminal/execute_code is treated as failure (untrustworthy completion).
    Non-terminal tools may still use structured ``success`` flags / text.
    """
    name = (tool_name or "").strip()
    text = _message_text(content)

    if name in {"terminal", "execute_code"} or not name:
        code = _extract_exit_code(content)
        if code is not None:
            return "success" if code == 0 else "failure"
        # No trustworthy completion → failure (keeps pins).
        return "failure"

    if name.startswith(("pytest", "test")):
        code = _extract_exit_code(content)
        if code is not None:
            return "success" if code == 0 else "failure"
        return "failure"

    # Structured non-terminal tools: JSON success flags, then text fallback.
    payload = _parse_tool_result_payload(content)
    if isinstance(payload.get("success"), bool):
        return "success" if payload["success"] else "failure"
    if _VERIFY_FAIL.search(text) and (
        '"success": false' in text.lower() or '"success":false' in text.lower()
    ):
        return "failure"
    if _VERIFY_PASS.search(text) and (
        '"success": true' in text.lower() or '"success":true' in text.lower()
    ):
        return "success"
    return None


def _is_user_abandon(text: str) -> bool:
    return bool(_USER_ABANDON.search(text or ""))


def _close_epoch(state: PinSet, reason: str, api_call_index: int) -> None:
    if state.open_epoch <= 0:
        return
    state.last_closed_epoch = state.open_epoch
    state.last_close_reason = reason
    state.open_epoch = 0
    state.pins = []
    state.last_updated_api_call = int(api_call_index)


def update_pin_epoch_from_messages(
    prior: Optional[PinSet],
    messages: Sequence[Mapping[str, Any]],
    *,
    api_call_index: int = 0,
    working_memory: Optional[WorkingMemory] = None,
) -> Tuple[PinSet, List[str]]:
    """Rebuild pin/epoch state from the transcript (deterministic).

    Pins are **not** TTL'd. Close only on verify success or user abandon.
    Returns ``(pin_set, event_tags)``.
    """
    _ = working_memory  # reserved for future path/blocker coupling
    # Rebuild pin state from the transcript each call (deterministic).
    # ``prior`` is only used to retain last-close telemetry when history was
    # compressed away; epoch numbers are derived from this message walk.
    state = PinSet()
    events: List[str] = []
    call_index = _index_tool_calls(messages)
    seen_tc: set[str] = set()

    for idx, msg in enumerate(messages):
        role = msg.get("role")
        if role == "user":
            text = _message_text(msg.get("content")).strip()
            if state.open_epoch > 0 and _is_user_abandon(text):
                _close_epoch(state, "user_abandon", api_call_index)
                events.append("abandoned")
            continue

        if role != "tool":
            continue

        tc_id = str(msg.get("tool_call_id") or "")
        if tc_id and tc_id in seen_tc:
            continue
        if tc_id:
            seen_tc.add(tc_id)

        name = str(msg.get("tool_name") or "")
        cmd = None
        if tc_id and tc_id in call_index:
            name = name or call_index[tc_id][0]
            cmd = call_index[tc_id][1]
        ev = classify_evidence(name, cmd)
        content = msg.get("content")
        chars = _content_chars(content)
        tokens = _tokens_from_chars(chars)
        path = ""
        # Recover path from the originating assistant tool_call args.
        if tc_id:
            for m in messages:
                if m.get("role") != "assistant":
                    continue
                for tc in m.get("tool_calls") or []:
                    if not isinstance(tc, Mapping):
                        continue
                    if str(tc.get("id") or "") != tc_id:
                        continue
                    path = _path_from_tool_args(name, _tool_args(tc))
                    break

        if ev is EvidenceClass.MUTATING:
            if state.open_epoch <= 0:
                state.mutation_epoch_counter += 1
                state.open_epoch = state.mutation_epoch_counter
                events.append("epoch_opened")
            pin = PinnedEvidence(
                tool_call_id=tc_id,
                tool_name=name,
                evidence_class=ev.value,
                mutation_epoch=state.open_epoch,
                message_index=idx,
                chars=chars,
                tokens_est=tokens,
                path=path,
                command=cmd or "",
                pinned_at_api_call=int(api_call_index),
            )
            state.pins.append(pin)
            events.append("pinned")
            state.last_updated_api_call = int(api_call_index)
            continue

        if ev is EvidenceClass.VERIFY and state.open_epoch > 0:
            outcome = detect_verify_outcome(name, content) or ""
            pin = PinnedEvidence(
                tool_call_id=tc_id,
                tool_name=name,
                evidence_class=ev.value,
                mutation_epoch=state.open_epoch,
                message_index=idx,
                chars=chars,
                tokens_est=tokens,
                path=path,
                command=cmd or "",
                verify_outcome=outcome,
                pinned_at_api_call=int(api_call_index),
            )
            state.pins.append(pin)
            events.append("pinned")
            state.last_updated_api_call = int(api_call_index)
            if outcome == "success":
                _close_epoch(state, "verify_success", api_call_index)
                events.append("verify_success")
            elif outcome == "failure":
                events.append("verify_failure")
            continue

        # SAFE / DELEGATE / OTHER while epoch open: no unpin (pins beat savings).

    if prior and prior.last_closed_epoch and not state.last_closed_epoch:
        # History may have dropped the closed mutate/verify pair (compression).
        if state.open_epoch == 0 and not state.pins:
            state.last_closed_epoch = prior.last_closed_epoch
            state.last_close_reason = prior.last_close_reason
            state.mutation_epoch_counter = max(
                state.mutation_epoch_counter, int(prior.mutation_epoch_counter or 0)
            )

    return state, events


def sync_working_memory_with_pins(
    wm: Optional[WorkingMemory],
    pins: PinSet,
) -> Optional[WorkingMemory]:
    if wm is None:
        return None
    out = WorkingMemory.from_dict(wm.to_dict())
    out.mutation_epoch = int(pins.open_epoch)
    if pins.open_epoch > 0:
        for p in pins.pins:
            if p.path and p.evidence_class == EvidenceClass.MUTATING.value:
                updated = False
                for af in out.active_files:
                    if af.get("path") == p.path:
                        af["intent"] = p.tool_name or af.get("intent") or "mutate"
                        updated = True
                        break
                if not updated:
                    out.active_files.append(
                        {"path": p.path, "intent": p.tool_name or "mutate"}
                    )
        if len(out.active_files) > _MAX_ACTIVE_FILES:
            out.active_files = out.active_files[-_MAX_ACTIVE_FILES:]
        # Surface verify failures as blockers.
        for p in pins.pins:
            if p.verify_outcome == "failure":
                note = f"verify failed: {p.command or p.tool_name}"
                if note not in out.blockers:
                    out.blockers.append(note)
                if len(out.blockers) > 8:
                    out.blockers = out.blockers[-8:]
    elif pins.last_close_reason == "verify_success":
        note = f"mutation epoch {pins.last_closed_epoch} verified"
        if note not in out.decisions:
            out.decisions.append(note)
            if len(out.decisions) > _MAX_DECISIONS:
                out.decisions = out.decisions[-_MAX_DECISIONS:]
        out.blockers = [
            b for b in out.blockers if not str(b).startswith("verify failed:")
        ]
    elif pins.last_close_reason == "user_abandon":
        note = f"mutation epoch {pins.last_closed_epoch} abandoned by user"
        if note not in out.decisions:
            out.decisions.append(note)
    return out


def _load_pin_epoch_config() -> Dict[str, Any]:
    defaults = {
        "enabled": False,
        "persist": True,
        "sync_wm": True,
        "log_filename": "context_engineering_v2_pins_shadow.jsonl",
        # Pin caps / expiry — shadow by default. Observed soak (25 sessions):
        # pin_count p50=6 p90=30; pin_tok p50≈3.6k p90≈10.1k.
        "pin_caps": {
            "shadow_enabled": False,
            "apply_to_dark_store": False,
            "max_pins_per_epoch": 20,
            "max_tokens_per_epoch": 12_000,
            "max_age_api_calls": 50,
            "dedupe_identical_tool_results": True,
            "fail_open_keep_verify": True,
            "log_filename": "context_engineering_v2_pin_caps_shadow.jsonl",
        },
    }
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        section = cfg.get("context_engineering_v2") or {}
        pin = section.get("pin_epoch") or {}
        if not isinstance(pin, dict):
            return defaults
        out = dict(defaults)
        for k in ("enabled", "persist", "sync_wm", "log_filename"):
            if k in pin:
                out[k] = pin[k]
        caps = pin.get("pin_caps")
        if isinstance(caps, dict):
            merged_caps = dict(defaults["pin_caps"])
            merged_caps.update(caps)
            out["pin_caps"] = merged_caps
        return out
    except Exception:
        return defaults


@dataclass
class MutationCheckpoint:
    """Compact durable stand-in for verbose open-epoch pins (shadow/dark)."""

    epoch: int
    objective: str = ""
    files_changed: List[str] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    verification_status: str = "unverified"
    evidence_needed: List[str] = field(default_factory=list)
    compacted_pin_count: int = 0
    compacted_tokens_est: int = 0
    created_at_api_call: int = 0
    kept_pin_ids: List[str] = field(default_factory=list)
    schema_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def checkpoint_meta_key(session_id: str) -> str:
    return f"context_mutation_checkpoint_v2:{session_id}"


def _pin_priority(pin: PinnedEvidence) -> int:
    """Higher = keep longer when capping. VERIFY evidence always wins."""
    name = (pin.tool_name or "").lower()
    if pin.verify_outcome == "success" or pin.evidence_class == EvidenceClass.VERIFY.value:
        return 100
    if pin.verify_outcome == "failure":
        return 95
    if name in {"write_file", "patch", "delete_file"}:
        return 80
    if name == "terminal":
        return 50
    if name.startswith("mcp__"):
        return 20
    return 40


def build_mutation_checkpoint(
    pins: PinSet,
    *,
    working_memory: Optional[WorkingMemory] = None,
    api_call_index: int = 0,
    compacted: Sequence[PinnedEvidence] = (),
    kept: Sequence[PinnedEvidence] = (),
) -> MutationCheckpoint:
    compacted_list = list(compacted)
    kept_list = list(kept)
    files: List[str] = []
    actions: List[str] = []
    for pin in compacted_list:
        if pin.path and pin.path not in files:
            files.append(pin.path)
        label = pin.tool_name or "tool"
        if pin.command:
            label = f"{label}: {pin.command[:120]}"
        actions.append(label)
    objective = ""
    unresolved: List[str] = []
    if working_memory is not None:
        objective = str(working_memory.objective or "")
        unresolved = list(working_memory.blockers or [])[:8]
        for af in working_memory.active_files or []:
            path = str((af or {}).get("path") or "")
            if path and path not in files:
                files.append(path)
    verify_status = "unverified"
    if any(p.verify_outcome == "success" for p in kept_list):
        verify_status = "verify_success_present"
    elif any(p.verify_outcome == "failure" for p in kept_list + compacted_list):
        verify_status = "verify_failed"
    evidence_needed = []
    if verify_status != "verify_success_present" and pins.open_epoch > 0:
        evidence_needed.append(
            "Run the relevant lint/test/check and associate VERIFY with the open epoch"
        )
    return MutationCheckpoint(
        epoch=int(pins.open_epoch or pins.last_closed_epoch or 0),
        objective=objective,
        files_changed=files[:24],
        actions=actions[:40],
        unresolved=unresolved,
        verification_status=verify_status,
        evidence_needed=evidence_needed,
        compacted_pin_count=len(compacted_list),
        compacted_tokens_est=sum(int(p.tokens_est) for p in compacted_list),
        created_at_api_call=int(api_call_index),
        kept_pin_ids=[p.tool_call_id for p in kept_list if p.tool_call_id],
    )


def shadow_apply_pin_caps(
    pins: PinSet,
    *,
    api_call_index: int = 0,
    working_memory: Optional[WorkingMemory] = None,
    caps: Optional[Mapping[str, Any]] = None,
) -> Tuple[PinSet, Optional[MutationCheckpoint], Dict[str, Any]]:
    """Propose (and optionally apply) pin compaction under per-epoch caps.

    Never drops the last VERIFY success/failure evidence when
    ``fail_open_keep_verify`` is true. Returns ``(pins, checkpoint, audit)``.
    """
    cfg = dict(caps or {})
    max_pins = int(cfg.get("max_pins_per_epoch") or 20)
    max_tokens = int(cfg.get("max_tokens_per_epoch") or 12_000)
    max_age = int(cfg.get("max_age_api_calls") or 50)
    dedupe = bool(cfg.get("dedupe_identical_tool_results", True))
    keep_verify = bool(cfg.get("fail_open_keep_verify", True))
    apply = bool(cfg.get("apply_to_dark_store", False))

    audit: Dict[str, Any] = {
        "triggered": False,
        "reasons": [],
        "before_pin_count": len(pins.pins),
        "before_tokens": pins.pinned_tokens,
        "deduped": 0,
        "aged_out": 0,
        "compacted": 0,
        "applied": False,
    }
    if pins.open_epoch <= 0 or not pins.pins:
        return pins, None, audit

    working = list(pins.pins)

    # Deduplicate identical tool dumps (same tool + path/command + token size).
    if dedupe and working:
        seen: Dict[str, PinnedEvidence] = {}
        deduped: List[PinnedEvidence] = []
        for pin in working:
            key = f"{pin.tool_name}|{pin.path}|{pin.command[:80]}|{pin.tokens_est}"
            prev = seen.get(key)
            if prev is None:
                seen[key] = pin
                deduped.append(pin)
            else:
                audit["deduped"] += 1
                # Keep the newer pin (higher api_call / message index).
                if int(pin.pinned_at_api_call) >= int(prev.pinned_at_api_call):
                    deduped = [p for p in deduped if p is not prev]
                    seen[key] = pin
                    deduped.append(pin)
        working = deduped

    # Age-based candidates (still checkpointed, never silent-drop verify).
    aged: List[PinnedEvidence] = []
    fresh: List[PinnedEvidence] = []
    for pin in working:
        age = int(api_call_index) - int(pin.pinned_at_api_call or 0)
        if max_age > 0 and age > max_age and not (
            keep_verify
            and (
                pin.verify_outcome in {"success", "failure"}
                or pin.evidence_class == EvidenceClass.VERIFY.value
            )
        ):
            aged.append(pin)
            audit["aged_out"] += 1
        else:
            fresh.append(pin)
    working = fresh

    over_count = len(working) > max_pins
    over_tokens = sum(int(p.tokens_est) for p in working) > max_tokens
    if over_count:
        audit["reasons"].append(f"pin_count>{max_pins}")
    if over_tokens:
        audit["reasons"].append(f"pin_tokens>{max_tokens}")
    if audit["aged_out"]:
        audit["reasons"].append(f"age>{max_age}_api_calls")
    if audit["deduped"]:
        audit["reasons"].append("deduped_identical")

    if not (over_count or over_tokens or aged or audit["deduped"]):
        return pins, None, audit

    audit["triggered"] = True
    # Sort ascending priority then oldest first — compact from the front.
    ranked = sorted(
        working,
        key=lambda p: (_pin_priority(p), int(p.pinned_at_api_call or 0), int(p.tokens_est or 0)),
    )
    keep: List[PinnedEvidence] = []
    compact: List[PinnedEvidence] = list(aged)

    # Always preserve verify evidence + highest-priority remainder under caps.
    verify_pins = [
        p
        for p in ranked
        if keep_verify
        and (
            p.verify_outcome in {"success", "failure"}
            or p.evidence_class == EvidenceClass.VERIFY.value
        )
    ]
    non_verify = [p for p in ranked if p not in verify_pins]
    keep.extend(verify_pins)

    token_budget = max_tokens
    keep_tokens = sum(int(p.tokens_est) for p in keep)
    for pin in reversed(non_verify):  # prefer newest/highest among non-verify
        if len(keep) >= max_pins:
            compact.append(pin)
            continue
        if keep_tokens + int(pin.tokens_est) > token_budget and keep:
            compact.append(pin)
            continue
        keep.append(pin)
        keep_tokens += int(pin.tokens_est)

    # Anything left in non_verify not kept goes to compact.
    keep_ids = {p.tool_call_id for p in keep}
    for pin in non_verify:
        if pin.tool_call_id not in keep_ids and pin not in compact:
            compact.append(pin)

    audit["compacted"] = len(compact)
    checkpoint = build_mutation_checkpoint(
        pins,
        working_memory=working_memory,
        api_call_index=api_call_index,
        compacted=compact,
        kept=keep,
    )

    if apply and (keep or compact):
        new_pins = PinSet(
            open_epoch=pins.open_epoch,
            mutation_epoch_counter=pins.mutation_epoch_counter,
            pins=keep,
            last_closed_epoch=pins.last_closed_epoch,
            last_close_reason=pins.last_close_reason,
            last_updated_api_call=int(api_call_index),
            schema_version=pins.schema_version,
        )
        audit["applied"] = True
        audit["after_pin_count"] = len(new_pins.pins)
        audit["after_tokens"] = new_pins.pinned_tokens
        return new_pins, checkpoint, audit

    audit["after_pin_count"] = len(keep)
    audit["after_tokens"] = sum(int(p.tokens_est) for p in keep)
    return pins, checkpoint, audit


def pin_caps_shadow_log_path(log_filename: str | None = None) -> Path:
    from hermes_constants import get_hermes_home

    name = log_filename or "context_engineering_v2_pin_caps_shadow.jsonl"
    return get_hermes_home() / "logs" / name


def pin_shadow_log_path(log_filename: str | None = None) -> Path:
    from hermes_constants import get_hermes_home

    name = log_filename or "context_engineering_v2_pins_shadow.jsonl"
    return get_hermes_home() / "logs" / name


def maybe_run_pin_epoch_shadow(
    *,
    api_messages: Sequence[Mapping[str, Any]],
    session_id: str,
    api_call_index: int,
    session_db: Any = None,
    working_memory: Optional[WorkingMemory] = None,
    config: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Dark pin/unpin tracker. Never mutates ``api_messages``. Fail-open."""
    try:
        cfg = dict(config) if config is not None else _load_pin_epoch_config()
        if not cfg.get("enabled"):
            return None
        prior = load_pin_set(session_id, session_db=session_db)
        pins, events = update_pin_epoch_from_messages(
            prior,
            api_messages,
            api_call_index=api_call_index,
            working_memory=working_memory,
        )
        cap_audit: Dict[str, Any] = {}
        checkpoint = None
        caps_cfg = cfg.get("pin_caps") if isinstance(cfg.get("pin_caps"), dict) else {}
        if caps_cfg.get("shadow_enabled"):
            pins, checkpoint, cap_audit = shadow_apply_pin_caps(
                pins,
                api_call_index=api_call_index,
                working_memory=working_memory,
                caps=caps_cfg,
            )
            if checkpoint is not None:
                try:
                    path = pin_caps_shadow_log_path(
                        str(caps_cfg.get("log_filename") or "")
                    )
                    write_shadow_profile_record(
                        path,
                        {
                            "ts": time.time(),
                            "session_id": session_id or "",
                            "api_call_index": api_call_index,
                            "checkpoint": checkpoint.to_dict(),
                            "audit": cap_audit,
                            "shadow": True,
                            "mutates_prompt": False,
                        },
                    )
                except Exception:
                    pass
                if (
                    caps_cfg.get("apply_to_dark_store")
                    and session_db is not None
                    and session_id
                ):
                    try:
                        session_db.set_meta(
                            checkpoint_meta_key(session_id),
                            json.dumps(checkpoint.to_dict(), ensure_ascii=False),
                        )
                    except Exception:
                        pass
        wm_out = working_memory
        if cfg.get("sync_wm", True) and working_memory is not None:
            wm_out = sync_working_memory_with_pins(working_memory, pins)
            if wm_out is not None:
                wm_out = trim_working_memory_to_budget(
                    wm_out, budget_tokens=_DEFAULT_WM_BUDGET_TOKENS
                )
                if (
                    cfg.get("persist", True)
                    and session_db is not None
                    and session_id
                ):
                    save_working_memory(session_id, wm_out, session_db=session_db)
        if cfg.get("persist", True) and session_db is not None and session_id:
            save_pin_set(session_id, pins, session_db=session_db)

        # VERIFY classifier diagnostics (shadow) — command samples + outcomes.
        verify_cmds: List[str] = []
        verify_outcomes = {"success": 0, "failure": 0, "none": 0}
        call_index = _index_tool_calls(api_messages)
        for msg in api_messages:
            if msg.get("role") != "tool":
                continue
            tc_id = str(msg.get("tool_call_id") or "")
            name = str(msg.get("tool_name") or "")
            cmd = None
            if tc_id and tc_id in call_index:
                name = name or call_index[tc_id][0]
                cmd = call_index[tc_id][1]
            if classify_evidence(name, cmd) is not EvidenceClass.VERIFY:
                continue
            if cmd and len(verify_cmds) < 5:
                verify_cmds.append(str(cmd)[:160])
            outcome = detect_verify_outcome(name, msg.get("content")) or "none"
            if outcome in verify_outcomes:
                verify_outcomes[outcome] += 1
            else:
                verify_outcomes["none"] += 1

        record = {
            "ts": time.time(),
            "session_id": session_id or "",
            "api_call_index": api_call_index,
            "open_epoch": pins.open_epoch,
            "mutation_epoch_counter": pins.mutation_epoch_counter,
            "pin_count": len(pins.pins),
            "pinned_tokens_est": pins.pinned_tokens,
            "last_closed_epoch": pins.last_closed_epoch,
            "last_close_reason": pins.last_close_reason,
            "events": events[-20:],
            "pinned_tool_call_ids": sorted(pins.pinned_tool_call_ids()),
            "verify_command_samples": verify_cmds,
            "verify_outcome_counts": verify_outcomes,
            "verify_classified_count": sum(verify_outcomes.values()),
            "pin_caps_audit": cap_audit or None,
            "mutation_checkpoint": checkpoint.to_dict() if checkpoint else None,
            "mutates_prompt": False,
            "shadow": True,
        }
        path = pin_shadow_log_path(str(cfg.get("log_filename") or ""))
        write_shadow_profile_record(path, record)
        record["_working_memory"] = wm_out
        record["_pin_set"] = pins
        return record
    except Exception:
        logger.debug("context_engineering_v2 pin_epoch shadow failed", exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Short-context bypass — skip WM/layer tax when savings cannot pay for it
# ---------------------------------------------------------------------------

_DEFAULT_SHORT_BYPASS_THRESHOLD = 40_000


def _load_short_context_bypass_config() -> Dict[str, Any]:
    defaults = {
        "enabled": False,
        # When apply is false, only log eligibility (shadow). When true, skip
        # WM/layer work for matching calls.
        "apply": False,
        "legacy_token_threshold": _DEFAULT_SHORT_BYPASS_THRESHOLD,
        "require_positive_layered_saving": True,
        "log_filename": "context_engineering_v2_short_bypass.jsonl",
    }
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        section = cfg.get("context_engineering_v2") or {}
        bypass = section.get("short_context_bypass") or {}
        if not isinstance(bypass, dict):
            return defaults
        out = dict(defaults)
        out.update({k: bypass[k] for k in defaults if k in bypass})
        return out
    except Exception:
        return defaults


def short_bypass_log_path(log_filename: str | None = None) -> Path:
    from hermes_constants import get_hermes_home

    name = log_filename or "context_engineering_v2_short_bypass.jsonl"
    return get_hermes_home() / "logs" / name


def should_bypass_v2_layers(
    *,
    legacy_tokens_est: int,
    layered_tokens_est: Optional[int] = None,
    step: Optional[str] = None,
    config: Optional[Mapping[str, Any]] = None,
) -> Tuple[bool, str]:
    """Return ``(eligible, reason)`` for short / non-positive-saving sessions.

    Eligibility is independent of ``apply``. Callers that only want shadow
    logging should ignore the bool when ``apply`` is false and still run V2.
    ``layered_saving<=0`` only applies when ``step=="inspect"``.
    """
    cfg = dict(config) if config is not None else _load_short_context_bypass_config()
    if not cfg.get("enabled"):
        return False, ""
    threshold = int(cfg.get("legacy_token_threshold") or _DEFAULT_SHORT_BYPASS_THRESHOLD)
    if int(legacy_tokens_est) < threshold:
        return True, f"legacy_tokens<{threshold}"
    if (
        cfg.get("require_positive_layered_saving", True)
        and layered_tokens_est is not None
        and (step or "") == "inspect"
    ):
        if int(layered_tokens_est) >= int(legacy_tokens_est):
            return True, "inspect_layered_saving<=0"
    return False, ""


def short_context_bypass_should_apply(
    config: Optional[Mapping[str, Any]] = None,
) -> bool:
    """True when eligibility should actually skip WM/layer work."""
    cfg = dict(config) if config is not None else _load_short_context_bypass_config()
    return bool(cfg.get("enabled")) and bool(cfg.get("apply"))


def maybe_log_short_context_bypass(
    *,
    session_id: str,
    api_call_index: int,
    reason: str,
    legacy_tokens_est: int,
    layered_tokens_est: Optional[int] = None,
    skipped: Sequence[str] = (),
) -> None:
    try:
        cfg = _load_short_context_bypass_config()
        if not cfg.get("enabled") and not reason:
            return
        path = short_bypass_log_path(str(cfg.get("log_filename") or ""))
        write_shadow_profile_record(
            path,
            {
                "ts": time.time(),
                "session_id": session_id or "",
                "api_call_index": api_call_index,
                "reason": reason,
                "legacy_tokens_est": int(legacy_tokens_est),
                "layered_tokens_est": (
                    int(layered_tokens_est) if layered_tokens_est is not None else None
                ),
                "skipped": list(skipped),
                "mutates_prompt": False,
            },
        )
    except Exception:
        logger.debug("short_context_bypass log failed", exc_info=True)


# ---------------------------------------------------------------------------
# P5 — Layered assemble for inspect steps (opt-in wire change)
# ---------------------------------------------------------------------------

_DEFAULT_ASSEMBLE_RECENT_TOKENS = 8_000
_WM_INJECT_START = "<hermes_working_memory>\n"
_WM_INJECT_END = "\n</hermes_working_memory>\n\n"


def classify_assemble_step(
    messages: Sequence[Mapping[str, Any]],
    pin_set: Optional[PinSet] = None,
) -> str:
    """Infer the upcoming step type from transcript + open pin epoch."""
    pins = pin_set or PinSet()
    if int(pins.open_epoch or 0) > 0:
        # Prefer verify if the most recent tool evidence was VERIFY.
        call_index = _index_tool_calls(messages)
        for msg in reversed(list(messages)):
            if msg.get("role") != "tool":
                continue
            tc_id = str(msg.get("tool_call_id") or "")
            name = str(msg.get("tool_name") or "")
            cmd = None
            if tc_id and tc_id in call_index:
                name = name or call_index[tc_id][0]
                cmd = call_index[tc_id][1]
            ev = classify_evidence(name, cmd)
            if ev is EvidenceClass.VERIFY:
                return "verify"
            if ev is EvidenceClass.MUTATING:
                return "mutate"
            break
        return "mutate"

    non_system = [m for m in messages if m.get("role") != "system"]
    if len(non_system) <= 3:
        return "orient"
    return "inspect"


def format_working_memory_block(wm: WorkingMemory) -> str:
    """Compact WM block for API injection (not merged into Layer 1 system)."""
    lines = [
        f"objective: {wm.objective or '(unspecified)'}",
    ]
    if wm.hypothesis:
        lines.append(f"hypothesis: {wm.hypothesis}")
    if wm.active_files:
        files = ", ".join(
            f"{af.get('path')}({af.get('intent') or 'touch'})"
            for af in wm.active_files[:8]
            if af.get("path")
        )
        if files:
            lines.append(f"active_files: {files}")
    if wm.blockers:
        lines.append("blockers: " + "; ".join(wm.blockers[:5]))
    if wm.decisions:
        lines.append("decisions: " + "; ".join(wm.decisions[-5:]))
    if wm.mutation_epoch:
        lines.append(f"mutation_epoch: {wm.mutation_epoch}")
    if wm.open_questions:
        lines.append("open_questions: " + "; ".join(wm.open_questions[:3]))
    body = "\n".join(lines)
    return f"{_WM_INJECT_START}{body}{_WM_INJECT_END}"


def _inject_wm_into_last_user(
    messages: List[Dict[str, Any]],
    wm: Optional[WorkingMemory],
) -> List[Dict[str, Any]]:
    if wm is None or not (wm.objective or wm.active_files or wm.decisions):
        return messages
    block = format_working_memory_block(wm)
    out = [dict(m) for m in messages]
    for i in range(len(out) - 1, -1, -1):
        if out[i].get("role") != "user":
            continue
        content = out[i].get("content")
        if isinstance(content, str):
            if _WM_INJECT_START in content:
                break
            out[i]["content"] = block + content
        elif isinstance(content, list):
            # Prepend a text part.
            out[i]["content"] = [{"type": "text", "text": block}, *content]
        else:
            out[i]["content"] = block + _message_text(content)
        break
    return out


def _assistant_tool_call_ids(msg: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for tc in msg.get("tool_calls") or []:
        if isinstance(tc, Mapping) and tc.get("id"):
            ids.add(str(tc["id"]))
    return ids


def _expand_indices_for_tool_pairs(
    messages: Sequence[Mapping[str, Any]],
    selected: set[int],
) -> set[int]:
    """Ensure assistant↔tool pairs stay complete when either side is selected."""
    out = set(selected)
    # Map tool_call_id → assistant index / tool indices
    assistant_for_tc: Dict[str, int] = {}
    tools_for_tc: Dict[str, List[int]] = {}
    for i, msg in enumerate(messages):
        if msg.get("role") == "assistant":
            for tc_id in _assistant_tool_call_ids(msg):
                assistant_for_tc[tc_id] = i
        elif msg.get("role") == "tool":
            tc_id = str(msg.get("tool_call_id") or "")
            if tc_id:
                tools_for_tc.setdefault(tc_id, []).append(i)

    changed = True
    while changed:
        changed = False
        for tc_id, aidx in assistant_for_tc.items():
            tool_idxs = tools_for_tc.get(tc_id) or []
            any_tool = any(t in out for t in tool_idxs)
            if aidx in out or any_tool:
                if aidx not in out:
                    out.add(aidx)
                    changed = True
                for t in tool_idxs:
                    if t not in out:
                        out.add(t)
                        changed = True
    return out


def assemble_layered_api_messages(
    legacy_messages: Sequence[Mapping[str, Any]],
    *,
    working_memory: Optional[WorkingMemory] = None,
    pin_set: Optional[PinSet] = None,
    archives_by_tool_call_id: Optional[Mapping[str, ArchiveEntry]] = None,
    step: str = "inspect",
    recent_turn_budget_tokens: int = _DEFAULT_ASSEMBLE_RECENT_TOKENS,
) -> List[Dict[str, Any]]:
    """Build a layered API message list for the given step.

    For non-inspect steps (mutate/verify/orient), returns a shallow copy of
    legacy — P5 only rewrites inspect packets. Pins always beat savings.
    """
    legacy = [dict(m) for m in legacy_messages]
    if step != "inspect":
        return legacy

    pins = pin_set or PinSet()
    archives = dict(archives_by_tool_call_id or {})
    pinned_ids = pins.pinned_tool_call_ids()
    call_index = _index_tool_calls(legacy)

    system_msgs: List[Dict[str, Any]] = []
    rest: List[Tuple[int, Dict[str, Any]]] = []
    for i, msg in enumerate(legacy):
        if msg.get("role") == "system" and not rest:
            system_msgs.append(dict(msg))
        else:
            rest.append((i, dict(msg)))

    if not rest:
        return _inject_wm_into_last_user(list(system_msgs), working_memory)

    # L3 recent window (indices into ``rest``)
    recent_local: set[int] = set()
    used = 0
    budget = max(0, int(recent_turn_budget_tokens))
    for local_i in range(len(rest) - 1, -1, -1):
        tok = _tokens_from_chars(_message_chars(rest[local_i][1]))
        if used + tok > budget and recent_local:
            break
        recent_local.add(local_i)
        used += tok

    keep_abs: set[int] = set()
    for local_i, (abs_i, msg) in enumerate(rest):
        if local_i in recent_local:
            keep_abs.add(abs_i)
        elif msg.get("role") == "tool":
            tc_id = str(msg.get("tool_call_id") or "")
            if tc_id and tc_id in pinned_ids:
                keep_abs.add(abs_i)

    # Also keep archived SAFE stubs outside the recent window (summary only).
    archive_stub_abs: set[int] = set()
    for local_i, (abs_i, msg) in enumerate(rest):
        if local_i in recent_local or abs_i in keep_abs:
            continue
        if msg.get("role") != "tool":
            continue
        tc_id = str(msg.get("tool_call_id") or "")
        if not tc_id or tc_id in pinned_ids:
            continue
        name = str(msg.get("tool_name") or "")
        cmd = None
        if tc_id in call_index:
            name = name or call_index[tc_id][0]
            cmd = call_index[tc_id][1]
        ev = classify_evidence(name, cmd)
        if ev in {EvidenceClass.SAFE, EvidenceClass.DELEGATE} and tc_id in archives:
            archive_stub_abs.add(abs_i)

    keep_abs |= archive_stub_abs
    keep_abs = _expand_indices_for_tool_pairs(legacy, keep_abs)

    # Emit Layer 1 system, then kept rest rows in original order.
    assembled: List[Dict[str, Any]] = list(system_msgs)
    recent_abs = {rest[i][0] for i in recent_local}
    for abs_i, msg in rest:
        if abs_i not in keep_abs:
            continue
        copy_msg = dict(msg)
        if copy_msg.get("role") == "tool":
            tc_id = str(copy_msg.get("tool_call_id") or "")
            if (
                abs_i not in recent_abs
                and tc_id
                and tc_id in archives
                and tc_id not in pinned_ids
            ):
                name = str(copy_msg.get("tool_name") or "")
                cmd = None
                if tc_id in call_index:
                    name = name or call_index[tc_id][0]
                    cmd = call_index[tc_id][1]
                if classify_evidence(name, cmd) in {
                    EvidenceClass.SAFE,
                    EvidenceClass.DELEGATE,
                }:
                    copy_msg["content"] = archives[tc_id].summary
        assembled.append(copy_msg)

    assembled = _inject_wm_into_last_user(assembled, working_memory)
    return assembled if assembled else legacy


def _load_assemble_config() -> Dict[str, Any]:
    defaults = {
        "enabled": False,
        "inspect_steps": True,
        "recent_turn_budget_tokens": _DEFAULT_ASSEMBLE_RECENT_TOKENS,
        "fail_open": True,
        "log_filename": "context_engineering_v2_assemble.jsonl",
    }
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        section = cfg.get("context_engineering_v2") or {}
        asm = section.get("assemble") or {}
        if not isinstance(asm, dict):
            return defaults
        out = dict(defaults)
        out.update({k: asm[k] for k in defaults if k in asm})
        # Inherit thin budget from shadow profiler when unset.
        if "recent_turn_budget_tokens" not in asm:
            shadow = section.get("shadow_profiler") or {}
            if isinstance(shadow, dict) and shadow.get("recent_turn_budget_tokens"):
                # Inspect uses a thinner default than the shadow L3 estimate.
                out["recent_turn_budget_tokens"] = min(
                    int(shadow["recent_turn_budget_tokens"]),
                    _DEFAULT_ASSEMBLE_RECENT_TOKENS,
                )
        return out
    except Exception:
        return defaults


def assemble_log_path(log_filename: str | None = None) -> Path:
    from hermes_constants import get_hermes_home

    name = log_filename or "context_engineering_v2_assemble.jsonl"
    return get_hermes_home() / "logs" / name


def maybe_assemble_layered_api_messages(
    *,
    api_messages: Sequence[Mapping[str, Any]],
    working_memory: Optional[WorkingMemory] = None,
    pin_set: Optional[PinSet] = None,
    archives_by_tool_call_id: Optional[Mapping[str, ArchiveEntry]] = None,
    session_id: str = "",
    api_call_index: int = 0,
    session_db: Any = None,
    config: Optional[Mapping[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """If enabled and step is inspect, return layered messages record.

    Returns None to signal fail-open / keep legacy. Never raises.
    """
    try:
        cfg = dict(config) if config is not None else _load_assemble_config()
        if not cfg.get("enabled"):
            return None
        if not api_messages:
            return None
        pins = pin_set if pin_set is not None else PinSet()
        step = classify_assemble_step(api_messages, pins)
        if step != "inspect" or not cfg.get("inspect_steps", True):
            return None

        layered = assemble_layered_api_messages(
            api_messages,
            working_memory=working_memory,
            pin_set=pins,
            archives_by_tool_call_id=archives_by_tool_call_id or {},
            step=step,
            recent_turn_budget_tokens=int(
                cfg.get("recent_turn_budget_tokens") or _DEFAULT_ASSEMBLE_RECENT_TOKENS
            ),
        )
        if not layered:
            return None

        retrieve_count = 0
        ret_cfg = _load_retrieve_config()
        if ret_cfg.get("enabled") and session_db is not None and session_id:
            if ret_cfg.get("auto_on_verify_failure", True):
                maybe_auto_enqueue_verify_failure_retrieves(
                    session_id, pin_set=pins, session_db=session_db
                )
            if ret_cfg.get("inject_on_assemble", True):
                layered, retrieve_count = append_retrieved_to_messages(
                    layered,
                    session_id=session_id,
                    session_db=session_db,
                    max_tokens_per=int(
                        ret_cfg.get("max_tokens") or _DEFAULT_RETRIEVE_MAX_TOKENS
                    ),
                )

        legacy_chars = sum(_message_chars(m) for m in api_messages)
        layered_chars = sum(_message_chars(m) for m in layered)
        record = {
            "ts": time.time(),
            "session_id": session_id or "",
            "api_call_index": api_call_index,
            "step": step,
            "mutates_prompt": True,
            "legacy_chars": legacy_chars,
            "layered_chars": layered_chars,
            "legacy_tokens_est": _tokens_from_chars(legacy_chars),
            "layered_tokens_est": _tokens_from_chars(layered_chars),
            "message_count_legacy": len(api_messages),
            "message_count_layered": len(layered),
            "open_epoch": int(pins.open_epoch or 0),
            "retrieve_count": retrieve_count,
            "messages": layered,
        }
        try:
            path = assemble_log_path(str(cfg.get("log_filename") or ""))
            log_rec = {k: v for k, v in record.items() if k != "messages"}
            write_shadow_profile_record(path, log_rec)
        except Exception:
            pass
        maybe_log_soak(
            session_id=session_id,
            api_call_index=api_call_index,
            step=step,
            arm="layered",
            legacy_tokens_est=record["legacy_tokens_est"],
            layered_tokens_est=record["layered_tokens_est"],
            retrieve_count=retrieve_count,
            open_epoch=int(pins.open_epoch or 0),
            mutates_prompt=True,
        )
        return record
    except Exception:
        logger.debug("context_engineering_v2 assemble failed", exc_info=True)
        if config is None:
            cfg = _load_assemble_config()
        else:
            cfg = dict(config)
        if cfg.get("fail_open", True):
            return None
        raise


def maybe_apply_retrieves_legacy_arm(
    *,
    api_messages: Sequence[Mapping[str, Any]],
    session_id: str,
    api_call_index: int,
    session_db: Any = None,
    pin_set: Optional[PinSet] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Inject pending retrieves on the legacy arm + soak log (P6).

    Called when P5 did not rewrite the prompt. Fail-open: returns a copy.
    """
    out = [dict(m) for m in api_messages]
    meta: Dict[str, Any] = {"retrieve_count": 0, "arm": "legacy"}
    try:
        pins = pin_set if pin_set is not None else PinSet()
        step = classify_assemble_step(out, pins)
        ret_cfg = _load_retrieve_config()
        retrieve_count = 0
        if ret_cfg.get("enabled") and session_db is not None and session_id:
            if ret_cfg.get("auto_on_verify_failure", True):
                maybe_auto_enqueue_verify_failure_retrieves(
                    session_id, pin_set=pins, session_db=session_db
                )
            if ret_cfg.get("inject_on_assemble", True):
                out, retrieve_count = append_retrieved_to_messages(
                    out,
                    session_id=session_id,
                    session_db=session_db,
                    max_tokens_per=int(
                        ret_cfg.get("max_tokens") or _DEFAULT_RETRIEVE_MAX_TOKENS
                    ),
                )
        legacy_tokens = _tokens_from_chars(sum(_message_chars(m) for m in api_messages))
        final_tokens = _tokens_from_chars(sum(_message_chars(m) for m in out))
        meta = {
            "retrieve_count": retrieve_count,
            "arm": "legacy",
            "step": step,
            "legacy_tokens_est": legacy_tokens,
            "layered_tokens_est": final_tokens,
        }
        maybe_log_soak(
            session_id=session_id,
            api_call_index=api_call_index,
            step=step,
            arm="legacy",
            legacy_tokens_est=legacy_tokens,
            layered_tokens_est=final_tokens,
            retrieve_count=retrieve_count,
            open_epoch=int(pins.open_epoch or 0),
            mutates_prompt=bool(retrieve_count),
        )
    except Exception:
        logger.debug("context_engineering_v2 legacy retrieve arm failed", exc_info=True)
    return out, meta


def archives_by_tool_call_id_from_db(
    session_id: str,
    *,
    session_db: Any = None,
) -> Dict[str, ArchiveEntry]:
    entries = load_archive_index(session_id, session_db=session_db)
    return {e.tool_call_id: e for e in entries if e.tool_call_id}


# ---------------------------------------------------------------------------
# P6 — Retrieval helper + A/B soak
# ---------------------------------------------------------------------------


def retrieve_meta_key(session_id: str) -> str:
    return f"{_RETRIEVE_META_PREFIX}{session_id}"


def list_archive_summaries(
    session_id: str,
    *,
    session_db: Any = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    entries = load_archive_index(session_id, session_db=session_db)
    out: List[Dict[str, Any]] = []
    for e in entries[-max(1, int(limit)) :]:
        out.append(
            {
                "archive_id": e.archive_id,
                "tool_name": e.tool_name,
                "command": e.command,
                "evidence_class": e.evidence_class,
                "summary": e.summary,
                "tokens_raw": e.tokens_raw,
                "tokens_summary": e.tokens_summary,
                "created_api_call": e.created_api_call,
                "tool_call_id": e.tool_call_id,
            }
        )
    return out


def resolve_archive_entry(
    session_id: str,
    archive_id: str,
    *,
    session_db: Any = None,
) -> Optional[ArchiveEntry]:
    if not archive_id:
        return None
    aid = str(archive_id).strip()
    for e in load_archive_index(session_id, session_db=session_db):
        if e.archive_id == aid:
            return e
    return None


def budget_raw_segment(
    raw: str,
    *,
    max_tokens: int = _DEFAULT_RETRIEVE_MAX_TOKENS,
    offset_chars: int = 0,
) -> Dict[str, Any]:
    text = raw or ""
    start = max(0, int(offset_chars or 0))
    max_chars = max(64, int(max_tokens) * _CHARS_PER_TOKEN)
    chunk = text[start : start + max_chars]
    next_offset = start + len(chunk)
    truncated = next_offset < len(text)
    return {
        "content": chunk,
        "offset_chars": start,
        "next_offset": next_offset,
        "total_chars": len(text),
        "truncated": truncated,
        "tokens_est": _tokens_from_chars(len(chunk)),
    }


def get_archive_raw(
    session_id: str,
    archive_id: str,
    *,
    session_db: Any = None,
    max_tokens: int = _DEFAULT_RETRIEVE_MAX_TOKENS,
    offset_chars: int = 0,
) -> Dict[str, Any]:
    entry = resolve_archive_entry(session_id, archive_id, session_db=session_db)
    if entry is None:
        return {"ok": False, "error": f"archive_id not found: {archive_id}"}
    raw = ""
    try:
        path = Path(entry.raw_ref)
        if path.is_file():
            raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        return {"ok": False, "error": f"failed to read blob: {exc}", "archive_id": archive_id}
    seg = budget_raw_segment(raw, max_tokens=max_tokens, offset_chars=offset_chars)
    return {
        "ok": True,
        "archive_id": entry.archive_id,
        "tool_name": entry.tool_name,
        "command": entry.command,
        "summary": entry.summary,
        "evidence_class": entry.evidence_class,
        **seg,
    }


def load_pending_retrieves(
    session_id: str,
    *,
    session_db: Any = None,
) -> List[Dict[str, Any]]:
    if not session_id or session_db is None:
        return []
    try:
        raw = session_db.get_meta(retrieve_meta_key(session_id))
    except Exception:
        return []
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict) and x.get("archive_id")]


def save_pending_retrieves(
    session_id: str,
    pending: Sequence[Mapping[str, Any]],
    *,
    session_db: Any = None,
) -> bool:
    if not session_id or session_db is None:
        return False
    try:
        session_db.set_meta(
            retrieve_meta_key(session_id),
            json.dumps(list(pending), ensure_ascii=False),
        )
        return True
    except Exception:
        logger.debug("pending retrieve set_meta failed", exc_info=True)
        return False


def enqueue_pending_retrieve(
    session_id: str,
    archive_id: str,
    *,
    session_db: Any = None,
    reason: str = "manual",
    max_tokens: int = _DEFAULT_RETRIEVE_MAX_TOKENS,
) -> bool:
    if not session_id or not archive_id or session_db is None:
        return False
    pending = load_pending_retrieves(session_id, session_db=session_db)
    if any(p.get("archive_id") == archive_id for p in pending):
        return True
    pending.append(
        {
            "archive_id": str(archive_id),
            "reason": reason,
            "max_tokens": int(max_tokens),
            "enqueued_at": time.time(),
        }
    )
    # Cap queue
    if len(pending) > 8:
        pending = pending[-8:]
    return save_pending_retrieves(session_id, pending, session_db=session_db)


def clear_pending_retrieves(session_id: str, *, session_db: Any = None) -> None:
    save_pending_retrieves(session_id, [], session_db=session_db)


def append_retrieved_to_messages(
    messages: Sequence[Mapping[str, Any]],
    *,
    session_id: str,
    session_db: Any = None,
    max_tokens_per: int = _DEFAULT_RETRIEVE_MAX_TOKENS,
    clear_after: bool = True,
) -> Tuple[List[Dict[str, Any]], int]:
    """Append budgeted archive raw at the end of the API message list.

    Returns ``(messages, injected_count)``. Cache-friendly: content is always
    at the tail, never Layer 1.
    """
    out = [dict(m) for m in messages]
    pending = load_pending_retrieves(session_id, session_db=session_db)
    if not pending:
        return out, 0
    blocks: List[str] = []
    injected = 0
    for item in pending:
        aid = str(item.get("archive_id") or "")
        budget = int(item.get("max_tokens") or max_tokens_per)
        payload = get_archive_raw(
            session_id,
            aid,
            session_db=session_db,
            max_tokens=budget,
            offset_chars=0,
        )
        if not payload.get("ok"):
            continue
        truncated = " (truncated)" if payload.get("truncated") else ""
        blocks.append(
            f"<hermes_context_archive id=\"{aid}\"{truncated}>\n"
            f"summary: {payload.get('summary') or ''}\n"
            f"---\n{payload.get('content') or ''}\n"
            f"</hermes_context_archive>"
        )
        injected += 1
    if not blocks:
        if clear_after:
            clear_pending_retrieves(session_id, session_db=session_db)
        return out, 0
    out.append(
        {
            "role": "user",
            "content": (
                "Retrieved archived context (Layer 5). Use if needed; "
                "raw dumps are not kept in the stable prefix.\n\n"
                + "\n\n".join(blocks)
            ),
        }
    )
    if clear_after:
        clear_pending_retrieves(session_id, session_db=session_db)
    return out, injected


def maybe_auto_enqueue_verify_failure_retrieves(
    session_id: str,
    *,
    pin_set: Optional[PinSet] = None,
    session_db: Any = None,
    limit: int = 2,
) -> int:
    """If open epoch has a verify failure, enqueue related SAFE archives."""
    pins = pin_set or PinSet()
    if int(pins.open_epoch or 0) <= 0:
        return 0
    failures = [p for p in pins.pins if p.verify_outcome == "failure"]
    if not failures:
        return 0
    paths = {p.path for p in pins.pins if p.path}
    entries = load_archive_index(session_id, session_db=session_db)
    if not entries:
        return 0
    enqueued = 0
    # Prefer archives whose summary/command mention an active path; else newest SAFE.
    candidates: List[ArchiveEntry] = []
    for e in reversed(entries):
        if e.evidence_class not in {
            EvidenceClass.SAFE.value,
            EvidenceClass.DELEGATE.value,
        }:
            continue
        blob = f"{e.summary} {e.command} {e.tool_name}"
        if paths and any(path and path in blob for path in paths):
            candidates.append(e)
    if not candidates:
        candidates = [
            e
            for e in reversed(entries)
            if e.evidence_class == EvidenceClass.SAFE.value
        ][:limit]
    for e in candidates[:limit]:
        if enqueue_pending_retrieve(
            session_id,
            e.archive_id,
            session_db=session_db,
            reason="auto_verify_failure",
        ):
            enqueued += 1
    return enqueued


def _load_retrieve_config() -> Dict[str, Any]:
    defaults = {
        "enabled": False,
        "max_tokens": _DEFAULT_RETRIEVE_MAX_TOKENS,
        "auto_on_verify_failure": True,
        "inject_on_assemble": True,
    }
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        section = cfg.get("context_engineering_v2") or {}
        ret = section.get("retrieve") or {}
        if not isinstance(ret, dict):
            return defaults
        out = dict(defaults)
        out.update({k: ret[k] for k in defaults if k in ret})
        return out
    except Exception:
        return defaults


def _load_soak_config() -> Dict[str, Any]:
    defaults = {
        "enabled": False,
        "log_filename": _DEFAULT_SOAK_LOG,
    }
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        section = cfg.get("context_engineering_v2") or {}
        soak = section.get("soak") or {}
        if not isinstance(soak, dict):
            return defaults
        out = dict(defaults)
        out.update({k: soak[k] for k in defaults if k in soak})
        return out
    except Exception:
        return defaults


def log_soak_record(
    record: Mapping[str, Any],
    *,
    log_filename: str | None = None,
) -> Path:
    from hermes_constants import get_hermes_home

    name = log_filename or _DEFAULT_SOAK_LOG
    path = get_hermes_home() / "logs" / name
    payload = dict(record)
    payload.setdefault("ts", time.time())
    write_shadow_profile_record(path, payload)
    return path


def maybe_log_soak(
    *,
    session_id: str,
    api_call_index: int,
    step: str,
    arm: str,
    legacy_tokens_est: int,
    layered_tokens_est: int,
    retrieve_count: int = 0,
    open_epoch: int = 0,
    mutates_prompt: bool = False,
) -> None:
    try:
        cfg = _load_soak_config()
        if not cfg.get("enabled"):
            return
        log_soak_record(
            {
                "session_id": session_id or "",
                "api_call_index": api_call_index,
                "step": step,
                "arm": arm,
                "legacy_tokens_est": int(legacy_tokens_est),
                "layered_tokens_est": int(layered_tokens_est),
                "retrieve_count": int(retrieve_count),
                "open_epoch": int(open_epoch),
                "mutates_prompt": bool(mutates_prompt),
                "savings_tokens_est": max(
                    0, int(legacy_tokens_est) - int(layered_tokens_est)
                ),
            },
            log_filename=str(cfg.get("log_filename") or _DEFAULT_SOAK_LOG),
        )
    except Exception:
        logger.debug("context_engineering_v2 soak log failed", exc_info=True)


def retrieve_enabled() -> bool:
    """Used by the context_archive tool check_fn."""
    return bool(_load_retrieve_config().get("enabled"))
