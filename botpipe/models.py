"""Values returned by provider operations and top-level workflow runs."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

from .artifacts import ArtifactMap

T = TypeVar("T")
RunStatus = Literal[
    "completed", "failed", "awaiting_input", "interrupted", "budget_exceeded"
]


@dataclass(frozen=True)
class Result(Generic[T]):
    value: T
    artifacts: ArtifactMap
    usage: dict[str, Any] = field(default_factory=dict)
    operation_id: str = ""
    run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunResult(Generic[T]):
    run_id: str
    task_id: str
    status: RunStatus
    value: T | None = None
    artifacts: ArtifactMap = field(default_factory=ArtifactMap)
    error: str | None = None
    pending_input: dict | None = None
    folder: Path = Path(".")
    usage: dict = field(default_factory=dict)
    exception: BaseException | None = field(default=None, repr=False, compare=False)

    @property
    def ok(self):
        return self.status == "completed"
