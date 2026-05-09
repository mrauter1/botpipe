"""Internal workflow reference graph.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .identifiers import ArtifactId
from .placeholders import PlaceholderRef


@dataclass(frozen=True, slots=True)
class ReferenceGraph:
    prompt_refs: dict[str, tuple[PlaceholderRef, ...]] = field(default_factory=dict)
    artifact_template_refs: dict[str, tuple[PlaceholderRef, ...]] = field(default_factory=dict)
    inferred_artifact_reads: dict[str, tuple[ArtifactId, ...]] = field(default_factory=dict)
    step_output_refs: dict[str, tuple[PlaceholderRef, ...]] = field(default_factory=dict)
    branch_refs: dict[str, tuple[PlaceholderRef, ...]] = field(default_factory=dict)
    fan_in_refs: dict[str, tuple[PlaceholderRef, ...]] = field(default_factory=dict)
    worklist_refs: dict[str, tuple[PlaceholderRef, ...]] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "ReferenceGraph":
        return cls()
