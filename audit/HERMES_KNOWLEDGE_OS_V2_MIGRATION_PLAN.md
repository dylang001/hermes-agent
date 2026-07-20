# Hermes Knowledge OS v2 — Architecture Refactor & Migration Plan

**Date:** 2026-07-20  
**Status:** PROPOSAL ONLY — no vault mutations performed  
**Vault (Mac):** `/Users/dylanangloher/Documents/Obsidian Vault`  
**Hermes mount:** `…/Obsidian Vault/Growth OS` only  
**VPS mirror:** `/opt/hermes/data/obsidian/Growth OS`  
**Companion:** `audit/HERMES_OBSIDIAN_ACCESS_POLICY.md`, `docs/HERMES_KNOWLEDGE_MAINTENANCE_RUNBOOK.md`, `Growth OS/SCHEMA.md`

---

## Executive verdict

This vault is **structurally conflicted**, not **content-bloated**.

| Metric | Value |
|--------|------:|
| Markdown files | 56 |
| Growth OS markdown | 41 |
| Vault size | ~10 MB |
| Attachments | 0 |
| Git history depth | ~10 commits (from 2026-06) |
| Frontmatter coverage | 13 / 56 (23%) |
| Wikilinks | 144 |
| Broken / placeholder links | 10 |
| Ambiguous entity links | 17 |
| Duplicate entity stems | Orchidea, Flockline, Lyra (+ Personal OS pair) |
| Brain pages (compiled) | 1 (`concepts/Knowledge OS.md`) |
| Knowledge OS scaffolding | Present (2026-07-20) but mostly empty |

**Implication:** This is not a years-deep note dump. It is a **dual-architecture vault**: vault-root PARA (“working brain”) + Growth OS (company ops + Knowledge OS v2 scaffold). Entropy is mostly **conflicting conventions and dual sources of truth**, not volume.

Knowledge OS v2 scaffolding already implements ~60% of the target design (`raw/`, `brain/`, `workspace/`, `hot.md`, lifecycle statuses, progressive indexes, skills, cron templates). The remaining work is to **collapse PARA into one canonical brain**, expand the ontology, retire obsolete integration paths, and turn maintenance from “enabled in docs” into “running in production.”

**Do not migrate until this document is approved.**

---

## 1. Current-state audit

### 1.1 Two competing layouts

```
Obsidian Vault/                          ← git root; Hermes MCP MUST NOT mount this
├── Home.md                              ← declares PARA as "working brain"
├── Projects.md
├── SYNC_SETUP.md
├── Hermes.base
├── 00 Inbox/ … 05 Receipts/             ← PARA layer (outside MCP)
└── Growth OS/                           ← Hermes MCP mount + company canon
    ├── INDEX.md, Agent Rules, …
    ├── Business Context/                ← legacy canon entities
    ├── SCHEMA.md, hot.md, compile-log.md
    ├── raw/, brain/, workspace/         ← Knowledge OS v2 (new)
    ├── Drafts/Hermes/                   ← promote staging
    └── Templates/                       ← dual template regimes
```

`Home.md` still says Growth OS is “read-mostly.” `Agent Rules` Rule 7 and Access Policy already allow Knowledge OS auto-writes. **Policy and navigation docs disagree.**

### 1.2 Inventory by zone

| Zone | Role today | Health |
|------|------------|--------|
| Vault-root PARA `00–05` | Parallel “working brain” for projects/areas/decisions/runbooks | Active content; **outside** Hermes MCP |
| Growth OS root docs | Operating system (priorities, rules, decision log) | Valuable; inconsistent with KOS metadata |
| `Business Context/` | Entity strategy pages | **Duplicates** PARA projects with low textual overlap |
| `brain/` | Compiled Knowledge OS | Scaffold only; 1 concept page |
| `raw/` | Immutable sources | 1 smoke article |
| `workspace/` + `Drafts/Hermes/` | Thinking + promotions | Overlapping purpose |
| Templates | Ops templates + KOS Brain Page + legacy note-template | **Three** metadata dialects |
| `.obsidian/plugins` | git, Local REST API, Claudian, Google Calendar | Local REST API path is **legacy** vs filesystem MCP |
| `.claude/` / `.claudian/` | Empty agent/command/skill dirs | Abandoned scaffolding |

