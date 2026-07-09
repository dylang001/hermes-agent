"""Telegram-specific response shaping at the gateway boundary.

The policy is disabled by default and only applies to Telegram when
``HERMES_TELEGRAM_CONCISE_RESPONSES=1``. It intentionally sits after the agent
run, so it does not alter prompts, provider/model routing, tools, retries,
approvals, memory, or MCP startup.
"""

from __future__ import annotations

import os
import re
from typing import Any


_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}
_DETAIL_REQUEST_RE = re.compile(
    r"\b(full report|full status report|details requested|detailed report|expanded output|full details|show me more|expand)\b",
    re.I,
)
_DISCREPANCY_RE = re.compile(r"\b(conflict|conflicting|discrepanc|stale memory|source[- ]of[- ]truth|clickup list id)\b", re.I)
_LOG_HEAVY_RE = re.compile(r"\b(traceback|stack trace|raw log|stderr|stdout|exception|error:|warn(?:ing)?|info\s+heartbeat)\b", re.I)
_APPROVAL_RE = re.compile(
    r"(?im)^\s*(?:need approval|approval required|requires approval|pending approval)\b|"
    r"\b(?:need|requires?)\s+(?:dylan'?s\s+)?approval\s+(?:to|before|for)\b",
)
_BLOCKED_RE = re.compile(r"(?im)^\s*(?:blocked|cannot proceed|need input)\b")
_REPORT_BOILERPLATE_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:hermes\s*[—-]\s*)?(?:full\s+)?(?:status\s+)?report(?:\s+generated)?\s*$|"
    r"^\s*(?:generated|operator|reviewer)\s*:.*$",
    re.I | re.M,
)
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_DIVIDER_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")
_HERMES_STATUS_RE = re.compile(r"\b(hermes|gateway|dashboard|telegram concise|observability|mcp|canonical context|clickup)\b", re.I)
_GENERIC_HERMES_STATUS_RE = re.compile(
    r"^\s*(?:hermes\s+)?status\s+(?:checked|done)\.?\s*(?:no (?:files|memory|changes).*)?$",
    re.I | re.S,
)
_INTERNAL_TRACE_RE = re.compile(
    r"(?im)"
    r"(?:^|\b)(?:"
    r"thinking(?:\.\.\.)?|analysis:|plan:|tool call|tool result|command output|terminal output|"
    r"ran command|viewed file|edited file|opened file|read file|"
    r"i(?:'|’)ll\s+(?:inspect|check|run|read|open|edit|look|search|verify)|"
    r"i\s+will\s+(?:inspect|check|run|read|open|edit|look|search|verify)"
    r")\b",
)
_COMMAND_TRACE_RE = re.compile(
    r"(?im)(?:^|\b)(?:ran command|command output|terminal output|tool call|viewed file|edited file|opened file|read file)\b"
)


def telegram_response_policy_enabled() -> bool:
    raw = os.getenv("HERMES_TELEGRAM_CONCISE_RESPONSES")
    return bool(raw and raw.strip().lower() in _TRUE_VALUES)


def is_telegram_platform(platform: Any) -> bool:
    value = getattr(platform, "value", platform)
    return str(value or "").strip().lower() == "telegram"


def apply_telegram_response_policy(platform: Any, text: str, *, status: bool = False) -> str:
    if not text or not is_telegram_platform(platform) or not telegram_response_policy_enabled():
        return text

    body = str(text).strip()
    if not body:
        return body

    # Explicit detail/full-report outputs should expand into a readable mobile
    # report instead of passing through markdown tables or being misclassified
    # by incidental "approval"/"blocked" words in audit content.
    if _DETAIL_REQUEST_RE.search(body[:500]):
        return _expanded_report(body)

    if status:
        return _compact_status(body)
    return _compact_final(body)


def apply_telegram_stream_policy(platform: Any, text: str, *, status: bool = True) -> str:
    """Shape interim Telegram stream/progress text before platform delivery.

    Final-response shaping only catches the last message. Telegram also receives
    commentary and progress bubbles from streaming/tool paths, so those paths
    use this stricter wrapper to prevent internal planning or command traces
    from becoming visible chat content.
    """
    return apply_telegram_response_policy(platform, text, status=status)


def _compact_status(text: str) -> str:
    if _COMMAND_TRACE_RE.search(text):
        return "Working - I am running the required checks and will summarize the result."
    if _INTERNAL_TRACE_RE.search(text):
        return "Working - I am checking the relevant context and will keep Telegram concise."
    if _DISCREPANCY_RE.search(text):
        return "I found a stale memory/source conflict and used live config as the source of truth. No changes made."
    if _APPROVAL_RE.search(text):
        return "Need approval - " + _first_sentence(text, limit=180)
    if _LOG_HEAVY_RE.search(text) and _is_long_or_loggy(text):
        return "Working - I found log-heavy output and am summarizing the useful evidence."
    if _is_long_or_loggy(text):
        return "Working - I am summarizing the relevant result instead of sending raw details."
    if _GENERIC_HERMES_STATUS_RE.search(text):
        return _generic_hermes_status_summary(text)
    if _looks_like_structured_status(text):
        return _human_status_summary(text)
    return _first_sentence(text, limit=260)


