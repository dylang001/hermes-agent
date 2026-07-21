#!/usr/bin/env python3
"""Phase 5B — obsolete VPS tree retirement manifest (no deletes)."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

VAULT = Path("/Users/dylanangloher/Documents/Obsidian Vault/Growth OS")
SNAP = VAULT / "archive/reconciliation/vps-divergence-2026-07-21/vps-only"
REMOTE = "hermes-production"
REMOTE_G = "/opt/hermes/data/obsidian/Growth OS"
TREES = [
    "Constitution",
    "Strategy",
    "Playbooks",
    "SOPs",
    "Hermes",
    "Operations",
    "Jobs",
    "Research",
    "Drafts",
]
E2E = "brain/concepts/_model-b-e2e-draft-2026-07-21.md"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

CLASS = json.loads(
    (
        VAULT
        / "workspace/review-queues/vps-divergence-2026-07-21/PHASE-3-CLASSIFICATION.json"
    ).read_text(encoding="utf-8")
)
dest_by_src = {f["source_path"]: f for f in CLASS["files"]}

KNOWN_MAC = {
    "Constitution/orchidea-constitution.md": [
        "brain/concepts/orchidea-philosophy-and-beliefs.md",
        "brain/policies/orchidea-operating-principles.md",
    ],
    "Constitution/decision-frameworks.md": ["brain/concepts/decision-frameworks.md"],
    "Constitution/knowledge-flywheel-v2.md": ["brain/concepts/knowledge-flywheel.md"],
    "Constitution/layered-architecture-map.md": [
        "brain/architecture/orchidea-layered-architecture.md"
    ],
    "Strategy/00-orchidea-strategic-turn-2026-07-20.md": [
        "brain/decisions/2026-07-20-ai-native-consulting-pivot.md"
    ],
    "Strategy/orchidea-operating-system.md": [
        "brain/concepts/orchidea-operating-system.md"
    ],
    "Strategy/orchidea-growth-engine.md": ["brain/concepts/orchidea-growth-engine.md"],
    "Strategy/orchidea-agency-production-system.md": [
        "brain/workflows/orchidea-agency-delivery.md"
    ],
    "Strategy/hermes-executive-playbook.md": [
        "brain/workflows/hermes-executive-operating.md"
    ],
    "Strategy/orchidea-knowledge-flywheel.md": ["brain/concepts/knowledge-flywheel.md"],
    "Hermes/Agent Run Logs.md": ["Agent Run Logs.md"],
    "Research/charlie-morgan-synthesis-2026-07-20.md": [
        "raw/exports/research/charlie-morgan-synthesis-2026-07-20.md",
        "brain/concepts/ep-operator-charlie-morgan.md",
        "brain/concepts/ep-founder-led-acquisition.md",
    ],
    "Research/multi-operator-synthesis-2026-07-20.md": [
        "raw/exports/research/multi-operator-synthesis-2026-07-20.md",
        "brain/concepts/ep-founder-led-acquisition.md",
        "brain/concepts/ep-offer-and-positioning.md",
        "brain/concepts/ep-agency-scaling.md",
        "brain/concepts/ep-operational-leverage.md",
        "brain/concepts/ep-content-led-distribution.md",
        "brain/concepts/ep-executive-decision-frameworks.md",
    ],
    "Research/nick-saraev-strategic-extracts-2026-07-20.md": [
        "raw/exports/research/nick-saraev-strategic-extracts-2026-07-20.md"
    ],
    "Research/twine-web-verification-2026-07-17.md": [
        "raw/exports/research/twine-web-verification-2026-07-17.md",
        "brain/insights/twine-web-verification-audit-2026-07-17.md",
    ],
}


def sha(p: Path) -> str | None:
    if not p.is_file():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


# List VPS files via find (avoid fragile python -c quoting over SSH)
find_cmd = (
    "cd /opt/hermes/data/obsidian/Growth\\ OS && "
    + " ".join(
        f'test -d {t} && find {t} -type f -print || true;' for t in TREES
    )
)
r = subprocess.run(
    ["ssh", "-o", "BatchMode=yes", REMOTE, find_cmd],
    capture_output=True,
    text=True,
    check=False,
)
if r.returncode not in (0, 1):
    raise SystemExit(f"ssh find failed: {r.stderr}")

vps_files = sorted({ln.strip() for ln in r.stdout.splitlines() if ln.strip()})

ref_patterns = [
    r"Constitution/",
    r"Strategy/",
    r"Playbooks/",
    r"SOPs/",
    r"Operations/",
    r"Jobs/",
    r"Research/",
    r"Drafts/",
    r"\[\[Hermes/",
]
refs: dict[str, list] = defaultdict(list)


def scan_file(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return
    rel = str(path.relative_to(VAULT))
    if rel.startswith("archive/") or "vps-divergence" in rel or "PHASE-" in rel:
        return
    for i, line in enumerate(text.splitlines(), 1):
        for pat in ref_patterns:
            if re.search(pat, line):
                refs[pat].append((rel, i, line.strip()[:160]))


for root in [VAULT / "brain", VAULT / "hot.md", VAULT / "compile-log.md", VAULT / "workspace"]:
    if root.is_file():
        scan_file(root)
    elif root.is_dir():
        for f in root.rglob("*"):
            if f.suffix in {".md", ".json", ".sh"} and f.is_file():
                scan_file(f)

agent = Path("/Users/dylanangloher/.hermes/hermes-agent")
agent_refs = []
scan_agent = list((agent / "skills/knowledge-os").rglob("*.md"))
scan_agent += [
    agent / "cron/knowledge_os_jobs.json",
    agent / "docs/HERMES_KNOWLEDGE_MAINTENANCE_RUNBOOK.md",
]
for f in scan_agent:
    if not f.exists():
        continue
    t = f.read_text(encoding="utf-8", errors="replace")
    for pat in ["Constitution/", "Strategy/", "Playbooks/", "SOPs/", "Operations/", "Jobs/"]:
        if pat in t and "_mutation-contract" not in str(f) and "PHASE-5" not in t:
            # ignore contract negatives
            if "Not Constitution" in t or "not Constitution" in t:
                continue
            agent_refs.append((str(f.relative_to(agent)), pat))


def resolve_mac(rel: str) -> list[str]:
    mac_paths = list(KNOWN_MAC.get(rel) or [])
    if not mac_paths and rel in dest_by_src:
        dest = dest_by_src[rel].get("proposed_destination", "")
        m = re.search(
            r"(brain/[^\s)]+|raw/[^\s)]+|workspace/[^\s)]+|logs/[^\s)]+|Agent Run Logs\.md)",
            dest,
        )
        if m:
            mac_paths = [m.group(1).rstrip(",")]
    present = [p for p in mac_paths if (VAULT / p).exists()]
    if present:
        return present

    name = Path(rel).name
    stem = Path(rel).stem
    if rel.startswith("Drafts/"):
        cand = VAULT / "workspace/drafts/outbound-e1" / name
        if cand.exists():
            return [str(cand.relative_to(VAULT))]
    if rel.startswith("Jobs/"):
        cand = VAULT / "raw/exports/jobs" / name
        if cand.exists():
            return [str(cand.relative_to(VAULT))]
    if rel.startswith("Operations/"):
        for sub in [
            "raw/exports/operations",
            "brain/workflows",
            "brain/architecture",
            "workspace/scratchpads/operations",
        ]:
            base = VAULT / sub
            if not base.exists():
                continue
            if (base / name).exists():
                return [str((base / name).relative_to(VAULT))]
            hits = []
            for m in base.rglob("*"):
                if m.is_file() and (stem[:16] in m.stem or m.stem in stem):
                    hits.append(str(m.relative_to(VAULT)))
            if hits:
                return hits[:3]
    if rel.startswith("Playbooks/") or rel.startswith("SOPs/"):
        hits = []
        wf = VAULT / "brain/workflows"
        tokens = [t for t in stem.replace("-playbook", "").split("-") if len(t) > 3]
        for m in wf.glob("*.md"):
            if any(tok in m.stem for tok in tokens):
                hits.append(str(m.relative_to(VAULT)))
        if hits:
            return hits
    if rel.startswith("Research/"):
        cand = VAULT / "raw/exports/research" / name
        if cand.exists():
            return [str(cand.relative_to(VAULT))]
    return []


rows = []
unresolved = []
ready = []

for rel in vps_files:
    snap_p = SNAP / rel
    in_snap = snap_p.is_file()
    snap_h = sha(snap_p) if in_snap else None
    mac_present = resolve_mac(rel)
    mac_ok = bool(mac_present)
    disposition = dest_by_src.get(rel, {}).get("proposed_disposition", "UNKNOWN")

    live_refs = []
    tree = rel.split("/", 1)[0] + "/"
    for pat, items in refs.items():
        if tree.rstrip("/") not in pat and pat.rstrip("/") != rel.split("/")[0]:
            continue
        for fr, ln, snippet in items:
            if Path(rel).name in snippet or rel in snippet or tree in snippet:
                live_refs.append(f"{fr}:{ln}")

    status = "READY_TO_RETIRE"
    blockers = []
    if not in_snap:
        blockers.append("not in Phase 1 snapshot")
        status = "BLOCKED"
    if not mac_ok:
        blockers.append("approved Mac value not found")
        status = "BLOCKED"
    if live_refs and status == "READY_TO_RETIRE":
        status = "REVIEW_REFS"
        blockers.append(f"live refs: {len(set(live_refs))}")

    row = {
        "vps_path": rel,
        "in_phase1_snapshot": in_snap,
        "snapshot_sha256": snap_h,
        "mac_approved_paths": mac_present,
        "phase3_disposition": disposition,
        "live_reference_samples": sorted(set(live_refs))[:5],
        "retirement_status": status,
        "blockers": blockers,
    }
    rows.append(row)
    if status == "READY_TO_RETIRE":
        ready.append(rel)
    else:
        unresolved.append(row)

rows.append(
    {
        "vps_path": E2E,
        "in_phase1_snapshot": False,
        "mac_approved_paths": [E2E] if (VAULT / E2E).exists() else [],
        "retirement_status": "READY_TO_RETIRE_DISPOSABLE",
        "blockers": [],
        "note": "Model B E2E disposable DRAFT — approved for retirement with obsolete trees",
    }
)

by_status: dict[str, int] = defaultdict(int)
by_tree: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
for row in rows:
    by_status[row["retirement_status"]] += 1
    tree = row["vps_path"].split("/", 1)[0]
    by_tree[tree][row["retirement_status"]] += 1

high = []
for pat, items in refs.items():
    for fr, ln, snip in items:
        if fr.startswith("brain/") and any(
            x in snip
            for x in (
                "[[Strategy/",
                "[[Constitution/",
                "[[Playbooks/",
                "[[SOPs/",
                "[[Research/",
                "[[Operations/",
                "[[Jobs/",
                "[[Drafts/",
            )
        ):
            high.append(f"{fr}:{ln}: {snip}")

decisions = []
blocked = [r for r in unresolved if r["retirement_status"] == "BLOCKED"]
review = [r for r in unresolved if r["retirement_status"] == "REVIEW_REFS"]
if blocked:
    decisions.append(
        {
            "id": 1,
            "ask": "Confirm Mac coverage for blocked VPS files (or accept archive-only)",
            "files": [r["vps_path"] for r in blocked],
        }
    )
if review:
    decisions.append(
        {
            "id": 2,
            "ask": "Accept leftover string/wikilink refs to old trees after compile",
            "count": len(review),
            "sample": [r["vps_path"] for r in review[:10]],
        }
    )
if high:
    decisions.append(
        {
            "id": 3,
            "ask": "Fix remaining brain/** wikilinks that still point at obsolete trees",
            "refs": high[:25],
        }
    )
decisions.append(
    {
        "id": 4,
        "ask": "Approve batch VPS retirement (delete obsolete trees + E2E draft) after 1–3",
        "includes_e2e_draft": True,
    }
)

manifest = {
    "created_utc": NOW,
    "phase": "5B",
    "mode": "manifest_only_no_deletes",
    "trees": TREES,
    "totals_by_status": dict(by_status),
    "totals_by_tree": {k: dict(v) for k, v in by_tree.items()},
    "files": rows,
    "mac_live_reference_index": {k: v[:20] for k, v in refs.items()},
    "hermes_agent_path_mentions": agent_refs,
    "smallest_unresolved_decisions": decisions,
}

out_dir = VAULT / "workspace/review-queues/vps-divergence-2026-07-21"
json_path = out_dir / "PHASE-5B-RETIREMENT-MANIFEST.json"
md_path = out_dir / "PHASE-5B-RETIREMENT-MANIFEST.md"
json_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

md = [
    "# Phase 5B — Obsolete VPS tree retirement manifest",
    "",
    f"**UTC:** {NOW}",
    "**Mode:** manifest only — **no deletes**",
    "",
    "## Totals by status",
    "",
]
for k, v in sorted(by_status.items()):
    md.append(f"- `{k}`: {v}")
md += ["", "## Totals by tree", ""]
for tree, st in sorted(by_tree.items()):
    md.append(f"### `{tree}/`")
    for k, v in sorted(st.items()):
        md.append(f"- {k}: {v}")
md += ["", "## Ready to retire (no blockers)", ""]
for rel in ready:
    md.append(f"- `{rel}`")
md.append(f"- `{E2E}` (disposable E2E)")
md += ["", "## Blocked / review", ""]
for r in unresolved:
    md.append(
        f"- `{r['vps_path']}` — **{r['retirement_status']}** — "
        f"blockers: {', '.join(r['blockers']) or 'n/a'}; mac={r['mac_approved_paths']}"
    )
md += ["", "## Smallest unresolved Dylan decisions", ""]
for d in decisions:
    md.append(f"### {d['id']}. {d['ask']}")
    for k, v in d.items():
        if k in {"id", "ask"}:
            continue
        md.append(f"- **{k}:** `{v}`")
md += ["", "## Hermes-agent mentions", ""]
if agent_refs:
    for a, p in agent_refs[:30]:
        md.append(f"- `{a}` mentions `{p}`")
else:
    md.append("- none material beyond pilot docs")
md += [
    "",
    "## Next",
    "",
    "Do **not** delete until decisions resolved.",
    "",
]
md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
print("vps_files", len(vps_files))
print("by_status", dict(by_status))
print("blocked", len(blocked), "review", len(review), "high", len(high))
print(md_path)
for r in blocked:
    print("BLOCKED", r["vps_path"], r["blockers"])
for h in high[:20]:
    print("HIGH", h)
