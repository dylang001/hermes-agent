"""Pure tool-call loop guardrail primitives.

The controller in this module is intentionally side-effect free: it tracks
per-turn tool-call observations and returns decisions. Runtime code owns whether
those decisions become warning guidance, synthetic tool results, strategy-change
payloads, or controlled turn halts.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from utils import safe_json_loads
from agent.tool_result_classification import file_mutation_result_landed

# Absolute paths embedded in terminal commands / file tool args.
# Prefer well-known roots, but also accept any multi-segment abs path so
# probes like `/engine/cli` participate in equivalent-failure signatures.
_ABS_PATH_RE = re.compile(
    r"(?<![\w.-])("
    r"/(?:root|opt|usr|home|var|tmp)[^\s;'\"`|&<>]*"
    r"|/(?:[^/\s;'\"`|&<>]+/){1,}[^/\s;'\"`|&<>]+"
    r")"
)
_MISSING_PATH_MARKERS = (
    "no such file or directory",
    "cannot access",
    "permission denied",
    "not a directory",
    "is a directory",
)
_NO_MATCH_MARKERS = (
    "no matches found",
    "no matches",
    "0 matches",
    "matched: 0",
    "did not match any files",
)
_COMMAND_CLASS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ripgrep", re.compile(r"(?:^|[\s;|&])(?:rg|ripgrep)\b")),
    ("grep", re.compile(r"(?:^|[\s;|&])grep\b")),
    ("find", re.compile(r"(?:^|[\s;|&])find\b")),
    ("fd", re.compile(r"(?:^|[\s;|&])fd\b")),
    ("git", re.compile(r"(?:^|[\s;|&])git\b")),
    ("ls", re.compile(r"(?:^|[\s;|&])ls\b")),
    ("python", re.compile(r"(?:^|[\s;|&])(?:python3?|ipython)\b")),
    ("systemctl", re.compile(r"(?:^|[\s;|&])systemctl\b")),
    ("cat", re.compile(r"(?:^|[\s;|&])(?:cat|head|tail)\b")),
)

_STRATEGY_SUGGESTIONS: dict[str, tuple[str, ...]] = {
    "grep": (
        "git ls-files / find / fd from the repo root",
        "ripgrep (rg) with a different root or glob",
        "python -c 'import pkgutil, inspect' to locate modules",
        "spawn an engineering/code-navigation subagent via delegate_task",
    ),
    "ripgrep": (
        "git ls-files or find/fd for repository discovery",
        "python inspect/pkgutil for installed packages",
        "inspect runtime roots (systemctl, ExecStart, /proc/<pid>/cwd)",
        "delegate_task to an engineering subagent",
    ),
    "ls": (
        "find / fd / git ls-files instead of repeated ls",
        "read_file / search_files on a known writable root",
        "runtime discovery via systemctl / EnvironmentFile / /proc/<pid>/cwd",
    ),
    "find": (
        "git ls-files or fd with a narrower pattern",
        "python inspect for package modules",
        "database / config inspection instead of source search",
    ),
    "default": (
        "change tool or target — do not repeat the same probe",
        "inspect runtime state (logs, timers, systemd, DB) if source search stalled",
        "validate independent workstreams (SMTP/IMAP/credentials/readiness) separately",
        "delegate_task when code navigation is the bottleneck",
        "escalate only for permissions, missing credentials, or destructive approval",
    ),
}


IDEMPOTENT_TOOL_NAMES = frozenset(
    {
        "read_file",
        "search_files",
        "web_search",
        "web_extract",
        "session_search",
        "browser_snapshot",
        "browser_console",
        "browser_get_images",
        "mcp_filesystem_read_file",
        "mcp_filesystem_read_text_file",
        "mcp_filesystem_read_multiple_files",
        "mcp_filesystem_list_directory",
        "mcp_filesystem_list_directory_with_sizes",
        "mcp_filesystem_directory_tree",
        "mcp_filesystem_get_file_info",
        "mcp_filesystem_search_files",
    }
)

MUTATING_TOOL_NAMES = frozenset(
    {
        "terminal",
        "execute_code",
        "write_file",
        "patch",
        "todo",
        "memory",
        "skill_manage",
        "browser_click",
        "browser_type",
        "browser_press",
        "browser_scroll",
        "browser_navigate",
        "send_message",
        "cronjob",
        "delegate_task",
        "process",
    }
)


@dataclass(frozen=True)
class ToolCallGuardrailConfig:
    """Thresholds for per-turn tool-call loop detection.

    Warnings are enabled by default and never prevent tool execution. Hard stops
    are explicit opt-in so interactive CLI/TUI sessions get a gentle nudge unless
    the user enables circuit-breaker behavior in config.yaml.

    Equivalent probe failures default to recovery-oriented strategy pivots
    (``planner_recovery_enabled``) rather than terminating the whole turn.
    """

    warnings_enabled: bool = True
    hard_stop_enabled: bool = False
    # When True (default), equivalent probe exhaustion returns StrategyChangeRequired
    # and continues the turn. When False, restores legacy task-halting behavior.
    planner_recovery_enabled: bool = True
    # Local scope + independent workstreams are always-on for recovery mode:
    # equivalent blocks are probe/workstream-scoped (never turn-global) so
    # alternate strategies and unrelated workstreams keep executing.
    exact_failure_warn_after: int = 2
    exact_failure_block_after: int = 5
    same_tool_failure_warn_after: int = 3
    same_tool_failure_halt_after: int = 8
    # Equivalent same-strategy retries (same tool/command-class/target/failure).
    equivalent_failure_warn_after: int = 1
    equivalent_retry_limit: int = 2
    # Materially different strategies allowed against the same workstream.
    strategy_pivot_limit: int = 5
    # Optional global investigation budget (distinct probe signatures that
    # exhausted). 0 disables the global cap.
    global_investigation_budget: int = 0
    no_progress_warn_after: int = 2
    no_progress_block_after: int = 5
    idempotent_tools: frozenset[str] = field(default_factory=lambda: IDEMPOTENT_TOOL_NAMES)
    mutating_tools: frozenset[str] = field(default_factory=lambda: MUTATING_TOOL_NAMES)

    # Back-compat alias used by older call sites / tests.
    @property
    def equivalent_failure_halt_after(self) -> int:
        return self.equivalent_retry_limit

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "ToolCallGuardrailConfig":
        """Build config from the `tool_loop_guardrails` config.yaml section."""
        if not isinstance(data, Mapping):
            return cls()

        warn_after = data.get("warn_after")
        if not isinstance(warn_after, Mapping):
            warn_after = {}
        hard_stop_after = data.get("hard_stop_after")
        if not isinstance(hard_stop_after, Mapping):
            hard_stop_after = {}

        defaults = cls()
        equivalent_retry = _positive_int(
            data.get(
                "equivalent_retry_limit",
                hard_stop_after.get(
                    "equivalent_failure",
                    data.get("equivalent_failure_halt_after"),
                ),
            ),
            defaults.equivalent_retry_limit,
        )
        return cls(
            warnings_enabled=_as_bool(data.get("warnings_enabled"), defaults.warnings_enabled),
            hard_stop_enabled=_as_bool(data.get("hard_stop_enabled"), defaults.hard_stop_enabled),
            planner_recovery_enabled=_as_bool(
                data.get("planner_recovery_enabled"), defaults.planner_recovery_enabled
            ),
            exact_failure_warn_after=_positive_int(
                warn_after.get("exact_failure", data.get("exact_failure_warn_after")),
                defaults.exact_failure_warn_after,
            ),
            same_tool_failure_warn_after=_positive_int(
                warn_after.get("same_tool_failure", data.get("same_tool_failure_warn_after")),
                defaults.same_tool_failure_warn_after,
            ),
            no_progress_warn_after=_positive_int(
                warn_after.get("idempotent_no_progress", data.get("no_progress_warn_after")),
                defaults.no_progress_warn_after,
            ),
            exact_failure_block_after=_positive_int(
                hard_stop_after.get("exact_failure", data.get("exact_failure_block_after")),
                defaults.exact_failure_block_after,
            ),
            same_tool_failure_halt_after=_positive_int(
                hard_stop_after.get("same_tool_failure", data.get("same_tool_failure_halt_after")),
                defaults.same_tool_failure_halt_after,
            ),
            equivalent_failure_warn_after=_positive_int(
                warn_after.get("equivalent_failure", data.get("equivalent_failure_warn_after")),
                defaults.equivalent_failure_warn_after,
            ),
            equivalent_retry_limit=equivalent_retry,
            strategy_pivot_limit=_positive_int(
                data.get("strategy_pivot_limit"), defaults.strategy_pivot_limit
            ),
            global_investigation_budget=_nonnegative_int(
                data.get("global_investigation_budget"), defaults.global_investigation_budget
            ),
            no_progress_block_after=_positive_int(
                hard_stop_after.get("idempotent_no_progress", data.get("no_progress_block_after")),
                defaults.no_progress_block_after,
            ),
        )


@dataclass(frozen=True)
class ToolCallSignature:
    """Stable, non-reversible identity for a tool name plus canonical args."""

    tool_name: str
    args_hash: str

    @classmethod
    def from_call(cls, tool_name: str, args: Mapping[str, Any] | None) -> "ToolCallSignature":
        canonical = canonical_tool_args(args or {})
        return cls(tool_name=tool_name, args_hash=_sha256(canonical))

    def to_metadata(self) -> dict[str, str]:
        """Return public metadata without raw argument values."""
        return {"tool_name": self.tool_name, "args_hash": self.args_hash}


@dataclass(frozen=True)
class FailureSignature:
    """Normalized identity for equivalent non-progressing probe failures."""

    tool: str
    command_class: str
    target: str
    failure_class: str
    exit_code: str
    stderr_class: str

    @property
    def key(self) -> str:
        return "|".join(
            (
                self.tool,
                self.command_class,
                self.target,
                self.failure_class,
                self.exit_code,
                self.stderr_class,
            )
        )

    @property
    def probe_key(self) -> str:
        """Args-only key used to block equivalent retries before execution."""
        return f"{self.tool}|{self.command_class}|{self.target}"

    @property
    def workstream(self) -> str:
        return self.target or f"{self.tool}:unscoped"

    def to_dict(self) -> dict[str, str]:
        return {
            "tool": self.tool,
            "command_class": self.command_class,
            "target": self.target,
            "failure_class": self.failure_class,
            "exit_code": self.exit_code,
            "stderr_class": self.stderr_class,
            "key": self.key,
            "probe_key": self.probe_key,
            "workstream": self.workstream,
        }


@dataclass(frozen=True)
class ToolGuardrailDecision:
    """Decision returned by the tool-call guardrail controller."""

    action: str = "allow"  # allow | warn | block | halt | strategy_change
    code: str = "allow"
    message: str = ""
    tool_name: str = ""
    count: int = 0
    signature: ToolCallSignature | None = None
    recovery: Mapping[str, Any] | None = None

    @property
    def allows_execution(self) -> bool:
        return self.action in {"allow", "warn"}

    @property
    def should_halt(self) -> bool:
        # strategy_change is local: block the probe, continue the turn.
        if self.action == "strategy_change":
            return False
        return self.action in {"block", "halt"}

    def to_metadata(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "action": self.action,
            "code": self.code,
            "message": self.message,
            "tool_name": self.tool_name,
            "count": self.count,
        }
        if self.signature is not None:
            data["signature"] = self.signature.to_metadata()
        if self.recovery is not None:
            data["recovery"] = dict(self.recovery)
        return data


def canonical_tool_args(args: Mapping[str, Any]) -> str:
    """Return sorted compact JSON for parsed tool arguments."""
    if not isinstance(args, Mapping):
        raise TypeError(f"tool args must be a mapping, got {type(args).__name__}")
    return json.dumps(
        args,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def classify_tool_failure(tool_name: str, result: str | None) -> tuple[bool, str]:
    """Safety-fallback classifier used only when callers don't pass ``failed``.

    Mirrors ``agent.display._detect_tool_failure`` exactly so the guardrail
    never disagrees with the CLI's user-visible ``[error]`` tag. Production
    callers in ``run_agent.py`` always pass an explicit ``failed=`` derived
    from ``_detect_tool_failure``; this function exists so standalone callers
    (tests, tooling) still get consistent behavior.
    """
    if result is None:
        return False, ""
    if file_mutation_result_landed(tool_name, result):
        return False, ""

    if tool_name == "terminal":
        data = safe_json_loads(result)
        if isinstance(data, dict):
            exit_code = data.get("exit_code")
            if exit_code is not None and exit_code != 0:
                return True, f" [exit {exit_code}]"
        return False, ""

    if tool_name == "memory":
        data = safe_json_loads(result)
        if isinstance(data, dict):
            if data.get("success") is False and "exceed the limit" in data.get("error", ""):
                return True, " [full]"

    lower = result[:500].lower()
    if '"error"' in lower or '"failed"' in lower or result.startswith("Error"):
        return True, " [error]"

    return False, ""


class ToolCallGuardrailController:
    """Per-turn controller for repeated failed/non-progressing tool calls."""

    def __init__(self, config: ToolCallGuardrailConfig | None = None):
        self.config = config or ToolCallGuardrailConfig()
        self.reset_for_turn()

    def reset_for_turn(self) -> None:
        self._exact_failure_counts: dict[ToolCallSignature, int] = {}
        self._same_tool_failure_counts: dict[str, int] = {}
        self._equivalent_failure_counts: dict[str, int] = {}
        self._blocked_probe_keys: set[str] = set()
        self._commands_attempted: dict[str, list[str]] = {}
        self._strategy_pivot_counts: dict[str, int] = {}
        self._exhausted_probe_signatures: set[str] = set()
        self._no_progress: dict[ToolCallSignature, tuple[str, int]] = {}
        self._halt_decision: ToolGuardrailDecision | None = None
        self._pending_telemetry: list[dict[str, Any]] = []

    @property
    def halt_decision(self) -> ToolGuardrailDecision | None:
        return self._halt_decision

    def drain_telemetry(self) -> list[dict[str, Any]]:
        """Return and clear side-effect-free telemetry events for the runtime."""
        events = list(self._pending_telemetry)
        self._pending_telemetry.clear()
        return events

    def before_call(self, tool_name: str, args: Mapping[str, Any] | None) -> ToolGuardrailDecision:
        args = _coerce_args(args)
        signature = ToolCallSignature.from_call(tool_name, args)
        if not self.config.hard_stop_enabled:
            return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

        exact_count = self._exact_failure_counts.get(signature, 0)
        if exact_count >= self.config.exact_failure_block_after:
            decision = ToolGuardrailDecision(
                action="block",
                code="repeated_exact_failure_block",
                message=(
                    f"Blocked {tool_name}: the same tool call failed {exact_count} "
                    "times with identical arguments. Stop retrying it unchanged; "
                    "change strategy or explain the blocker."
                ),
                tool_name=tool_name,
                count=exact_count,
                signature=signature,
            )
            self._halt_decision = decision
            return decision

        probe = build_probe_identity(tool_name, args)
        if probe is not None and probe.probe_key in self._blocked_probe_keys:
            # Local block only — never terminate the turn for a blocked probe.
            # Independent workstreams and alternate strategies remain available.
            recovery = self._strategy_change_payload(
                probe,
                commands=self._commands_attempted.get(probe.workstream, []),
                count=self._count_for_probe(probe),
            )
            decision = ToolGuardrailDecision(
                action="strategy_change",
                code="strategy_change_required",
                message=recovery["message"],
                tool_name=tool_name,
                count=recovery["count"],
                signature=signature,
                recovery=recovery,
            )
            self._queue_telemetry(
                "guardrail_blocked_equivalent_probe",
                probe=probe,
                decision=decision,
            )
            return decision

        # Legacy path-only key: keep blocking cosmetic retries when recovery is off.
        if not self.config.planner_recovery_enabled:
            eq_key = equivalent_failure_key(tool_name, args)
            if eq_key is not None:
                eq_count = self._equivalent_failure_counts.get(eq_key, 0)
                if eq_count >= self.config.equivalent_retry_limit:
                    decision = ToolGuardrailDecision(
                        action="block",
                        code="equivalent_path_failure_block",
                        message=(
                            f"Blocked {tool_name}: equivalent probes of the same missing "
                            f"path failed {eq_count} times (key={eq_key}). Do not retry "
                            "with cosmetic command changes (pwd/echo/ls variations). "
                            "Inspect authoritative runtime roots, use a different path "
                            "or tool, or report the blocker."
                        ),
                        tool_name=tool_name,
                        count=eq_count,
                        signature=signature,
                    )
                    self._halt_decision = decision
                    return decision

        if self._is_idempotent(tool_name):
            record = self._no_progress.get(signature)
            if record is not None:
                _result_hash, repeat_count = record
                if repeat_count >= self.config.no_progress_block_after:
                    decision = ToolGuardrailDecision(
                        action="block",
                        code="idempotent_no_progress_block",
                        message=(
                            f"Blocked {tool_name}: this read-only call returned the same "
                            f"result {repeat_count} times. Stop repeating it unchanged; "
                            "use the result already provided or try a different query."
                        ),
                        tool_name=tool_name,
                        count=repeat_count,
                        signature=signature,
                    )
                    self._halt_decision = decision
                    return decision

        return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

    def after_call(
        self,
        tool_name: str,
        args: Mapping[str, Any] | None,
        result: str | None,
        *,
        failed: bool | None = None,
    ) -> ToolGuardrailDecision:
        args = _coerce_args(args)
        signature = ToolCallSignature.from_call(tool_name, args)
        if failed is None:
            failed, _ = classify_tool_failure(tool_name, result)

        if failed:
            exact_count = self._exact_failure_counts.get(signature, 0) + 1
            self._exact_failure_counts[signature] = exact_count
            self._no_progress.pop(signature, None)

            same_count = self._same_tool_failure_counts.get(tool_name, 0) + 1
            self._same_tool_failure_counts[tool_name] = same_count

            failure_sig = build_failure_signature(tool_name, args, result)
            eq_count = 0
            if failure_sig is not None:
                eq_count = self._equivalent_failure_counts.get(failure_sig.key, 0) + 1
                self._equivalent_failure_counts[failure_sig.key] = eq_count
                # Also track legacy path-only key for recovery-disabled mode.
                legacy_key = equivalent_failure_key(tool_name, args)
                if legacy_key is not None:
                    self._equivalent_failure_counts[legacy_key] = (
                        self._equivalent_failure_counts.get(legacy_key, 0) + 1
                    )
                cmd = _command_text(tool_name, args)
                if cmd:
                    attempted = self._commands_attempted.setdefault(failure_sig.workstream, [])
                    if cmd not in attempted:
                        attempted.append(cmd)

            if (
                self.config.hard_stop_enabled
                and failure_sig is not None
                and eq_count >= self.config.equivalent_retry_limit
            ):
                recovery = self._strategy_change_payload(
                    failure_sig,
                    commands=self._commands_attempted.get(failure_sig.workstream, []),
                    count=eq_count,
                )
                if (
                    not self.config.planner_recovery_enabled
                    or self._should_escalate_workstream(failure_sig.workstream, about_to_pivot=True)
                ):
                    code = (
                        "strategy_pivots_exhausted"
                        if self.config.planner_recovery_enabled
                        else "equivalent_path_failure_halt"
                    )
                    decision = ToolGuardrailDecision(
                        action="halt",
                        code=code,
                        message=(
                            f"Stopped {tool_name}: recovery strategies for "
                            f"{failure_sig.workstream} are exhausted after "
                            f"{self._strategy_pivot_counts.get(failure_sig.workstream, 0)} "
                            "pivots / equivalent retries. Escalate only for a genuine "
                            "external blocker (permissions, credentials, destructive approval)."
                            if code == "strategy_pivots_exhausted"
                            else (
                                f"Stopped {tool_name}: equivalent probes of path target "
                                f"{failure_sig.target or failure_sig.key} failed {eq_count} times. "
                                "Do not retry with syntactically different commands against "
                                "the same missing path."
                            )
                        ),
                        tool_name=tool_name,
                        count=eq_count,
                        signature=signature,
                        recovery=recovery,
                    )
                    self._halt_decision = decision
                    self._queue_telemetry(
                        "guardrail_halt",
                        probe=failure_sig,
                        decision=decision,
                    )
                    return decision

                # Recovery path: mark this probe exhausted, count a pivot, continue.
                self._blocked_probe_keys.add(failure_sig.probe_key)
                self._exhausted_probe_signatures.add(failure_sig.key)
                self._strategy_pivot_counts[failure_sig.workstream] = (
                    self._strategy_pivot_counts.get(failure_sig.workstream, 0) + 1
                )
                decision = ToolGuardrailDecision(
                    action="strategy_change",
                    code="strategy_change_required",
                    message=recovery["message"],
                    tool_name=tool_name,
                    count=eq_count,
                    signature=signature,
                    recovery=recovery,
                )
                self._queue_telemetry(
                    "guardrail_strategy_change",
                    probe=failure_sig,
                    decision=decision,
                    extra={
                        "strategy_pivots": self._strategy_pivot_counts.get(
                            failure_sig.workstream, 0
                        ),
                    },
                )
                return decision

            if self.config.hard_stop_enabled and same_count >= self.config.same_tool_failure_halt_after:
                decision = ToolGuardrailDecision(
                    action="halt",
                    code="same_tool_failure_halt",
                    message=(
                        f"Stopped {tool_name}: it failed {same_count} times this turn. "
                        "Stop retrying the same failing tool path and choose a different approach."
                    ),
                    tool_name=tool_name,
                    count=same_count,
                    signature=signature,
                )
                self._halt_decision = decision
                return decision

            if (
                self.config.warnings_enabled
                and failure_sig is not None
                and eq_count >= self.config.equivalent_failure_warn_after
            ):
                return ToolGuardrailDecision(
                    action="warn",
                    code="equivalent_path_failure_warning",
                    message=_path_failure_recovery_hint(
                        tool_name, failure_sig.target or failure_sig.key, eq_count
                    ),
                    tool_name=tool_name,
                    count=eq_count,
                    signature=signature,
                    recovery=self._strategy_change_payload(
                        failure_sig,
                        commands=self._commands_attempted.get(failure_sig.workstream, []),
                        count=eq_count,
                    ),
                )

            if self.config.warnings_enabled and exact_count >= self.config.exact_failure_warn_after:
                return ToolGuardrailDecision(
                    action="warn",
                    code="repeated_exact_failure_warning",
                    message=(
                        f"{tool_name} has failed {exact_count} times with identical arguments. "
                        "This looks like a loop; inspect the error and change strategy "
                        "instead of retrying it unchanged."
                    ),
                    tool_name=tool_name,
                    count=exact_count,
                    signature=signature,
                )

            if self.config.warnings_enabled and same_count >= self.config.same_tool_failure_warn_after:
                return ToolGuardrailDecision(
                    action="warn",
                    code="same_tool_failure_warning",
                    message=_tool_failure_recovery_hint(tool_name, same_count),
                    tool_name=tool_name,
                    count=same_count,
                    signature=signature,
                )

            return ToolGuardrailDecision(tool_name=tool_name, count=exact_count, signature=signature)

        # Success: clear exact/same-tool streaks. A successful different probe
        # under a workstream resets that workstream's equivalent retry counters.
        self._exact_failure_counts.pop(signature, None)
        self._same_tool_failure_counts.pop(tool_name, None)
        probe = build_probe_identity(tool_name, args)
        if probe is not None:
            self._reset_equivalent_counters_for_workstream(probe.workstream)
            if probe.probe_key in self._blocked_probe_keys:
                self._queue_telemetry(
                    "guardrail_recovery_success",
                    probe=probe,
                    decision=ToolGuardrailDecision(tool_name=tool_name, signature=signature),
                )

        if not self._is_idempotent(tool_name):
            self._no_progress.pop(signature, None)
            return ToolGuardrailDecision(tool_name=tool_name, signature=signature)

        result_hash = _result_hash(result)
        previous = self._no_progress.get(signature)
        repeat_count = 1
        if previous is not None and previous[0] == result_hash:
            repeat_count = previous[1] + 1
        self._no_progress[signature] = (result_hash, repeat_count)

        if self.config.warnings_enabled and repeat_count >= self.config.no_progress_warn_after:
            return ToolGuardrailDecision(
                action="warn",
                code="idempotent_no_progress_warning",
                message=(
                    f"{tool_name} returned the same result {repeat_count} times. "
                    "Use the result already provided or change the query instead of "
                    "repeating it unchanged."
                ),
                tool_name=tool_name,
                count=repeat_count,
                signature=signature,
            )

        return ToolGuardrailDecision(tool_name=tool_name, count=repeat_count, signature=signature)

    def _is_idempotent(self, tool_name: str) -> bool:
        if tool_name in self.config.mutating_tools:
            return False
        return tool_name in self.config.idempotent_tools

    def _count_for_probe(self, probe: FailureSignature) -> int:
        matching = [
            count
            for key, count in self._equivalent_failure_counts.items()
            if key == probe.key or key.startswith(probe.probe_key + "|")
        ]
        if matching:
            return max(matching)
        return self.config.equivalent_retry_limit

    def _should_escalate_workstream(self, workstream: str, *, about_to_pivot: bool = False) -> bool:
        pivots = self._strategy_pivot_counts.get(workstream, 0)
        # Already used the full pivot budget — next equivalent exhaustion escalates.
        if about_to_pivot and pivots >= self.config.strategy_pivot_limit:
            return True
        if (
            self.config.global_investigation_budget > 0
            and len(self._exhausted_probe_signatures) >= self.config.global_investigation_budget
            and about_to_pivot
        ):
            return True
        return False

    def _reset_equivalent_counters_for_workstream(self, workstream: str) -> None:
        """A successful pivot resets equivalent retry counters for that workstream."""
        drop_keys = [
            key
            for key in self._equivalent_failure_counts
            if key == f"terminal:{workstream}"
            or key.endswith(f"|{workstream}|")
            or f"|{workstream}|" in f"|{key}|"
            or key.endswith(f":{workstream}")
        ]
        # Prefer exact workstream bookkeeping via probe keys.
        drop_probes = {pk for pk in self._blocked_probe_keys if pk.endswith(f"|{workstream}")}
        for key in drop_keys:
            self._equivalent_failure_counts.pop(key, None)
        self._blocked_probe_keys -= drop_probes
        self._exhausted_probe_signatures = {
            key
            for key in self._exhausted_probe_signatures
            if f"|{workstream}|" not in f"|{key}|"
        }

    def _strategy_change_payload(
        self,
        probe: FailureSignature,
        *,
        commands: list[str],
        count: int,
    ) -> dict[str, Any]:
        suggestions = list(
            _STRATEGY_SUGGESTIONS.get(probe.command_class, _STRATEGY_SUGGESTIONS["default"])
        )
        message = (
            "StrategyChangeRequired: current diagnostic approach exhausted for "
            f"{probe.probe_key} after {count} equivalent failure(s). "
            "Select a materially different strategy; continue independent workstreams. "
            "This is not a task failure."
        )
        return {
            "StrategyChangeRequired": True,
            "failure_signature": probe.to_dict(),
            "commands_attempted": list(commands),
            "affected_path": probe.target,
            "suggested_alternative_strategies": suggestions,
            "planner_directive": (
                "Current approach exhausted. Select a different diagnostic strategy."
            ),
            "message": message,
            "count": count,
            "strategy_pivots": self._strategy_pivot_counts.get(probe.workstream, 0),
            "strategy_pivot_limit": self.config.strategy_pivot_limit,
        }

    def _queue_telemetry(
        self,
        event: str,
        *,
        probe: FailureSignature,
        decision: ToolGuardrailDecision,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "event": event,
            "code": decision.code,
            "action": decision.action,
            "tool_name": decision.tool_name,
            "count": decision.count,
            "failure_signature": probe.to_dict(),
            "commands_blocked": list(self._commands_attempted.get(probe.workstream, [])),
        }
        if extra:
            payload.update(dict(extra))
        self._pending_telemetry.append(payload)


def toolguard_synthetic_result(decision: ToolGuardrailDecision) -> str:
    """Build a synthetic role=tool content string for a blocked tool call."""
    payload: dict[str, Any] = {
        "error": decision.message,
        "guardrail": decision.to_metadata(),
    }
    if decision.recovery is not None:
        payload["StrategyChangeRequired"] = decision.recovery.get("StrategyChangeRequired", True)
        for key in (
            "failure_signature",
            "commands_attempted",
            "affected_path",
            "suggested_alternative_strategies",
            "planner_directive",
        ):
            if key in decision.recovery:
                payload[key] = decision.recovery[key]
    return json.dumps(payload, ensure_ascii=False)


def append_toolguard_guidance(result: str, decision: ToolGuardrailDecision) -> str:
    """Append runtime guidance to the current tool result content."""
    if decision.action not in {"warn", "halt", "strategy_change"} or not decision.message:
        return result
    if decision.action == "halt":
        label = "Tool loop hard stop"
    elif decision.action == "strategy_change":
        label = "StrategyChangeRequired"
    else:
        label = "Tool loop warning"
    suffix = (
        f"\n\n[{label}: "
        f"{decision.code}; count={decision.count}; {decision.message}]"
    )
    if decision.action == "strategy_change" and decision.recovery:
        try:
            suffix += "\n" + json.dumps(
                {
                    "StrategyChangeRequired": decision.recovery.get("StrategyChangeRequired", True),
                    "failure_signature": decision.recovery.get("failure_signature"),
                    "commands_attempted": decision.recovery.get("commands_attempted"),
                    "affected_path": decision.recovery.get("affected_path"),
                    "suggested_alternative_strategies": decision.recovery.get(
                        "suggested_alternative_strategies"
                    ),
                    "planner_directive": decision.recovery.get("planner_directive"),
                },
                ensure_ascii=False,
            )
        except TypeError:
            pass
    return (result or "") + suffix


def _tool_failure_recovery_hint(tool_name: str, count: int) -> str:
    """Action-oriented guidance for recovering from repeated tool failures."""
    common = (
        f"{tool_name} has failed {count} times this turn. This looks like a loop. "
        "Do not switch to text-only replies; keep using tools, but diagnose before retrying. "
        "First inspect the latest error/output and verify your assumptions. "
    )
    if tool_name == "terminal":
        return common + (
            "For terminal failures, change strategy: read authoritative runtime roots from "
            "the system prompt, avoid stale /root paths, and use a different tool "
            "(read_file/search_files) or a different absolute path under Writable roots. "
            "Cosmetic retries (pwd/echo/ls variations of the same missing path) are not progress."
        )
    return common + (
        "Try different arguments, a narrower query/path, an absolute path when relevant, "
        "or a different tool that can make progress. If the blocker is external, report "
        "the blocker after one diagnostic attempt instead of repeating the same failing path."
    )


def _path_failure_recovery_hint(tool_name: str, eq_key: str, count: int) -> str:
    """Guidance after the first equivalent missing-path failure."""
    try:
        from agent.runtime_metadata import collect_runtime_metadata, remap_stale_paths

        meta = collect_runtime_metadata()
        path = eq_key.split(":", 1)[-1] if ":" in eq_key and not eq_key.startswith("/") else eq_key
        remapped = remap_stale_paths(path, meta)
        roots = ", ".join(meta.writable_roots[:6]) or meta.hermes_home
        return (
            f"{tool_name} failed {count} time(s) against equivalent path target {eq_key}. "
            "Do not retry with a syntactically different command against the same path. "
            f"Authoritative writable roots: {roots}. "
            f"If this was a stale migration path, try: {remapped}. "
            "Change strategy: list a writable root, use read_file/search_files, or abandon "
            "the missing path and report the blocker."
        )
    except Exception:
        return (
            f"{tool_name} failed {count} time(s) against equivalent path target {eq_key}. "
            "Do not retry with cosmetic command changes. Inspect authoritative runtime "
            "roots from the system prompt and choose a different path or tool."
        )


def looks_like_missing_path_failure(result: str | None) -> bool:
    """True when a tool result indicates a missing/inaccessible filesystem path."""
    if not result:
        return False
    lower = result[:2000].lower()
    return any(marker in lower for marker in _MISSING_PATH_MARKERS)


def looks_like_no_match_failure(result: str | None) -> bool:
    """True when a search-style tool result indicates zero matches / empty hit set."""
    if not result:
        return False
    lower = result[:2000].lower()
    if any(marker in lower for marker in _NO_MATCH_MARKERS):
        return True
    data = safe_json_loads(result)
    if not isinstance(data, dict):
        return False
    exit_code = data.get("exit_code")
    stdout = str(data.get("stdout") or "").strip()
    stderr = str(data.get("stderr") or "").strip().lower()
    if exit_code == 1 and not stdout and (
        not stderr or any(marker in stderr for marker in _NO_MATCH_MARKERS)
    ):
        return True
    return False


def classify_command_class(tool_name: str, args: Mapping[str, Any] | None) -> str:
    """Classify the primary CLI/tool strategy represented by a call."""
    if tool_name != "terminal":
        return tool_name
    command = _command_text(tool_name, args)
    if not command:
        return "other"
    for name, pattern in _COMMAND_CLASS_PATTERNS:
        if pattern.search(command):
            return name
    return "other"


def classify_stderr_class(result: str | None) -> str:
    if not result:
        return "empty"
    lower = result[:2000].lower()
    if "permission denied" in lower:
        return "permission_denied"
    if "no such file" in lower or "cannot access" in lower:
        return "missing_path"
    if any(marker in lower for marker in _NO_MATCH_MARKERS):
        return "no_matches"
    data = safe_json_loads(result)
    if isinstance(data, dict):
        stderr = str(data.get("stderr") or "").strip()
        if not stderr:
            return "empty_stderr"
    return "other"


def classify_failure_class(result: str | None) -> str:
    if looks_like_missing_path_failure(result):
        lower = (result or "")[:2000].lower()
        if "permission denied" in lower:
            return "permission"
        return "missing_path"
    if looks_like_no_match_failure(result):
        return "no_matches"
    data = safe_json_loads(result or "")
    if isinstance(data, dict) and data.get("exit_code") not in (None, 0):
        return "exit_nonzero"
    return "other"


def build_probe_identity(
    tool_name: str, args: Mapping[str, Any] | None
) -> FailureSignature | None:
    """Build a probe identity from args alone (no result yet)."""
    target = _preferred_target(tool_name, args)
    if not target and tool_name == "terminal":
        # Still track command-class-only probes when no abs path is present.
        command_class = classify_command_class(tool_name, args)
        if command_class == "other":
            return None
        target = f"cmd:{command_class}"
    elif not target:
        return None
    return FailureSignature(
        tool=tool_name,
        command_class=classify_command_class(tool_name, args),
        target=target,
        failure_class="unknown",
        exit_code="",
        stderr_class="",
    )


def build_failure_signature(
    tool_name: str,
    args: Mapping[str, Any] | None,
    result: str | None,
) -> FailureSignature | None:
    """Construct a normalized failure signature when the result is trackable."""
    if not is_trackable_probe_failure(tool_name, args, result):
        return None
    probe = build_probe_identity(tool_name, args)
    if probe is None:
        return None
    exit_code = ""
    data = safe_json_loads(result or "")
    if isinstance(data, dict) and data.get("exit_code") is not None:
        exit_code = str(data.get("exit_code"))
    return FailureSignature(
        tool=probe.tool,
        command_class=probe.command_class,
        target=probe.target,
        failure_class=classify_failure_class(result),
        exit_code=exit_code,
        stderr_class=classify_stderr_class(result),
    )


def is_trackable_probe_failure(
    tool_name: str,
    args: Mapping[str, Any] | None,
    result: str | None,
) -> bool:
    """Whether this failure should feed the equivalent-probe / strategy-pivot budget."""
    if looks_like_missing_path_failure(result):
        return True
    command_class = classify_command_class(tool_name, args)
    if command_class in {"grep", "ripgrep", "find", "fd", "ls", "git", "cat"} and (
        looks_like_no_match_failure(result) or looks_like_missing_path_failure(result)
    ):
        return True
    return False


def extract_absolute_path_targets(tool_name: str, args: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Extract absolute path targets from common tool argument shapes."""
    args = _coerce_args(args)
    blobs: list[str] = []
    if tool_name == "terminal":
        for key in ("command", "cmd", "working_directory", "cwd"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                blobs.append(value)
    else:
        for key in ("path", "file_path", "directory", "target", "cwd"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                blobs.append(value)
        command = args.get("command")
        if isinstance(command, str):
            blobs.append(command)

    found: list[str] = []
    seen: set[str] = set()
    for blob in blobs:
        for match in _ABS_PATH_RE.findall(blob):
            cleaned = match.rstrip("/").rstrip(")'\",")
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                found.append(cleaned)
    return tuple(found)


def equivalent_failure_key(tool_name: str, args: Mapping[str, Any] | None) -> str | None:
    """Stable key for 'same missing path, different command syntax' retries."""
    target = _preferred_target(tool_name, args)
    if not target:
        return None
    return f"{tool_name}:{target}"


def _preferred_target(tool_name: str, args: Mapping[str, Any] | None) -> str | None:
    targets = extract_absolute_path_targets(tool_name, args)
    if not targets:
        return None
    preferred = next((t for t in targets if t.startswith("/root") or "/hermes" in t), targets[0])
    return preferred.rstrip("/")


def _command_text(tool_name: str, args: Mapping[str, Any] | None) -> str:
    args = _coerce_args(args)
    if tool_name == "terminal":
        for key in ("command", "cmd"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _coerce_args(args: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return args if isinstance(args, Mapping) else {}


def _result_hash(result: str | None) -> str:
    parsed = safe_json_loads(result or "")
    if parsed is not None:
        try:
            canonical = json.dumps(
                parsed,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        except TypeError:
            canonical = str(parsed)
    else:
        canonical = result or ""
    return _sha256(canonical)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enabled"}:
            return True
        if lowered in {"0", "false", "no", "off", "disabled"}:
            return False
    return default


def _positive_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 1 else default


def _nonnegative_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 0 else default


def _sha256(value: str) -> str:
    # surrogatepass: tool results scraped from the web can carry unpaired
    # UTF-16 surrogates (e.g. half of a mathematical-bold pair); a strict
    # encode raises and takes down the whole conversation loop. The hash only
    # needs deterministic bytes, not valid UTF-8.
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()
