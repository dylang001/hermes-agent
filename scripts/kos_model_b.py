#!/usr/bin/env python3
"""Controlled Model B — hash-based VPS→Mac pull-back for Growth OS.

Consumes compact touched-path receipts, compares baseline/Mac/VPS hashes,
applies allowlisted paths, quarantines conflicts/protected mutations,
optionally auto-commits clean batches and Mac→VPS converges.

Never autonomously deletes, moves, archives, edits governance, or CANONICAL.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "kos-touched-path-receipt/v1"
DEFAULT_VAULT = Path(
    os.environ.get(
        "OBSIDIAN_VAULT_PATH",
        "/Users/dylanangloher/Documents/Obsidian Vault",
    )
)
GROWTH = Path(os.environ.get("GROWTH_OS_PATH", str(DEFAULT_VAULT / "Growth OS")))
REMOTE = os.environ.get("HERMES_REMOTE_SSH", "hermes-production")
REMOTE_GROWTH = os.environ.get(
    "HERMES_REMOTE_OBSIDIAN_VAULT", "/opt/hermes/data/obsidian/Growth OS"
)

BASELINE_PATH = GROWTH / "workspace/sync/baseline-hashes.json"
RECEIPTS_DIR = GROWTH / "workspace/receipts"
QUARANTINE_DIR = GROWTH / "workspace/quarantine"
SYNC_STATE_DIR = GROWTH / "workspace/sync"

PROTECTED_PREFIXES = (
    "AGENTS.md",
    "Agent Rules.md",
    "Operating Principles.md",
    "SCHEMA.md",
    "ONTOLOGY.md",
    "TAXONOMY.md",
    "Access Policy",
    "Decision Log.md",
    "INDEX.md",
)

ALLOWLIST_PREFIXES = (
    "workspace/",
    "logs/",
    "hot.md",
    "compile-log.md",
    "brain/_indexes/",
    "brain/",
    "raw/",
)

# Within brain/, never auto-apply if Mac page is CANONICAL
def is_protected(rel: str) -> bool:
    norm = rel.lstrip("./")
    for p in PROTECTED_PREFIXES:
        if norm == p or norm.startswith(p):
            return True
    return False


def is_allowlisted(rel: str) -> bool:
    norm = rel.lstrip("./")
    if is_protected(norm):
        return False
    for p in ALLOWLIST_PREFIXES:
        if norm == p.rstrip("/") or norm.startswith(p):
            return True
    return False


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_baseline() -> dict:
    if BASELINE_PATH.exists():
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {"schema": "kos-baseline/v1", "updated_at": None, "hashes": {}}


def save_baseline(baseline: dict) -> None:
    SYNC_STATE_DIR.mkdir(parents=True, exist_ok=True)
    baseline["updated_at"] = utc_now()
    BASELINE_PATH.write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def ssh_cat(rel: str) -> bytes | None:
    remote_path = f"{REMOTE_GROWTH}/{rel}"
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        REMOTE,
        f"if [ -f {json.dumps(remote_path)} ]; then cat {json.dumps(remote_path)}; else exit 2; fi",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, check=False)
    except Exception:
        return None
    if r.returncode == 2:
        return None
    if r.returncode != 0:
        raise RuntimeError(f"ssh cat failed for {rel}: {r.stderr.decode()[:400]}")
    return r.stdout


def ssh_write(rel: str, data: bytes) -> None:
    remote_path = f"{REMOTE_GROWTH}/{rel}"
    parent = str(Path(remote_path).parent)
    # pipe via ssh
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        REMOTE,
        f"mkdir -p {json.dumps(parent)} && cat > {json.dumps(remote_path)}",
    ]
    r = subprocess.run(cmd, input=data, capture_output=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"ssh write failed for {rel}: {r.stderr.decode()[:400]}")


def ssh_list_receipts() -> list[str]:
    remote_dir = f"{REMOTE_GROWTH}/workspace/receipts"
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        REMOTE,
        f"mkdir -p {json.dumps(remote_dir)}; "
        f"find {json.dumps(remote_dir)} -maxdepth 1 -type f -name '*.json' 2>/dev/null | sort",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return []
    lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    # return basename only
    return [Path(ln).name for ln in lines]


def pull_receipt_file(name: str) -> dict | None:
    data = ssh_cat(f"workspace/receipts/{name}")
    if data is None:
        return None
    # also mirror locally
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    (RECEIPTS_DIR / name).write_bytes(data)
    return json.loads(data.decode("utf-8"))


def mac_status_canonical(rel: str) -> bool:
    p = GROWTH / rel
    if not p.is_file():
        return False
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    if not text.startswith("---"):
        return False
    end = text.find("\n---\n", 4)
    if end < 0:
        return False
    fm = text[4:end]
    return any(
        line.strip() == "status: CANONICAL" or line.strip().startswith("status: CANONICAL")
        for line in fm.splitlines()
    )


def quarantine(rel: str, side: str, data: bytes | None, reason: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest_dir = QUARANTINE_DIR / stamp
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = rel.replace("/", "__")
    meta = {
        "path": rel,
        "side": side,
        "reason": reason,
        "sha256": sha256_bytes(data) if data is not None else None,
        "quarantined_at": utc_now(),
    }
    (dest_dir / f"{safe}.{side}.meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    if data is not None:
        (dest_dir / f"{safe}.{side}").write_bytes(data)
    return dest_dir


def emit_receipt(paths: list[dict], session_id: str, host: str = "mac") -> Path:
    """Write a local receipt (also usable on VPS via same schema)."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = f"{stamp}-{session_id}.json"
    doc = {
        "schema": SCHEMA,
        "emitted_at": utc_now(),
        "session_id": session_id,
        "host": host,
        "paths": paths,
    }
    path = RECEIPTS_DIR / name
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


