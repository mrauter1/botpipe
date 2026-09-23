"""Deterministically persist typed review verdicts for workflow feedback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from botpipe import activity


@activity(retry_safe=True, name="save typed review")
def save_review(path: str, verdict: BaseModel | dict[str, Any]) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        verdict.model_dump(mode="json", by_alias=True)
        if isinstance(verdict, BaseModel)
        else verdict
    )
    serialized = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    if target.suffix.lower() == ".md":
        serialized = f"# Review\n\n```json\n{serialized}\n```\n"
    else:
        serialized += "\n"
    target.write_text(serialized, encoding="utf-8")
    return str(target)


__all__ = ["save_review"]
