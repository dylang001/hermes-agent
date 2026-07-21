# Knowledge OS skills

Growth OS–aware skills for Hermes Knowledge OS v2. Prefer these over generic `llm-wiki` / unrestricted `obsidian` for the company vault.

Install / sync into `$HERMES_HOME/skills/knowledge-os/` (copy or symlink from this tree).

| Skill | Role |
|-------|------|
| `wiki-daily` | Orient via `hot.md` + indexes |
| `wiki-query` | Progressive answer + compile offer |
| `wiki-ingest` | Capture raw + compile ≤ VERIFIED |
| `wiki-promote` | CANONICAL approval packages |
| `wiki-lint` | Knowledge lint |
| `wiki-refactor` | Entropy reduction |
| `wiki-research` | External research → ingest |

Policy: `audit/HERMES_OBSIDIAN_ACCESS_POLICY.md` · Runbook: `docs/HERMES_KNOWLEDGE_MAINTENANCE_RUNBOOK.md`

## Model B pilot (2026-07-21)

Mutating skills must use the shared receipt wrapper — see `_mutation-contract.md` and `scripts/knowledge_os_mutation.py`.

| Job | Template enabled | VPS schedule |
|-----|------------------|--------------|
| `knowledge-os-lint` | yes (read-only + receipt for reports) | allowed when installed |
| `knowledge-os-daily/nightly/weekly/monthly` | **paused** | keep disabled until receipt-aware + obsolete-tree retirement + observed cycle |

