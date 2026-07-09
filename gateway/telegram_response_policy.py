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
_LOG_HEAVY_RE = re.compile(r"\b(traceback|stack trace|raw log|stderr|stdout|exception|error:|warn(?:ing)?|info\s+heartbeat)\b", re.I)
_APPROVAL_RE = re.compile(
    r"(?im)^\s*(?:need approval|approval required|requires approval|pending approval)\b|"
    r"\b(?:need|requires?)\s+(?:dylan'?s\s+)?approval\s+(?:to|before|for)\b",
)
_BLOCKED_RE = re.compile(r"(?im)^\s*(?:blocked|cannot proceed|need input)\b")
_REPORT_BOILERPLATE_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:hermes\s*[—-]\s*)?(?:full\s+)?(?:status\s+)?report(?:\s+generated)?\s*$|"
    r"^\s*(?:#+\s*)?(?:hermes\s*[—-]\s*)?short\s+status\b.*$|"
    r"^\s*(?:generated|operator|reviewer)\s*:.*$",
    re.I | re.M,
)
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$", re.M)
_TABLE_DIVIDER_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$", re.M)
_HERMES_STATUS_RE = re.compile(r"\b(hermes|gateway|dashboard|telegram concise|observability|mcp|canonical context|clickup)\b", re.I)
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

    # Explicit detail/full-report outputs should preserve the agent's actual
    # expanded answer while removing report chrome that is awkward on Telegram.
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
        return "Working on it. I’ll keep the update short."
    if _INTERNAL_TRACE_RE.search(text):
        return "Working on it. I’ll keep the update short."
    if _APPROVAL_RE.search(text):
        return "Need approval - " + _first_sentence(text, limit=180)
    if _LOG_HEAVY_RE.search(text) and _is_long_or_loggy(text):
        return "Working on it. I found noisy output and will summarize the useful part."
    if _is_long_or_loggy(text):
        return _summary_from_lines(text, prefix="Working on it.")
    if _looks_like_structured_status(text):
        return _mobile_friendly_report(text, max_lines=4)
    return _first_sentence(text, limit=260)


def _compact_final(text: str) -> str:
    if _COMMAND_TRACE_RE.search(text):
        return "Done. I summarized the work. Ask for details if you want the full trace."
    if _APPROVAL_RE.search(text):
        return "Need approval - " + _first_sentence(text, limit=220)
    if _BLOCKED_RE.search(text):
        if not _looks_like_structured_status(text):
            return "Blocked - " + _first_sentence(text, limit=220)
    if _looks_like_structured_status(text):
        return _mobile_friendly_report(text, max_lines=6)
    return text


def _is_long_or_loggy(text: str) -> bool:
    if len(text) > 900 or text.count("\n") > 8:
        return True
    lowered = text.lower()
    return lowered.count("traceback") > 0 or lowered.count("error") > 3 or "```" in text and len(text) > 500


def _first_sentence(text: str, *, limit: int) -> str:
    clean = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(clean) <= limit:
        return clean
    pieces = re.findall(r".+?[.!?](?:\s|$)", clean)
    if pieces:
        out = ""
        for piece in pieces:
            candidate = (out + piece).strip()
            if len(candidate) > limit:
                break
            out = candidate + " "
        if out.strip():
            return out.strip()
    return clean[: max(0, limit - 1)].rstrip() + "."


def _summary_from_lines(text: str, *, prefix: str = "Summary:") -> str:
    lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    useful = [_first_sentence(line, limit=220) for line in lines[:3]]
    return "\n".join([prefix, *useful, "Ask for details if you want the full output."])


def _looks_like_structured_status(text: str) -> bool:
    if _HERMES_STATUS_RE.search(text) and (_TABLE_ROW_RE.search(text) or "#" in text[:80]):
        return True
    return bool(_HERMES_STATUS_RE.search(text) and len(text) > 240 and text.count("\n") >= 2)


def _mobile_friendly_report(text: str, *, max_lines: int) -> str:
    clean = _strip_report_chrome(text)
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    if not lines:
        return _first_sentence(clean, limit=260)
    return "\n".join(_dedupe_lines(lines[:max_lines]))


def _expanded_report(text: str) -> str:
    clean = _strip_report_chrome(text)
    useful = [line.strip() for line in clean.splitlines() if line.strip()]
    if not useful:
        return ""
    if not useful[0].lower().startswith("full report"):
        useful.insert(0, "Full report:")
    return "\n".join(_dedupe_lines(useful[:24]))


def _strip_report_chrome(text: str) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            lines.append("")
            continue
        if re.match(r"(?i)^(?:need approval|blocked)\s*[-–—]\s*#?\s*hermes\s*[—-]", line):
            line = re.sub(r"(?i)^(?:need approval|blocked)\s*[-–—]\s*", "", line).strip()
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