### 1.3 Duplicate folders / systems

| Conflict | Details |
|----------|---------|
| PARA vs Knowledge OS | `Home.md` PARA layout vs `SCHEMA.md` compiler layout |
| `Drafts/` vs `workspace/` | Both are “non-canon scratch”; two landing zones |
| `Business Context/` vs `brain/entities` + `brain/projects` | Same companies live in BC; brain folders empty |
| `03 Decisions/` vs `Decision Log.md` vs `brain/decisions/` | Three decision homes |
| `Research Inbox.md` vs `raw/` | Capture vs compile not unified |
| Generic `llm-wiki` (`~/wiki`) vs Growth OS | Skills/docs warn against `~/wiki` for company knowledge — correct |
| Obsidian Local REST API vs filesystem MCP | `INTEGRATION_SPEC.md` still describes cycle-1 REST; production uses filesystem MCP |
| Referenced `AGENTS.md` | Cited by Agent Rules / note-template; **missing from vault** |
| Referenced `06 Archive/` | Named in `Home.md`; **does not exist** |
| Referenced `/root/audit/…` | Stale absolute paths in Agent Rules |

### 1.4 Duplicate notes (same stem, different content)

Jaccard token overlap is low → **merge, do not pick one file blindly.**

| Entity | PARA path | Business Context path | Jaccard | Action |
|--------|-----------|----------------------|--------:|--------|
| Orchidea | `01 Projects/Orchidea.md` (114 lines) | `Business Context/Orchidea.md` (64) | 0.08 | Merge → one canonical `brain/projects/orchidea.md` |
| Flockline | `01 Projects/Flockline.md` (83) | `Business Context/Flockline.md` (57) | 0.20 | Merge → canonical project + channel policy |
| Lyra | `01 Projects/Lyra.md` (71) | `Business Context/Lyra.md` (50) | 0.33 | Merge → canonical project (maintenance mode) |
| Personal OS | `02 Areas/Personal Operating System.md` (100) | `Business Context/Personal OS.md` (51) | 0.47 | Merge → `brain/entities` or `brain/areas` |

Hermes exists only under PARA (`01 Projects/Hermes.md`) — promote into `brain/projects/hermes.md`.

### 1.5 Conflicting conventions

| Dimension | Dialect A (legacy PARA / note-template) | Dialect B (Knowledge OS SCHEMA) |
|-----------|-----------------------------------------|----------------------------------|
| `type` | inbox\|project\|area\|decision\|runbook\|… | entity\|concept\|project\|decision |
| `status` | draft\|proposed\|active\|paused\|… | RAW→…→CANONICAL→ARCHIVED |
| Frontmatter required? | Claimed for all notes; mostly absent | Required for brain pages only |
| Navigation | Flat Home + Projects | `hot.md` → INDEX → `_indexes` → page |
| Filename style | Title Case with spaces | SCHEMA silent; Karpathy prefers kebab-case |
| Capture | Inbox / Research Inbox | `raw/<kind>/YYYY-MM-DD-slug.md` |

### 1.6 Abandoned / obsolete artifacts

| Artifact | Why obsolete / abandoned | Disposition |
|----------|--------------------------|-------------|
| `INTEGRATION_SPEC.md` + `.patch` | Describes Local REST MCP cycle-1; production is filesystem MCP | Archive after pointer note |
| `Remote Gateway Status.md` | Point-in-time ops status | Archive under `50 Archive/ops/` |
| `ClickUp Documented Baseline.md` | Audit snapshot | Archive (keep for evidence) |
| `00 Inbox/Memory Export - Pre Migration.md` | One-shot migration dump (312 lines) | Archive as raw historical source |
| `05 Receipts/*` | Migration / review receipts | Archive as evidence |
| `.claude/{agents,commands,skills}` empty | Unused | Leave or remove empty dirs after archive pass |
| Plugin `obsidian-local-rest-api` | Superseded for Hermes by filesystem MCP | Disable for Hermes path; optional keep for Claudian UX |
| Reverse-tunnel REST bridge (ops) | Known failing; not Knowledge OS | Out of vault scope; ops cleanup |

