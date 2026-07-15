"""High-risk action detection for Phase 1 approval walls."""

from __future__ import annotations

import re
from typing import Iterable, List, Mapping, Sequence


DEFAULT_HIGH_RISK_PATTERNS: Sequence[str] = (
    r"\bpublish\b",
    r"\bsend\s+email\b",
    r"\bemail\s+customer\b",
    r"\bcustomer[- ]facing\b",
    r"\bwire\s+money\b",
    r"\btransfer\s+funds\b",
    r"\bdelete\s+production\b",
    r"\bdrop\s+table\b",
    r"\brevoke\b",
    r"\bcredential\b",
    r"\bapi\s*key\b",
    r"\bpassword\s+reset\b",
    r"\bpost\s+to\s+(twitter|x|linkedin|instagram)\b",
    r"\btweet\b",
)


def _compile_patterns(patterns: Iterable[str]) -> List[re.Pattern[str]]:
    out: List[re.Pattern[str]] = []
    for pat in patterns:
        try:
            out.append(re.compile(pat, re.IGNORECASE))
        except re.error:
            out.append(re.compile(re.escape(pat), re.IGNORECASE))
    return out


def detect_high_risk(text: str, cfg: Mapping | None = None) -> List[str]:
    """Return matching high-risk pattern strings (empty = clear for auto-exec)."""
    patterns = list(DEFAULT_HIGH_RISK_PATTERNS)
    if cfg:
        custom = cfg.get("high_risk_patterns") or []
        if isinstance(custom, list) and custom:
            # Additive — YAML keywords extend builtins, they do not replace them.
            patterns.extend(str(p) for p in custom)
    compiled = _compile_patterns(patterns)
    hits: List[str] = []
    for pattern in compiled:
        if pattern.search(text or ""):
            hits.append(pattern.pattern)
    return hits


def requires_human_approval(text: str, cfg: Mapping | None = None) -> bool:
    return bool(detect_high_risk(text, cfg))
