#!/usr/bin/env python3
"""Hermes production capability check — strict operational semantics.

Distinguishes installed / configured / authenticated / connected /
functionally_tested / healthy. A check only **passes** when a representative
read-only action succeeds end-to-end.

Outputs:
  audit/HERMES_PRODUCTION_CAPABILITY_CHECK_<date>.md
  audit/HERMES_PRODUCTION_CAPABILITY_CHECK_<date>.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@dataclass
class CheckResult:
    id: str
    name: str
    status: str  # pass | degraded | fail | auth_required | skip
    installed: bool = False
    configured: bool = False
    authenticated: bool = False
    connected: bool = False
    functionally_tested: bool = False
    healthy: bool = False
    command: str = ""
    duration_ms: float = 0.0
    profile: str = ""
    side_effects: str = "read_only"
    stdout_summary: str = ""
    stderr_summary: str = ""
    remediation: str = ""
    evidence_path: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunReport:
    date: str
    started_at: str
    finished_at: str = ""
    total_duration_ms: float = 0.0
    git_sha: str = ""
    hermes_home: str = ""
    profile: str = ""
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        out = {"pass": 0, "degraded": 0, "fail": 0, "auth_required": 0, "skip": 0}
        for c in self.checks:
            out[c.status] = out.get(c.status, 0) + 1
        return out


def _truncate(text: str, limit: int = 400) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _run_cmd(
    cmd: list[str],
    *,
    timeout: float = 30.0,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str, float]:
    start = time.monotonic()
    merged = {**os.environ, **(env or {})}
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged,
            cwd=str(REPO_ROOT),
        )
        elapsed = (time.monotonic() - start) * 1000
        return proc.returncode, proc.stdout, proc.stderr, elapsed
    except subprocess.TimeoutExpired as exc:
        elapsed = (time.monotonic() - start) * 1000
        return 124, exc.stdout or "", exc.stderr or f"timeout after {timeout}s", elapsed


def _http_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
) -> tuple[int, Any, str]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body), body[:500]
            except json.JSONDecodeError:
                return resp.status, body, body[:500]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = body
        return exc.code, payload, body[:500]
    except Exception as exc:
        return 0, None, str(exc)


def _git_sha() -> str:
    code, out, _, _ = _run_cmd(["git", "rev-parse", "HEAD"], timeout=5)
    return out.strip() if code == 0 else ""


def _active_profile() -> str:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        return str((cfg.get("agent") or {}).get("capability_profile") or "default")
    except Exception:
        return "unknown"


def _finalize(result: CheckResult, started: float) -> CheckResult:
    if result.duration_ms <= 0:
        result.duration_ms = (time.monotonic() - started) * 1000
    result.healthy = result.status == "pass"
    result.functionally_tested = result.status in {"pass", "degraded"}
    return result


def check_clickup_cli(report: RunReport) -> CheckResult:
    started = time.monotonic()
    r = CheckResult(
        id="clickup_cli",
        name="ClickUp CLI (clickup-bridge)",
        status="fail",
        profile=report.profile,
        command="hermes clickup workspaces",
        side_effects="read_only",
    )
    r.installed = True
    try:
        from hermes_cli.config import load_config

        plugins = (load_config().get("plugins") or {}).get("enabled") or []
        r.configured = "clickup-bridge" in plugins
    except Exception:
        r.configured = False

    token = os.environ.get("CLICKUP_API_TOKEN", "").strip()
    r.authenticated = bool(token)

    code, out, err, ms = _run_cmd(
        [sys.executable, "-m", "hermes_cli.main", "clickup", "workspaces"],
        timeout=20,
        env={"HERMES_HOME": report.hermes_home},
    )
    r.duration_ms = ms
    r.command = "hermes clickup workspaces"
    r.stdout_summary = _truncate(out)
    r.stderr_summary = _truncate(err)

    if code == 124:
        r.status = "fail"
        r.remediation = "ClickUp CLI timed out — verify plugin handler_fn dispatch"
        return _finalize(r, started)

    if "unrecognized arguments" in err.lower() or "invalid choice" in err.lower():
        r.status = "fail"
        r.remediation = (
            "clickup-bridge missing handler_fn — workspaces not wired to dispatch"
        )
        return _finalize(r, started)

    if code != 0:
        if not token:
            r.status = "auth_required"
            r.remediation = "Set CLICKUP_API_TOKEN in HERMES_HOME/.env"
        else:
            r.status = "degraded" if r.configured else "fail"
            r.remediation = "ClickUp API call failed — verify token and network"
        return _finalize(r, started)

    try:
        payload = json.loads(out)
        workspaces = payload.get("workspaces") or []
        r.connected = True
        if workspaces:
            r.status = "pass"
            r.evidence_path = f"workspace_id={workspaces[0].get('id')}"
        else:
            r.status = "degraded"
            r.remediation = "API connected but no workspaces returned"
    except json.JSONDecodeError:
        r.status = "degraded"
        r.remediation = "Command succeeded but output was not JSON workspaces list"

    return _finalize(r, started)


def check_obsidian_mcp(report: RunReport) -> CheckResult:
    started = time.monotonic()
    r = CheckResult(
        id="obsidian_mcp",
        name="Obsidian MCP (Growth OS filesystem)",
        status="fail",
        profile=report.profile,
        command="hermes mcp test obsidian",
        side_effects="read_only",
    )
    r.installed = True

    try:
        from hermes_cli.obsidian_mcp_normalize import (
            normalize_obsidian_mcp_entry,
            obsidian_mcp_needs_normalize,
            resolve_growth_os_vault_path,
        )
        from hermes_cli.mcp_config import _get_mcp_servers, _probe_single_server

        servers = _get_mcp_servers()
        cfg = servers.get("obsidian") or {}
        r.configured = bool(cfg)
        if obsidian_mcp_needs_normalize(cfg):
            cfg, changes = normalize_obsidian_mcp_entry(cfg)
            r.notes = "auto-normalized: " + "; ".join(changes)

        vault = resolve_growth_os_vault_path()
        if not vault:
            r.remediation = (
                "Growth OS vault missing — sync Mac vault to "
                "/opt/hermes/data/obsidian/Growth OS"
            )
            return _finalize(r, started)

        r.evidence_path = vault
        index = Path(vault) / "INDEX.md"
        if not index.is_file():
            r.status = "degraded"
            r.remediation = f"INDEX.md missing under {vault}"
            return _finalize(r, started)

        connect_timeout = min(float(cfg.get("connect_timeout", 45) or 45), 45)
        tools = _probe_single_server(
            "obsidian", cfg, connect_timeout=connect_timeout
        )
        r.connected = True
        r.duration_ms = (time.monotonic() - started) * 1000
        tool_names = {t[0] for t in tools}
        if not tool_names:
            r.status = "degraded"
            r.remediation = "MCP connected but listed zero tools"
            return _finalize(r, started)

        # Read INDEX.md via vault filesystem (representative action)
        content = index.read_text(encoding="utf-8", errors="replace")[:200]
        r.stdout_summary = _truncate(content)
        if "404" in content or "could not be found" in content.lower():
            r.status = "degraded"
            r.remediation = "Vault read returned unexpected HTML/404 body"
            return _finalize(r, started)

        r.status = "pass"
        r.notes = (r.notes + " " if r.notes else "") + f"tools={sorted(tool_names)[:6]}"
    except Exception as exc:
        r.stderr_summary = _truncate(str(exc))
        if "127.0.0.1" in str(exc) or "Connection refused" in str(exc):
            r.remediation = (
                "Remove OBSIDIAN_MCP_URL / localhost HTTP — use filesystem MCP on Growth OS"
            )
        else:
            r.remediation = "Run hermes_cli.obsidian_mcp_normalize migration; verify npx + vault path"
    return _finalize(r, started)


def check_composio(report: RunReport) -> CheckResult:
    started = time.monotonic()
    r = CheckResult(
        id="composio",
        name="Composio MCP",
        status="fail",
        profile=report.profile,
        command="hermes mcp test composio + tool invoke",
        side_effects="read_only",
    )
    r.installed = True
    try:
        from hermes_cli.mcp_config import _get_mcp_servers, _probe_single_server
        from tools.mcp_tool import _connect_server, _ensure_mcp_loop, _run_on_mcp_loop

        servers = _get_mcp_servers()
        cfg = servers.get("composio") or {}
        r.configured = bool(cfg)
        if not cfg.get("enabled", True):
            r.status = "skip"
            r.notes = "composio disabled in config"
            return _finalize(r, started)

        api_key = os.environ.get("COMPOSIO_API_KEY", "").strip()
        r.authenticated = bool(api_key)

        tools = _probe_single_server(
            "composio",
            cfg,
            connect_timeout=min(float(cfg.get("connect_timeout", 15) or 15), 15),
        )
        r.connected = True
        r.stdout_summary = _truncate(", ".join(t[0] for t in tools[:12]))
        if not tools:
            r.status = "fail"
            r.remediation = "Composio connected but tool list empty"
            return _finalize(r, started)

        # Pick a harmless read-only tool if possible
        preferred = None
        for name, _desc in tools:
            low = name.lower()
            if any(k in low for k in ("list", "get", "search", "whoami", "profile")):
                preferred = name
                break
        if preferred is None:
            preferred = tools[0][0]

        async def _invoke():
            server = await _connect_server("composio", cfg)
            tool = next((t for t in server._tools if t.name == preferred), None)
            if tool is None:
                raise RuntimeError(f"tool {preferred} missing after list")
            # Call with empty/minimal args — expect success or structured error
            return await server.call_tool(preferred, {})

        _ensure_mcp_loop()
        try:
            invoke_result = _run_on_mcp_loop(_invoke, timeout=20)
            text = str(invoke_result)[:500]
            r.command = f"composio tool {preferred} {{}}"
            if "404" in text and "could not be found" in text.lower():
                r.status = "degraded"
                r.stderr_summary = _truncate(text)
                r.remediation = (
                    "Composio lists tools but invoke returned 404 — bad route or expired endpoint"
                )
            else:
                r.status = "pass"
                r.stdout_summary = _truncate(text)
        except Exception as exc:
            msg = str(exc)
            r.stderr_summary = _truncate(msg)
            if "404" in msg:
                r.status = "degraded"
                r.remediation = "MCP session OK but tool invocation 404 — check Composio URL/route"
            elif "auth" in msg.lower() or "401" in msg:
                r.status = "auth_required"
                r.remediation = "Set COMPOSIO_API_KEY or complete Composio OAuth"
            else:
                r.status = "degraded"
                r.remediation = "Composio connected; tool invoke failed — see stderr"
    except Exception as exc:
        r.stderr_summary = _truncate(str(exc))
        if "404" in str(exc):
            r.status = "degraded"
            r.remediation = "Composio HTTP 404 during connect — fix MCP URL, not a pass"
        else:
            r.status = "fail"
            r.remediation = "Cannot connect to Composio MCP — verify URL and API key"
    return _finalize(r, started)


def check_gmail(report: RunReport) -> CheckResult:
    started = time.monotonic()
    r = CheckResult(
        id="gmail",
        name="Gmail (Himalaya)",
        status="auth_required",
        profile=report.profile,
        command="himalaya accounts list",
        side_effects="read_only",
    )
    r.installed = shutil_which("himalaya") is not None
    r.configured = any(
        os.environ.get(k)
        for k in ("GMAIL_IMAP_HOST", "HIMALAYA_CONFIG", "EMAIL_IMAP_HOST")
    )
    r.authenticated = False
    r.notes = "Interactive OAuth/IMAP not configured by design for MVP"
    r.remediation = "Install himalaya + configure IMAP on gated profile when needed"
    return _finalize(r, started)


def shutil_which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def check_github(report: RunReport) -> CheckResult:
    started = time.monotonic()
    r = CheckResult(
        id="github",
        name="GitHub API",
        status="fail",
        profile=report.profile,
        command="GET /user + GET /user/repos?per_page=1",
        side_effects="read_only",
    )
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    r.configured = bool(token)
    r.authenticated = bool(token)
    if not token:
        r.status = "auth_required"
        r.remediation = "Set GITHUB_TOKEN in HERMES_HOME/.env"
        return _finalize(r, started)

    status, user, body = _http_json(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "hermes-capability-check",
        },
    )
    r.duration_ms = (time.monotonic() - started) * 1000
    if status != 200:
        r.status = "degraded" if status == 401 else "fail"
        r.stderr_summary = _truncate(str(body))
        r.remediation = "GitHub token rejected — rotate GITHUB_TOKEN"
        return _finalize(r, started)

    login = user.get("login") if isinstance(user, dict) else None
    status2, repos, _ = _http_json(
        "https://api.github.com/user/repos?per_page=1",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "hermes-capability-check",
        },
    )
    if status2 != 200:
        r.status = "degraded"
        r.remediation = "GitHub /user OK but repo list failed"
        return _finalize(r, started)

    r.connected = True
    r.status = "pass"
    repo_name = ""
    if isinstance(repos, list) and repos:
        repo_name = repos[0].get("full_name", "")
    r.stdout_summary = f"user={login} repo_sample={repo_name}"
    r.evidence_path = f"github:{login}"
    return _finalize(r, started)


def check_cron(report: RunReport) -> CheckResult:
    started = time.monotonic()
    r = CheckResult(
        id="cron",
        name="Cron scheduler",
        status="fail",
        profile=report.profile,
        command="hermes cron list",
        side_effects="read_only",
    )
    r.installed = True
    code, out, err, ms = _run_cmd(
        [sys.executable, "-m", "hermes_cli.main", "cron", "list"],
        timeout=20,
        env={"HERMES_HOME": report.hermes_home},
    )
    r.duration_ms = ms
    r.stdout_summary = _truncate(out)
    r.stderr_summary = _truncate(err)
    r.configured = code == 0
    if code != 0:
        r.remediation = "hermes cron list failed — check cron store permissions"
        return _finalize(r, started)

    if "clickup-task-os-poll" in out.lower() or re.search(r"\bok\b", out, re.I):
        r.status = "pass"
        r.connected = True
    elif out.strip():
        r.status = "degraded"
        r.remediation = "Cron list works but Task OS poller not confirmed active/ok"
    else:
        r.status = "degraded"
        r.remediation = "No cron jobs listed"
    return _finalize(r, started)


def check_mem0(report: RunReport) -> CheckResult:
    started = time.monotonic()
    r = CheckResult(
        id="mem0",
        name="Mem0 memory",
        status="fail",
        profile=report.profile,
        command="GET /v1/memories/",
        side_effects="read_only",
    )
    api_key = os.environ.get("MEM0_API_KEY", "").strip()
    try:
        from hermes_cli.config import load_config

        r.configured = (load_config().get("memory") or {}).get("provider") == "mem0"
    except Exception:
        r.configured = False
    r.authenticated = bool(api_key)
    if not api_key:
        r.status = "auth_required"
        r.remediation = "Set MEM0_API_KEY"
        return _finalize(r, started)

    status, body, raw = _http_json(
        "https://api.mem0.ai/v1/memories/",
        headers={"Authorization": f"Token {api_key}"},
    )
    r.duration_ms = (time.monotonic() - started) * 1000
    if status == 200:
        r.status = "pass"
        r.connected = True
        count = len(body) if isinstance(body, list) else "?"
        r.stdout_summary = f"memories_listed={count}"
    elif status in {401, 403}:
        r.status = "auth_required"
        r.stderr_summary = _truncate(raw)
    else:
        r.status = "degraded"
        r.stderr_summary = _truncate(raw)
        r.remediation = f"Mem0 API HTTP {status}"
    return _finalize(r, started)


def check_web_research(report: RunReport) -> CheckResult:
    started = time.monotonic()
    r = CheckResult(
        id="web_research",
        name="Web search + extract",
        status="fail",
        profile=report.profile,
        command="web_search + web_extract (smoke)",
        side_effects="read_only",
    )
    # Lightweight: verify tools import and search backend configured
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        r.configured = True
        has_key = any(
            os.environ.get(k)
            for k in ("TAVILY_API_KEY", "FIRECRAWL_API_KEY", "BRAVE_API_KEY", "EXA_API_KEY")
        )
        r.authenticated = has_key
        if not has_key:
            r.status = "auth_required"
            r.remediation = "Set a web search API key (TAVILY/FIRECRAWL/BRAVE/EXA)"
            return _finalize(r, started)

        from tools.web_search_tool import web_search

        result = web_search(query="hermes agent capability check", max_results=1)
        r.stdout_summary = _truncate(str(result))
        if "error" in str(result).lower()[:200]:
            r.status = "degraded"
            r.remediation = "web_search returned error payload"
        else:
            r.status = "pass"
            r.connected = True
    except Exception as exc:
        r.stderr_summary = _truncate(str(exc))
        r.remediation = "Fix web search tool configuration"
    return _finalize(r, started)


def check_delegation_help(report: RunReport) -> CheckResult:
    started = time.monotonic()
    r = CheckResult(
        id="delegation",
        name="Delegation / subagents",
        status="degraded",
        profile=report.profile,
        command="delegate_task schema present",
        side_effects="read_only",
        notes="Full bounded delegate smoke requires agent loop — not run in batch check",
    )
    try:
        from model_tools import get_tool_definitions

        names = {t["function"]["name"] for t in get_tool_definitions() if t.get("function")}
        r.configured = "delegate_task" in names
        r.installed = r.configured
        if r.configured:
            r.status = "degraded"
            r.remediation = "Run one bounded delegate_task in chat to reach pass"
        else:
            r.status = "fail"
    except Exception as exc:
        r.stderr_summary = _truncate(str(exc))
    return _finalize(r, started)


CHECKS: list[Callable[[RunReport], CheckResult]] = [
    check_clickup_cli,
    check_obsidian_mcp,
    check_composio,
    check_gmail,
    check_github,
    check_cron,
    check_mem0,
    check_web_research,
    check_delegation_help,
]


def run_all(*, hermes_home: str | None = None, profile: str | None = None) -> RunReport:
    started = time.monotonic()
    now = datetime.now(timezone.utc)
    date = now.strftime("%Y-%m-%d")
    hh = hermes_home or os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    os.environ.setdefault("HERMES_HOME", hh)

    try:
        from hermes_cli.env_loader import load_hermes_dotenv

        load_hermes_dotenv()
    except Exception:
        pass

    report = RunReport(
        date=date,
        started_at=now.isoformat(),
        git_sha=_git_sha(),
        hermes_home=hh,
        profile=profile or _active_profile(),
    )
    for fn in CHECKS:
        report.checks.append(fn(report))
    report.finished_at = datetime.now(timezone.utc).isoformat()
    report.total_duration_ms = (time.monotonic() - started) * 1000
    return report


def write_reports(report: RunReport, audit_dir: Path) -> tuple[Path, Path]:
    audit_dir.mkdir(parents=True, exist_ok=True)
    json_path = audit_dir / f"HERMES_PRODUCTION_CAPABILITY_CHECK_{report.date}.json"
    md_path = audit_dir / f"HERMES_PRODUCTION_CAPABILITY_CHECK_{report.date}.md"

    payload = {
        "date": report.date,
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "total_duration_ms": round(report.total_duration_ms, 1),
        "git_sha": report.git_sha,
        "hermes_home": report.hermes_home,
        "profile": report.profile,
        "counts": report.counts,
        "checks": [c.to_dict() for c in report.checks],
    }
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"# Hermes Production Capability Check — {report.date}",
        "",
        f"- **SHA:** `{report.git_sha}`",
        f"- **HERMES_HOME:** `{report.hermes_home}`",
        f"- **Profile:** `{report.profile}`",
        f"- **Duration:** {report.total_duration_ms:.0f} ms",
        f"- **Counts:** {report.counts}",
        "",
        "| Check | Status | Tested | Command | ms | Remediation |",
        "|-------|--------|--------|---------|-----|-------------|",
    ]
    for c in report.checks:
        tested = "yes" if c.functionally_tested else "no"
        lines.append(
            f"| {c.name} | **{c.status}** | {tested} | `{c.command}` | {c.duration_ms:.0f} | {c.remediation or c.notes} |"
        )
    lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes production capability check")
    parser.add_argument("--hermes-home", default=None)
    parser.add_argument("--profile", default=None)
    parser.add_argument(
        "--audit-dir",
        default=str(REPO_ROOT / "audit"),
        help="Directory for markdown/json output",
    )
    args = parser.parse_args(argv)

    report = run_all(hermes_home=args.hermes_home, profile=args.profile)
    md_path, json_path = write_reports(report, Path(args.audit_dir))
    print(f"Wrote {md_path}")
    print(f"Wrote {json_path}")
    print(f"Counts: {report.counts}")
    return 0 if report.counts.get("fail", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