### 1.7 Templates

| Template | Keep? | Notes |
|----------|-------|-------|
| `Templates/Knowledge OS/Brain Page.md` | **Yes — expand** | Become type-specific templates |
| `Templates/Decision.md`, `Proposal.md`, `Review.md`, `Agent Run Log.md` | Yes | Ops workflow; map statuses carefully |
| `Templates/note-template.md` | **Retire** | Conflicts with SCHEMA lifecycle |
| `Templates/Permissions.md`, `Mandate.md`, `Learnings.md`, `Operating Rhythm.md` | Review | Keep if referenced; else archive |
| Missing: Person, Company, Workflow, Policy, Prompt, Meeting, Failure, Insight, Question, API, Tool | **Add** | Ontology Phase 5 |

### 1.8 Plugins

| Plugin | Verdict |
|--------|---------|
| `obsidian-git` | **Keep** — vault is git-backed |
| `realclaudian` | Keep if you use in-Obsidian agents; not Hermes runtime |
| `google-calendar` | Keep only if used; unrelated to Knowledge OS |
| `obsidian-local-rest-api` | **Deprecate for Hermes**; filesystem MCP is canonical |

Core plugins: Daily Notes enabled but **no Daily folder** exists yet — aligns with proposed `40 Logs/Daily`.

### 1.9 Indexes / MOCs

| Index | Status |
|-------|--------|
| `Home.md` | PARA MOC; stale vs KOS |
| `Projects.md` | PARA project MOC |
| `Growth OS/INDEX.md` | Growth OS TOC + KOS section — **keep as root TOC** |
| `brain/_indexes/{root,entities,concepts,projects,decisions}.md` | Present; mostly empty stubs |
| Missing | Type indexes for workflows, policies, prompts, architecture |

### 1.10 Link / attachment health

- **Broken / placeholder:** `[[wikilink]]` in Operating Principles, Weekly Review, Research Inbox, Proposal template; `[[INTEGRATION_SPEC.patch]]` (file exists but not `.md` — Obsidian link mismatch); template placeholders.
- **Ambiguous:** bare `[[Orchidea]]` / `[[Flockline]]` / `[[Lyra]]` resolve to both PARA and Business Context.
- **Attachments:** none found; no dead media.
- **Orphans (zero inbound, excl. templates):** 12 including Home, SYNC_SETUP, receipts, LinkedIn BC, READMEs.
- **Empty content folders:** brain entity/project/decision dirs only have `.gitkeep`.

### 1.11 Page size / quality

Largest pages are **runbooks and migration dumps**, not AI essay spam:

1. Orchidea Prospecting runbook — 422 lines  
2. Memory Migration Receipt — 421  
3. Memory Export — 312  

No evidence of widespread low-quality AI note sprawl in this vault. Risk is **future** sprawl once ingest cron is live without lint.

### 1.12 Tags / properties

- Almost no `#tags` in use (noise from markdown headings like `#N`).
- Properties dialect split (see §1.5).
- Unused property surface is large relative to actual adoption.

---

## 2. Problems discovered (ranked)

1. **Dual source of truth** for every major entity (PARA ↔ Business Context).
2. **Ambiguous wikilinks** make agents load the wrong page.
3. **Three metadata dialects** → lint and compile cannot be consistent.
4. **Home.md / Agent Rules / SCHEMA disagree** on write posture.
5. **Knowledge OS brain is empty** while valuable knowledge sits outside `brain/`.
6. **Ontology too narrow** (4 types) for a company operating brain.
7. **Obsolete integration docs** teach wrong Hermes access model.
8. **Missing AGENTS.md** referenced as constitution.
9. **Capture paths fragmented** (Inbox, Research Inbox, raw/).
10. **Maintenance cron templates disabled**; nightly entropy control not live.
11. **No log layer** (daily/weekly/agent) under Knowledge OS structure.
12. **Filename spaces + Title Case** hurt agent path hygiene vs Karpathy kebab-case.

---

## 3. Phase 2 — Compare to modern best practices

### 3.1 Karpathy LLM Wiki (gist) — alignment

