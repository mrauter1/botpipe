"""Internal artifact identity values.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True, order=True)
class ArtifactId:
    namespace: Literal["workflow", "step"]
    name: str
    step: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("ArtifactId.name must be non-empty")
        if self.namespace == "step":
            if not isinstance(self.step, str) or not self.step.strip():
                raise ValueError("step ArtifactId requires step")
            return
        if self.namespace == "workflow":
            if self.step is not None:
                raise ValueError("workflow ArtifactId must not include step")
            return
        raise ValueError(f"unsupported ArtifactId namespace {self.namespace!r}")

    @property
    def qualified_name(self) -> str:
        return self.name if self.step is None else f"{self.step}.{self.name}"

    @property
    def display(self) -> str:
        return self.qualified_name
