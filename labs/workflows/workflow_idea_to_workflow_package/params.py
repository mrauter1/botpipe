"""Typed invocation parameters for the workflow builder."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_name: str = Field(min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    package_title: str | None = None
    workflow_kind: str = Field(default="workflow", min_length=1)
    aliases: list[str] = Field(default_factory=list)
    target_test_command: str | None = Field(default=None, min_length=1)
    target_test_argv: list[str] | None = Field(default=None, min_length=1)
    max_provider_turns: int = Field(default=32, gt=0, strict=True)

    @field_validator("target_test_argv")
    @classmethod
    def validate_test_argv(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and any(not item.strip() for item in value):
            raise ValueError("target_test_argv must contain nonblank arguments")
        return value

    @model_validator(mode="after")
    def one_test_command(self) -> Params:
        if self.target_test_argv is not None and self.target_test_command is not None:
            raise ValueError("supply target_test_argv or target_test_command, not both")
        return self

    @field_validator("workflow_kind")
    @classmethod
    def normalize_kind(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("workflow_kind must not be blank")
        return normalized

    @field_validator("aliases")
    @classmethod
    def validate_aliases(cls, value: list[str]) -> list[str]:
        aliases = [item.strip() for item in value]
        if any(not item for item in aliases):
            raise ValueError("aliases must not contain blank values")
        if len(set(aliases)) != len(aliases):
            raise ValueError("aliases must be unique")
        return aliases


__all__ = ["Params"]
