"""Typed invocation parameters."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

EvidencePath = Annotated[str, Field(min_length=1, max_length=1024)]


class Params(BaseModel):
    max_provider_turns: int = Field(default=32, gt=0, strict=True)
    finding_title: str = Field(min_length=1)
    finding_source: Literal[
        "pentest",
        "bug_bounty",
        "scanner",
        "internal_review",
        "customer_report",
        "other",
    ]
    severity: Literal["critical", "high", "medium", "low", "unknown"] = "unknown"
    affected_system: str | None = None
    sponsor_role: str | None = None
    evidence_paths: list[EvidencePath] = Field(default_factory=list, max_length=32)
    deployment_constraints: list[str] = Field(default_factory=list)


__all__ = ["Params"]