| Principle | Current Growth OS | Gap |
|-----------|-------------------|-----|
| Raw immutable | `raw/` yes | PARA Inbox still used as capture |
| LLM owns compiled wiki | `brain/` yes | Content still human-authored in BC/PARA |
| Schema is product | `SCHEMA.md` yes | Incomplete ontology; dual dialects |
| Index-first query | `_indexes/` + `hot.md` yes | Not enforced; Home.md still PARA-first |
| Append-only log | `compile-log.md` yes | No rotation; Agent Run Logs separate |
| Ingest / query / lint workflows | knowledge-os skills yes | Generic `llm-wiki` still points at `~/wiki` |
| Human curates, agent compiles | Policy yes | Dual SoT undermines compile |
| Contradictions flagged | Skills mention | No vault convention callouts yet |

### 3.2 Hermes `llm-wiki` skill vs `knowledge-os` skills

| | `skills/research/llm-wiki` | `skills/knowledge-os/*` |
|--|----------------------------|-------------------------|
| Path | `$WIKI_PATH` / `~/wiki` | Growth OS only |
| Domain | Research wiki | Company brain + ops |
| Approval | Agent-owned wiki | CANONICAL gated |
| Hot cache | No | `hot.md` |
| Lifecycle | Implicit | Explicit status enum |

**Rule:** Company knowledge uses `knowledge-os` only. Keep `llm-wiki` for personal/research wikis outside Growth OS.

### 3.3 Obsidian LLM Wiki implementations / Kepano Skills

Modern pattern: progressive disclosure, schema-driven agent behavior, Obsidian as **reader IDE**, agent as **writer**. Kepano-style Skills emphasize small, composable instruction packs — matches our per-skill `wiki-*` design.

**Divergence to fix:** vault still invites human+agent free-form PARA notes as equals to compiled pages.

### 3.4 PARA — where still useful

Keep PARA **concepts**, not PARA **folders at vault root**:

| PARA idea | Knowledge OS home |
|-----------|-------------------|
| Projects | `brain/projects/` |
| Areas | `brain/areas/` (or entities with `type: area`) |
| Resources | `20 Sources/raw` + compiled concepts |
| Archive | `50 Archive/` |

Inbox becomes `20 Sources/raw/` + `30 Workspace/Temporary`.

---

## 4. Proposed architecture

**Decision:** Keep **Growth OS as the single Hermes brain mount**. Do not expand MCP to the vault root. Migrate PARA *into* Growth OS, then archive the vault-root PARA tree.

### 4.1 Target folder structure (refined)

Slightly improved vs the brief: keep Knowledge OS names agents already use (`SCHEMA`, `hot`, `compile-log`, `brain`), add numbered top-level zones for human navigation, and put system docs under `00 System`.

```text
Growth OS/                              # MCP root (unchanged mount)
├── 00 System/
│   ├── SCHEMA.md                       # moved from root (stub redirect at old path optional)
│   ├── INDEX.md                        # vault TOC (or keep INDEX at root for discoverability)
│   ├── ONTOLOGY.md                     # type catalog + linking rules
│   ├── TAXONOMY.md                     # tags/domains (minimal)
│   ├── Agent Rules.md
│   └── Operating Principles.md
├── 10 Brain/                           # = today's brain/ (rename optional; see note)
│   ├── _indexes/
│   │   ├── root.md
│   │   ├── projects.md
│   │   ├── entities.md
│   │   ├── concepts.md
│   │   ├── decisions.md
│   │   ├── workflows.md
│   │   ├── policies.md
│   │   └── prompts.md
│   ├── concepts/
│   ├── entities/                       # Person, Company, Tool, API…
│   ├── projects/
│   ├── decisions/
│   ├── architecture/
│   ├── workflows/
│   ├── policies/
│   ├── prompts/
│   ├── meetings/                       # compiled meeting knowledge (not raw)
│   ├── insights/
│   └── questions/
├── 20 Sources/
│   ├── raw/                            # immutable (articles, pdfs, transcripts, exports, meetings)
│   ├── conversations/                  # agent/session extracts worth keeping as sources
│   └── research/                       # staged research clips before compile
├── 30 Workspace/
│   ├── drafts/
│   ├── scratchpads/
│   ├── experiments/
│   └── promotions/                     # was Drafts/Hermes/promotions
├── 40 Logs/
│   ├── daily/
│   ├── weekly/
│   ├── monthly/
│   ├── agent/                          # Agent Run Logs (split or symlink)
│   └── compile-log.md
├── 50 Archive/
│   ├── para-migration/                 # frozen PARA snapshots after merge
│   ├── obsolete-integration/
│   └── receipts/
├── hot.md                              # stays at Growth OS root for path stability
├── Current Priorities.md               # ops hot document (or fold into hot.md over time)
├── Decision Log.md                     # append-only ops log (distinct from brain/decisions pages)
└── Business Context/                   # TRANSITIONAL — migrate to 10 Brain then archive
```

