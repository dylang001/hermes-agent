"""Tests for clickup-bridge CLI dispatch (user plugin fixture)."""

from __future__ import annotations

import argparse
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "clickup-bridge"


def _load_plugin_modules():
    pkg_name = "clickup_bridge_fixture"
    if pkg_name in sys.modules:
        for key in list(sys.modules):
            if key == pkg_name or key.startswith(pkg_name + "."):
                del sys.modules[key]

    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(FIXTURE)]  # type: ignore[attr-defined]
    sys.modules[pkg_name] = pkg

    def _load(sub: str):
        path = FIXTURE / f"{sub}.py"
        full = f"{pkg_name}.{sub}"
        spec = importlib.util.spec_from_file_location(full, path, submodule_search_locations=[])
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = pkg_name
        sys.modules[full] = mod
        pkg.__dict__[sub] = mod
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        return mod

    client = _load("clickup_client")
    cli = _load("cli")
    init = _load("__init__")
    return types.SimpleNamespace(cli=cli, init=init, client=client)


@pytest.fixture()
def clickup_pkg():
    return _load_plugin_modules()


def test_build_parser_workspaces_help(clickup_pkg):
    parser = clickup_pkg.cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    args = parser.parse_args(["workspaces"])
    assert args.subcommand == "workspaces"


def test_build_parser_lists_help(clickup_pkg):
    parser = clickup_pkg.cli.build_parser()
    args = parser.parse_args(["lists", "--workspace", "90152507264"])
    assert args.workspace == "90152507264"

    with pytest.raises(SystemExit):
        parser.parse_args(["create-task"])


def test_clickup_command_workspaces_dispatches(clickup_pkg):
    cli = clickup_pkg.cli
    mock_client = MagicMock()
    mock_client.list_workspaces.return_value = [{"id": "90152507264", "name": "Main"}]

    args = argparse.Namespace(clickup_subcommand="workspaces")
    with patch.object(cli, "ClickUpClient", return_value=mock_client):
        rc = cli.clickup_command(args)

    assert rc == 0
    mock_client.list_workspaces.assert_called_once()


def test_clickup_command_missing_subcommand_prints_help(clickup_pkg, capsys):
    rc = clickup_pkg.cli.clickup_command(argparse.Namespace(clickup_subcommand=None))
    assert rc == 2
    assert "workspaces" in capsys.readouterr().out


def test_hermes_clickup_main_argv_roundtrip(clickup_pkg):
    cli = clickup_pkg.cli
    mock_client = MagicMock()
    mock_client.list_workspaces.return_value = []

    with patch.object(cli, "ClickUpClient", return_value=mock_client):
        rc = cli.main(["workspaces"])
    assert rc == 0


def test_register_cli_sets_handler(clickup_pkg):
    parent = argparse.ArgumentParser(prog="hermes clickup")
    clickup_pkg.init.register_cli(parent)
    args = parent.parse_args(["workspaces"])
    assert args.clickup_subcommand == "workspaces"
    assert args.func is clickup_pkg.cli.clickup_command
