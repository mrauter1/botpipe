"""Internal workflow reference graph.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass

from .identifiers import ArtifactId
from .placeholders import PlaceholderRef


@dataclass(frozen=True, slots=True)
class ReferenceGraph:
    prompt_refs: dict[str, tuple[PlaceholderRef, ...]]
    artifact_template_refs: dict[str, tuple[PlaceholderRef, ...]]
    inferred_artifact_reads: dict[str, tuple[ArtifactId, ...]]
