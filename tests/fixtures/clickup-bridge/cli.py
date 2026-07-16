"""CLI for the clickup-bridge plugin.

Implements the ``hermes clickup`` subcommand. The plugin's ``__init__`` wires
this module's ``register`` function into the hermes CLI under that name.

The CLI is intentionally thin: every subcommand parses its own args, builds
a payload (or reads one from disk), and delegates to ``ClickUpClient``. The
approval gate lives in ``create_task`` and in the client itself — both
layers refuse to write without an explicit Dylan approval.

No third-party deps. Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .clickup_client import (  # noqa: F401  (re-exported for tests)
    ApprovalGateError,
    AuthError,
    ClickUpClient,
    ClickUpError,
    ForbiddenEndpointError,
    HTTPError,
    ProposalValidationError,
)

# ── Proposal storage ────────────────────────────────────────────────────────

# We honour $HERMES_HOME so the hermetic test runner can redirect the
# proposals dir to a tempdir. In production, HERMES_HOME defaults to
# ~/.hermes (per hermes_constants.get_hermes_home).


def _hermes_home() -> Path:
    """Return the active Hermes home (env-overridable)."""
    val = os.environ.get("HERMES_HOME", "").strip()
    return Path(val) if val else Path.home() / ".hermes"


def proposal_dir() -> Path:
    """Directory where propose-task writes JSON proposals."""
    return _hermes_home() / "sandboxes" / "clickup-proposals"


# ── Argument parser ─────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse tree for ``hermes clickup ...``."""
    parser = argparse.ArgumentParser(
        prog="hermes clickup",
        description=(
            "Read-only ClickUp bridge. Every write requires explicit Dylan "
            "approval (--approved-by-dylan AND approved_by: dylan in the "
            "proposal file)."
        ),
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    # 1. workspaces ────────────────────────────────────────────────────────
    sub.add_parser(
        "workspaces",
        help="List workspaces (read-only).",
    )

    # 2. lists ─────────────────────────────────────────────────────────────
    p_lists = sub.add_parser(
        "lists",
        help="List folders+lists in a workspace (read-only).",
    )
    p_lists.add_argument("--workspace", required=True, help="Workspace id (team id).")

    # 3. tasks ─────────────────────────────────────────────────────────────
    p_tasks = sub.add_parser(
        "tasks",
        help="List tasks in a list (read-only).",
    )
    p_tasks.add_argument("--list", dest="list_id", required=True, help="List id.")
    p_tasks.add_argument(
        "--status",
        choices=["open", "closed", "all"],
        default="open",
        help="Filter by task status (default: open).",
    )

    # 4. task ──────────────────────────────────────────────────────────────
    p_task = sub.add_parser(
        "task",
        help="Show a single task (read-only).",
    )
    p_task.add_argument("--task-id", required=True, help="Task id.")

    # 5. propose-task ──────────────────────────────────────────────────────
    p_propose = sub.add_parser(
        "propose-task",
        help=(
            "Build a JSON proposal for a new task. Prints the payload to "
            "stdout and saves a copy under "
            "$HERMES_HOME/sandboxes/clickup-proposals/. NEVER posts to "
            "ClickUp."
        ),
    )
    p_propose.add_argument("--list", dest="list_id", required=True, help="Target list id.")
    p_propose.add_argument("--title", required=True, help="Task title.")
    p_propose.add_argument("--body", required=True, help="Task body (markdown).")
    p_propose.add_argument(
        "--tag",
        choices=["orchidea", "flockline", "personal-os"],
        help="Optional tag for the task (orchidea|flockline|personal-os).",
    )

    # 6. create-task ───────────────────────────────────────────────────────
    p_create = sub.add_parser(
        "create-task",
        help=(
            "Create a task in ClickUp from an approved proposal JSON. "
            "REQUIRES --approved-by-dylan AND an approved proposal file."
        ),
    )
    p_create.add_argument(
        "--from-proposal",
        dest="proposal_path",
        required=True,
        help="Path to the proposal JSON file.",
    )
    p_create.add_argument(
        "--approved-by-dylan",
        action="store_true",
        help=(
            "Explicit operator consent. Without this flag, the command "
            "refuses to run. The proposal file must ALSO contain "
            "approved_by: dylan and an ISO approved_at timestamp."
        ),
    )

    return parser


# ── Subcommand bodies ──────────────────────────────────────────────────────


def cmd_workspaces(client: ClickUpClient, _args: argparse.Namespace) -> int:
    rows = client.list_workspaces()
    print(json.dumps({"workspaces": rows}, indent=2))
    return 0


def cmd_lists(client: ClickUpClient, args: argparse.Namespace) -> int:
    rows = client.list_lists(args.workspace)
    print(json.dumps({"lists": rows}, indent=2))
    return 0


def cmd_tasks(client: ClickUpClient, args: argparse.Namespace) -> int:
    rows = client.list_tasks(args.list_id, status=args.status)
    print(json.dumps({"tasks": rows}, indent=2))
    return 0


def cmd_task(client: ClickUpClient, args: argparse.Namespace) -> int:
    row = client.get_task(args.task_id)
    print(json.dumps({"task": row}, indent=2))
    return 0


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str, max_len: int = 40) -> str:
    """Turn ``Hello, World!`` into ``hello-world`` for filenames."""
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s[:max_len] or "untitled"


