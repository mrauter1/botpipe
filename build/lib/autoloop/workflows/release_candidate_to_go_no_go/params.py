"""Workflow-specific parameter model for the release go/no-go package."""

from __future__ import annotations

from autoloop.stdlib import deduped_string_list_fields, optional_text_fields, required_text_fields

from pydantic import BaseModel, Field


class Params(BaseModel):
    """Invocation contract for ``release_candidate_to_go_no_go``."""

    release_name: str
    target_date: str | None = None
    deployment_environment: str = "production"
    release_owner: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)

    _validate_required_text = required_text_fields("release_name", "deployment_environment")
    _normalize_optional_text = optional_text_fields("target_date", "release_owner")
    _normalize_evidence_paths = deduped_string_list_fields("evidence_paths")


__all__ = ["Params"]
