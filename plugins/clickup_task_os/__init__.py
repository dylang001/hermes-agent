"""ClickUp Task OS plugin — operator CLI only; no model tools registered."""

from __future__ import annotations

from plugins.clickup_task_os.cli import register_cli, task_os_command


def register(ctx) -> None:
    ctx.register_cli_command(
        name="task-os",
        help="ClickUp Task OS (Orchidea Ops poller / setup)",
        setup_fn=register_cli,
        handler_fn=task_os_command,
        description=(
            "Fork-local ClickUp Task OS. Polls Orchidea Ops for Ready+hermes-ready, "
            "locks via Kanban idempotency_key=clickup:<id>, executes on the task-os "
            "profile, and lands work in Review/Waiting. Does not add core tool schemas."
        ),
    )
