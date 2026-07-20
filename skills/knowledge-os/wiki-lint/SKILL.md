---
name: wiki-lint
description: Knowledge lint for orphans, dupes, and stale pages.
version: 0.1.0
author: Dylan Angloher
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: knowledge-os
    tags: [obsidian, wiki, lint, knowledge-os]
    related_skills: [wiki-refactor, wiki-ingest]
---

# Wiki Lint

Knowledge lint for Growth OS brain — not markdown style. Find structural entropy; fix only safe auto issues (index rows, missing frontmatter defaults ≤ CONNECTED). Propose the rest.

## When to Use

- Nightly cron `knowledge-os-nightly`.
- User asks for a vault health check.
- Before a promote batch.

## Checklist

1. **Broken wikilinks** under `brain/` (target missing).
2. **Duplicate concepts/entities** (same title/slug or near-identical summaries).
3. **Contradictions** (conflicting claims across pages — flag, do not auto-merge).
4. **Dead / empty pages** (no Summary/Claims).
5. **Unlinked pages** (not in any `_indexes` row).
6. **Outdated pages** (`updated` older than threshold or superseded by newer source).
7. **Missing citations** (claims without `sources`).
8. **Orphaned projects** (project page with no related entities/decisions).
9. **Status violations** (CANONICAL without `promoted_by`; missing status).
10. **Raw immutability** (detect edits to raw if mtime/policy check available — report only).

## How to Run

**Preferred (deterministic, read-only):**

```bash
python scripts/knowledge_os_lint.py "/Users/dylanangloher/Documents/Obsidian Vault/Growth OS"
# or: HERMES_GROWTH_OS="…/Growth OS" python scripts/knowledge_os_lint.py
```

Exit code 1 means CRITICAL findings. Reports land in `workspace/drafts/YYYY-MM-DD-wiki-lint.{md,json}`.

**Agent checklist (when script unavailable):**

1. Walk `brain/` + `_indexes/` with `search_files` / list.
2. Emit a severity table: CRITICAL / WARN / INFO (broken links, ambiguous stems, missing status, CANONICAL without `promoted_by`, duplicates).
3. **Phase B automation stage:** report only — do not auto-merge, archive, or ingest.
4. After Phase C critical-clean: auto-fix only safe issues (index rows; default `status: DRAFT` on unstatused non-canon pages); append compile-log `LINT`.
5. Hand merge/archive work to `wiki-refactor` (human-approved).

## Pitfalls

- Do not auto-delete pages.
- Do not demote CANONICAL.
- Keep report actionable (paths + one-line fix).

## Verification

Report path exists; every CRITICAL has a next action; compile-log LINT line if auto-fixes applied.
