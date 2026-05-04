"""Workflow-specific parameter model for the incident hardening package."""

from __future__ import annotations

from autoloop.stdlib import deduped_string_list_fields, optional_text_fields, required_text_fields

from pydantic import BaseModel, Field


class Params(BaseModel):
    """Invocation contract for ``incident_to_hardening_program``."""

    incident_title: str
    incident_window: str | None = None
    affected_system: str | None = None
    severity: str | None = None
    incident_commander: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)

    _validate_incident_title = required_text_fields("incident_title")
    _normalize_optional_text = optional_text_fields("incident_window", "affected_system", "severity", "incident_commander")
    _normalize_evidence_paths = deduped_string_list_fields("evidence_paths")


__all__ = ["Params"]
