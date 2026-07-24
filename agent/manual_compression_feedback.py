"""User-facing summaries for manual compression commands."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from agent.redact import redact_sensitive_text


_SKIP_REASON_COPY = {
    "concurrent_lock": (
        "Blocked: another compression is already running on this session "
        "(often a client retry while the first /compress is still summarizing). "
        "Wait for it to finish, then reload the session tip — do not assume "
        "zero work happened."
    ),
    "already_rotated": (
        "Blocked: this session tip was already rotated by a concurrent "
        "compression. Reload the conversation to see the compacted tip."
    ),
    "history_race": (
        "Blocked: live history changed while compression ran, so the result "
        "was not applied to the in-memory transcript. Check whether a child "
        "session was created in the session list."
    ),
    "compression_still_running": (
        "Blocked: an in-flight peer compression is still running "
        "(wait timed out). This is not a no-op success — reload the session "
        "list or retry /compress later to adopt the winner tip when ready."
    ),
    "peer_timeout": (
        "Blocked: waited for an in-flight peer compression but it did not "
        "finish in time. Reload the session list — a child tip may still appear."
    ),
    "peer_failed": (
        "Blocked: the in-flight peer compression released its lock without "
        "rotating the session (aborted or failed). Retry /compress once."
    ),
    "too_few_messages": (
        "Blocked: need at least 4 messages before /compress can run."
    ),
    "compression_disabled": (
        "Blocked: compression.enabled is false in config."
    ),
}


def estimate_transcript_retention(
    messages: Sequence[Mapping[str, Any]],
    *,
    system_prompt: str = "",
    tools: Any = None,
    pin_tokens: int = 0,
    open_epoch: int = 0,
    working_memory_tokens: int = 0,
) -> dict[str, Any]:
    """Rough retention buckets for a /compress report (chars/4 heuristic)."""
    role_chars = {"user": 0, "assistant": 0, "tool": 0, "system": 0, "other": 0}
    for msg in messages:
        role = str(msg.get("role") or "other")
        if role not in role_chars:
            role = "other"
        content = msg.get("content")
        if isinstance(content, str):
            role_chars[role] += len(content)
        elif isinstance(content, list):
            role_chars[role] += sum(
                len(str(part.get("text") or ""))
                if isinstance(part, dict)
                else len(str(part))
                for part in content
            )
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            role_chars[role] += len(str(tool_calls))

    def _tok(chars: int) -> int:
        return max(0, chars // 4)

    transcript = {
        "user": _tok(role_chars["user"]),
        "assistant": _tok(role_chars["assistant"]),
        "tool": _tok(role_chars["tool"]),
        "system_in_transcript": _tok(role_chars["system"]),
        "other": _tok(role_chars["other"]),
    }
    system_prefix = _tok(len(system_prompt or ""))
    tools_est = 0
    if tools:
        try:
            from agent.model_metadata import estimate_tokens_rough

            tools_est = int(estimate_tokens_rough(str(tools)) or 0)
        except Exception:
            tools_est = max(0, len(str(tools)) // 4)

    return {
        "transcript": transcript,
        "transcript_total": sum(transcript.values()),
        "system_stable_prefix": system_prefix,
        "tool_schemas": tools_est,
        "v2_open_epoch_pins": int(pin_tokens or 0),
        "v2_open_epoch": int(open_epoch or 0),
        "v2_working_memory": int(working_memory_tokens or 0),
        "note": (
            "/compress only rewrites ordinary transcript history via the "
            "Hermes ContextCompressor. V2 pins / Working Memory are outside "
            "its authority and remain until epoch close or pin-cap checkpoint."
        ),
    }


def format_retention_lines(retention: Mapping[str, Any]) -> list[str]:
    """Render retention buckets as short user-facing lines."""
    lines: list[str] = ["Retained (approx):"]
    tr = retention.get("transcript") or {}
    if isinstance(tr, Mapping):
        for key, label in (
            ("tool", "Tool results"),
            ("assistant", "Assistant turns"),
            ("user", "User turns"),
            ("system_in_transcript", "System-in-transcript"),
        ):
            val = int(tr.get(key) or 0)
            if val:
                lines.append(f"- {label}: {val:,}")
    for key, label in (
        ("system_stable_prefix", "System/stable prefix"),
        ("tool_schemas", "Tool schemas"),
        ("v2_open_epoch_pins", "V2 open-epoch pins (not compressed by /compress)"),
        ("v2_working_memory", "V2 working memory (not compressed by /compress)"),
    ):
        val = int(retention.get(key) or 0)
        if val:
            lines.append(f"- {label}: {val:,}")
    open_epoch = int(retention.get("v2_open_epoch") or 0)
    if open_epoch:
        lines.append(f"- Open mutation epoch: {open_epoch}")
    note = retention.get("note")
    if isinstance(note, str) and note.strip():
        lines.append(note.strip())
    return lines


def build_compression_retention(
    messages: Sequence[Mapping[str, Any]],
    *,
    agent: Any = None,
    system_prompt: str = "",
    tools: Any = None,
) -> dict[str, Any]:
    """Collect transcript + optional V2 pin/WM retention for /compress reports."""
    pin_tokens = 0
    open_epoch = 0
    wm_tokens = 0
    if agent is not None:
        pins = getattr(agent, "_pin_epoch_v2", None)
        if pins is not None:
            try:
                pin_tokens = int(getattr(pins, "pinned_tokens", 0) or 0)
                open_epoch = int(getattr(pins, "open_epoch", 0) or 0)
            except Exception:
                pass
        wm = getattr(agent, "_working_memory_v2", None)
        if wm is not None:
            try:
                from agent.context_engineering_v2 import estimate_working_memory_tokens

                wm_tokens = int(estimate_working_memory_tokens(wm) or 0)
            except Exception:
                wm_tokens = 0
        if not system_prompt:
            system_prompt = getattr(agent, "_cached_system_prompt", "") or ""
        if tools is None:
            tools = getattr(agent, "tools", None)
    return estimate_transcript_retention(
        messages,
        system_prompt=system_prompt or "",
        tools=tools,
        pin_tokens=pin_tokens,
        open_epoch=open_epoch,
        working_memory_tokens=wm_tokens,
    )


def describe_compression_lock_skip(lock_signal: Any) -> str:
    """User-facing text for a manual /compress skipped by the compression lock.

    ``lock_signal`` is ``agent._compression_skipped_due_to_lock`` (or the
    ``holder`` carried by the TUI's ``CompressionLockHeld``): a descriptive
    holder string when another compressor CONFIRMED holds the lock, or
    ``True``/``None`` when acquisition failed without a confirmed holder
    (``hermes_state.try_acquire_compression_lock`` catches ``sqlite3.Error``
    internally and returns ``False``, so a failed acquire is NOT proof that
    another compression is running). The two cases must be worded
    differently: claiming "already in progress" on an unconfirmed failure
    misdirects the user when the real problem is a broken lock subsystem.
    """
    holder = (
        lock_signal
        if isinstance(lock_signal, str) and lock_signal.strip()
        else None
    )
    if holder:
        return (
            f"⏳ Compression already in progress for this session "
            f"(holder: {holder}). Please wait for it to finish."
        )
    return (
        "⏳ Compression skipped: could not acquire this session's "
        "compression lock. Another compression may still be running, or "
        "the lock check failed — try again shortly."
    )


def summarize_manual_compression(
    before_messages: Sequence[dict[str, Any]],
    after_messages: Sequence[dict[str, Any]],
    before_tokens: int,
    after_tokens: int,
    *,
    compression_state: Any = None,
    retention: Optional[Mapping[str, Any]] = None,
    agent: Any = None,
) -> dict[str, Any]:
    """Return consistent user-facing feedback for manual compression."""
    before_count = len(before_messages)
    after_count = len(after_messages)
    noop = list(after_messages) == list(before_messages)
    aborted = (
        compression_state is not None
        and getattr(compression_state, "_last_compress_aborted", False) is True
    )
    fallback_used = (
        compression_state is not None
        and getattr(compression_state, "_last_summary_fallback_used", False) is True
    )
    failure_reason = (
        getattr(compression_state, "_last_summary_error", None)
        if compression_state is not None
        else None
    )
    if not isinstance(failure_reason, str) or not failure_reason.strip():
        failure_reason = None

    skip_reason = None
    for source in (compression_state, agent):
        if source is None:
            continue
        candidate = getattr(source, "_last_compress_skip_reason", None)
        if isinstance(candidate, str) and candidate.strip():
            skip_reason = candidate.strip()
            break

    attached = False
    for source in (compression_state, agent):
        if source is None:
            continue
        if getattr(source, "_last_compress_attached_to_winner", False) is True:
            attached = True
            break

    reduced = max(0, int(before_tokens) - int(after_tokens))
    reduced_pct = (
        (100.0 * reduced / before_tokens) if before_tokens > 0 and reduced else 0.0
    )

    if aborted:
        headline = f"Compression aborted: {before_count} messages preserved"
    elif attached and not noop:
        headline = (
            f"Compressed (attached to in-flight /compress): "
            f"{before_count} → {after_count} messages"
        )
    elif skip_reason == "concurrent_lock":
        headline = (
            f"Compression busy: {before_count} messages unchanged "
            f"(concurrent /compress in flight)"
        )
    elif skip_reason == "already_rotated":
        headline = (
            f"Compression already completed elsewhere: "
            f"{before_count} live messages unchanged"
        )
    elif skip_reason == "history_race":
        headline = (
            f"Compression result discarded: history race "
            f"({before_count} messages kept in memory)"
        )
    elif skip_reason in {"peer_timeout", "compression_still_running"}:
        headline = (
            f"Compression wait timed out: {before_count} messages unchanged"
        )
    elif skip_reason == "peer_failed":
        headline = (
            f"Peer compression failed: {before_count} messages unchanged"
        )
    elif fallback_used:
        headline = (
            f"Compressed with fallback: {before_count} → {after_count} messages"
        )
    elif noop:
        headline = f"No changes from compression: {before_count} messages"
    else:
        headline = f"Compressed: {before_count} → {after_count} messages"

    if noop and after_tokens == before_tokens:
        token_line = (
            f"Before: {before_tokens:,} tokens\n"
            f"After: {after_tokens:,} tokens\n"
            f"Reduced: 0 tokens (0.0%)"
        )
    else:
        token_line = (
            f"Before: {before_tokens:,} tokens\n"
            f"After: {after_tokens:,} tokens\n"
            f"Reduced: {reduced:,} tokens ({reduced_pct:.1f}%)"
        )
    # Keep legacy single-line field for older UIs.
    if noop and after_tokens == before_tokens:
        legacy_token_line = (
            f"Approx request size: ~{before_tokens:,} tokens (unchanged)"
        )
    else:
        legacy_token_line = (
            f"Approx request size: ~{before_tokens:,} → "
            f"~{after_tokens:,} tokens"
        )

    note = None
    blocked_because: list[str] = []
    next_action = None

    if aborted:
        note = "Summary generation failed; no messages were removed."
        blocked_because.append("Summary LLM failed")
        next_action = "Fix the compression auxiliary model/provider, then retry /compress."
    elif attached and not noop:
        note = (
            "Adopted the in-flight /compress winner tip; this request did not "
            "run a second summariser or rotate the session again."
        )
        next_action = "Continue on the compressed tip; reload if the UI still shows the parent."
    elif skip_reason in _SKIP_REASON_COPY:
        note = _SKIP_REASON_COPY[skip_reason]
        blocked_because.append(skip_reason)
        if skip_reason == "concurrent_lock":
            next_action = (
                "Wait ~1–3 minutes for the in-flight summarizer, then reopen "
                "the latest session tip (compression rotates session_id)."
            )
        elif skip_reason == "already_rotated":
            next_action = "Reload / switch to the newest tip in this conversation lineage."
        else:
            next_action = "Retry /compress once, or /new if the session is wedged."
    elif fallback_used:
        dropped_count = getattr(
            compression_state, "_last_summary_dropped_count", None
        )
        if not isinstance(dropped_count, int) or isinstance(dropped_count, bool):
            dropped_count = max(before_count - after_count, 0)
        note = (
            "Summary generation failed; Hermes used limited fallback context "
            f"and removed {dropped_count} message(s)."
        )
    elif noop:
        note = (
            "The Hermes ContextCompressor ran but kept the full transcript "
            "(protected head/tail and/or nothing eligible to summarize). "
            "V2 pins and Working Memory are not compacted by /compress."
        )
        blocked_because.append("No eligible transcript reduction")
        open_epoch = int((retention or {}).get("v2_open_epoch") or 0)
        pin_tok = int((retention or {}).get("v2_open_epoch_pins") or 0)
        if open_epoch and pin_tok:
            blocked_because.append(
                f"Epoch {open_epoch} remains open with ~{pin_tok:,} pinned tokens "
                "(outside /compress authority)"
            )
            next_action = (
                "Run mutate → relevant lint/test/check → associate VERIFY with "
                "the open epoch so pins can close, or wait for pin-cap "
                "checkpointing. /compress alone cannot remove open-epoch pins."
            )
        else:
            next_action = (
                "Retry with `/compress here 2` to force a boundary, or `/new` "
                "if the session should start fresh."
            )
    elif not noop and after_count < before_count and after_tokens > before_tokens:
        note = (
            "Note: fewer messages can still raise this estimate when "
            "compression rewrites the transcript into denser summaries."
        )

    if failure_reason and (aborted or fallback_used):
        safe_reason = redact_sensitive_text(failure_reason.strip(), force=True)
        note = f"{note} Reason: {safe_reason}"

    retention_lines: list[str] = []
    if retention:
        retention_lines = format_retention_lines(retention)

    report_lines = [headline, *token_line.split("\n")]
    if retention_lines:
        report_lines.extend(retention_lines)
    if blocked_because:
        report_lines.append("Blocked because:")
        for item in blocked_because:
            report_lines.append(f"- {item}")
    if next_action:
        report_lines.append(f"Next: {next_action}")
    if note and note not in report_lines:
        report_lines.append(note)

    return {
        "noop": noop,
        "aborted": aborted,
        "fallback_used": fallback_used,
        "attached_to_winner": attached,
        "skip_reason": skip_reason,
        "headline": headline,
        "token_line": legacy_token_line,
        "token_report": token_line,
        "note": note,
        "blocked_because": blocked_because,
        "next_action": next_action,
        "retention": dict(retention) if retention else None,
        "report_lines": report_lines,
        "before_tokens": int(before_tokens),
        "after_tokens": int(after_tokens),
        "reduced_tokens": reduced,
        "reduced_pct": reduced_pct,
    }
