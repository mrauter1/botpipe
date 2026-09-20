"""Typed invocation parameters."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Params(BaseModel):
    release_name: str = Field(min_length=1)
    target_date: str | None = None
    deployment_environment: str = Field(default="production", min_length=1)
    release_owner: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)


__all__ = ["Params"]