def cmd_propose_task(_client: ClickUpClient, args: argparse.Namespace) -> int:
    """Build a proposal JSON, print it, and persist a copy.

    Never touches ClickUp. The output JSON is the contract that
    ``create-task --from-proposal`` consumes.
    """
    now = datetime.now(timezone.utc)
    proposal: Dict[str, Any] = {
        "schema_version": 1,
        "created_at": now.isoformat(),
        "list_id": args.list_id,
        "title": args.title,
        "body": args.body,
        "tag": args.tag,
        # These two fields start blank — Dylan fills them in before
        # running create-task. Refusing to set them here is the whole
        # point of the approval gate.
        "approved_by": None,
        "approved_at": None,
    }
    payload = json.dumps(proposal, indent=2)
    print(payload)

    # Persist a copy. Create the dir if missing.
    out_dir = proposal_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    slug = _slugify(args.title)
    out_path = out_dir / f"{timestamp}-{slug}.json"
    out_path.write_text(payload + "\n", encoding="utf-8")
    # Emit a small hint on stderr so the JSON on stdout stays clean.
    print(f"[clickup] proposal saved to {out_path}", file=sys.stderr)
    return 0


def cmd_create_task(client: ClickUpClient, args: argparse.Namespace) -> int:
    """Read proposal from disk, validate, then POST to ClickUp.

    Refuses (exit 1) if any of the following is missing:
      * ``--approved-by-dylan`` flag on the command line
      * ``approved_by: dylan`` in the proposal metadata
      * non-empty ``approved_at`` ISO timestamp in the proposal metadata
      * non-empty ``list_id``, ``title``, ``body`` fields

    On success, prints the created task as JSON to stdout.
    """
    if not args.approved_by_dylan:
        print(
            "REFUSED: --approved-by-dylan flag is required for any write. "
            "Re-run with --approved-by-dylan once Dylan has reviewed the "
            "proposal.",
            file=sys.stderr,
        )
        return 1

    proposal_path = Path(args.proposal_path)
    try:
        raw = proposal_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"REFUSED: cannot read proposal file {proposal_path}: {e}", file=sys.stderr)
        return 1

    try:
        proposal = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ProposalValidationError(
            f"Proposal file is not valid JSON: {e}"
        ) from e

    _validate_proposal(proposal)

    result = client.create_task_from_proposal(proposal)
    print(json.dumps({"created_task": result}, indent=2))
    return 0


# ── Proposal validation ────────────────────────────────────────────────────


REQUIRED_PROPOSAL_FIELDS = ("list_id", "title", "body", "approved_by", "approved_at")


