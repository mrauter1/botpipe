"""Typed invocation parameters."""

from __future__ import annotations

from pydantic import Field

from botpipe_optimizer import TaskFramingWithEvidenceParameters


class Params(TaskFramingWithEvidenceParameters):
    max_provider_turns: int = Field(default=32, gt=0, strict=True)


__all__ = ["Params"]