**Rename note:** Renaming `brain/` → `10 Brain/` breaks skills/docs/MCP habits. **Recommendation:** keep filesystem path `brain/` (and `raw/`, `workspace/`) as the machine paths; use numbered folders only if you want human Obsidian aesthetics — **or** use numbered folders and update skills in the same PR. Prefer **stable machine paths** (`brain/`, `raw/`, `workspace/`) + `00 System/` for schema docs.

### 4.2 Recommended machine paths (minimal churn)

```text
Growth OS/
├── SCHEMA.md, ONTOLOGY.md, TAXONOMY.md, INDEX.md
├── hot.md, compile-log.md
├── raw/…
├── brain/…          # expanded type folders + indexes
├── workspace/…      # drafts, scratchpads, experiments, promotions/
├── logs/            # daily, weekly, monthly, agent/
├── archive/
├── (ops root docs)  # Agent Rules, Decision Log, Current Priorities, Weekly Review
└── Business Context/  # temporary until compile complete
```

This is the structure I recommend approving.

---

## 5. Knowledge lifecycle design

**Representation: frontmatter `status` (not folders).**  
Folders express **type/role**; status expresses **maturity**. Folders-as-lifecycle forces moves that break links and cache.

```text
RAW → EXTRACTED → STRUCTURED → CONNECTED → VERIFIED → CANONICAL → ARCHIVED
```

| Stage | Where | Who |
|-------|-------|-----|
| RAW | `raw/**` only | Capture (Hermes auto) |
| EXTRACTED…VERIFIED | `brain/**` | Hermes auto |
| CANONICAL | `brain/**` | Dylan via `wiki-promote` |
| ARCHIVED | `status: ARCHIVED` + optional move to `archive/` | Propose auto; approve destructive |

Optional: `lifecycle_stage` alias deprecated — keep single field `status`.

---

## 6. Knowledge ontology

### 6.1 Types

| Type | Folder | Required metadata | Linking rules | Default owner |
|------|--------|-------------------|---------------|---------------|
| `person` | `brain/entities/` | name, aliases, org?, role? | → company, projects | dylan |
| `company` | `brain/entities/` | name, domain | → people, projects | dylan |
| `project` | `brain/projects/` | name, status(ops), goals | → decisions, workflows, entities | dylan |
| `decision` | `brain/decisions/` | decided_on, reversible | → project, policy | dylan |
| `workflow` | `brain/workflows/` | steps, tools | → project, tool | hermes/dylan |
| `technology` | `brain/concepts/` or entities | maturity | → architecture, tools | hermes |
| `architecture` | `brain/architecture/` | scope, constraints | → projects, decisions | dylan |
| `meeting` | `brain/meetings/` | date, attendees | → entities, decisions; source→raw | hermes |
| `experiment` | `brain/insights/` or projects | hypothesis, result | → project | hermes |
| `failure` | `brain/insights/` | blameless summary | → project, decision | hermes |
| `insight` | `brain/insights/` | claim, confidence | → sources | hermes |
| `question` | `brain/questions/` | open/closed | → related pages | hermes |
| `prompt` | `brain/prompts/` | purpose, model? | → workflow | dylan |
| `api` | `brain/entities/` | base, auth_ref (no secrets) | → tools | hermes |
| `tool` | `brain/entities/` | name, when_to_use | → workflows | hermes |
| `policy` | `brain/policies/` | enforcement | → Agent Rules / decisions | dylan |
| `concept` | `brain/concepts/` | definition | ≥2 related links | hermes |
| `area` | `brain/entities/` or `brain/areas/` | ongoing concern | → projects | dylan |

