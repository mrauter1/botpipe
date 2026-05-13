"""Workflow-owned Botpipe-v1 naming and path conventions."""

from __future__ import annotations

import re
from pathlib import Path

from botpipe.runtime.stores.filesystem import scope_key


PHASE_DIR_SAFE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
MAX_PHASE_ID_UTF8_BYTES = 96


def phase_dir_key(phase_id: str) -> str:
    normalized = phase_id.strip()
    if not normalized:
        raise ValueError("phase_id must be non-empty")
    if len(normalized.encode("utf-8")) > MAX_PHASE_ID_UTF8_BYTES:
        raise ValueError(f"phase_id {normalized!r} exceeds {MAX_PHASE_ID_UTF8_BYTES} UTF-8 bytes")
    if PHASE_DIR_SAFE_RE.fullmatch(normalized):
        return normalized
    return f"_pid-{normalized.encode('utf-8').hex()}"


def botpipe_v1_session_path(run_dir: Path, ref_name: str, scope: str | None) -> Path:
    sessions_dir = run_dir / "sessions"
    if ref_name == "plan_session" and scope is None:
        return sessions_dir / "plan.json"
    if ref_name == "phase_session" and scope is not None:
        return sessions_dir / "phases" / f"{phase_dir_key(scope)}.json"
    if scope is None:
        return sessions_dir / f"{ref_name}.json"
    return sessions_dir / "scopes" / scope_key(scope) / f"{ref_name}.json"


class BotpipeV1SessionPathStrategy:
    """Workflow-owned session naming policy for Botpipe-v1 parity."""

    def path_for(self, run_dir: Path, ref_name: str, scope: str | None) -> Path:
        return botpipe_v1_session_path(run_dir, ref_name, scope)


__all__ = ["BotpipeV1SessionPathStrategy", "botpipe_v1_session_path", "phase_dir_key"]
