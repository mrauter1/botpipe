"""Internal branch-group result values.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypeAlias


BranchStatus: TypeAlias = Literal["completed", "needs_input", "failed", "cancelled", "skipped"]


@dataclass(frozen=True, slots=True)
class BranchArtifactObservation:
    name: str
    path: str
    kind: str | None
    exists: bool
    validation: str
    validation_errors: tuple[str, ...]

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "kind": self.kind,
            "exists": self.exists,
            "validation": self.validation,
            "validation_errors": list(self.validation_errors),
        }


@dataclass(frozen=True, slots=True)
class BranchResult:
    name: str
    index: int
    input: Any
    step_name: str
    status: BranchStatus
    route: str | None
    destination: str | None
    runtime_control: str | None
    reason: str | None
    question: str | None
    artifacts: tuple[BranchArtifactObservation, ...]
    raw_output_path: str | None
    raw_output_paths: dict[str, str]
    provider_session: str | None
    provider_sessions: dict[str, str]
    error: dict[str, Any] | None
    started_at: str
    finished_at: str
    duration_ms: int
    usage: dict[str, Any]
    cancellation_requested: bool = False
    cancellation_completed: bool = False
    cancellation_supported: bool = True

    def to_manifest_dict(self) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "index": self.index,
            "input": self.input,
            "step_name": self.step_name,
            "status": self.status,
            "route": self.route,
            "destination": self.destination,
            "runtime_control": self.runtime_control,
            "reason": self.reason,
            "question": self.question,
            "artifacts": [artifact.to_manifest_dict() for artifact in self.artifacts],
            "raw_output_path": self.raw_output_path,
            "raw_output_paths": dict(self.raw_output_paths),
            "provider_session": self.provider_session,
            "provider_sessions": dict(self.provider_sessions),
            "error": None if self.error is None else dict(self.error),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
            "usage": dict(self.usage),
        }
        if self.status in {"cancelled", "skipped"}:
            payload["cancellation_requested"] = self.cancellation_requested
            payload["cancellation_completed"] = self.cancellation_completed
            payload["cancellation_supported"] = self.cancellation_supported
        return payload