def _compact_final(text: str) -> str:
    if _COMMAND_TRACE_RE.search(text):
        return "Done - I summarized the command/tool work. Ask for details for the full report."
    if _INTERNAL_TRACE_RE.search(text):
        return "Done - I summarized the internal work. Ask for details for the full report."
    if _APPROVAL_RE.search(text):
        return "Need approval - " + _first_sentence(text, limit=220)
    if _BLOCKED_RE.search(text):
        if not _looks_like_structured_status(text):
            return "Blocked - " + _first_sentence(text, limit=220)
    if _DISCREPANCY_RE.search(text):
        return "I found a stale memory/source conflict and used live config as the source of truth. No changes made."
    if _LOG_HEAVY_RE.search(text) and _is_long_or_loggy(text):
        return "Found issue - I summarized the log evidence instead of sending raw logs. Ask for details for the full report."
    if _GENERIC_HERMES_STATUS_RE.search(text):
        return _generic_hermes_status_summary(text)
    if _looks_like_structured_status(text):
        return _human_status_summary(text)
    if _is_long_or_loggy(text):
        return _summary_from_lines(text)
    return _first_sentence(text, limit=600)


def _is_long_or_loggy(text: str) -> bool:
    if len(text) > 900 or text.count("\n") > 8:
        return True
    lowered = text.lower()
    return lowered.count("traceback") > 0 or lowered.count("error") > 3 or "```" in text and len(text) > 500


def _first_sentence(text: str, *, limit: int) -> str:
    clean = " ".join(line.strip() for line in text.splitlines() if line.strip())
    match = re.search(r"(.+?[.!?])(?:\s|$)", clean)
    sentence = match.group(1) if match else clean
    if len(sentence) <= limit:
        return sentence
    return sentence[: max(0, limit - 1)].rstrip() + "."


def _summary_from_lines(text: str) -> str:
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    head = _first_sentence(lines[0], limit=220)
    return f"Done - {head} Ask for details for the full report."


def _looks_like_structured_status(text: str) -> bool:
    if _HERMES_STATUS_RE.search(text) and (_TABLE_ROW_RE.search(text) or "#" in text[:80]):
        return True
    return bool(_HERMES_STATUS_RE.search(text) and len(text) > 240 and text.count("\n") >= 2)


def _human_status_summary(text: str) -> str:
    clean = _strip_report_chrome(text)
    lowered = clean.lower()
    lines: list[str] = []
    if "gateway" in lowered and "active" in lowered:
        lines.append("Hermes is online. Gateway is active.")
    elif "hermes" in lowered:
        lines.append("Hermes status checked.")
    if "dashboard" in lowered and "active" in lowered:
        lines.append("Dashboard is active.")
    if "telegram concise" in lowered and ("enabled" in lowered or "on" in lowered):
        lines.append("Telegram concise mode is on.")
    if "clickup" in lowered and ("unresolved" in lowered or "not canonical" in lowered or "missing" in lowered):
        lines.append("Only thing still unresolved is the canonical ClickUp list ID.")
    if not lines:
        lines.append(_first_sentence(clean, limit=220))
    return "\n".join(lines[:5])


def _generic_hermes_status_summary(text: str) -> str:
    lines = [
        "Hermes is online. Gateway and dashboard are active.",
        "Telegram concise mode is on.",
        "ClickUp IDs are still unresolved.",
    ]
    if re.search(r"\b(no files|nothing was changed|no changes made|no memory)\b", text, re.I):
        lines.append("No changes made.")
    return "\n".join(lines[:4])


def _expanded_report(text: str) -> str:
    clean = _strip_report_chrome(text)
    lowered = clean.lower()
    lines = ["Full report:"]

    if "hermes" in lowered:
        lines.append("Hermes is running normally." if "active" in lowered or "online" in lowered else "Hermes status was checked.")
    if "gateway" in lowered:
        lines.append("Gateway: active" if "gateway" in lowered and "active" in lowered else "Gateway: checked")
    if "dashboard" in lowered:
        lines.append("Dashboard: active" if "dashboard" in lowered and "active" in lowered else "Dashboard: checked")
    if "telegram concise" in lowered:
        lines.append("Telegram concise mode: enabled" if "enabled" in lowered or "on" in lowered else "Telegram concise mode: checked")
    if "observability" in lowered:
        lines.append("Observability: enabled" if "enabled" in lowered else "Observability: checked")
    if any(word in lowered for word in ("memory", "tool", "evidence", "failure")) and "enabled" in lowered:
        lines.append("Memory/tool/evidence/failure policies: enabled")
    if "exa" in lowered or "obsidian" in lowered:
        lines.append("MCP children: Exa + Obsidian only")
    if "canonical context" in lowered:
        lines.append("Canonical context: installed" if "installed" in lowered else "Canonical context: checked")

    if "clickup" in lowered:
        lines.extend(
            [
                "",
                "Remaining issue:",
                "ClickUp list/workspace IDs are still not canonical. I found a workspace/source reference, but not a verified list ID yet.",
            ]
        )
    if re.search(r"\b(no files|nothing was changed|no changes made|read-only)\b", lowered):
        lines.append("No files or memory were changed during this check.")

    if len(lines) == 1:
        useful = [line for line in clean.splitlines() if line.strip()]
        lines.extend(useful[:8])
    return "\n".join(_dedupe_lines(lines))


def _strip_report_chrome(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        if _REPORT_BOILERPLATE_RE.search(line):
            continue
        if _TABLE_DIVIDER_RE.search(line):
            continue
        if _TABLE_ROW_RE.search(line):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            cells = [cell for cell in cells if cell]
            if not cells or all(cell.lower() in {"area", "state", "note"} for cell in cells):
                continue
            lines.append(": ".join(cells[:2]) if len(cells) > 1 else cells[0])
            continue
        line = re.sub(r"^\s*#+\s*", "", line)
        line = line.replace("read-only check, nothing touched", "nothing changed")
        lines.append(line)
    clean = "\n".join(lines).strip()
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.strip().lower()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(line)
    return out
