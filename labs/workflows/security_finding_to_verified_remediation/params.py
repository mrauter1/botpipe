"""Typed invocation parameters."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Params(BaseModel):
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
    evidence_paths: list[str] = Field(default_factory=list)
    deployment_constraints: list[str] = Field(default_factory=list)


__all__ = ["Params"]
