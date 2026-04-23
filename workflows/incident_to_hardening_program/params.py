"""Workflow-specific parameter model for the incident hardening package."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Parameters(BaseModel):
    """Invocation contract for ``incident_to_hardening_program``."""

    incident_title: str
    incident_window: str | None = None
    affected_system: str | None = None
    severity: str | None = None
    incident_commander: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)

    @field_validator("incident_title")
    @classmethod
    def _validate_incident_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("incident_title must be non-empty")
        return normalized

    @field_validator("incident_window", "affected_system", "severity", "incident_commander")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("evidence_paths")
    @classmethod
    def _normalize_evidence_paths(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            path = value.strip()
            if path and path not in normalized:
                normalized.append(path)
        return normalized


__all__ = ["Parameters"]
