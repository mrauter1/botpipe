"""Small contracts for real workflow trials and rubric judgments."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class TrialCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
    description: str = Field(min_length=1)
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    workspace: Literal["empty", "fixture"] = "empty"
    # Destination in the case workspace -> path inside frozen analysis evidence.
    assets: dict[str, str] = Field(default_factory=dict)
    # Required fixture references and file outputs for a tool-free judge.
    judge_input_paths: list[str] = Field(default_factory=list)
    output_paths: list[str] = Field(default_factory=list)


class TrialSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_provider_turns: int = Field(default=12, ge=1)
    timeout_seconds: float = Field(default=180, gt=0, allow_inf_nan=False)
    max_elapsed_seconds: float = Field(default=1200, gt=0, allow_inf_nan=False)
    max_judge_turns: int = Field(default=12, ge=1)
    max_judge_seconds: float = Field(default=600, gt=0, allow_inf_nan=False)
    judge_timeout_seconds: float = Field(default=120, gt=0, allow_inf_nan=False)
    repetitions: int = Field(default=1, ge=1)
    reverse_order_judgment: bool = False
    max_packet_bytes: int = Field(default=48000, ge=1024)
    max_output_bytes: int = Field(default=2 * 1024 * 1024, ge=1024)
    max_fixture_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    max_fixture_files: int = Field(default=10000, ge=1)


class TrialResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    execution: Literal["complete", "infrastructure_error", "interrupted"]
    outcome: str
    run_id: str | None = None
    value: Any = None
    error: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    operations: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    elapsed_seconds: float | None = None
    provider_budget: dict[str, Any] = Field(default_factory=dict)
    omissions: list[str] = Field(default_factory=list)


class CriterionJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: str
    a: Literal["met", "not_met", "unknown"]
    b: Literal["met", "not_met", "unknown"]
    explanation: str = Field(min_length=1)


class RubricJudgment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preference: Literal["A", "B", "tie", "inconclusive"]
    criteria: list[CriterionJudgment] = Field(min_length=1)
    explanation: str = Field(min_length=1)
    # Exact excerpts from the supplied anonymous packet, not source identities.
    evidence_quotes: list[str] = Field(min_length=1)
