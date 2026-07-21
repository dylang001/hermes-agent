#!/usr/bin/env python3
"""Knowledge OS mutation hooks — receipt-aware write gate (Controlled Model B pilot).

Mutating Knowledge OS skills MUST use this module (CLI or Python API). A run
must not report success unless:

1. every touched path is in the receipt;
2. every path is inside an approved lane;
3. protected-path checks pass;
4. lifecycle transitions are valid (brain pages);
5. append-only behavior holds for compile-log / existing raw.

Optional ``--run-cycle`` emits the receipt then runs Mac-side Model B
pull-back → commit → Mac→VPS converge → hash verify.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RECEIPT_SCHEMA = "kos-touched-path-receipt/v1"
SESSION_SCHEMA = "kos-mutation-session/v1"

ALLOWED_STATUSES = frozenset(
    {
        "DRAFT",
        "EXTRACTED",
        "STRUCTURED",
        "CONNECTED",
        "VERIFIED",
        "RAW",  # rare on brain; allow for safety
    }
)
# CANONICAL is proposal-only — blocked for autonomous mutation
BLOCKED_STATUSES = frozenset({"CANONICAL", "ARCHIVED"})

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

# Limited Model B pilot lanes (explicit user-directed writes)
APPROVED_LANES = (
    "workspace/",
    "brain/",
    "brain/_indexes/",
    "hot.md",
    "compile-log.md",
    "raw/",
    "logs/",  # append logs allowed as operational; pilot list named workspace/brain/hot/compile/raw primarily
    "workspace/receipts/",  # receipts themselves
)

APPEND_ONLY_PATHS = frozenset({"compile-log.md"})


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_growth_os() -> Path:
    env = os.environ.get("GROWTH_OS_PATH") or os.environ.get("HERMES_GROWTH_OS")
    if env:
        return Path(env).expanduser().resolve()
    mac = Path.home() / "Documents/Obsidian Vault/Growth OS"
    vps = Path("/opt/hermes/data/obsidian/Growth OS")
    if mac.is_dir():
        return mac.resolve()
    if vps.is_dir():
        return vps.resolve()
    raise FileNotFoundError("Growth OS not found; set GROWTH_OS_PATH")


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def norm_rel(rel: str) -> str:
    return rel.lstrip("./").replace("\\", "/")


def is_protected(rel: str) -> bool:
    n = norm_rel(rel)
    return any(n == p or n.startswith(p) for p in PROTECTED_PREFIXES)


def in_approved_lane(rel: str) -> bool:
    n = norm_rel(rel)
    if is_protected(n):
        return False
    if n == "hot.md" or n == "compile-log.md":
        return True
    if n.startswith("workspace/"):
        return True
    if n.startswith("brain/"):
        return True
    if n.startswith("raw/"):
        return True
    if n.startswith("logs/"):
        return True
    return False


def parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    raw = text[4:end]
    out: dict[str, str] = {}
    for line in raw.splitlines():
        if not line or line.startswith(" ") or line.startswith("\t") or line.startswith("-"):
            continue
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


@dataclass
class TouchedPath:
    path: str
    op: str  # create | update | append
    sha256: str | None = None
    prior_sha256: str | None = None
    status: str | None = None


@dataclass
class MutationSession:
    """Shared pre/post mutation hooks for Knowledge OS skills."""

    session_id: str
    skill: str
    growth_os: Path
    host: str = "auto"
    touched: list[TouchedPath] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    _started_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.host == "auto":
            self.host = "vps" if str(self.growth_os).startswith("/opt/hermes") else "mac"

    # ----- pre hooks -----
    def preflight_path(
        self,
        rel: str,
        *,
        op: str,
        append_only: bool = False,
        skip_create_exists_check: bool = False,
    ) -> None:
        rel = norm_rel(rel)
        if is_protected(rel):
            raise PermissionError(f"protected path blocked: {rel}")
        if not in_approved_lane(rel):
            raise PermissionError(f"path outside approved pilot lanes: {rel}")
        target = self.growth_os / rel
        if rel.startswith("raw/") and op in {"update", "append"} and target.exists():
            raise PermissionError(f"raw files are immutable after create: {rel}")
        if append_only or rel in APPEND_ONLY_PATHS:
            if op not in {"append", "create"}:
                # create allowed if missing; update (rewrite) forbidden
                if target.exists() and op == "update":
                    raise PermissionError(f"append-only path cannot be rewritten: {rel}")
        if (
            not skip_create_exists_check
            and op == "create"
            and target.exists()
            and rel.startswith("raw/")
        ):
            raise PermissionError(f"raw create refused; file exists: {rel}")

    # ----- mutation recording -----
    def note_touch(
        self,
        rel: str,
        *,
        op: str,
        content: bytes | None = None,
        status: str | None = None,
        skip_create_exists_check: bool = False,
    ) -> TouchedPath:
        rel = norm_rel(rel)
        self.preflight_path(
            rel,
            op=op,
            append_only=rel in APPEND_ONLY_PATHS,
            skip_create_exists_check=skip_create_exists_check,
        )
        path = self.growth_os / rel
        prior = sha256_file(path)
        digest = sha256_bytes(content) if content is not None else sha256_file(path)
        if status is None and content is not None and rel.startswith("brain/") and not rel.startswith("brain/_indexes/"):
            try:
                fm = parse_frontmatter(content.decode("utf-8", errors="replace"))
                status = fm.get("status")
            except Exception:
                status = None
        if status:
            self._validate_status(rel, status)
        tp = TouchedPath(path=rel, op=op, sha256=digest, prior_sha256=prior, status=status)
        self.touched.append(tp)
        return tp

    def _validate_status(self, rel: str, status: str) -> None:
        st = status.strip().upper() if status else ""
        # allow lowercase accidental
        st_norm = status.strip()
        if st_norm in BLOCKED_STATUSES or st in BLOCKED_STATUSES:
            raise PermissionError(
                f"lifecycle blocked for autonomous mutation ({st_norm}) on {rel}"
            )
        if rel.startswith("brain/") and not rel.startswith("brain/_indexes/"):
            if st_norm not in ALLOWED_STATUSES and st not in ALLOWED_STATUSES:
                # allow unknown only as warning for indexes
                self.errors.append(f"invalid brain status {st_norm!r} on {rel}")

    def write_text(self, rel: str, text: str, *, op: str | None = None) -> Path:
        rel = norm_rel(rel)
        path = self.growth_os / rel
        exists = path.exists()
        resolved_op = op or ("update" if exists else "create")
        data = text.encode("utf-8")
        self.preflight_path(rel, op=resolved_op)
        if rel.startswith("brain/") and not rel.startswith("brain/_indexes/"):
            fm = parse_frontmatter(text)
            if "status" in fm:
                self._validate_status(rel, fm["status"])
            elif resolved_op == "create":
                self.errors.append(f"brain create missing status frontmatter: {rel}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.note_touch(
            rel,
            op=resolved_op,
            content=data,
            skip_create_exists_check=True,
        )
        return path

    def append_text(self, rel: str, text: str) -> Path:
        rel = norm_rel(rel)
        path = self.growth_os / rel
        self.preflight_path(rel, op="append", append_only=True)
        prior = path.read_bytes() if path.exists() else b""
        addition = text if text.endswith("\n") else text + "\n"
        # verify append-only: new content must start with prior bytes
        new_data = prior + addition.encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(new_data)
        if prior and not new_data.startswith(prior):
            self.errors.append(f"append-only violation on {rel}")
        self.note_touch(
            rel, op="append", content=new_data, skip_create_exists_check=True
        )
        return path

    # ----- post hooks -----
    def postflight(self) -> list[str]:
        """Return list of blocking errors. Empty => success eligible."""
        errs = list(self.errors)
        if not self.touched:
            errs.append("no touched paths recorded")
        seen: set[str] = set()
        for t in self.touched:
            if t.path in seen:
                continue
            seen.add(t.path)
            if is_protected(t.path):
                errs.append(f"protected path in receipt: {t.path}")
            if not in_approved_lane(t.path):
                errs.append(f"lane violation: {t.path}")
            path = self.growth_os / t.path
            if not path.exists():
                errs.append(f"touched path missing on disk: {t.path}")
                continue
            live = sha256_file(path)
            if t.sha256 and live and t.sha256 != live:
                errs.append(f"receipt hash mismatch for {t.path}")
            if t.path in APPEND_ONLY_PATHS and t.op == "update":
                errs.append(f"append-only path used update op: {t.path}")
            if t.path.startswith("raw/") and t.op != "create" and t.prior_sha256:
                errs.append(f"raw mutation not create-only: {t.path}")
            if t.status and (
                t.status in BLOCKED_STATUSES or t.status.upper() in BLOCKED_STATUSES
            ):
                errs.append(f"blocked status on {t.path}: {t.status}")
        return errs

    def build_receipt(self) -> dict[str, Any]:
        # dedupe by path keeping last
        by_path: dict[str, TouchedPath] = {}
        for t in self.touched:
            by_path[t.path] = t
        return {
            "schema": RECEIPT_SCHEMA,
            "emitted_at": utc_now(),
            "session_id": self.session_id,
            "skill": self.skill,
            "host": self.host,
            "paths": [
                {
                    "path": t.path,
                    "sha256": t.sha256 or sha256_file(self.growth_os / t.path),
                    "op": t.op,
                    **({"status": t.status} if t.status else {}),
                }
                for t in by_path.values()
            ],
        }

    def emit_receipt(self) -> Path:
        errs = self.postflight()
        if errs:
            raise RuntimeError("postflight failed:\n- " + "\n- ".join(errs))
        receipt = self.build_receipt()
        out_dir = self.growth_os / "workspace" / "receipts"
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        name = f"{stamp}-{self.session_id}.json"
        # also include receipt path in a sidecar? receipt file itself is meta
        path = out_dir / name
        path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        return path

    def run_model_b_cycle(self, receipt_name: str | None = None) -> dict[str, Any]:
        """Mac-side pull-back → commit → converge → verify.

        When running on VPS, SSH to Mac if KOS_MAC_SSH is set; else instruct.
        """
        mac_ssh = os.environ.get("KOS_MAC_SSH", "")
        model_b = Path.home() / ".hermes/bin/kos-model-b.py"
        repo_model_b = Path(__file__).resolve().parent / "kos_model_b.py"
        script = model_b if model_b.is_file() else repo_model_b

        if self.host == "vps" and mac_ssh:
            # trigger Mac pullback remotely
            cmd = [
                "ssh",
                "-o",
                "BatchMode=yes",
                mac_ssh,
                f"python3 {json.dumps(str(Path.home() / '.hermes/bin/kos-model-b.py'))} "
                f"pullback --only-pending --commit --converge",
            ]
            r = subprocess.run(cmd, capture_output=True, text=True)
            return {
                "ok": r.returncode == 0,
                "stdout": r.stdout[-2000:],
                "stderr": r.stderr[-1000:],
                "mode": "ssh-mac",
            }

        if script.is_file() and self.host == "mac":
            cmd = [
                sys.executable,
                str(script),
                "pullback",
                "--only-pending",
                "--commit",
                "--converge",
            ]
            r = subprocess.run(cmd, capture_output=True, text=True)
            return {
                "ok": r.returncode == 0,
                "stdout": r.stdout[-2000:],
                "stderr": r.stderr[-1000:],
                "mode": "local-mac",
            }

        return {
            "ok": False,
            "mode": "deferred",
            "message": (
                "Receipt emitted. Run on Mac: "
                "python3 ~/.hermes/bin/kos-model-b.py pullback --only-pending --commit --converge"
            ),
        }


# ----- session file helpers (for multi-step skill runs) -----

def session_dir(growth: Path) -> Path:
    d = growth / "workspace" / "receipts" / ".sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_session(session: MutationSession) -> Path:
    path = session_dir(session.growth_os) / f"{session.session_id}.json"
    doc = {
        "schema": SESSION_SCHEMA,
        "session_id": session.session_id,
        "skill": session.skill,
        "host": session.host,
        "started_at": session._started_at,
        "growth_os": str(session.growth_os),
        "touched": [t.__dict__ for t in session.touched],
        "errors": session.errors,
        "warnings": session.warnings,
    }
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


def load_session(growth: Path, session_id: str) -> MutationSession:
    path = session_dir(growth) / f"{session_id}.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    s = MutationSession(
        session_id=doc["session_id"],
        skill=doc["skill"],
        growth_os=Path(doc["growth_os"]),
        host=doc.get("host", "auto"),
    )
    s._started_at = doc.get("started_at", utc_now())
    s.errors = list(doc.get("errors") or [])
    s.warnings = list(doc.get("warnings") or [])
    for t in doc.get("touched") or []:
        s.touched.append(TouchedPath(**t))
    return s


def cmd_begin(args: argparse.Namespace) -> int:
    growth = Path(args.growth_os) if args.growth_os else resolve_growth_os()
    s = MutationSession(session_id=args.session, skill=args.skill, growth_os=growth)
    path = save_session(s)
    print(json.dumps({"ok": True, "session": args.session, "state": str(path)}))
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    growth = Path(args.growth_os) if args.growth_os else resolve_growth_os()
    s = load_session(growth, args.session) if args.session else MutationSession(
        session_id="ad-hoc", skill="preflight", growth_os=growth
    )
    try:
        s.preflight_path(args.path, op=args.op, append_only=args.append_only)
    except PermissionError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 2
    print(json.dumps({"ok": True, "path": args.path, "op": args.op}))
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    growth = Path(args.growth_os) if args.growth_os else resolve_growth_os()
    s = load_session(growth, args.session)
    path = growth / norm_rel(args.path)
    content = path.read_bytes() if path.exists() else None
    status = args.status
    if status is None and content and args.path.startswith("brain/"):
        status = parse_frontmatter(content.decode("utf-8", errors="replace")).get("status")
    try:
        s.note_touch(args.path, op=args.op, content=content, status=status)
    except PermissionError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 2
    save_session(s)
    print(json.dumps({"ok": True, "touched": len(s.touched), "path": args.path}))
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    growth = Path(args.growth_os) if args.growth_os else resolve_growth_os()
    s = load_session(growth, args.session)
    text = Path(args.file).read_text(encoding="utf-8") if args.file else sys.stdin.read()
    try:
        if args.append:
            s.append_text(args.path, text)
        else:
            s.write_text(args.path, text)
    except PermissionError as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 2
    save_session(s)
    print(json.dumps({"ok": True, "path": args.path, "touched": len(s.touched)}))
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    growth = Path(args.growth_os) if args.growth_os else resolve_growth_os()
    s = load_session(growth, args.session)
    # re-hash live files for any notes missing sha
    for t in s.touched:
        if not t.sha256:
            t.sha256 = sha256_file(growth / t.path)
    try:
        receipt_path = s.emit_receipt()
    except RuntimeError as e:
        print(json.dumps({"ok": False, "error": str(e), "errors": s.postflight()}))
        return 3
    result: dict[str, Any] = {
        "ok": True,
        "receipt": str(receipt_path.relative_to(growth)),
        "paths": [t.path for t in s.touched],
        "success_eligible": True,
    }
    if args.run_cycle:
        result["model_b_cycle"] = s.run_model_b_cycle(receipt_path.name)
        if not result["model_b_cycle"].get("ok") and result["model_b_cycle"].get("mode") != "deferred":
            result["ok"] = False
            print(json.dumps(result, indent=2))
            return 4
    # cleanup session state
    state = session_dir(growth) / f"{args.session}.json"
    if state.exists() and not args.keep_session:
        state.unlink()
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 4


def cmd_validate_receipt(args: argparse.Namespace) -> int:
    growth = Path(args.growth_os) if args.growth_os else resolve_growth_os()
    doc = json.loads(Path(args.receipt).read_text(encoding="utf-8"))
    errs = []
    if doc.get("schema") != RECEIPT_SCHEMA:
        errs.append("bad schema")
    claimed = []
    for p in doc.get("paths") or []:
        rel = p.get("path")
        claimed.append(rel)
        if is_protected(rel):
            errs.append(f"protected: {rel}")
        if not in_approved_lane(rel):
            errs.append(f"lane: {rel}")
        live = sha256_file(growth / rel)
        if p.get("sha256") and live and p["sha256"] != live:
            errs.append(f"hash mismatch: {rel}")
    if args.expect_paths:
        missing = set(args.expect_paths) - set(claimed)
        extra_check = set(claimed) - set(args.expect_paths)
        if missing:
            errs.append(f"receipt missing paths: {sorted(missing)}")
        if args.strict and extra_check:
            errs.append(f"receipt unexpected paths: {sorted(extra_check)}")
    ok = not errs
    print(json.dumps({"ok": ok, "errors": errs, "paths": claimed}))
    return 0 if ok else 3


def main() -> int:
    ap = argparse.ArgumentParser(description="KOS mutation hooks / receipt wrapper")
    ap.add_argument("--growth-os", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("begin")
    b.add_argument("--session", required=True)
    b.add_argument("--skill", required=True)
    b.set_defaults(func=cmd_begin)

    p = sub.add_parser("preflight")
    p.add_argument("--session", default=None)
    p.add_argument("--path", required=True)
    p.add_argument("--op", default="update")
    p.add_argument("--append-only", action="store_true")
    p.set_defaults(func=cmd_preflight)

    n = sub.add_parser("note")
    n.add_argument("--session", required=True)
    n.add_argument("--path", required=True)
    n.add_argument("--op", default="update")
    n.add_argument("--status", default=None)
    n.set_defaults(func=cmd_note)

    w = sub.add_parser("write")
    w.add_argument("--session", required=True)
    w.add_argument("--path", required=True)
    w.add_argument("--file", default=None)
    w.add_argument("--append", action="store_true")
    w.set_defaults(func=cmd_write)

    f = sub.add_parser("finalize")
    f.add_argument("--session", required=True)
    f.add_argument("--run-cycle", action="store_true")
    f.add_argument("--keep-session", action="store_true")
    f.set_defaults(func=cmd_finalize)

    v = sub.add_parser("validate-receipt")
    v.add_argument("receipt")
    v.add_argument("--expect-paths", nargs="*", default=None)
    v.add_argument("--strict", action="store_true")
    v.set_defaults(func=cmd_validate_receipt)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
