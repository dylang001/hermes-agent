"""Read-only aggregator for Context Engineering telemetry JSONL.

No config writes. No V2 runtime imports. Safe under observation mode.
"""

from __future__ import annotations

import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


_STREAM_FILES = {
    "shadow": "context_engineering_v2_shadow.jsonl",
    "soak": "context_engineering_v2_soak.jsonl",
    "pins": "context_engineering_v2_pins_shadow.jsonl",
    "archive": "context_engineering_v2_archive_shadow.jsonl",
    "assemble": "context_engineering_v2_assemble.jsonl",
    "pin_caps": "context_engineering_v2_pin_caps_shadow.jsonl",
    "short_bypass": "context_engineering_v2_short_bypass.jsonl",
}

_COMPRESS_START_RE = re.compile(
    r"context compression started: session=(\S+) messages=(\d+) tokens=~?([\d,]+)"
)
_COMPRESS_DONE_RE = re.compile(
    r"context compression done: session=(\S+) messages=(\d+)->(\d+)"
)
_COMPRESS_SKIP_RE = re.compile(
    r"compression skipped: another path is compressing session=(\S+)"
)


def _hermes_home() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        return Path.home() / ".hermes"


def logs_dir(home: Optional[Path] = None) -> Path:
    return (home or _hermes_home()) / "logs"


def load_jsonl(path: Path, *, max_lines: Optional[int] = None) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    if max_lines is not None and max_lines > 0:
        lines = lines[-max_lines:]
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _mean(vals: list[float]) -> Optional[float]:
    return statistics.mean(vals) if vals else None


def _median(vals: list[float]) -> Optional[float]:
    return statistics.median(vals) if vals else None


def _pct(n: float, d: float) -> Optional[float]:
    if d <= 0:
        return None
    return 100.0 * n / d


def _file_meta(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "path": str(path), "bytes": 0, "mtime": None}
    st = path.stat()
    return {
        "exists": True,
        "path": str(path),
        "bytes": int(st.st_size),
        "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        "mtime_epoch": float(st.st_mtime),
    }


def _layer_means(rows: Iterable[dict]) -> dict[str, Optional[float]]:
    keys = (
        "l1_system_tokens",
        "l1_tools_tokens",
        "l2_working_memory_tokens",
        "l3_recent_tokens",
        "l4_pinned_tokens",
        "l5_summary_tokens",
    )
    buckets: dict[str, list[float]] = {k: [] for k in keys}
    for r in rows:
        layers = r.get("layers") or {}
        if not isinstance(layers, dict):
            continue
        for k in keys:
            try:
                buckets[k].append(float(layers.get(k) or 0))
            except (TypeError, ValueError):
                continue
    return {k: _mean(v) for k, v in buckets.items()}


def summarize_shadow(rows: list[dict]) -> dict[str, Any]:
    if not rows:
        return {"records": 0}
    by_session: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_session[str(r.get("session_id") or "")].append(r)
    legacy = [float(r.get("legacy_attended_tokens") or 0) for r in rows]
    v2 = [float(r.get("v2_attended_tokens") or 0) for r in rows]
    v2_ex = [
        float(r.get("v2_attended_tokens_ex_wm") or r.get("v2_attended_tokens") or 0)
        for r in rows
    ]
    savings = [float(r.get("estimated_savings_tokens") or 0) for r in rows]
    top = []
    for sid, recs in sorted(by_session.items(), key=lambda kv: -len(kv[1]))[:20]:
        last = recs[-1]
        top.append(
            {
                "session_id": sid,
                "records": len(recs),
                "legacy": last.get("legacy_attended_tokens"),
                "v2": last.get("v2_attended_tokens"),
                "l4": (last.get("layers") or {}).get("l4_pinned_tokens"),
                "save_pct": last.get("estimated_savings_pct"),
            }
        )
    leg_mean = _mean(legacy) or 0.0
    sav_mean = _mean(savings) or 0.0
    return {
        "records": len(rows),
        "sessions": len(by_session),
        "legacy_mean": _mean(legacy),
        "legacy_p50": _median(legacy),
        "legacy_max": max(legacy) if legacy else None,
        "v2_ex_wm_mean": _mean(v2_ex),
        "v2_plus_wm_mean": _mean(v2),
        "savings_mean": _mean(savings),
        "savings_pct_of_legacy_mean": _pct(sav_mean, leg_mean),
        "layers_mean": _layer_means(rows),
        "top_sessions": top,
    }


