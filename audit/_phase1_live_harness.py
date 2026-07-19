#!/usr/bin/env python3
"""Phase 1 context-cost LIVE measurement harness (OpenCode Go / minimax-m3).

Does not modify MEMORY.md / USER.md. Uses skip_memory=True.
Does not alter Phase 1 config. Writes audit JSON/MD via caller.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure checkout is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("HERMES_HOME", str(Path.home() / ".hermes"))
# Load secrets without printing them
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

# Quiet down noisy loggers; capture governor INFO
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
gov_log = logging.getLogger("agent.conversation_loop")
gov_log.setLevel(logging.INFO)

OFFLINE_INPUT_USD_PER_MTOK = 0.4  # matches Phase 1 offline report


class _GovCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.events: List[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        msg = record.getMessage()
        if "Context governor" in msg or "context governor" in msg.lower():
            self.events.append(msg)


def _redact_key(key: Optional[str]) -> str:
    if not key:
        return "(missing)"
    return f"***{key[-4:]}" if len(key) >= 4 else "***"


def _make_agent(session_id: str, max_iterations: int):
    from run_agent import AIAgent

    return AIAgent(
        model="minimax-m3",
        provider="opencode-go",
        quiet_mode=True,
        skip_memory=True,  # do not touch long-term memory stores
        max_iterations=max_iterations,
        session_id=session_id,
        platform="cli",
        # Keep cwd as hermes-agent for coding scenario
    )


def _usage_from_agent(agent) -> Dict[str, Any]:
    inp = int(getattr(agent, "session_input_tokens", 0) or 0)
    out = int(getattr(agent, "session_output_tokens", 0) or 0)
    cache_r = int(getattr(agent, "session_cache_read_tokens", 0) or 0)
    cache_w = int(getattr(agent, "session_cache_write_tokens", 0) or 0)
    reasoning = int(getattr(agent, "session_reasoning_tokens", 0) or 0)
    api_calls = int(getattr(agent, "_api_call_count", 0) or 0)
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_tokens": cache_r,
        "cache_write_tokens": cache_w,
        "reasoning_tokens": reasoning,
        "api_call_count": api_calls,
        "est_cost_usd_offline_rate": round(
            (inp + cache_r) * OFFLINE_INPUT_USD_PER_MTOK / 1_000_000
            + out * OFFLINE_INPUT_USD_PER_MTOK / 1_000_000,  # same rate used offline for input; output unknown → use same for rough
            6,
        ),
        # Prefer true estimate_usage_cost when available
    }


def _enrich_cost(usage: Dict[str, Any], model: str, provider: str) -> Dict[str, Any]:
    try:
        from agent.usage_pricing import CanonicalUsage, estimate_usage_cost

        cu = CanonicalUsage(
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            cache_write_tokens=usage.get("cache_write_tokens", 0),
            reasoning_tokens=usage.get("reasoning_tokens", 0),
            request_count=max(1, usage.get("api_call_count") or 1),
        )
        cr = estimate_usage_cost(model, cu, provider=provider)
        usage["billing_status"] = cr.status
        usage["billing_label"] = cr.label
        usage["billing_amount_usd"] = float(cr.amount_usd) if cr.amount_usd is not None else None
        usage["billing_notes"] = list(cr.notes or ())
    except Exception as exc:
        usage["billing_status"] = "error"
        usage["billing_label"] = str(exc)
        usage["billing_amount_usd"] = None
    # Apples-to-apples with Phase 1 offline ($0.4/MTok on input-like tokens)
    usage["est_cost_usd_phase1_rate_input_only"] = round(
        usage["input_tokens"] * OFFLINE_INPUT_USD_PER_MTOK / 1_000_000, 6
    )
    return usage


def _db_usage(session_id: str) -> Optional[Dict[str, Any]]:
    try:
        import sqlite3

        db = Path(os.environ["HERMES_HOME"]) / "state.db"
        if not db.exists():
            return None
        con = sqlite3.connect(str(db))
        con.row_factory = sqlite3.Row
        row = con.execute(
            """
            SELECT session_id, model, api_call_count, input_tokens, output_tokens,
                   cache_read_tokens, cache_write_tokens, reasoning_tokens
            FROM session_model_usage WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        # Also try sessions table aggregates
        row2 = con.execute(
            """
            SELECT input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                   reasoning_tokens, message_count, tool_call_count
            FROM sessions WHERE id = ?
            """,
            (session_id,),
        ).fetchone()
        con.close()
        out: Dict[str, Any] = {}
        if row:
            out["session_model_usage"] = dict(row)
        if row2:
            out["sessions"] = dict(row2)
        return out or None
    except Exception as exc:
        return {"error": str(exc)}


