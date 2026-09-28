"""Invocation parameters for the bounded workflow author."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    package_title: str | None = None
    workflow_kind: str = Field(default="workflow", min_length=1)
    aliases: list[str] = Field(default_factory=list)
    max_rounds: int = Field(default=4, gt=0, strict=True)
    max_provider_turns: int = Field(default=32, gt=0, strict=True)
    target_test_argv: list[str] | None = Field(default=None, min_length=1)

    @field_validator("aliases", "target_test_argv")
    @classmethod
    def nonblank_items(cls, value):
        if value is not None and any(not item.strip() for item in value):
            raise ValueError("arguments and aliases must not be blank")
        return value
