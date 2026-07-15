# Hermes Tool Failure Root Cause — stale `/root/audit` loop

**Date:** 2026-07-15  
**Symptom:** Desktop session probes `/root/audit/` with `ls` / `pwd` / `echo` variations, then:

`same_tool_failure_halt after 8 repeated non-progressing attempts`

**Deploy facts (live VPS):**

| Fact | Value |
|------|--------|
| App | `/opt/hermes/app` |
| HERMES_HOME | `/opt/hermes/home` |
| Gateway/Dashboard WD | `/opt/hermes/home` |
| Service user | `dylan` |
| Live audit dir | `/opt/hermes/app/audit` |
| Obsidian vault (data) | `/opt/hermes/data/obsidian/Growth OS` |
| `/root/audit` | Permission denied for `dylan` (stale) |

---

## 1. Root cause (multi-factor)

| Factor | Finding | Severity |
|--------|---------|----------|
| **A. Recalled Mem0 / session facts** | Prefetch injects verbatim bullets into the *user* message. Old VPS paths (`/root/audit`, `/root/.hermes`) survive migration and look authoritative. No path remap existed. | **Primary** |
| **B. Missing authoritative runtime block** | System prompt had host OS + cwd + `$HOME`, but **not** app root, HERMES_HOME, writable roots, or an explicit “stale /root is invalid” rule. | High |
| **C. CANONICAL_CONTEXT.md not loaded** | Docs-only; never injected into sessions. | Medium |
| **D. Guardrail too coarse** | `same_tool_failure_halt_after=8` counts by tool name. Cosmetically different commands (`ls`, `echo; ls`, `pwd`) each reset exact-signature counts but still fail on the same path until 8. | High (amplifier) |
| **E. Recovery text invited more terminal probes** | Hint suggested `pwd && ls -la` — models treated that as progress while still targeting `/root/audit`. | Medium |
| **F. Broken Obsidian MCP path** | `mcp_servers.obsidian` still mounts `/root/obsidian-vault` (inaccessible). Reinforces stale-root assumptions. | High (related) |
| **G. Desktop remote cwd** | Dashboard `WorkingDirectory=/opt/hermes/home`, `terminal.cwd: .` — cwd itself is correct. Bug is **path selection**, not wrong process cwd. | Ruled out as primary |

**Causal chain:**

```
Mem0/session recalls /root/audit
  → model probes /root/audit (permission denied)
  → changes syntax, same path
  → same_tool_failure counter → 8
  → same_tool_failure_halt
```

---

## 2. Classification

| Item | Status |
|------|--------|
| Runtime/path defect | **Confirmed** |
| Missing tools | Not the cause |
| Wrong gateway WorkingDirectory | Not the cause (correct `/opt/hermes/home`) |
| Guardrail working as configured | Yes — halt is correct; threshold/equivalence were wrong for this failure class |

---

## 3. Fixes shipped (smallest safe)

| Fix | Location |
|-----|----------|
| Authoritative runtime metadata block every local-backend session | `agent/runtime_metadata.py` + `build_environment_hints()` |
| Mem0/session stale-path remap at injection | `sanitize_context()` / `build_memory_context_block()` |
| Equivalent missing-path halt after **2** | `agent/tool_guardrails.py` (`equivalent_path_failure_*`) |
| Recovery instructions require strategy change + writable roots | tool guardrail hints |
| Tests for stale `/root` remap, equivalent halt, discovery, resume | `tests/agent/test_runtime_metadata.py` |
| DEFAULT_CONFIG documents `equivalent_failure: 2` | `hermes_cli/config.py` |

**Not done in core (ops):** rewrite VPS `mcp_servers.obsidian` args to `/opt/hermes/data/obsidian/Growth OS`; optional Mem0 purge of stale `/root` memories.

---

## 4. Acceptance mapping

| Requirement | Met by |
|-------------|--------|
| Session gets app/home/cwd/user/platform/writable roots | `RuntimeMetadata.as_prompt_block()` |
| First missing-path → discover roots, don’t blind-retry | equivalent warn + remapped suggestion |
| Equivalent terminal retries halt after 2 | `equivalent_failure_halt_after=2` |
| Recovery requires changed strategy | updated terminal recovery hint |
| Mem0 must not override live paths | remap + system-note precedence |
| Tests | 8 new + existing guardrail suite green |

---

## 5. Ops follow-ups

1. Patch VPS `config.yaml` MCP Obsidian path → `/opt/hermes/data/obsidian/Growth OS`.
2. Add VPS `tool_loop_guardrails.hard_stop_after.equivalent_failure: 2` (code default applies after deploy; nested key deep-merges for new installs).
3. Optionally search Mem0 for `/root/audit` and archive/delete stale memories.
4. Restart `hermes-dashboard` / gateway after deploy so Desktop sessions get the new prompt block.

---

## 6. Rollback

Revert commits touching:

- `agent/runtime_metadata.py`
- `agent/tool_guardrails.py`
- `agent/prompt_builder.py`
- `agent/memory_manager.py`
- `hermes_cli/config.py` (DEFAULT_CONFIG keys only)

No schema/DB migrations. Prompt-cache impact: runtime block is stable per process/`HERMES_HOME` — safe for caching within a session.
