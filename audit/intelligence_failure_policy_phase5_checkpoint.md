# Phase 5 Failure Policy Checkpoint

Date: 2026-07-09

Scope:
- Added disabled-by-default failure policy flag:
  - `agent.intelligence_failure_policy_enabled`
  - `HERMES_INTELLIGENCE_FAILURE_POLICY=1`
- Added deterministic failure-policy decisions for:
  - `transient`
  - `auth_or_quota`
  - `configuration_or_schema`
  - `tool_unavailable`
  - `approval_required`
- Wired the enabled-only branch into the central API exception path after existing one-shot provider-specific recoveries and before generic retry/backoff.
- Extended sanitized run reports with failure-policy metadata only.

Behavior:
- Flag off: existing retry/fallback behavior is unchanged.
- Flag on:
  - `auth_or_quota`: activate the existing configured fallback once when available; otherwise fail closed.
  - `configuration_or_schema`: fail closed; no blind retry.
  - `tool_unavailable`: fail closed unless a future explicit safe fallback is added.
  - `approval_required`: stop and surface approval-required state; no retry/fallback.
  - `transient`: preserve existing bounded retry behavior.

Compaction guard dependency:
- The existing Phase 4 guard test remains part of the required suite.
- Failure-policy classification does not depend on raw evidence that the compaction hook may remove; compacted errors preserve HTTP status, provider/model, quota/auth keywords, timeout markers, schema/configuration messages, tool names, traceback file/line, and approval markers.

Verification:
```text
./.venv/bin/python -m pytest tests/agent/test_intelligence_policy.py tests/agent/test_intelligence_policy_phase1_5.py -q
................................                                         [100%]
32 passed in 6.75s
```

```text
./.venv/bin/python -m py_compile agent/intelligence_policy.py agent/agent_init.py agent/conversation_loop.py tests/agent/test_intelligence_policy.py
```

Non-changes:
- No production deployment.
- No service restart.
- No provider/model routing change except the flag-enabled auth/quota path using the existing fallback chain.
- No credential, MCP, schedule, startup, or approval-gate changes.

Rollback:
- Disable `agent.intelligence_failure_policy_enabled` or unset `HERMES_INTELLIGENCE_FAILURE_POLICY`.
- To remove the patch, revert the Phase 5 hunks in:
  - `agent/intelligence_policy.py`
  - `agent/agent_init.py`
  - `agent/conversation_loop.py`
  - `tests/agent/test_intelligence_policy.py`
  - `audit/intelligence_failure_policy_phase5_checkpoint.md`