def classify(rel: str, mac_h: str | None, vps_h: str | None, base_h: str | None) -> str:
    if mac_h == vps_h:
        return "identical"
    if base_h is None:
        # no baseline: if only one side exists, take that; if both differ → conflict
        if mac_h is None and vps_h is not None:
            return "pull_vps"
        if vps_h is None and mac_h is not None:
            return "keep_mac"
        return "conflict"
    if mac_h == base_h and vps_h != base_h:
        return "pull_vps"
    if vps_h == base_h and mac_h != base_h:
        return "keep_mac"
    if mac_h != base_h and vps_h != base_h:
        return "conflict"
    return "identical"


def git_commit(paths: list[str], message: str) -> str | None:
    repo = GROWTH.parent  # Obsidian Vault
    if not paths:
        return None
    # stage only under Growth OS
    rels = [f"Growth OS/{p}" for p in paths]
    subprocess.run(["git", "add", "--"] + rels, cwd=repo, check=False)
    # also baseline / quarantine / receipts under Growth OS
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    )
    if not status.stdout.strip():
        return None
    r = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(r.stdout, r.stderr, file=sys.stderr)
        return None
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    return sha


def mac_to_vps() -> None:
    script = Path.home() / ".hermes/bin/kos-mac-to-vps.sh"
    subprocess.run(["bash", str(script)], check=True)


def cmd_init_baseline(args: argparse.Namespace) -> int:
    """Hash allowlisted existing Mac files into baseline (optional scope)."""
    baseline = load_baseline()
    roots = args.paths or ["brain/", "workspace/", "logs/", "hot.md", "compile-log.md", "raw/"]
    count = 0
    for root in roots:
        p = GROWTH / root
        if p.is_file():
            files = [p]
        elif p.is_dir():
            files = [f for f in p.rglob("*") if f.is_file()]
        else:
            continue
        for f in files:
            rel = str(f.relative_to(GROWTH))
            if not is_allowlisted(rel) and not rel.startswith("brain/"):
                continue
            if is_protected(rel):
                continue
            h = sha256_file(f)
            if h:
                baseline["hashes"][rel] = h
                count += 1
    # always baseline governance as protected markers
    for g in PROTECTED_PREFIXES:
        gp = GROWTH / g
        if gp.is_file():
            baseline["hashes"][g] = sha256_file(gp)
    save_baseline(baseline)
    print(json.dumps({"ok": True, "hashed": count, "baseline": str(BASELINE_PATH)}, indent=2))
    return 0


