"""Internal canonical artifact-plan values.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from pydantic import BaseModel

from .identifiers import ArtifactId


ArtifactKind: TypeAlias = Literal["text", "markdown", "json", "raw"]
ArtifactSchema: TypeAlias = type[BaseModel] | dict[str, object] | None


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    id: ArtifactId
    name: str
    template: str
    kind: ArtifactKind
    schema: ArtifactSchema
    required: bool
    owner_step: str | None
    workflow_level: bool
    producer_steps: tuple[str, ...]

    @property
    def qualified_name(self) -> str:
        return self.id.qualified_name
