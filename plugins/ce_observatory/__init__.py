"""Context Engineering Observatory — read-only telemetry dashboard.

Observation-mode plugin. Reads existing HERMES_HOME/logs JSONL streams.
Does not enable, mutate, or depend on Context Engineering V2 runtime flags.
"""

from __future__ import annotations


def register(ctx) -> None:
    """No tools or hooks — dashboard-only plugin."""
    return None