Each type gets `Templates/Knowledge OS/<Type>.md`.

### 6.2 Minimal frontmatter schema (permanent pages)

```yaml
---
id: kos-<slug>                 # stable id; optional initially, required for CANONICAL
title: Human Title
aliases: []
type: project                  # ontology type
status: CONNECTED              # lifecycle
confidence: 0.0-1.0
evidence: []                   # claim ids or short keys
sources: []                    # raw/ paths or URLs
owner: dylan                   # dylan | hermes | <agent>
created: YYYY-MM-DD
updated: YYYY-MM-DD
related: []                    # optional explicit list; body ## Related still required
domain: orchidea               # orchidea|flockline|lyra|personal|systems|meta
promoted_by: null              # required non-null when CANONICAL
tags: []                       # sparse; prefer type+domain
---
```

**Keep minimal:** do not require `evidence`/`id` until CONNECTED; require full set for CANONICAL.

---

## 7. Progressive navigation + hot context

Already partially built. Harden as:

```text
hot.md  (≤150 words)
  → INDEX.md / SCHEMA.md (policy)
  → brain/_indexes/root.md
  → brain/_indexes/<type>.md
  → brain/<type>/<page>.md
```

**Forbidden:** recursive vault walk; injecting vault bodies into SOUL/system prompt.

`hot.md` contents (keep):

- current projects  
- current priorities (pointer or 3 bullets)  
- active decisions  
- open questions  
- recent discoveries  

---

## 8. Linting specification

Extend `wiki-lint` (skill today is checklist-only) to a deterministic checker script later (`scripts/knowledge_os_lint.py` or cron-driven agent).

| Check | Severity | Auto-fix? |
|-------|----------|-------------|
| Broken wikilink under `brain/` | CRITICAL | No (propose) |
| Ambiguous stem (multi-path) | CRITICAL | No |
| Duplicate title/slug | CRITICAL | No — `wiki-refactor` |
| Missing `status` on brain page | WARN | Yes → `DRAFT` |
| CANONICAL without `promoted_by` | CRITICAL | No |
| Claim without source | WARN | No |
| Not listed in type index | WARN | Yes — add row |
| Zero inbound (non-raw, non-template) | INFO | No |
| Zero outbound | INFO | No |
| Page > 400 lines | WARN | Propose split |
| `updated` older than N days + no inbound | INFO stale | Propose archive |
| Conflicting claims (heuristic) | WARN | Flag only |
| Edit detected on `raw/` | CRITICAL | Report only |
| Unused attachment | INFO | Propose archive |
| Unused tag | INFO | Prune taxonomy |

Report path: `workspace/drafts/YYYY-MM-DD-wiki-lint.md`.

---

## 9. Continuous maintenance specification

Align with existing `cron/knowledge_os_jobs.json` (currently `enabled: false` in template):

| Cadence | Job | Actions |
|---------|-----|---------|
| Session | `wiki-daily` | hot + indexes |
| On capture | `wiki-ingest` / `wiki-research` | raw → ≤ CONNECTED |
| Daily 07:00 UTC | `knowledge-os-daily` | pending raw; refresh hot |
| Nightly 02:30 UTC | `knowledge-os-nightly` | lint + safe repairs |
| Weekly Mon 09:00 | `knowledge-os-weekly` | gaps, promote queue, synthesis |
| Monthly 1st 10:00 | `knowledge-os-monthly` | archive proposals, ontology drift, entropy |

Post-task compile questions (Hermes mindset):

1. Does this deserve permanent knowledge?  
2. Update existing concept or new page?  
3. Contradict existing knowledge?  
4. Improve an existing page?  
5. Promote toward CANONICAL?  
6. Should HERMES.md / SOUL / a skill evolve? (`self-improvement`)

---

## 10. Migration plan (phased; approval-gated)

### Phase A — Freeze & backup (no semantic change)

1. Git commit / tag vault: `pre-kos-v2-migration`.  
2. Mac→VPS dry-run sync.  
3. Snapshot tree listing into `archive/receipts/`.

### Phase B — System docs (Growth OS only)

