# Hermes ClickUp CLI Fix — 2026-07-16

## Symptom

`hermes clickup --help` showed subcommands, but `hermes clickup workspaces` did not execute — argparse parsed `clickup` but no dispatch `func` ran, so Hermes printed top-level help (VPS: `unrecognized arguments`).

## Root cause

`clickup-bridge` registered CLI subparsers via `setup_fn` but omitted `handler_fn`. `hermes_cli/main.py` only calls `args.func(args)` when `handler_fn` is set on plugin CLI registration (see `google_meet` / `teams_pipeline` for the canonical pattern).

## Fix (smallest layer)

User plugin `~/.hermes/plugins/clickup-bridge/`:

1. Added `clickup_command(args)` in `cli.py` — dispatches on `clickup_subcommand`.
2. Passed `handler_fn=clickup_command` in `register(ctx)`.
3. Set `parent.set_defaults(func=clickup_command)` in `_attach_subcommands_to_parent` / `register()`.
4. Changed `plugin.yaml` `kind: tool` → `kind: standalone` (removes loader warning).

**No core changes.** Task OS (`plugins/clickup_task_os`) untouched. No duplicate plugin registration.

## Verification

```bash
hermes clickup --help
hermes clickup workspaces          # JSON workspaces list
hermes clickup lists --workspace 90152507264
hermes clickup create-task --help
```

Tests: `scripts/run_tests.sh tests/plugins/test_clickup_bridge_cli.py -q`

## VPS deploy note

Copy the fixed plugin tree to `/opt/hermes/home/plugins/clickup-bridge/` when deploying (user plugin, not in app git tree).