def summarize_pins(rows: list[dict]) -> dict[str, Any]:
    if not rows:
        return {"records": 0}
    open_epoch = [r for r in rows if int(r.get("open_epoch") or 0) > 0]
    pin_counts = [float(r.get("pin_count") or 0) for r in rows]
    pin_toks = [float(r.get("pinned_tokens_est") or 0) for r in rows]
    close_reasons = Counter(
        str(r.get("last_close_reason") or "")
        for r in rows
        if r.get("last_close_reason")
    )
    events = Counter()
    for r in rows:
        for ev in r.get("events") or []:
            events[str(ev)] += 1
    by_session: dict[str, dict] = {}
    for r in rows:
        sid = str(r.get("session_id") or "")
        by_session[sid] = r
    top_pinned = sorted(
        (
            {
                "session_id": sid,
                "pin_count": int(r.get("pin_count") or 0),
                "pinned_tokens_est": int(r.get("pinned_tokens_est") or 0),
                "open_epoch": int(r.get("open_epoch") or 0),
            }
            for sid, r in by_session.items()
        ),
        key=lambda x: (-x["pinned_tokens_est"], -x["pin_count"]),
    )[:20]
    return {
        "records": len(rows),
        "open_epoch_rate_pct": _pct(len(open_epoch), len(rows)),
        "pin_count_mean": _mean(pin_counts),
        "pin_count_p50": _median(pin_counts),
        "pin_count_max": max(pin_counts) if pin_counts else None,
        "pinned_tokens_mean": _mean(pin_toks),
        "pinned_tokens_p50": _median(pin_toks),
        "pinned_tokens_max": max(pin_toks) if pin_toks else None,
        "close_reasons": dict(close_reasons.most_common(12)),
        "events": dict(events.most_common(20)),
        "top_pinned_sessions": top_pinned,
    }


def summarize_soak(rows: list[dict]) -> dict[str, Any]:
    if not rows:
        return {"records": 0}
    arms = Counter(str(r.get("arm") or "") for r in rows)
    steps = Counter(str(r.get("step") or "") for r in rows)
    retrieve = [float(r.get("retrieve_count") or 0) for r in rows]
    legacy = [float(r.get("legacy_tokens_est") or 0) for r in rows]
    layered = [float(r.get("layered_tokens_est") or 0) for r in rows]
    return {
        "records": len(rows),
        "arms": dict(arms),
        "steps": dict(steps),
        "retrieve_mean": _mean(retrieve),
        "retrieve_nonzero": sum(1 for v in retrieve if v > 0),
        "legacy_mean": _mean(legacy),
        "layered_mean": _mean(layered),
    }


def summarize_assemble(rows: list[dict]) -> dict[str, Any]:
    if not rows:
        return {"records": 0}
    legacy = [float(r.get("legacy_tokens_est") or 0) for r in rows]
    layered = [float(r.get("layered_tokens_est") or 0) for r in rows]
    saves = [l - y for l, y in zip(legacy, layered)]
    mutates = sum(1 for r in rows if r.get("mutates_prompt"))
    return {
        "records": len(rows),
        "legacy_mean": _mean(legacy),
        "layered_mean": _mean(layered),
        "inspect_savings_mean": _mean(saves),
        "mutates_prompt_count": mutates,
        "mutates_prompt_rate_pct": _pct(mutates, len(rows)),
    }


def summarize_archive(rows: list[dict]) -> dict[str, Any]:
    if not rows:
        return {"records": 0}
    legacy = [float(r.get("legacy_attended_tokens") or 0) for r in rows]
    v2 = [float(r.get("v2_attended_tokens_ex_wm") or 0) for r in rows]
    savings = [float(r.get("estimated_savings_tokens") or 0) for r in rows]
    archived_new = [float(r.get("archived_new") or 0) for r in rows]
    return {
        "records": len(rows),
        "legacy_mean": _mean(legacy),
        "v2_ex_wm_mean": _mean(v2),
        "savings_mean": _mean(savings),
        "archived_new_mean": _mean(archived_new),
    }


