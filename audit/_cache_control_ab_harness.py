#!/usr/bin/env python3
"""Track A — EXPLICIT prompt-cache A/B on OpenCode Go Anthropic wire.

Validates the transport capability layer (not MiniMax-slug gating): OpenCode
Go + anthropic_messages advertises EXPLICIT/native for any model on that wire.

Strict scope (half-day max):
  * Arm OFF: no cache_control markers
  * Arm ON:  Hermes system_and_3 native markers (apply_anthropic_cache_control)
  * Deterministic 20-turn Anthropic Messages loop against OpenCode Go
  * Metrics: cache hit %, cache writes/reads, latency, approx Go list $, completion
  * Decision: keep ON only if cache-hit improvement > 5pp OR list-$ savings > 5%

Does not modify MEMORY.md / USER.md / config.yaml.
Writes JSON + MD under audit/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("HERMES_HOME", str(Path.home() / ".hermes"))
_env = Path(os.environ["HERMES_HOME"]) / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

# OpenCode Go MiniMax M3 list rates (opencode.ai/docs/go) — for relative A/B only.
_GO_M3_INPUT = 0.30
_GO_M3_CACHE = 0.06
_GO_M3_OUTPUT = 1.20

TURNS = 20
MODEL = "minimax-m3"
# Anthropic Messages surface for MiniMax on Go
MESSAGES_URL = "https://opencode.ai/zen/go/v1/messages"

STABLE_SYSTEM = (
    "You are a deterministic benchmark agent. "
    "For every user turn, call the tool `echo_probe` exactly once with "
    "the provided turn index, then stop. Do not explain. Do not call other tools."
)

TOOLS = [
    {
        "name": "echo_probe",
        "description": "Acknowledge a benchmark turn index.",
        "input_schema": {
            "type": "object",
            "properties": {
                "turn": {"type": "integer", "description": "1-based turn index"},
            },
            "required": ["turn"],
        },
    }
]


def _load_key() -> str:
    key = os.environ.get("OPENCODE_GO_API_KEY", "").strip()
    if not key:
        raise SystemExit("OPENCODE_GO_API_KEY missing — cannot run live A/B")
    return key


def _usage_from_body(body: Dict[str, Any]) -> Dict[str, int]:
    usage = body.get("usage") or {}
    # Anthropic / MiniMax fields
    inp = int(usage.get("input_tokens") or 0)
    out = int(usage.get("output_tokens") or 0)
    cr = int(
        usage.get("cache_read_input_tokens")
        or usage.get("cache_read_tokens")
        or 0
    )
    cw = int(
        usage.get("cache_creation_input_tokens")
        or usage.get("cache_write_tokens")
        or 0
    )
    # Some gateways nest under prompt_tokens_details
    details = usage.get("prompt_tokens_details") or {}
    if not cr:
        cr = int(details.get("cached_tokens") or 0)
    if not cw:
        cw = int(details.get("cache_creation_tokens") or 0)
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_tokens": cr,
        "cache_write_tokens": cw,
    }


def _list_cost_usd(u: Dict[str, int]) -> float:
    return (
        (u["input_tokens"] / 1_000_000) * _GO_M3_INPUT
        + (u["cache_read_tokens"] / 1_000_000) * _GO_M3_CACHE
        + (u["output_tokens"] / 1_000_000) * _GO_M3_OUTPUT
        + (u["cache_write_tokens"] / 1_000_000) * (_GO_M3_INPUT * 1.25)
    )


def _hit_pct(u: Dict[str, int]) -> float:
    denom = u["input_tokens"] + u["cache_read_tokens"]
    if denom <= 0:
        return 0.0
    return 100.0 * u["cache_read_tokens"] / denom


def _apply_markers(messages: List[Dict[str, Any]], enabled: bool) -> List[Dict[str, Any]]:
    if not enabled:
        return messages
    from agent.prompt_caching import apply_anthropic_cache_control

    # Native layout: markers on content / top-level as Anthropic expects.
    return apply_anthropic_cache_control(
        messages, cache_ttl="5m", native_anthropic=True
    )


def _post_messages(
    *,
    key: str,
    messages: List[Dict[str, Any]],
    with_markers: bool,
    timeout: float = 90.0,
) -> Tuple[int, Dict[str, Any], float, Optional[str]]:
    import httpx

    payload_messages = _apply_markers(messages, with_markers)
    # Anthropic Messages API: system is separate from messages
    system = None
    api_msgs: List[Dict[str, Any]] = []
    for m in payload_messages:
        if m.get("role") == "system":
            system = m.get("content")
        else:
            api_msgs.append(m)

    body: Dict[str, Any] = {
        "model": MODEL,
        "max_tokens": 256,
        "tools": TOOLS,
        "messages": api_msgs,
    }
    if system is not None:
        body["system"] = system

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "anthropic-version": "2023-06-01",
        "x-api-key": key,
    }
    t0 = time.perf_counter()
    try:
        r = httpx.post(MESSAGES_URL, headers=headers, json=body, timeout=timeout)
        latency = time.perf_counter() - t0
        try:
            data = r.json()
        except Exception:
            data = {"raw": r.text[:500]}
        err = None
        if r.status_code >= 400:
            err = f"HTTP {r.status_code}: {str(data)[:240]}"
        return r.status_code, data if isinstance(data, dict) else {"raw": data}, latency, err
    except Exception as exc:
        latency = time.perf_counter() - t0
        return 0, {}, latency, f"{type(exc).__name__}: {exc}"


def _extract_tool_use(body: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    content = body.get("content") or []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                return block
    return None


def run_arm(*, key: str, with_markers: bool, turns: int) -> Dict[str, Any]:
    """20-turn deterministic loop: user → (tool_use) → tool_result → …"""
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": STABLE_SYSTEM},
    ]
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }
    latencies: List[float] = []
    per_turn: List[Dict[str, Any]] = []
    completed = 0
    errors: List[str] = []

    for turn in range(1, turns + 1):
        messages.append(
            {
                "role": "user",
                "content": f"Benchmark turn {turn}. Call echo_probe with turn={turn}.",
            }
        )
        status, body, latency, err = _post_messages(
            key=key, messages=messages, with_markers=with_markers
        )
        latencies.append(latency)
        if err:
            errors.append(f"turn {turn}: {err}")
            per_turn.append(
                {
                    "turn": turn,
                    "ok": False,
                    "latency_s": round(latency, 3),
                    "error": err,
                    "usage": {},
                }
            )
            # Fail-fast on hard provider outage
            if status in (0, 429, 500, 502, 503) or "usage limit" in (err or "").lower():
                break
            continue

        usage = _usage_from_body(body)
        for k, v in usage.items():
            totals[k] += v

        tool = _extract_tool_use(body)
        # Record assistant content (with tool_use) for next turn
        assistant_content = body.get("content")
        if assistant_content is None:
            assistant_content = [{"type": "text", "text": str(body)[:200]}]
        messages.append({"role": "assistant", "content": assistant_content})

        if tool and tool.get("id"):
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool["id"],
                            "content": json.dumps({"ok": True, "turn": turn}),
                        }
                    ],
                }
            )
            completed += 1
            ok = True
        else:
            ok = False
            errors.append(f"turn {turn}: no tool_use in response")

        per_turn.append(
            {
                "turn": turn,
                "ok": ok,
                "latency_s": round(latency, 3),
                "usage": usage,
                "hit_pct": round(_hit_pct(usage), 2),
            }
        )

    return {
        "arm": "on" if with_markers else "off",
        "with_markers": with_markers,
        "turns_requested": turns,
        "turns_completed_ok": completed,
        "task_completion": completed >= turns,
        "totals": totals,
        "cache_hit_pct": round(_hit_pct(totals), 2),
        "list_cost_usd_est": round(_list_cost_usd(totals), 6),
        "latency_total_s": round(sum(latencies), 3),
        "latency_avg_s": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
        "errors": errors[:10],
        "per_turn": per_turn,
        "policy_check": _policy_snapshot(),
    }


def _policy_snapshot() -> Dict[str, Any]:
    from agent.agent_runtime_helpers import anthropic_prompt_cache_policy

    class _A:
        provider = "opencode-go"
        base_url = "https://opencode.ai/zen/go/v1"
        api_mode = "anthropic_messages"
        model = MODEL

    should, native = anthropic_prompt_cache_policy(_A())
    return {"should_cache": should, "native_layout": native}


def decide(off: Dict[str, Any], on: Dict[str, Any]) -> Dict[str, Any]:
    """Keep ON only if hit% improves by >5pp OR list-$ drops by >5%."""
    if off.get("provider_blocked") or on.get("provider_blocked"):
        return {
            "decision": "blocked",
            "keep_markers": True,  # policy patch is correct-by-docs; keep code
            "reason": "Provider unavailable; cannot measure. Policy patch retained (docs-correct); no credit claim.",
            "hit_pp_delta": None,
            "cost_pct_delta": None,
        }

    hit_delta = on["cache_hit_pct"] - off["cache_hit_pct"]
    off_cost = off["list_cost_usd_est"] or 0.0
    on_cost = on["list_cost_usd_est"] or 0.0
    if off_cost > 0:
        cost_pct = 100.0 * (off_cost - on_cost) / off_cost
    else:
        cost_pct = 0.0

    keep = hit_delta > 5.0 or cost_pct > 5.0
    if not off["task_completion"] and not on["task_completion"]:
        return {
            "decision": "inconclusive",
            "keep_markers": True,
            "reason": "Neither arm completed the task; keep docs-correct markers, no savings claim.",
            "hit_pp_delta": round(hit_delta, 2),
            "cost_pct_delta": round(cost_pct, 2),
        }

    return {
        "decision": "keep" if keep else "rollback_policy_optional",
        "keep_markers": keep,
        "reason": (
            f"hit% Δ={hit_delta:+.2f}pp, list-$ savings={cost_pct:+.2f}% — "
            + (">5% threshold met" if keep else "<5% improvement; prefer simpler of two")
        ),
        "hit_pp_delta": round(hit_delta, 2),
        "cost_pct_delta": round(cost_pct, 2),
    }


def probe_provider(key: str) -> Optional[str]:
    status, body, _, err = _post_messages(
        key=key,
        messages=[
            {"role": "system", "content": "Reply with pong only."},
            {"role": "user", "content": "ping"},
        ],
        with_markers=False,
        timeout=45.0,
    )
    if err:
        return err
    if status >= 400:
        return f"HTTP {status}: {str(body)[:200]}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=int, default=TURNS)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "audit",
    )
    args = parser.parse_args()
    turns = max(2, min(args.turns, 40))

    key = _load_key()
    measured_at = datetime.now(timezone.utc).isoformat()
    run_id = uuid.uuid4().hex[:10]

    print(f"[ab] policy snapshot: {_policy_snapshot()}")
    print("[ab] probing OpenCode Go …")
    probe_err = probe_provider(key)
    if probe_err:
        print(f"[ab] PROVIDER BLOCKED: {probe_err}")
        report = {
            "phase": "track-a-cache-control-ab",
            "measured_at": measured_at,
            "run_id": run_id,
            "model": MODEL,
            "provider": "opencode-go",
            "messages_url": MESSAGES_URL,
            "turns": turns,
            "provider_blocked": True,
            "provider_error": probe_err,
            "policy_after_patch": _policy_snapshot(),
            "decision": {
                "decision": "blocked",
                "keep_markers": True,
                "reason": (
                    "OpenCode Go unavailable (quota/500). Policy patch kept "
                    "(correct for MiniMax Anthropic wire). A/B not measured."
                ),
            },
        }
        _write(args.out_dir, report)
        print("[ab] wrote blocked report — policy patch retained, no savings claim")
        return 2

    print(f"[ab] arm OFF (no markers), {turns} turns …")
    off = run_arm(key=key, with_markers=False, turns=turns)
    print(
        f"[ab] OFF hit%={off['cache_hit_pct']} cost≈${off['list_cost_usd_est']} "
        f"ok={off['turns_completed_ok']}/{turns}"
    )

    print(f"[ab] arm ON (markers), {turns} turns …")
    on = run_arm(key=key, with_markers=True, turns=turns)
    print(
        f"[ab] ON  hit%={on['cache_hit_pct']} cost≈${on['list_cost_usd_est']} "
        f"ok={on['turns_completed_ok']}/{turns}"
    )

    decision = decide(off, on)
    report = {
        "phase": "track-a-cache-control-ab",
        "measured_at": measured_at,
        "run_id": run_id,
        "model": MODEL,
        "provider": "opencode-go",
        "messages_url": MESSAGES_URL,
        "turns": turns,
        "provider_blocked": False,
        "threshold": {
            "min_hit_pp_improvement": 5.0,
            "min_list_cost_savings_pct": 5.0,
        },
        "arm_off": {k: v for k, v in off.items() if k != "per_turn"},
        "arm_on": {k: v for k, v in on.items() if k != "per_turn"},
        "arm_off_per_turn": off["per_turn"],
        "arm_on_per_turn": on["per_turn"],
        "decision": decision,
        "policy_after_patch": _policy_snapshot(),
        "note": (
            "Go credit consumption approximated via published list rates "
            "($0.30/$0.06/$1.20 per MTok). Subscription included quota may "
            "differ; relative A/B still valid."
        ),
    }
    paths = _write(args.out_dir, report)
    print(f"[ab] decision={decision['decision']} keep_markers={decision['keep_markers']}")
    print(f"[ab] reason: {decision['reason']}")
    print(f"[ab] wrote {paths['json']} and {paths['md']}")
    return 0 if decision["decision"] in {"keep", "rollback_policy_optional", "inconclusive"} else 2


def _write(out_dir: Path, report: Dict[str, Any]) -> Dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "HERMES_CACHE_CONTROL_AB.json"
    md_path = out_dir / "HERMES_CACHE_CONTROL_AB.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")

    d = report.get("decision") or {}
    off = report.get("arm_off") or {}
    on = report.get("arm_on") or {}
    lines = [
        "# Track A — OpenCode Go + MiniMax cache_control A/B",
        "",
        f"**Measured at:** {report.get('measured_at')}",
        f"**Model:** `{report.get('model')}` via `{report.get('provider')}`",
        f"**Turns:** {report.get('turns')}",
        "",
        "## Decision",
        "",
        f"- **decision:** `{d.get('decision')}`",
        f"- **keep_markers:** `{d.get('keep_markers')}`",
        f"- **reason:** {d.get('reason')}",
        "",
    ]
    if report.get("provider_blocked"):
        lines += [
            "## Provider blocked",
            "",
            f"```\n{report.get('provider_error')}\n```",
            "",
            "Policy patch retained (docs-correct). No credit-savings claim.",
            "",
        ]
    else:
        lines += [
            "## Results",
            "",
            "| Arm | Hit % | Cache read | Cache write | New input | List $ est | Latency | Task OK |",
            "|-----|------:|-----------:|------------:|----------:|-----------:|--------:|--------:|",
            (
                f"| OFF | {off.get('cache_hit_pct')} | {off.get('totals', {}).get('cache_read_tokens')} | "
                f"{off.get('totals', {}).get('cache_write_tokens')} | {off.get('totals', {}).get('input_tokens')} | "
                f"${off.get('list_cost_usd_est')} | {off.get('latency_total_s')}s | {off.get('task_completion')} |"
            ),
            (
                f"| ON | {on.get('cache_hit_pct')} | {on.get('totals', {}).get('cache_read_tokens')} | "
                f"{on.get('totals', {}).get('cache_write_tokens')} | {on.get('totals', {}).get('input_tokens')} | "
                f"${on.get('list_cost_usd_est')} | {on.get('latency_total_s')}s | {on.get('task_completion')} |"
            ),
            "",
            f"- hit Δ (pp): `{d.get('hit_pp_delta')}`",
            f"- list-$ savings %: `{d.get('cost_pct_delta')}`",
            "",
            "## Threshold",
            "",
            "Keep ON only if hit% improves by **>5pp** OR list-$ savings **>5%**.",
            "Otherwise ship whichever is cleaner (prefer keeping docs-correct markers if complexity equal).",
            "",
        ]
    lines += [
        "## Policy after patch",
        "",
        f"```json\n{json.dumps(report.get('policy_after_patch'), indent=2)}\n```",
        "",
        "## Next",
        "",
        "If keep or blocked-with-docs-correct: leave policy patch.",
        "If rollback_policy_optional and team prefers zero-marker Go path: revert "
        "`agent/agent_runtime_helpers.py` MiniMax-on-OpenCode branch.",
        "Then proceed to Track B Milestone 1 (execution batching).",
        "",
    ]
    md_path.write_text("\n".join(lines))
    return {"json": json_path, "md": md_path}


if __name__ == "__main__":
    raise SystemExit(main())
