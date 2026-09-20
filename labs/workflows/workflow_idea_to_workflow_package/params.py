"""Typed invocation parameters."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Params(BaseModel):
    package_name: str = Field(min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    package_title: str | None = None
    workflow_kind: Literal["end_to_end", "building_block"]
    authoring_shape: Literal["single", "flow_specs", "package"] = "flow_specs"
    aliases: list[str] = Field(default_factory=list)
    target_test_command: str = Field(default="pytest", min_length=1)

    @field_validator("authoring_shape", mode="before")
    @classmethod
    def normalize_shape(cls, value):
        return str(value).strip().replace("-", "_")


__all__ = ["Params"]