def _patch_governor_capture(agent, sink: List[Dict[str, Any]]):
    """Wrap govern_request via monkeypatch on conversation_loop import site."""
    import agent.context_governor as cg

    orig = cg.govern_request

    def wrapped(*args, **kwargs):
        result = orig(*args, **kwargs)
        sink.append(
            {
                "tokens_before": result.tokens_before,
                "tokens_after": result.tokens_after,
                "actions": list(result.actions or []),
                "blocked": bool(result.blocked),
                "block_reason": result.block_reason or "",
            }
        )
        return result

    cg.govern_request = wrapped
    return lambda: setattr(cg, "govern_request", orig)


def run_scenario(
    name: str,
    prompts: List[str],
    *,
    max_iterations: int,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    if cwd:
        os.chdir(cwd)
    sid = f"phase1-live-{uuid.uuid4().hex[:12]}"
    gov_sink: List[Dict[str, Any]] = []
    log_cap = _GovCapture()
    gov_log.addHandler(log_cap)
    t0 = time.perf_counter()
    agent = _make_agent(sid, max_iterations=max_iterations)
    unpatch = _patch_governor_capture(agent, gov_sink)
    history: List[Dict[str, Any]] = []
    responses: List[str] = []
    errors: List[str] = []
    per_turn: List[Dict[str, Any]] = []
    try:
        for i, prompt in enumerate(prompts):
            turn_t0 = time.perf_counter()
            before = _usage_from_agent(agent)
            try:
                result = agent.run_conversation(
                    prompt,
                    conversation_history=history if history else None,
                )
            except Exception as exc:
                errors.append(f"turn{i+1}: {type(exc).__name__}: {exc}")
                per_turn.append(
                    {
                        "turn": i + 1,
                        "prompt": prompt[:200],
                        "error": str(exc),
                        "latency_s": round(time.perf_counter() - turn_t0, 3),
                    }
                )
                break
            after = _usage_from_agent(agent)
            msgs = result.get("messages") if isinstance(result, dict) else None
            if msgs:
                history = list(msgs)
            final = ""
            if isinstance(result, dict):
                final = result.get("final_response") or ""
            elif isinstance(result, str):
                final = result
            responses.append((final or "")[:800])
            per_turn.append(
                {
                    "turn": i + 1,
                    "prompt": prompt[:200],
                    "latency_s": round(time.perf_counter() - turn_t0, 3),
                    "delta_input": after["input_tokens"] - before["input_tokens"],
                    "delta_output": after["output_tokens"] - before["output_tokens"],
                    "delta_cache_read": after["cache_read_tokens"] - before["cache_read_tokens"],
                    "response_preview": (final or "")[:240],
                    "failed": bool(isinstance(result, dict) and result.get("failed")),
                }
            )
    finally:
        unpatch()
        gov_log.removeHandler(log_cap)

    wall_s = round(time.perf_counter() - t0, 3)
    usage = _enrich_cost(_usage_from_agent(agent), "minimax-m3", "opencode-go")
    useful = any(len((r or "").strip()) > 20 for r in responses) and not any(
        "blocked by context governor" in (r or "").lower() for r in responses
    )
    blocked = any(g.get("blocked") for g in gov_sink) or any(
        "blocked by context governor" in (r or "").lower() for r in responses
    )
    return {
        "name": name,
        "session_id": sid,
        "model": "minimax-m3",
        "provider": "opencode-go",
        "wall_latency_s": wall_s,
        "turns": len(prompts),
        "usage": usage,
        "per_turn": per_turn,
        "governor_events": gov_sink,
        "governor_log_lines": log_cap.events,
        "governor_fired": any(bool(g.get("actions")) for g in gov_sink),
        "governor_blocked": blocked,
        "capability_ok": useful and not blocked,
        "response_previews": responses,
        "errors": errors,
        "db_usage": _db_usage(sid),
    }


def main() -> int:
    out_dir = ROOT / "audit"
    key = os.environ.get("OPENCODE_GO_API_KEY", "")
    print(f"OPENCODE_GO_API_KEY present={bool(key)} redacted={_redact_key(key)}", flush=True)
    print(f"HERMES_HOME={os.environ.get('HERMES_HOME')}", flush=True)

    # prompt-size health
    prompt_size = {}
    try:
        from hermes_cli.prompt_size import compute_prompt_size  # type: ignore
    except Exception:
        compute_prompt_size = None
    if compute_prompt_size is None:
        # fallback: invoke hermes CLI helper if exists
        try:
            import subprocess

            r = subprocess.run(
                [str(ROOT / ".venv" / "bin" / "hermes"), "prompt-size", "--json"],
                cwd=str(ROOT),
                env={**os.environ},
                capture_output=True,
                text=True,
                timeout=120,
            )
            # try parse last json object from stdout
            txt = r.stdout.strip()
            if txt.startswith("{"):
                prompt_size = json.loads(txt)
            else:
                prompt_size = {"raw_stdout": txt[-2000:], "stderr": (r.stderr or "")[-500:], "rc": r.returncode}
        except Exception as exc:
            prompt_size = {"error": str(exc)}
    else:
        try:
            prompt_size = compute_prompt_size()
        except Exception as exc:
            prompt_size = {"error": str(exc)}

    repo = str(ROOT)
    scenarios: List[Dict[str, Any]] = []

    print("\n=== Scenario 1: simple conversational ===", flush=True)
    scenarios.append(
        run_scenario(
            "1. simple conversational",
            ["What is Hermes in one sentence?"],
            max_iterations=3,
            cwd=repo,
        )
    )
    print(json.dumps(scenarios[-1]["usage"], indent=2), flush=True)

    print("\n=== Scenario 2: ten-turn conversation ===", flush=True)
    ten = [
        "Reply with just the number 1.",
        "What is 2+2? One number only.",
        "Name one color.",
        "Say OK.",
        "What day comes after Monday? One word.",
        "Reply with the word ping.",
        "Capital of France? One word.",
        "Reply with yes.",
        "How many legs does a dog have? One number.",
        "End with the word done.",
    ]
    scenarios.append(
        run_scenario(
            "2. ten-turn conversation",
            ten,
            max_iterations=2,
            cwd=repo,
        )
    )
    print(json.dumps(scenarios[-1]["usage"], indent=2), flush=True)

    print("\n=== Scenario 3: one coding task ===", flush=True)
    scenarios.append(
        run_scenario(
            "3. one coding task",
            [
                "In the current repo, use read_file to read ONLY the first 30 lines of "
                "agent/project_brief.py and tell me the module docstring in one short sentence. "
                "Do not edit any files. Do not write memory."
            ],
            max_iterations=6,
            cwd=repo,
        )
    )
    print(json.dumps(scenarios[-1]["usage"], indent=2), flush=True)

    print("\n=== Scenario 4: tool-heavy research ===", flush=True)
    scenarios.append(
        run_scenario(
            "4. tool-heavy research",
            [
                "Do a tiny research pass with tools only (keep it small):\n"
                "1) web_search query: 'Hermes Agent Nous Research' (1 search)\n"
                "2) If available, web_extract ONE short page from results OR skip if no key\n"
                "3) read_file on agent/context_governor.py lines 1-80\n"
                "4) Optionally search_files for 'govern_request' under agent/\n"
                "Return a 4-bullet summary. Do not write memory. Cap tool use."
            ],
            max_iterations=10,
            cwd=repo,
        )
    )
    print(json.dumps(scenarios[-1]["usage"], indent=2), flush=True)

    report = {
        "phase": "context-cost-phase1-live",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "provider": "opencode-go",
        "model": "minimax-m3",
        "api_key_redacted": _redact_key(key),
        "hermes_home": os.environ.get("HERMES_HOME"),
        "workspace": repo,
        "offline_baseline_source": str(
            Path.home()
            / ".hermes/backups/context-cost-phase1-20260717/prompt-size-baseline.json"
        ),
        "offline_scenario_source": str(
            Path.home()
            / ".hermes/backups/context-cost-phase1-20260717/phase1-scenario-report.json"
        ),
        "cost_note": (
            "OpenCode Go is subscription-included; billing_amount_usd is usually 0. "
            "est_cost_usd_phase1_rate_input_only uses $0.4/MTok input to compare with offline Phase 1."
        ),
        "prompt_size_live": prompt_size,
        "scenarios": scenarios,
    }

    json_path = out_dir / "HERMES_CONTEXT_COST_PHASE1_LIVE.json"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {json_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