def _validate_proposal(proposal: Dict[str, Any]) -> None:
    """Raise ProposalValidationError if anything is missing or empty."""
    if not isinstance(proposal, dict):
        raise ProposalValidationError(
            f"Proposal must be a JSON object, got {type(proposal).__name__}."
        )
    missing = [f for f in REQUIRED_PROPOSAL_FIELDS if not proposal.get(f)]
    if missing:
        raise ProposalValidationError(
            "Proposal is missing required fields (or they are empty): "
            + ", ".join(missing)
        )
    if proposal["approved_by"] != "dylan":
        raise ProposalValidationError(
            "Proposal.approved_by must be exactly 'dylan' "
            f"(got {proposal['approved_by']!r})."
        )
    # Light ISO timestamp check — we don't need full RFC 3339 parsing.
    if "T" not in str(proposal["approved_at"]):
        raise ProposalValidationError(
            "Proposal.approved_at must be an ISO 8601 timestamp "
            f"(got {proposal['approved_at']!r})."
        )


# ── Entry point ─────────────────────────────────────────────────────────────


def clickup_command(args: argparse.Namespace) -> int:
    """Dispatch ``hermes clickup <subcommand>`` after argparse parsing."""
    sub = getattr(args, "clickup_subcommand", None) or getattr(args, "subcommand", None)
    if not sub:
        build_parser().print_help()
        return 2

    # Inner handlers read ``subcommand``; plugin wiring uses ``clickup_subcommand``.
    args.subcommand = sub

    if sub == "propose-task":
        try:
            return cmd_propose_task(None, args)  # type: ignore[arg-type]
        except (ClickUpError, ProposalValidationError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    if sub == "create-task":
        try:
            _validate_create_task_preflight(args)
        except ProposalValidationError as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        try:
            client = ClickUpClient()
        except AuthError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        try:
            return cmd_create_task(client, args)
        except AuthError as e:
            print(f"AUTH: {e}", file=sys.stderr)
            return 2
        except ForbiddenEndpointError as e:
            print(f"FORBIDDEN: {e}", file=sys.stderr)
            return 3
        except HTTPError as e:
            print(f"HTTP {e.status}: {e.body[:200]}", file=sys.stderr)
            return 4
        except ProposalValidationError as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        except ClickUpError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 5

    try:
        client = ClickUpClient()
    except AuthError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    dispatch = {
        "workspaces": cmd_workspaces,
        "lists": cmd_lists,
        "tasks": cmd_tasks,
        "task": cmd_task,
    }
    handler = dispatch.get(sub)
    if handler is None:
        build_parser().print_help()
        return 2
    try:
        return handler(client, args)
    except AuthError as e:
        print(f"AUTH: {e}", file=sys.stderr)
        return 2
    except ForbiddenEndpointError as e:
        print(f"FORBIDDEN: {e}", file=sys.stderr)
        return 3
    except HTTPError as e:
        print(f"HTTP {e.status}: {e.body[:200]}", file=sys.stderr)
        return 4
    except ProposalValidationError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    except ClickUpError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 5


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point. Returns a unix-style exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Subcommands that don't need a client: propose-task (purely local).
    if args.subcommand == "propose-task":
        try:
            return cmd_propose_task(None, args)  # type: ignore[arg-type]
        except (ClickUpError, ProposalValidationError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 1

    # create-task performs its own local validation (flag + proposal file)
    # BEFORE constructing a network client, so a missing CLICKUP_API_TOKEN
    # doesn't mask approval-gate refusals. This is intentional: the gate
    # check must work even when the operator forgets to export the token.
    if args.subcommand == "create-task":
        try:
            _validate_create_task_preflight(args)
        except ProposalValidationError as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        # Preflight passed; now build the client for the actual POST.
        try:
            client = ClickUpClient()
        except AuthError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        try:
            return cmd_create_task(client, args)
        except AuthError as e:
            print(f"AUTH: {e}", file=sys.stderr)
            return 2
        except ForbiddenEndpointError as e:
            print(f"FORBIDDEN: {e}", file=sys.stderr)
            return 3
        except HTTPError as e:
            print(f"HTTP {e.status}: {e.body[:200]}", file=sys.stderr)
            return 4
        except ProposalValidationError as e:
            print(f"REFUSED: {e}", file=sys.stderr)
            return 1
        except ClickUpError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 5

    # All other subcommands: read paths, need a client, no preflight.
    try:
        client = ClickUpClient()
    except AuthError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    dispatch = {
        "workspaces": cmd_workspaces,
        "lists": cmd_lists,
        "tasks": cmd_tasks,
        "task": cmd_task,
    }
    handler = dispatch[args.subcommand]
    try:
        return handler(client, args)
    except AuthError as e:
        print(f"AUTH: {e}", file=sys.stderr)
        return 2
    except ForbiddenEndpointError as e:
        print(f"FORBIDDEN: {e}", file=sys.stderr)
        return 3
    except HTTPError as e:
        print(f"HTTP {e.status}: {e.body[:200]}", file=sys.stderr)
        return 4
    except ProposalValidationError as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 1
    except ClickUpError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 5


def _validate_create_task_preflight(args: argparse.Namespace) -> None:
    """Run all local checks for create-task BEFORE building a network client.

    This is the only path where we accept that auth may not be configured
    yet — a missing token never overrides the approval gate. We check, in
    order:
      1. The --approved-by-dylan flag is present.
      2. The proposal file exists and is readable.
      3. The file is valid JSON, parses to a dict, and passes the
         ``_validate_proposal`` rules.
    """
    if not args.approved_by_dylan:
        raise ProposalValidationError(
            "--approved-by-dylan flag is required for any write. Re-run "
            "with --approved-by-dylan once Dylan has reviewed the proposal."
        )
    proposal_path = Path(args.proposal_path)
    try:
        raw = proposal_path.read_text(encoding="utf-8")
    except OSError as e:
        raise ProposalValidationError(
            f"cannot read proposal file {proposal_path}: {e}"
        ) from e
    try:
        proposal = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ProposalValidationError(
            f"proposal file is not valid JSON: {e}"
        ) from e
    _validate_proposal(proposal)


# ── Hermes plugin hook ──────────────────────────────────────────────────────


def register(subparsers) -> None:
    """Hook the hermes CLI uses to discover this plugin's subcommand.

    Adds a single ``clickup`` parent parser whose subcommands mirror the
    argparse tree built by ``build_parser``.
    """
    parser = subparsers.add_parser(
        "clickup",
        help=(
            "Read-only ClickUp bridge (workspaces, lists, tasks). Writes "
            "are approval-gated."
        ),
        description=(
            "Read-only ClickUp bridge. Every write requires explicit Dylan "
            "approval (--approved-by-dylan AND approved_by: dylan in the "
            "proposal file)."
        ),
    )
    # Re-use the existing subparser tree by grafting its subcommands onto
    # the new parent. This keeps the contract identical whether the user
    # calls ``hermes clickup workspaces`` directly or via the plugin hook.
    sub = parser.add_subparsers(dest="clickup_subcommand", required=True)
    inner = build_parser()
    for action in inner._actions:
        # We only want the subparsers' choices. Skip help and the parent.
        if isinstance(action, argparse._SubParsersAction):
            for name, sub_action in action.choices.items():
                # Rebuild each subcommand on the new parser.
                sub.add_parser(
                    name,
                    parents=[sub_action],
                    add_help=False,
                )
            break
    parser.set_defaults(func=clickup_command)


def main_from_plugin_args(argv: Sequence[str]) -> int:
    """Adapter for the plugin hook: strip the leading 'clickup' subcommand
    name so the inner ``main`` sees the same argv regardless of the caller.
    """
    if argv and argv[0] == "clickup":
        argv = argv[1:]
    return main(argv)