def cmd_emit(args: argparse.Namespace) -> int:
    paths = []
    for rel in args.paths:
        h = sha256_file(GROWTH / rel)
        if h is None and args.host == "vps":
            data = ssh_cat(rel)
            h = sha256_bytes(data) if data else None
        paths.append({"path": rel, "sha256": h, "op": args.op})
    if args.host == "vps":
        # write receipt on VPS
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"{stamp}-{args.session}.json"
        doc = {
            "schema": SCHEMA,
            "emitted_at": utc_now(),
            "session_id": args.session,
            "host": "vps",
            "paths": paths,
        }
        ssh_write(f"workspace/receipts/{name}", json.dumps(doc, indent=2).encode() + b"\n")
        print(json.dumps({"ok": True, "receipt": f"workspace/receipts/{name}", "host": "vps"}))
    else:
        path = emit_receipt(paths, args.session, host="mac")
        print(json.dumps({"ok": True, "receipt": str(path)}))
    return 0


def cmd_pullback(args: argparse.Namespace) -> int:
    baseline = load_baseline()
    hashes: dict = baseline.setdefault("hashes", {})
    report = {
        "started_at": utc_now(),
        "applied": [],
        "kept_mac": [],
        "identical": [],
        "quarantined": [],
        "skipped_protected": [],
        "skipped_not_allowlisted": [],
        "skipped_canonical": [],
        "errors": [],
    }

    receipt_names = args.receipts or ssh_list_receipts()
    if args.only_pending:
        # prefer unprocessed: those without .processed marker locally
        pending = []
        for name in receipt_names:
            marker = RECEIPTS_DIR / f".processed-{name}"
            if not marker.exists():
                pending.append(name)
        receipt_names = pending

    touched: set[str] = set()
    for name in receipt_names:
        try:
            doc = pull_receipt_file(name)
        except Exception as e:
            report["errors"].append({"receipt": name, "error": str(e)})
            continue
        if not doc:
            continue
        if doc.get("schema") != SCHEMA:
            report["errors"].append({"receipt": name, "error": "bad schema"})
            continue
        for entry in doc.get("paths") or []:
            rel = entry.get("path")
            if not rel:
                continue
            touched.add(rel)

    applied_paths: list[str] = []

    for rel in sorted(touched):
        if is_protected(rel):
            vps_data = ssh_cat(rel)
            mac_h = sha256_file(GROWTH / rel)
            vps_h = sha256_bytes(vps_data) if vps_data else None
            if vps_h and vps_h != mac_h:
                quarantine(rel, "vps", vps_data, "protected_path_vps_mutation")
                report["quarantined"].append({"path": rel, "reason": "protected"})
            report["skipped_protected"].append(rel)
            continue

        if not is_allowlisted(rel):
            report["skipped_not_allowlisted"].append(rel)
            continue

        if mac_status_canonical(rel):
            vps_data = ssh_cat(rel)
            if vps_data and sha256_bytes(vps_data) != sha256_file(GROWTH / rel):
                quarantine(rel, "vps", vps_data, "canonical_mac_page")
                report["quarantined"].append({"path": rel, "reason": "canonical"})
            report["skipped_canonical"].append(rel)
            continue

        # raw/**: only allow create-new (Mac missing)
        if rel.startswith("raw/") and (GROWTH / rel).exists():
            vps_data = ssh_cat(rel)
            mac_h = sha256_file(GROWTH / rel)
            vps_h = sha256_bytes(vps_data) if vps_data else None
            if vps_h and vps_h != mac_h:
                quarantine(rel, "vps", vps_data, "raw_immutable_conflict")
                report["quarantined"].append({"path": rel, "reason": "raw_immutable"})
            continue

        mac_path = GROWTH / rel
        mac_h = sha256_file(mac_path)
        vps_data = ssh_cat(rel)
        vps_h = sha256_bytes(vps_data) if vps_data is not None else None
        base_h = hashes.get(rel)

        decision = classify(rel, mac_h, vps_h, base_h)

        if decision == "identical":
            if vps_h:
                hashes[rel] = vps_h
            report["identical"].append(rel)
            continue

        if decision == "keep_mac":
            report["kept_mac"].append(rel)
            if mac_h:
                hashes[rel] = mac_h
            continue

        if decision == "conflict":
            mac_data = mac_path.read_bytes() if mac_path.exists() else None
            quarantine(rel, "mac", mac_data, "both_changed")
            quarantine(rel, "vps", vps_data, "both_changed")
            report["quarantined"].append({"path": rel, "reason": "both_changed"})
            continue

        if decision == "pull_vps":
            if vps_data is None:
                report["errors"].append({"path": rel, "error": "vps missing"})
                continue
            mac_path.parent.mkdir(parents=True, exist_ok=True)
            mac_path.write_bytes(vps_data)
            hashes[rel] = vps_h
            applied_paths.append(rel)
            report["applied"].append(rel)

    save_baseline(baseline)

    for name in receipt_names:
        (RECEIPTS_DIR / f".processed-{name}").write_text(utc_now() + "\n", encoding="utf-8")

    commit_sha = None
    if args.commit and applied_paths:
        # include baseline + receipts markers
        extra = [
            "workspace/sync/baseline-hashes.json",
        ]
        commit_sha = git_commit(
            applied_paths + extra,
            args.commit_message
            or f"chore(kos): Model B pull-back ({len(applied_paths)} paths)",
        )
        report["commit"] = commit_sha

    if args.converge and (applied_paths or args.force_converge):
        mac_to_vps()
        report["converged"] = True

    report["finished_at"] = utc_now()
    report_path = SYNC_STATE_DIR / f"pullback-report-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    SYNC_STATE_DIR.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"report={report_path}", file=sys.stderr)
    return 0