1. Add `ONTOLOGY.md`, `TAXONOMY.md`.  
2. Update `SCHEMA.md` to expanded types + minimal frontmatter.  
3. Add vault-root `AGENTS.md` **or** Growth OS `00 System/AGENTS.md` (single constitution).  
4. Rewrite `Home.md` as a pointer: “Brain lives in Growth OS; PARA archived.”  
5. Retire `note-template.md` → redirect to Brain templates.  
6. Mark `INTEGRATION_SPEC*` obsolete; move to archive after stub.

### Phase C — Compile PARA → brain (merge, don’t delete)

For each entity (Orchidea, Flockline, Lyra, Personal OS, Hermes):

1. Create `brain/projects|entities/<slug>.md` with merged claims.  
2. Cite PARA + Business Context as `sources` (copy into `raw/exports/` first if not already immutable).  
3. Status `CONNECTED` or `VERIFIED`.  
4. Update indexes + wikilinks.  
5. Leave stubs at old paths: `# Redirect` → canonical page.  
6. Promote packages for Dylan approval to CANONICAL.

### Phase D — Relocate supporting PARA

| Source | Destination |
|--------|-------------|
| `03 Decisions/Memory Architecture.md` | `brain/architecture/` or `brain/decisions/` |
| `04 Runbooks/*` | `brain/workflows/` (+ keep ClickUp model as policy) |
| `00 Inbox/*`, `05 Receipts/*` | `raw/exports/` or `archive/receipts/` |
| `Research Inbox.md` open items | compile or `brain/questions/` |

### Phase E — Collapse Business Context

After CANONICAL brain pages exist: convert `Business Context/*.md` to stubs → archive folder.

### Phase F — Vault-root PARA archive

Move `00–05`, old Home/Projects into `Growth OS/archive/para-migration/` **or** vault `50 Archive` outside mount (prefer inside Growth OS so agents can still read history). Keep git history.

### Phase G — Enable maintenance

Enable VPS cron jobs; run first lint; fix CRITICAL ambiguity.

### Phase H — Optional path renames

Only after skills updated: numbered folders aesthetic pass.

---

## 11. File move map (proposed)

| From | To | Mode |
|------|----|------|
| `01 Projects/Orchidea.md` + `Business Context/Orchidea.md` | `brain/projects/orchidea.md` | **Merge** |
| `01 Projects/Flockline.md` + `Business Context/Flockline.md` | `brain/projects/flockline.md` | **Merge** |
| `01 Projects/Lyra.md` + `Business Context/Lyra.md` | `brain/projects/lyra.md` | **Merge** |
| `01 Projects/Hermes.md` | `brain/projects/hermes.md` | Move+compile |
| `02 Areas/Personal Operating System.md` + `Business Context/Personal OS.md` | `brain/entities/personal-os.md` | **Merge** |
| `Business Context/LinkedIn.md` | `brain/workflows/linkedin.md` or entities | Compile |
| `03 Decisions/Memory Architecture.md` | `brain/architecture/memory-architecture.md` | Compile |
| `04 Runbooks/Orchidea Prospecting.md` | `brain/workflows/orchidea-prospecting.md` | Compile |
| `04 Runbooks/Memory Maintenance.md` | `brain/policies/memory-maintenance.md` | Compile |
| `04 Runbooks/ClickUp + Obsidian Operating Model.md` | `brain/policies/clickup-obsidian.md` | Compile |
| `00 Inbox/Memory Export…` | `raw/exports/` or `archive/receipts/` | Archive as source |
| `05 Receipts/*` | `archive/receipts/` | Archive |
| `INTEGRATION_SPEC.md` + `.patch` | `archive/obsolete-integration/` | Archive |
| `Remote Gateway Status.md` | `archive/ops/` | Archive |
| `ClickUp Documented Baseline.md` | `archive/receipts/` | Archive |
| `Drafts/Hermes/promotions/` | `workspace/promotions/` | Move (update skills) |
| `Prospecting Requirements.md` | merge into orchidea project/workflow | Merge |
| Vault-root `Home.md` / `Projects.md` | stubs → Growth OS INDEX | Rewrite |

---

## 12. Files to archive / merge / delete

### Archive (preserve content)

