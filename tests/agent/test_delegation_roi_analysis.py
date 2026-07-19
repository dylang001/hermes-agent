"""Tests for Delegation ROI analytics."""

import json

from agent.delegation_roi_analysis import (
    count_mutations,
    parse_delegate_outcomes,
)


def test_count_mutations():
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"path":"a.py"}',
                    },
                }
            ],
        },
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "2",
                    "function": {
                        "name": "terminal",
                        "arguments": json.dumps({"command": "rm -rf /tmp/x"}),
                    },
                }
            ],
        },
    ]
    m = count_mutations(messages)
    assert m["write_file"] == 1
    assert m["terminal_mutate"] == 1
    assert m["total_mutations"] == 2


def test_parse_outcomes():
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "d1",
                    "function": {"name": "delegate_task", "arguments": "{}"},
                }
            ],
        },
        {
            "role": "tool",
            "tool_name": "delegate_task",
            "content": json.dumps(
                {"status": "dispatched", "delegation_id": "deleg_1"}
            ),
        },
        {
            "role": "tool",
            "tool_name": "delegate_task",
            "content": json.dumps(
                {"error": "Async delegation capacity reached (3 running)."}
            ),
        },
    ]
    o = parse_delegate_outcomes(messages)
    assert o["spawn_calls"] == 1
    assert o["dispatched"] == 1
    assert o["capacity_error"] == 1
