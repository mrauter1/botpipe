"""Workflow-specific parameter model for the security remediation package."""

from __future__ import annotations

from typing import Literal

from botlane.stdlib import deduped_string_list_fields, optional_text_fields, required_text_fields

from pydantic import BaseModel, Field, field_validator


FindingSource = Literal["pentest", "bug_bounty", "scanner", "internal_review", "customer_report", "other"]
Severity = Literal["critical", "high", "medium", "low", "unknown"]


class Params(BaseModel):
    """Invocation contract for ``security_finding_to_verified_remediation``."""

    finding_title: str
    finding_source: FindingSource
    severity: Severity = "unknown"
    affected_system: str | None = None
    sponsor_role: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    deployment_constraints: list[str] = Field(default_factory=list)

    _validate_finding_title = required_text_fields("finding_title")

    @field_validator("finding_source", "severity", mode="before")
    @classmethod
    def _normalize_literal_text(cls, value: object) -> object:
        if value is None:
            return value
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("value must be non-empty")
        return normalized

    _normalize_optional_text = optional_text_fields("affected_system", "sponsor_role")
    _normalize_repeatable_strings = deduped_string_list_fields("evidence_paths", "deployment_constraints")


__all__ = ["Params"]
