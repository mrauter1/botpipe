"""Typed invocation parameters."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Params(BaseModel):
    investigation_title: str = Field(min_length=1)
    investigation_kind: Literal[
        "release_readiness",
        "incident_response",
        "security_remediation",
        "delivery_recovery",
        "customer_escalation",
        "general",
    ]
    sponsor_role: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    source_constraints: list[str] = Field(default_factory=list)


__all__ = ["Params"]
