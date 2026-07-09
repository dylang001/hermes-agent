"""``hermes intelligence-policy`` subcommand parser."""

from __future__ import annotations

from typing import Callable


def build_intelligence_policy_parser(subparsers, *, cmd_intelligence_policy: Callable) -> None:
    parser = subparsers.add_parser(
        "intelligence-policy",
        help="Show the latest read-only intelligence policy run report",
        description=(
            "Read the latest disabled-by-default intelligence policy run report. "
            "This command is read-only and never exposes credentials or raw tool output."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit the report as JSON")
    parser.set_defaults(func=cmd_intelligence_policy)
