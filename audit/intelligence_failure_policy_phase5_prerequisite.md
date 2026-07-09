# Phase 5 Failure Policy Prerequisite

Before implementing failure-policy behaviour, verify that Phase 4 evidence compaction does not remove classifier-critical failure details needed by retry/fallback classification.

Required preserved evidence in compacted tool output:

- HTTP status code
- provider/model name where available
- quota/auth keywords
- timeout markers
- schema/configuration error messages
- tool name
- traceback file path and line number
- approval-required marker

Focused guard test:

```bash
./.venv/bin/python -m pytest tests/agent/test_intelligence_policy.py -q
```

Relevant test:

- `test_phase5_failure_classifier_evidence_survives_compaction`

If any of these markers are lost, preserve them explicitly in compacted output before Phase 5 retry/fallback behaviour is added.
