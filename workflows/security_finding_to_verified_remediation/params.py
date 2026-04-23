"""Workflow-specific parameter model for the security remediation package."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


FindingSource = Literal["pentest", "bug_bounty", "scanner", "internal_review", "customer_report", "other"]
Severity = Literal["critical", "high", "medium", "low", "unknown"]


class Parameters(BaseModel):
    """Invocation contract for ``security_finding_to_verified_remediation``."""

    finding_title: str
    finding_source: FindingSource
    severity: Severity = "unknown"
    affected_system: str | None = None
    sponsor_role: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    deployment_constraints: list[str] = Field(default_factory=list)

    @field_validator("finding_title")
    @classmethod
    def _validate_finding_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("finding_title must be non-empty")
        return normalized

    @field_validator("finding_source", "severity", mode="before")
    @classmethod
    def _normalize_literal_text(cls, value: object) -> object:
        if value is None:
            return value
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    @field_validator("affected_system", "sponsor_role")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("evidence_paths", "deployment_constraints")
    @classmethod
    def _normalize_repeatable_strings(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            candidate = value.strip()
            if candidate and candidate not in normalized:
                normalized.append(candidate)
        return normalized


__all__ = ["Parameters"]
