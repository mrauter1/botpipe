"""Workflow-specific parameter model for the investigation evidence-pack building block."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


InvestigationKind = Literal[
    "release_readiness",
    "incident_response",
    "security_remediation",
    "delivery_recovery",
    "customer_escalation",
    "general",
]


class Parameters(BaseModel):
    """Invocation contract for ``investigation_request_to_evidence_pack``."""

    investigation_title: str
    investigation_kind: InvestigationKind
    sponsor_role: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    source_constraints: list[str] = Field(default_factory=list)

    @field_validator("investigation_title")
    @classmethod
    def _validate_investigation_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("investigation_title must be non-empty")
        return normalized

    @field_validator("investigation_kind", mode="before")
    @classmethod
    def _normalize_investigation_kind(cls, value: object) -> object:
        if value is None:
            return value
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("investigation_kind must be non-empty")
        return normalized

    @field_validator("sponsor_role")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("evidence_paths", "source_constraints")
    @classmethod
    def _normalize_repeatable_strings(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = value.strip()
            if candidate and candidate not in normalized:
                normalized.append(candidate)
        return normalized


__all__ = ["Parameters"]
