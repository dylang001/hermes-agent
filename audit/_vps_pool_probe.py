#!/usr/bin/env python3
"""Probe OpenCode-Go credential pool on VPS (redacted)."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", "/opt/hermes/home"))
APP = Path(os.environ.get("HERMES_APP", "/opt/hermes/app"))
sys.path.insert(0, str(APP))

env_path = HERMES_HOME / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
os.environ["HERMES_HOME"] = str(HERMES_HOME)

from agent.credential_pool import load_pool  # noqa: E402

now = time.time()
for provider in ("opencode-go", "opencode-zen", "opencode"):
    pool = load_pool(provider)
    print(f"=== provider={provider!r} pool={pool!r} ===")
    if pool is None:
        continue
    entries = getattr(pool, "entries", None) or []
    print(f"entries={len(entries)}")
    for i, e in enumerate(entries):
        status = getattr(e, "status", None) or getattr(e, "last_status", None)
        last_err = getattr(e, "last_error_code", None)
        last_at = getattr(e, "last_status_at", None)
        key = getattr(e, "api_key", None) or getattr(e, "key", None) or ""
        label = getattr(e, "label", None) or getattr(e, "id", None)
        ttl_left = None
        if last_at and status == "exhausted":
            # rough: show age
            ttl_left = now - float(last_at)
        print(
            f"  [{i}] label={label!r} status={status!r} err={last_err!r} "
            f"age_s={ttl_left!r} key_len={len(str(key))} key_suf=...{str(key)[-4:] if key else ''}"
        )
    # try select
    for meth in ("acquire", "select", "get"):
        fn = getattr(pool, meth, None)
        if callable(fn):
            try:
                got = fn()
                print(f"{meth}() -> {got!r}"[:200])
            except TypeError:
                try:
                    got = fn(None)
                    print(f"{meth}(None) -> {got!r}"[:200])
                except Exception as ex:
                    print(f"{meth} err {ex}")
            except Exception as ex:
                print(f"{meth} err {ex}")

auth = HERMES_HOME / "auth.json"
if auth.exists():
    d = json.loads(auth.read_text(encoding="utf-8"))
    print("auth.json keys:", sorted(d.keys()))
    pools = d.get("credential_pools") or d.get("pools")
    if pools:
        print("pools type", type(pools).__name__)
        if isinstance(pools, dict):
            for pk, pv in pools.items():
                if isinstance(pv, list):
                    print(f"  pool[{pk}]: {len(pv)} entries")
                else:
                    print(f"  pool[{pk}]: {type(pv).__name__}")
