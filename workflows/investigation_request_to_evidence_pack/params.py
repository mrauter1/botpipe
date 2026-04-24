"""Workflow-specific parameter model for the investigation evidence-pack building block."""

from __future__ import annotations

from typing import Literal

try:
    from autoloop_v3.stdlib import deduped_string_list_fields, optional_text_fields, required_text_fields
except ImportError:  # pragma: no cover - direct repo execution fallback
    from stdlib import deduped_string_list_fields, optional_text_fields, required_text_fields

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

    _validate_investigation_title = required_text_fields("investigation_title")

    @field_validator("investigation_kind", mode="before")
    @classmethod
    def _normalize_investigation_kind(cls, value: object) -> object:
        if value is None:
            return value
        normalized = str(value).strip()
        if not normalized:
            raise ValueError("investigation_kind must be non-empty")
        return normalized

    _normalize_optional_text = optional_text_fields("sponsor_role")
    _normalize_repeatable_strings = deduped_string_list_fields("evidence_paths", "source_constraints")


__all__ = ["Parameters"]
