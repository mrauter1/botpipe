"""Typed invocation parameters."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

EvidencePath = Annotated[str, Field(min_length=1, max_length=1024)]


class Params(BaseModel):
    max_provider_turns: int = Field(default=32, gt=0, strict=True)
    incident_title: str = Field(min_length=1)
    incident_window: str | None = None
    affected_system: str | None = None
    severity: str | None = None
    incident_commander: str | None = None
    evidence_paths: list[EvidencePath] = Field(default_factory=list, max_length=32)


__all__ = ["Params"]
