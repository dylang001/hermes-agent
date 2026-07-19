"""Hermes Observatory Phase 1 — process-local Prometheus text metrics.

Loopback-only scrape surface. No third-party clients, no SaaS, no prompt /
credential / PII labels. All public record_* helpers are fail-open no-ops when
disabled or on any internal error so normal agent execution is unaffected.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Fixed latency buckets (seconds) — low cardinality, enough for p95 via PromQL.
_LATENCY_BUCKETS: Tuple[float, ...] = (0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, float("inf"))

# Tool categories — never emit raw tool names (MCP/skills explode cardinality).
_TOOL_CATEGORY_MAP = {
    "terminal": "terminal",
    "execute_code": "code",
    "read_file": "file",
    "write_file": "file",
    "search_files": "file",
    "patch": "file",
    "web_search": "web",
    "web_extract": "web",
    "browser_navigate": "browser",
    "browser_snapshot": "browser",
    "delegate_task": "delegation",
    "session_search": "session",
    "skill_view": "skills",
    "skills_list": "skills",
    "memory": "memory",
    "todo": "todo",
}

_ALLOWED_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


class _Registry:
    """Thread-safe in-process counters / gauges / histograms."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
        self._gauges: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
        self._hist_counts: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], List[float]] = {}
        self._hist_sums: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
        self._started_at = time.time()

    @staticmethod
    def _key(name: str, labels: Optional[Dict[str, str]]) -> Tuple[str, Tuple[Tuple[str, str], ...]]:
        items = tuple(sorted((labels or {}).items()))
        return name, items

    def inc(self, name: str, value: float = 1.0, labels: Optional[Dict[str, str]] = None) -> None:
        if value <= 0:
            return
        key = self._key(name, labels)
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def set_gauge(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        key = self._key(name, labels)
        with self._lock:
            self._gauges[key] = float(value)

    def observe(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        if value < 0:
            return
        key = self._key(name, labels)
        with self._lock:
            buckets = self._hist_counts.get(key)
            if buckets is None:
                buckets = [0.0] * len(_LATENCY_BUCKETS)
                self._hist_counts[key] = buckets
            for i, le in enumerate(_LATENCY_BUCKETS):
                if value <= le:
                    buckets[i] += 1.0
            self._hist_sums[key] = self._hist_sums.get(key, 0.0) + value

    def render(self) -> str:
        lines: List[str] = [
            "# HELP hermes_process_uptime_seconds Seconds since metrics registry start.",
            "# TYPE hermes_process_uptime_seconds gauge",
            f"hermes_process_uptime_seconds {time.time() - self._started_at:.3f}",
        ]
        with self._lock:
            counters = list(self._counters.items())
            gauges = list(self._gauges.items())
            hists = list(self._hist_counts.items())
            sums = dict(self._hist_sums)

        # Group HELP/TYPE once per metric name.
        seen_help: set[str] = set()

        def _ensure_meta(name: str, kind: str, help_text: str) -> None:
            if name in seen_help:
                return
            seen_help.add(name)
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} {kind}")

        for (name, label_items), value in sorted(counters, key=lambda x: (x[0][0], x[0][1])):
            _ensure_meta(name, "counter", "Hermes counter")
            lines.append(f"{name}{_fmt_labels(label_items)} {value:.0f}")

        for (name, label_items), value in sorted(gauges, key=lambda x: (x[0][0], x[0][1])):
            _ensure_meta(name, "gauge", "Hermes gauge")
            lines.append(f"{name}{_fmt_labels(label_items)} {value:.3f}")

        for (name, label_items), buckets in sorted(hists, key=lambda x: (x[0][0], x[0][1])):
            _ensure_meta(name, "histogram", "Hermes histogram")
            cumulative = 0.0
            for i, le in enumerate(_LATENCY_BUCKETS):
                cumulative += buckets[i]
                le_label = "+Inf" if le == float("inf") else f"{le:g}"
                bucket_labels = list(label_items) + [("le", le_label)]
                lines.append(
                    f"{name}_bucket{_fmt_labels(tuple(sorted(bucket_labels)))} {cumulative:.0f}"
                )
            lines.append(f"{name}_sum{_fmt_labels(label_items)} {sums.get((name, label_items), 0.0):.6f}")
            lines.append(f"{name}_count{_fmt_labels(label_items)} {cumulative:.0f}")

        lines.append("")
        return "\n".join(lines)


def _fmt_labels(items: Sequence[Tuple[str, str]]) -> str:
    if not items:
        return ""
    parts = [f'{k}="{_escape(v)}"' for k, v in items]
    return "{" + ",".join(parts) + "}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


_registry = _Registry()
_enabled = False
_server: Optional[ThreadingHTTPServer] = None
_server_thread: Optional[threading.Thread] = None
_bind_host = "127.0.0.1"
_bind_port = 9108
_lock = threading.Lock()


def is_enabled() -> bool:
    return _enabled


def tool_category(tool_name: str) -> str:
    name = (tool_name or "").strip()
    if name in _TOOL_CATEGORY_MAP:
        return _TOOL_CATEGORY_MAP[name]
    if name.startswith("browser_"):
        return "browser"
    if name.startswith("mcp_") or "__" in name:
        return "mcp"
    if name.startswith("kanban_"):
        return "kanban"
    return "other"


def _safe(fn, *args, **kwargs) -> None:
    if not _enabled:
        return
    try:
        fn(*args, **kwargs)
    except Exception:
        logger.debug("hermes_metrics: record failed open", exc_info=True)


def record_gateway_turn(*, success: bool, duration_seconds: float) -> None:
    def _do() -> None:
        outcome = "success" if success else "failure"
        _registry.inc("hermes_gateway_turns_total", labels={"outcome": outcome})
        _registry.observe("hermes_gateway_turn_duration_seconds", float(duration_seconds))

    _safe(_do)


def record_model_call(*, success: bool, duration_seconds: float) -> None:
    def _do() -> None:
        status = "ok" if success else "error"
        _registry.inc("hermes_model_calls_total", labels={"status": status})
        _registry.observe("hermes_model_call_duration_seconds", float(duration_seconds))

    _safe(_do)


def record_tool_call(*, category: str, success: bool, duration_seconds: float) -> None:
    def _do() -> None:
        cat = category if category in {
            "terminal", "code", "file", "web", "browser", "delegation",
            "session", "skills", "memory", "todo", "mcp", "kanban", "other",
        } else "other"
        status = "ok" if success else "error"
        _registry.inc(
            "hermes_tool_calls_total",
            labels={"category": cat, "status": status},
        )
        _registry.observe(
            "hermes_tool_call_duration_seconds",
            float(duration_seconds),
            labels={"category": cat},
        )

    _safe(_do)


def record_compression(*, kind: str) -> None:
    def _do() -> None:
        allowed = {
            "auto", "emergency", "hygiene", "overflow", "manual", "governor",
        }
        k = kind if kind in allowed else "other"
        _registry.inc("hermes_compression_total", labels={"kind": k})

    _safe(_do)


def record_governor_event(*, kind: str, live_tokens: int = 0) -> None:
    def _do() -> None:
        allowed = {"pass", "soft_warning", "compact", "emergency", "blocked"}
        k = kind if kind in allowed else "other"
        _registry.inc("hermes_context_governor_events_total", labels={"kind": k})
        if live_tokens > 0:
            _registry.set_gauge("hermes_context_live_tokens", float(live_tokens))

    _safe(_do)


def record_token_usage(
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> None:
    def _do() -> None:
        if prompt_tokens:
            _registry.inc("hermes_tokens_prompt_total", float(prompt_tokens))
        if completion_tokens:
            _registry.inc("hermes_tokens_completion_total", float(completion_tokens))
        if cache_read_tokens:
            _registry.inc("hermes_tokens_cache_read_total", float(cache_read_tokens))
        if cache_write_tokens:
            _registry.inc("hermes_tokens_cache_write_total", float(cache_write_tokens))

    _safe(_do)


def record_error(*, kind: str) -> None:
    def _do() -> None:
        allowed = {
            "api", "tool", "governor_blocked", "compression", "other",
        }
        k = kind if kind in allowed else "other"
        _registry.inc("hermes_errors_total", labels={"kind": k})

    _safe(_do)


def render_metrics() -> str:
    return _registry.render()


def reset_for_tests() -> None:
    """Test-only: clear registry + disable server state."""
    global _enabled, _server, _server_thread
    stop_metrics_server()
    with _lock:
        _enabled = False
    global _registry
    _registry = _Registry()


def _is_loopback_host(host: str) -> bool:
    h = (host or "").strip().lower()
    if h in _ALLOWED_LOOPBACK:
        return True
    try:
        infos = socket.getaddrinfo(h, None)
        return all(info[4][0] in ("127.0.0.1", "::1") for info in infos)
    except Exception:
        return False


class _MetricsHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # silence default stderr logs
        logger.debug("metrics_http: " + fmt, *args)

    def _client_is_loopback(self) -> bool:
        host = self.client_address[0]
        return host in ("127.0.0.1", "::1", "localhost")

    def do_GET(self) -> None:  # noqa: N802
        if not self._client_is_loopback():
            self.send_error(403, "loopback only")
            return
        path = urlparse(self.path).path
        if path in ("/metrics", "/metrics/"):
            body = render_metrics().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path in ("/health", "/healthz"):
            body = b"ok\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404, "not found")

    def do_POST(self) -> None:  # noqa: N802
        self.send_error(405, "method not allowed")


def start_metrics_server(
    *,
    enabled: bool = False,
    bind_host: str = "127.0.0.1",
    port: int = 9108,
) -> bool:
    """Start loopback metrics HTTP server. Returns True if listening."""
    global _enabled, _server, _server_thread, _bind_host, _bind_port

    with _lock:
        if not enabled:
            _enabled = False
            return False
        if not _is_loopback_host(bind_host):
            logger.error(
                "Observatory refused non-loopback bind_host=%r — metrics not started",
                bind_host,
            )
            _enabled = False
            return False
        if _server is not None:
            _enabled = True
            return True

        host = bind_host.strip() or "127.0.0.1"
        try:
            httpd = ThreadingHTTPServer((host, int(port)), _MetricsHandler)
        except OSError as exc:
            logger.error("Observatory metrics bind failed on %s:%s: %s", host, port, exc)
            _enabled = False
            return False

        # Belt-and-suspenders: refuse if the socket somehow isn't loopback.
        bound = httpd.server_address[0]
        if not _is_loopback_host(str(bound)):
            httpd.server_close()
            logger.error("Observatory refused bound address %r", bound)
            _enabled = False
            return False

        _server = httpd
        _bind_host = host
        _bind_port = int(port)
        _enabled = True

        def _serve() -> None:
            logger.info(
                "Observatory metrics listening on http://%s:%s/metrics (loopback only)",
                host,
                port,
            )
            try:
                httpd.serve_forever(poll_interval=0.5)
            except Exception:
                logger.debug("metrics server stopped", exc_info=True)

        _server_thread = threading.Thread(
            target=_serve, name="hermes-observatory-metrics", daemon=True
        )
        _server_thread.start()
        return True


def stop_metrics_server() -> None:
    global _server, _server_thread, _enabled
    with _lock:
        httpd = _server
        _server = None
        _server_thread = None
        _enabled = False
    if httpd is not None:
        try:
            httpd.shutdown()
        except Exception:
            pass
        try:
            httpd.server_close()
        except Exception:
            pass


def load_and_start_from_config() -> bool:
    """Read ``observatory`` from config.yaml and start if enabled."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config() or {}
        obs = cfg.get("observatory") or {}
        if not isinstance(obs, dict):
            obs = {}
        return start_metrics_server(
            enabled=bool(obs.get("enabled", False)),
            bind_host=str(obs.get("bind_host", "127.0.0.1") or "127.0.0.1"),
            port=int(obs.get("port", 9108) or 9108),
        )
    except Exception:
        logger.debug("Observatory config load failed open", exc_info=True)
        return False


__all__ = [
    "is_enabled",
    "tool_category",
    "record_gateway_turn",
    "record_model_call",
    "record_tool_call",
    "record_compression",
    "record_governor_event",
    "record_token_usage",
    "record_error",
    "render_metrics",
    "reset_for_tests",
    "start_metrics_server",
    "stop_metrics_server",
    "load_and_start_from_config",
]
