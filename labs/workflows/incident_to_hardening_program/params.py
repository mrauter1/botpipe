"""Typed invocation parameters."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Params(BaseModel):
    incident_title: str = Field(min_length=1)
    incident_window: str | None = None
    affected_system: str | None = None
    severity: str | None = None
    incident_commander: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)


__all__ = ["Params"]