def cmd_verify_hashes(args: argparse.Namespace) -> int:
    out = []
    for rel in args.paths:
        mac_h = sha256_file(GROWTH / rel)
        data = ssh_cat(rel)
        vps_h = sha256_bytes(data) if data is not None else None
        out.append(
            {
                "path": rel,
                "mac": mac_h,
                "vps": vps_h,
                "match": mac_h == vps_h and mac_h is not None,
            }
        )
    print(json.dumps({"results": out}, indent=2))
    return 0 if all(r["match"] for r in out) else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="KOS Controlled Model B sync tooling")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p0 = sub.add_parser("init-baseline")
    p0.add_argument("--paths", nargs="*", default=None)
    p0.set_defaults(func=cmd_init_baseline)

    p1 = sub.add_parser("emit-receipt")
    p1.add_argument("--session", required=True)
    p1.add_argument("--op", default="update")
    p1.add_argument("--host", choices=["mac", "vps"], default="mac")
    p1.add_argument("paths", nargs="+")
    p1.set_defaults(func=cmd_emit)

    p2 = sub.add_parser("pullback")
    p2.add_argument("--receipts", nargs="*", default=None)
    p2.add_argument("--only-pending", action="store_true")
    p2.add_argument("--commit", action="store_true")
    p2.add_argument("--commit-message", default=None)
    p2.add_argument("--converge", action="store_true")
    p2.add_argument("--force-converge", action="store_true")
    p2.set_defaults(func=cmd_pullback)

    p3 = sub.add_parser("verify-hashes")
    p3.add_argument("paths", nargs="+")
    p3.set_defaults(func=cmd_verify_hashes)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
