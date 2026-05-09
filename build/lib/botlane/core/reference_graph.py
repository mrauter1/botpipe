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


@dataclass(slots=True)
class ReferenceGraphBuilder:
    step_names: frozenset[str]
    prompt_refs: dict[str, list[PlaceholderRef]] = field(default_factory=dict)
    artifact_template_refs: dict[str, list[PlaceholderRef]] = field(default_factory=dict)
    inferred_artifact_reads: dict[str, list[ArtifactId]] = field(default_factory=dict)
    step_output_refs: dict[str, list[PlaceholderRef]] = field(default_factory=dict)
    branch_refs: dict[str, list[PlaceholderRef]] = field(default_factory=dict)
    fan_in_refs: dict[str, list[PlaceholderRef]] = field(default_factory=dict)
    worklist_refs: dict[str, list[PlaceholderRef]] = field(default_factory=dict)

    def add_prompt_refs(self, source_key: str, refs: tuple[PlaceholderRef, ...]) -> None:
        self._append_refs(self.prompt_refs, source_key, refs)
        self._classify_refs(source_key, refs)

    def add_artifact_template_refs(self, source_key: str, refs: tuple[PlaceholderRef, ...]) -> None:
        self._append_refs(self.artifact_template_refs, source_key, refs)
        self._classify_refs(source_key, refs)

    def add_inferred_artifact_reads(self, source_key: str, artifact_ids: tuple[ArtifactId, ...]) -> None:
        if not artifact_ids:
            return
        bucket = self.inferred_artifact_reads.setdefault(source_key, [])
        for artifact_id in artifact_ids:
            if artifact_id not in bucket:
                bucket.append(artifact_id)

    def build(self) -> ReferenceGraph:
        return ReferenceGraph(
            prompt_refs={key: tuple(value) for key, value in self.prompt_refs.items()},
            artifact_template_refs={key: tuple(value) for key, value in self.artifact_template_refs.items()},
            inferred_artifact_reads={key: tuple(value) for key, value in self.inferred_artifact_reads.items()},
            step_output_refs={key: tuple(value) for key, value in self.step_output_refs.items()},
            branch_refs={key: tuple(value) for key, value in self.branch_refs.items()},
            fan_in_refs={key: tuple(value) for key, value in self.fan_in_refs.items()},
            worklist_refs={key: tuple(value) for key, value in self.worklist_refs.items()},
        )

    def _append_refs(
        self,
        target: dict[str, list[PlaceholderRef]],
        source_key: str,
        refs: tuple[PlaceholderRef, ...],
    ) -> None:
        if not refs:
            return
        bucket = target.setdefault(source_key, [])
        for ref in refs:
            if ref not in bucket:
                bucket.append(ref)

    def _classify_refs(self, source_key: str, refs: tuple[PlaceholderRef, ...]) -> None:
        step_output_refs: list[PlaceholderRef] = []
        branch_refs: list[PlaceholderRef] = []
        fan_in_refs: list[PlaceholderRef] = []
        worklist_refs: list[PlaceholderRef] = []
        for ref in refs:
            if not ref.raw:
                continue
            if ref.root == "branch":
                branch_refs.append(ref)
                continue
            if ref.root == "fan_in":
                fan_in_refs.append(ref)
                continue
            if ref.root in {"item", "worklist"}:
                worklist_refs.append(ref)
                continue
            if ref.root in self.step_names or ref.root in {"artifacts", "step", "self"}:
                step_output_refs.append(ref)
        self._append_refs(self.step_output_refs, source_key, tuple(step_output_refs))
        self._append_refs(self.branch_refs, source_key, tuple(branch_refs))
        self._append_refs(self.fan_in_refs, source_key, tuple(fan_in_refs))
        self._append_refs(self.worklist_refs, source_key, tuple(worklist_refs))
