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
_DETAIL_REQUEST_RE = re.compile(r"\b(full report|details requested|detailed report|expanded output|full details)\b", re.I)
_DISCREPANCY_RE = re.compile(r"\b(conflict|conflicting|discrepanc|stale memory|source[- ]of[- ]truth|clickup list id)\b", re.I)
_LOG_HEAVY_RE = re.compile(r"\b(traceback|stack trace|raw log|stderr|stdout|exception|error:|warn(?:ing)?|info\s+heartbeat)\b", re.I)
_APPROVAL_RE = re.compile(r"\b(approval required|need approval|requires approval|pending approval)\b", re.I)
_BLOCKED_RE = re.compile(r"\b(blocked|cannot proceed|need input)\b", re.I)


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

    # Explicit detail/full-report requests should be honored. This keeps the
    # first-pass Telegram default concise while preserving an escape hatch.
    if _DETAIL_REQUEST_RE.search(body[:500]):
        return body

    if status:
        return _compact_status(body)
    return _compact_final(body)


def _compact_status(text: str) -> str:
    if _DISCREPANCY_RE.search(text):
        return "Found a stale memory/source conflict. I am verifying against live config before touching anything."
    if _APPROVAL_RE.search(text):
        return "Need approval - " + _first_sentence(text, limit=180)
    if _LOG_HEAVY_RE.search(text) and _is_long_or_loggy(text):
        return "Working - I found log-heavy output and am summarizing the useful evidence."
    if _is_long_or_loggy(text):
        return "Working - I am summarizing the relevant result instead of sending raw details."
    return _first_sentence(text, limit=260)


def _compact_final(text: str) -> str:
    if _APPROVAL_RE.search(text):
        return "Need approval - " + _first_sentence(text, limit=220)
    if _BLOCKED_RE.search(text):
        return "Blocked - " + _first_sentence(text, limit=220)
    if _DISCREPANCY_RE.search(text):
        count = _extract_count(text)
        prefix = f"Done - I found {count} source discrepancy item" + ("" if count == "1" else "s") if count else "Done - I found source discrepancies"
        return prefix + ". Nothing was changed. Ask for details for the full report."
    if _LOG_HEAVY_RE.search(text) and _is_long_or_loggy(text):
        return "Found issue - I summarized the log evidence instead of sending raw logs. Ask for details for the full report."
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


def _extract_count(text: str) -> str:
    match = re.search(r"\b(\d{1,4})\s+(?:stale|conflicting|source|clickup|memory|discrepanc)", text, re.I)
    return match.group(1) if match else ""