- Memory export + migration receipts  
- INTEGRATION_SPEC + patch  
- Remote Gateway Status  
- ClickUp Documented Baseline  
- Post-merge PARA originals (after stubs)  
- Empty `.claude` scaffolding (optional)

### Merge (one canonical)

- Orchidea / Flockline / Lyra / Personal OS pairs  
- Prospecting Requirements ↔ Orchidea Prospecting runbook (dedupe after compile)  
- Decision homes → Decision Log (ops) + `brain/decisions` (compiled) with clear split

### Delete (only after archive + stub period ≥ 14 days)

- True duplicates with identical content (none found today)  
- Placeholder-only template noise (not whole templates)  
- `.gitkeep` once real files exist  

**Never delete `raw/` captures. Never delete without archive path + git commit.**

---

## 13. Align Hermes (compiler mindset)

| Old habit | New habit |
|-----------|-----------|
| “Write a note in Obsidian” | “Compile knowledge into brain” |
| Dump vault into context | `hot.md` + one index + one page |
| Edit Business Context freely | Promote package |
| Use `~/wiki` for company facts | Growth OS + knowledge-os skills |
| Treat Mem0 as SOP store | Mem0 = preferences; Obsidian = canon |
| Treat PARA Inbox as brain | Inbox/raw is intake only |

Working Memory (CE V2) remains **runtime**. Obsidian remains **persistent compiled truth**.

---

## 14. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Merge loses unique PARA/BC claims | Medium | High | Diff both files; low Jaccard → human review of merge PR |
| Broken wikilinks after moves | High | Medium | Stubs for 14+ days; lint CRITICAL |
| Skills still point at old paths | Medium | High | Update knowledge-os skills in same change set |
| Expanding MCP to full vault | — | High | **Do not**; migrate into Growth OS |
| Auto-CANONICAL | Low | High | Keep promote gate |
| Cron entropy before ontology solid | Medium | Medium | Enable lint nightly before aggressive refactor job |
| Filename kebab-case rename churn | Medium | Medium | Defer rename; aliases frontmatter first |
| VPS/Mac drift during migration | Medium | High | Pause bidirectional scripts; Mac-primary sync only |
| Agent Rules `/root/audit` ghosts | High | Low | Fix paths in same doc pass |

---

## 15. Success criteria (acceptance)

- [ ] One canonical page per entity/concept (no ambiguous stems)  
- [ ] PARA vault-root no longer a second brain (archived or stubbed)  
- [ ] All `brain/**` pages use SCHEMA frontmatter  
- [ ] `hot.md` + layered indexes are the only default orientation path  
- [ ] Lint clean of CRITICAL issues  
- [ ] Daily/nightly/weekly/monthly jobs enabled on VPS  
- [ ] Hermes skills speak “compile,” not “note-taking,” for Growth OS  
- [ ] Business Context either archived or stub→brain  
- [ ] No secrets in vault; no vault dump into system prompt  

---

## 16. Approval checklist (stop here)

Approve or amend before any vault mutation:

1. **Machine paths:** keep `brain/`/`raw/`/`workspace/` (recommended) vs numbered rename?  
2. **Merge order:** Orchidea → Flockline → Lyra → Personal OS → Hermes?  
3. **Business Context:** stub-then-archive vs keep as human-facing mirrors of CANONICAL?  
4. **Vault-root PARA:** move into `Growth OS/archive/` vs leave stubs outside MCP?  
5. **Enable cron now or after Phase C merges?**  
6. **Promote** pending package `Drafts/Hermes/promotions/2026-07-20-knowledge-os-canonical.md`?  
7. **Disable** Local REST API plugin for Hermes ops?

---

## Appendix A — Audit method

- Full filesystem inventory of Mac vault (2026-07-20)  
- Python pass: frontmatter, wikilinks, orphans, duplicate stems, sizes  
- Cross-read: SCHEMA, INDEX, hot, Agent Rules, Home, Access Policy, knowledge-os skills, llm-wiki skill, cron templates  
- Karpathy gist principles via public summary + bundled Hermes skill  

## Appendix B — What we did **not** do

- No file moves, deletes, or merges in the vault  
- No CANONICAL promotions applied  
- No cron enablement on VPS  
- No MCP mount changes  
