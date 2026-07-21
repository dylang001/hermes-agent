# Knowledge OS mutation contract (Model B pilot)

**Status:** mandatory for every mutating Knowledge OS skill  
**Authority:** Controlled Model B limited pilot (2026-07-21)

## Approved lanes (user-directed only)

- `workspace/**`
- `brain/**` with `status` ∈ DRAFT…VERIFIED (never CANONICAL)
- `brain/_indexes/**`
- `hot.md`
- `compile-log.md` (append-only)
- **new** `raw/**` files only

## Forbidden without Dylan proposal

- Governance / protected roots (`AGENTS`, `SCHEMA`, `ONTOLOGY`, …)
- CANONICAL promote/edit
- Deletes, moves, archives
- Edit/delete existing `raw/**`
- Unattended cron write jobs (remain paused)

## Required wrapper (do not rely on prompt memory alone)

```bash
GROWTH_OS="${GROWTH_OS_PATH:-/opt/hermes/data/obsidian/Growth OS}"  # or Mac path
MUT="python3 ${HERMES_HOME:-$HOME/.hermes}/hermes-agent/scripts/knowledge_os_mutation.py --growth-os \"$GROWTH_OS\""
# Prefer repo checkout path when present:
# MUT="python3 /path/to/hermes-agent/scripts/knowledge_os_mutation.py --growth-os \"$GROWTH_OS\""

$MUT begin --session "<session-id>" --skill "<skill-name>"
# For each intended write:
$MUT preflight --session "<session-id>" --path "<rel>" --op create|update|append
# Prefer gated write:
$MUT write --session "<session-id>" --path "<rel>" --file /tmp/body.md
# Or after MCP write_file:
$MUT note --session "<session-id>" --path "<rel>" --op update
# Append compile-log:
$MUT write --session "<session-id>" --path compile-log.md --append --file /tmp/line.md

$MUT finalize --session "<session-id>" --run-cycle
```

On VPS without Mac SSH, `finalize --run-cycle` emits the receipt and returns deferred cycle instructions. The Mac operator (or `KOS_MAC_SSH`) must run:

```bash
python3 ~/.hermes/bin/kos-model-b.py pullback --only-pending --commit --converge
```

## Success gate

A mutating skill **must not report success** unless `finalize` returns `"ok": true` and:

1. all touched paths are in the receipt;
2. all paths are in approved lanes;
3. protected-path checks passed;
4. lifecycle transitions are valid;
5. append-only verified for `compile-log.md` (and raw create-only).

## Skills in scope

| Skill | Mutates? | Notes |
|-------|----------|-------|
| `wiki-daily` | yes (optional `hot.md`) | Use wrapper if hot updated |
| `wiki-ingest` | yes | Always |
| `wiki-research` | yes (via raw + ingest) | Always |
| `wiki-refactor` | yes | Always |
| `wiki-promote` | yes on apply only | Package draft = workspace; apply still gated |
| `wiki-lint` | yes (report under `workspace/drafts/`) | Read-only vault pages; still receipt reports |
| `wiki-query` | no | Offer compile → hand off to ingest |
