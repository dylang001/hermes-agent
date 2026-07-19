"""Tests for Model Wake-up Analysis (Track B evidence gate)."""

from agent.wakeup_analysis import analyze_messages


def _asst(tools=None, content=None):
    raw = None
    if tools is not None:
        raw = [
            {
                "id": f"c{i}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": args if isinstance(args, str) else __import__("json").dumps(args),
                },
            }
            for i, (name, args) in enumerate(tools)
        ]
    return {"role": "assistant", "content": content, "tool_calls": raw}


class TestWakeupClassification:
    def test_consecutive_safe_turns_estimate_save(self):
        messages = [
            _asst([("read_file", {"path": "a.py"})]),
            {"role": "tool", "content": "a"},
            _asst([("read_file", {"path": "b.py"})]),
            {"role": "tool", "content": "b"},
            _asst([("read_file", {"path": "c.py"})]),
            {"role": "tool", "content": "c"},
            _asst(content="done"),  # breaks streak
        ]
        stats = analyze_messages(messages)
        # 3 consecutive SAFE turns → save 2
        assert stats["batchable_wakeups_saved_estimate"] == 2
        assert stats["turn_labels"]["safe_only"] == 3
        assert stats["batchable_save_pct_of_tool_turns"] == round(100.0 * 2 / 3, 1)

    def test_mutating_breaks_streak(self):
        messages = [
            _asst([("read_file", {"path": "a.py"})]),
            _asst([("terminal", {"command": "ls"})]),
            _asst([("read_file", {"path": "b.py"})]),
        ]
        stats = analyze_messages(messages)
        assert stats["batchable_wakeups_saved_estimate"] == 0

    def test_duplicate_reads(self):
        messages = [
            _asst([("read_file", {"path": "a.py"})]),
            _asst([("read_file", {"path": "a.py"})]),
        ]
        stats = analyze_messages(messages)
        assert stats["files_reread"] == 1
        assert stats["duplicate_ops"] == 1
        assert stats["turns_only_duplicates"] == 1

    def test_subagent_labeled(self):
        messages = [
            _asst([("delegate_task", {"goal": "x"})]),
        ]
        stats = analyze_messages(messages)
        assert stats["turn_labels"]["subagent"] == 1
        assert stats["subagent_spawns"] == 1
