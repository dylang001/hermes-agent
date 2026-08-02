from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


path = Path(__file__).parents[2] / "scripts" / "ci" / "verify_agent_run_manifest.py"
spec = importlib.util.spec_from_file_location("verify_agent_run_manifest", path)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def valid():
    return {
        "schema": "hermes-agent-run-manifest/v1", "run_id_hash": "abc",
        "objective_hash": "def", "privacy_classification": "restricted-source/aggregate-only",
        "started_at": "2026-08-02T20:00:00Z", "ended_at": "2026-08-02T20:01:00Z",
        "outcome": "completed", "reviewer_result": "passed",
        "artifact_refs": {"branch": "agent/example", "commit": "HEAD"},
        "recovery_refs": {"manifest": "audit/agent-runs/example.json"},
    }


class ValidatorTests(unittest.TestCase):
    def test_valid_terminal_reviewed_manifest(self):
        self.assertEqual(module.validate(valid()), [])

    def test_pending_or_raw_payload_fails(self):
        value = valid()
        value["reviewer_result"] = "pending"
        value["evidence"] = {"tool_arguments": {"token": "unsafe"}}
        errors = module.validate(value)
        self.assertIn("invalid:reviewer_result", errors)
        self.assertIn("forbidden:tool_arguments", errors)
        self.assertIn("forbidden:token", errors)


if __name__ == "__main__":
    unittest.main()