def summarize_optional(rows: list[dict], kind: str) -> dict[str, Any]:
    if not rows:
        return {"records": 0, "status": "pending_no_file_or_empty"}
    if kind == "short_bypass":
        reasons = Counter(str(r.get("reason") or "") for r in rows)
        legacy = [float(r.get("legacy_tokens_est") or 0) for r in rows]
        return {
            "records": len(rows),
            "status": "present",
            "reasons": dict(reasons.most_common(10)),
            "legacy_mean": _mean(legacy),
        }
    if kind == "pin_caps":
        triggered = sum(1 for r in rows if r.get("triggered"))
        return {
            "records": len(rows),
            "status": "present",
            "triggered": triggered,
            "triggered_rate_pct": _pct(triggered, len(rows)),
        }
    return {"records": len(rows), "status": "present"}


def parse_compression_events(agent_log: Path, *, max_bytes: int = 4_000_000) -> dict[str, Any]:
    if not agent_log.is_file():
        return {"starts": 0, "dones": 0, "skips": 0, "recent": []}
    try:
        size = agent_log.stat().st_size
        with agent_log.open("rb") as fh:
            if size > max_bytes:
                fh.seek(size - max_bytes)
            raw = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return {"starts": 0, "dones": 0, "skips": 0, "recent": []}
    starts = dones = skips = 0
    recent: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if "context compression started:" in line:
            starts += 1
            m = _COMPRESS_START_RE.search(line)
            if m:
                recent.append(
                    {
                        "kind": "started",
                        "session_id": m.group(1),
                        "messages": int(m.group(2)),
                        "tokens": int(m.group(3).replace(",", "")),
                    }
                )
        elif "context compression done:" in line:
            dones += 1
            m = _COMPRESS_DONE_RE.search(line)
            if m:
                recent.append(
                    {
                        "kind": "done",
                        "session_id": m.group(1),
                        "messages_before": int(m.group(2)),
                        "messages_after": int(m.group(3)),
                    }
                )
        elif "compression skipped: another path is compressing" in line:
            skips += 1
            m = _COMPRESS_SKIP_RE.search(line)
            if m:
                recent.append({"kind": "skipped_concurrent", "session_id": m.group(1)})
    return {
        "starts": starts,
        "dones": dones,
        "skips": skips,
        "recent": recent[-40:],
    }


def build_summary(
    *,
    home: Optional[Path] = None,
    max_lines: Optional[int] = None,
) -> dict[str, Any]:
    home = home or _hermes_home()
    log_root = logs_dir(home)
    streams: dict[str, Any] = {}
    loaded: dict[str, list[dict]] = {}
    for key, name in _STREAM_FILES.items():
        path = log_root / name
        meta = _file_meta(path)
        streams[key] = meta
        loaded[key] = load_jsonl(path, max_lines=max_lines) if meta["exists"] else []

    observation = {
        "mode": "observation",
        "no_v2_config_changes": True,
        "prs_held": ["#3 restore", "#4 shadow instrumentation"],
        "note": (
            "Dashboard is read-only over existing JSONL. Pin-cap and "
            "short-bypass streams appear only after those PRs are deployed."
        ),
    }

    freshest = None
    for meta in streams.values():
        if meta.get("mtime_epoch"):
            if freshest is None or meta["mtime_epoch"] > freshest:
                freshest = meta["mtime_epoch"]

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "hermes_home": str(home),
        "logs_dir": str(log_root),
        "observation": observation,
        "streams": streams,
        "telemetry_freshest_mtime": (
            datetime.fromtimestamp(freshest, tz=timezone.utc).isoformat()
            if freshest
            else None
        ),
        "shadow": summarize_shadow(loaded["shadow"]),
        "pins": summarize_pins(loaded["pins"]),
        "soak": summarize_soak(loaded["soak"]),
        "assemble": summarize_assemble(loaded["assemble"]),
        "archive": summarize_archive(loaded["archive"]),
        "pin_caps": summarize_optional(loaded["pin_caps"], "pin_caps"),
        "short_bypass": summarize_optional(loaded["short_bypass"], "short_bypass"),
        "compression": parse_compression_events(log_root / "agent.log"),
    }
