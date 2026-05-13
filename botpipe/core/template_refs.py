"""Template reference metadata used by Jinja validation and reference graphs."""

from __future__ import annotations

from dataclasses import dataclass, field


BRANCH_SCOPED_TEMPLATE_ROOTS = frozenset({"branch"})
FAN_IN_SCOPED_TEMPLATE_ROOTS = frozenset({"fan_in"})
ACTIVE_WORKLIST_SCOPED_TEMPLATE_ROOTS = frozenset(
    {"item", "current_worklist", "item_state", "step_item_state"}
)
WORKLIST_SELECTION_TEMPLATE_ROOTS = frozenset({"worklist", "worklists"})
ARTIFACT_TEMPLATE_PHASE_ROOTS = frozenset({"route", "event", "outcome"})
ROOT_STABLE_ARTIFACT_TEMPLATE_BLOCKING_ROOTS = (
    BRANCH_SCOPED_TEMPLATE_ROOTS
    | FAN_IN_SCOPED_TEMPLATE_ROOTS
    | ACTIVE_WORKLIST_SCOPED_TEMPLATE_ROOTS
    | WORKLIST_SELECTION_TEMPLATE_ROOTS
)


@dataclass(frozen=True, slots=True)
class PlaceholderRef:
    raw: str
    root: str
    path: tuple[str, ...]
    source: str


@dataclass(frozen=True, slots=True)
class TemplateRequirements:
    refs: tuple[PlaceholderRef, ...] = field(default_factory=tuple)
    roots: frozenset[str] = field(default_factory=frozenset)
    dynamic_artifact_access: bool = False

    @classmethod
    def empty(cls) -> "TemplateRequirements":
        return cls()

    def merge(self, other: "TemplateRequirements") -> "TemplateRequirements":
        refs = tuple(dict.fromkeys((*self.refs, *other.refs)))
        return TemplateRequirements(
            refs=refs,
            roots=self.roots | other.roots,
            dynamic_artifact_access=self.dynamic_artifact_access or other.dynamic_artifact_access,
        )


__all__ = [
    "ACTIVE_WORKLIST_SCOPED_TEMPLATE_ROOTS",
    "ARTIFACT_TEMPLATE_PHASE_ROOTS",
    "BRANCH_SCOPED_TEMPLATE_ROOTS",
    "FAN_IN_SCOPED_TEMPLATE_ROOTS",
    "PlaceholderRef",
    "ROOT_STABLE_ARTIFACT_TEMPLATE_BLOCKING_ROOTS",
    "TemplateRequirements",
    "WORKLIST_SELECTION_TEMPLATE_ROOTS",
]
