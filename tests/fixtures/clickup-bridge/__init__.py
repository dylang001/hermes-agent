"""clickup-bridge — read-only ClickUp bridge for the Hermes Growth OS.

Plugin entrypoint. The hermes plugin loader discovers this file in
``~/.hermes/plugins/clickup-bridge/`` and calls ``register`` to wire the
``hermes clickup`` subcommand into the top-level CLI.

Hard rules baked in:
  * No writes without explicit Dylan approval.
  * Approval requires BOTH ``--approved-by-dylan`` on the command line
    AND ``approved_by: dylan`` / ``approved_at: <iso>`` in the proposal file.
  * No ``delete``, ``archive``, ``move``, or ``edit`` calls — ever. The
    client module's path guard refuses those endpoints at the network
    layer, not just at the CLI layer.
"""

from __future__ import annotations

__version__ = "0.1.0"

# Re-export the public API for convenience (tests import from here).
from .clickup_client import (  # noqa: F401
    ApprovalGateError,
    AuthError,
    ClickUpClient,
    ClickUpError,
    ForbiddenEndpointError,
    HTTPError,
    ProposalValidationError,
)
from .cli import (  # noqa: F401
    build_parser as _cli_build_parser,
    clickup_command,
    main,
    proposal_dir,
    main_from_plugin_args,
)
# Imported under the alias ``_cli_register`` so it does not shadow this
# module's public ``register(ctx)`` hook. The host's plugin manager
# discovers this module via ``getattr(module, "register", None)`` and
# calls it with a ``PluginContext``; that contract is the one this
# module must satisfy, NOT the older argparse ``register(subparsers)``
# shape.
from .cli import register as _cli_register  # noqa: F401


import argparse as _argparse
from typing import Any


# ClickUp plugin metadata exposed to the host. Pulling these out as
# module-level constants keeps ``register(ctx)`` declarative and makes
# them trivially assertable from the regression test.
PLUGIN_CLI_COMMAND_NAME = "clickup"
PLUGIN_CLI_COMMAND_HELP = (
    "Read-only ClickUp bridge (workspaces, lists, tasks). Writes are "
    "approval-gated."
)
PLUGIN_CLI_COMMAND_DESCRIPTION = (
    "Read-only ClickUp bridge. Every write requires explicit Dylan "
    "approval (--approved-by-dylan AND approved_by: dylan in the "
    "proposal file)."
)


def _is_subparsers_container(obj: Any) -> bool:
    """Return True iff ``obj`` looks like an argparse ``_SubParsersAction``.

    The host's plugin manager calls our ``setup_fn`` with a *parent*
    ``argparse.ArgumentParser`` (it has already created the ``clickup``
    parser for us — see ``hermes_cli/main.py`` ~line 11930: it does
    ``subparsers.add_parser(name, ...)`` and then ``setup_fn(parser)``).
    Older direct callers pass a subparsers container. We detect the
    difference by duck-typing on the ``add_parser`` method shape, which
    is the only thing that distinguishes the two at runtime.
    """
    return hasattr(obj, "choices") and isinstance(
        getattr(obj, "choices", None), dict
    )


def register_cli(target) -> None:
    """Argparse-setup hook: attach the ``clickup`` subparser tree.

    Handles BOTH of the calling conventions the hermes codebase uses:

    1. **Host path (new):** the host's plugin manager has already
       created the ``clickup`` parent parser and passes it in as
       ``target``. We add the subparser tree onto it.
    2. **Direct path (legacy):** a caller passes an argparse
       subparsers container. We create the ``clickup`` parent on it
       and then add the subparser tree.

    Both paths converge on ``_cli_register(target)`` for the direct
    case, and on ``_attach_subcommands_to_parent(target)`` for the
    host case.
    """
    if _is_subparsers_container(target):
        # Direct-import / legacy path: container expects add_parser().
        _cli_register(target)
        return

    # Host path: ``target`` is the already-created ``clickup`` parent
    # parser. Build the inner subparser tree directly on it.
    _attach_subcommands_to_parent(target)


def _attach_subcommands_to_parent(parent: "_argparse.ArgumentParser") -> None:
    """Graft ``workspaces``, ``lists``, ``tasks``, ``task``,
    ``propose-task``, ``create-task`` onto an existing parent parser.

    This mirrors the second half of ``cli.register`` but operates on
    a parent that the host has already created for us. We re-use the
    subparser definitions from ``cli.build_parser()`` so the
    contracts are identical regardless of who creates the parent.
    """
    sub = parent.add_subparsers(dest="clickup_subcommand", required=True)
    inner = _cli_build_parser()
    for action in inner._actions:
        # We only want the subparsers' choices. Skip help and the parent.
        if isinstance(action, _argparse._SubParsersAction):
            for name, sub_action in action.choices.items():
                # Rebuild each subcommand on the new parser.
                sub.add_parser(
                    name,
                    parents=[sub_action],
                    add_help=False,
                )
            break
    parent.set_defaults(func=clickup_command)


def register(ctx) -> None:
    """Hermes plugin manager hook: register the ``clickup`` CLI command.

    The host's plugin manager discovers this module and calls
    ``register(ctx)`` with a ``PluginContext``. We forward to
    ``ctx.register_cli_command`` with this module's
    ``register_cli`` as the argparse setup function.

    No network calls. No file writes. No ClickUp API.
    """
    ctx.register_cli_command(
        name=PLUGIN_CLI_COMMAND_NAME,
        help=PLUGIN_CLI_COMMAND_HELP,
        setup_fn=register_cli,
        handler_fn=clickup_command,
        description=PLUGIN_CLI_COMMAND_DESCRIPTION,
    )
