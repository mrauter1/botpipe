"""Workflow-specific parameter model for the release go/no-go package."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Parameters(BaseModel):
    """Invocation contract for ``release_candidate_to_go_no_go``."""

    release_name: str
    target_date: str | None = None
    deployment_environment: str = "production"
    release_owner: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)

    @field_validator("release_name")
    @classmethod
    def _validate_release_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("release_name must be non-empty")
        return normalized

    @field_validator("target_date", "release_owner")
    @classmethod
    def _normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("deployment_environment")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("deployment_environment must be non-empty")
        return normalized

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
