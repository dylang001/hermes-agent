#!/usr/bin/env python3
"""Fail CI when agent-created work lacks a terminal reviewed manifest."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REQUIRED = {
    "schema", "run_id_hash", "objective_hash", "privacy_classification",
    "started_at", "ended_at", "outcome", "reviewer_result", "artifact_refs",
    "recovery_refs",
}
TERMINAL = {"completed", "failed", "interrupted", "cancelled"}
REVIEWS = {"passed", "approved", "failed", "rejected", "not_required"}
FORBIDDEN = {
    "prompt", "message", "messages", "tool_args", "tool_arguments", "tool_result",
    "tool_results", "email", "recipient", "password", "token", "secret",
}
COMMIT_SHA = re.compile(r"^[0-9a-f]{7,40}$")


def nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {str(key).lower() for key in value} | {
            child for item in value.values() for child in nested_keys(item)
        }
    if isinstance(value, list):
        return {child for item in value for child in nested_keys(item)}
    return set()


def validate(payload: dict[str, Any]) -> list[str]:
    errors = [f"missing:{key}" for key in sorted(REQUIRED - payload.keys())]
    errors.extend(f"forbidden:{key}" for key in sorted(nested_keys(payload) & FORBIDDEN))
    if payload.get("privacy_classification") != "restricted-source/aggregate-only":
        errors.append("invalid:privacy_classification")
    if payload.get("outcome") not in TERMINAL:
        errors.append("invalid:outcome")
    if payload.get("reviewer_result") not in REVIEWS:
        errors.append("invalid:reviewer_result")
    artifacts = payload.get("artifact_refs")
    if not isinstance(artifacts, dict) or not artifacts.get("branch") or not artifacts.get("commit"):
        errors.append("invalid:artifact_refs")
    elif not COMMIT_SHA.fullmatch(str(artifacts["commit"])):
        errors.append("invalid:artifact_refs.commit")
    recovery = payload.get("recovery_refs")
    if not isinstance(recovery, dict) or not recovery.get("manifest"):
        errors.append("invalid:recovery_refs")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()
    failed = False
    for path in args.paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        errors = validate(value) if isinstance(value, dict) else ["invalid:root_object"]
        print(json.dumps({"path": str(path), "valid": not errors, "errors": errors}))
        failed |= bool(errors)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
