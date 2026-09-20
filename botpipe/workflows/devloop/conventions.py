"""Stable path conventions used by devloop domain artifacts."""

from __future__ import annotations

import re

PHASE_DIR_SAFE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
MAX_PHASE_ID_UTF8_BYTES = 96


def phase_dir_key(phase_id: str) -> str:
    normalized = phase_id.strip()
    if not normalized:
        raise ValueError("phase_id must be non-empty")
    if len(normalized.encode("utf-8")) > MAX_PHASE_ID_UTF8_BYTES:
        raise ValueError(
            f"phase_id {normalized!r} exceeds {MAX_PHASE_ID_UTF8_BYTES} UTF-8 bytes"
        )
    if PHASE_DIR_SAFE_RE.fullmatch(normalized):
        return normalized
    return f"_pid-{normalized.encode('utf-8').hex()}"


__all__ = ["phase_dir_key"]
