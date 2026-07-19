"""Tests for Terminal Loop Analysis."""

import json

from agent.terminal_loop_analysis import (
    analyze_terminal_events,
    classify_command,
    extract_terminal_events,
)


def _asst_terminal(cmd: str, call_id: str = "c1"):
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": "terminal",
                    "arguments": json.dumps({"command": cmd}),
                },
            }
        ],
    }


def _tool_result(call_id: str, exit_code: int, output: str = "ok"):
    return {
        "role": "tool",
        "tool_name": "terminal",
        "tool_call_id": call_id,
        "content": json.dumps(
            {"output": output, "exit_code": exit_code, "error": None}
        ),
    }


class TestClassify:
    def test_categories(self):
        assert classify_command("pytest tests/") == "test"
        assert classify_command("git status") == "git"
        assert classify_command("grep -r foo .") == "search"
        assert classify_command("ls -la && cat README") == "inspect"
        assert classify_command("pip install foo") == "install"
        assert classify_command("ssh host uptime") == "ssh"


class TestExtract:
    def test_duplicate_and_retry(self):
        messages = [
            _asst_terminal("pytest tests/foo.py", "a"),
            _tool_result("a", 1, "FAIL"),
            _asst_terminal("pytest tests/foo.py", "b"),
            _tool_result("b", 1, "FAIL"),
            _asst_terminal("ls", "c"),
            _tool_result("c", 0, "ok"),
            _asst_terminal("ls", "d"),
            _tool_result("d", 0, "ok"),
        ]
        events = extract_terminal_events(messages)
        stats = analyze_terminal_events(events)
        assert stats["terminal_calls"] == 4
        assert stats["retry_events"] >= 1
        assert stats["duplicate_commands"] >= 2
        assert stats["categories"]["test"] == 2
        assert stats["categories"]["inspect"] == 2
