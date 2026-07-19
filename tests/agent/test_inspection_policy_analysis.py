"""Tests for inspection policy analytics."""

import json

from agent.inspection_policy_analysis import analyze_session_messages


def _asst(tools):
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": f"c{i}",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args),
                },
            }
            for i, (name, args) in enumerate(tools)
        ],
    }


def test_inspect_before_first_mutate():
    messages = [
        _asst([("terminal", {"command": "ls -la"})]),
        _asst([("read_file", {"path": "a.py"})]),
        _asst([("terminal", {"command": "grep foo a.py"})]),
        _asst([("write_file", {"path": "a.py", "content": "x"})]),
        _asst([("terminal", {"command": "ls"})]),
    ]
    r = analyze_session_messages(messages, session_meta={"id": "s1"})
    assert r.inspect_before_first_mutate == 3
    assert r.inspect_turns >= 3
    assert r.mutate_turns >= 1
    assert r.shell_replaceable_cmds >= 2
