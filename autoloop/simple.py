"""Progressive authoring declarations for simplified workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import BaseModel

try:  # pragma: no branch - prefer installed-package imports when available
    from autoloop_v3.core import Artifact, Workflow as _StrictWorkflow
    from autoloop_v3.core.prompts import Prompt
    from autoloop_v3.core.routes import Route, RouteInfo
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core import Artifact, Workflow as _StrictWorkflow
    from core.prompts import Prompt
    from core.routes import Route, RouteInfo


PromptInput = str | Path | Prompt
RouteMapping = Mapping[str, Route | object]
ChainNode = object | tuple[object, str]


class EmptyState(BaseModel):
    """Placeholder state for simple workflows until lowering is wired in."""


class Workflow:
    """Non-strict declaration surface for simplified workflow authoring."""

    __workflow_abstract__ = True
    __strict_workflow__ = False
    extensions: tuple[object, ...] = ()
    State = EmptyState


class StrictWorkflow(_StrictWorkflow):
    """Strict declaration surface retained for opt-in explicit workflows."""

    __workflow_abstract__ = True
    __strict_workflow__ = True


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    """Simple authoring artifact declaration with optional inferred step-local paths."""

    __autoloop_simple_artifact_spec__ = True

    name: str
    kind: str
    schema: type[BaseModel] | dict[str, object] | None = None
    path: str | Path | None = None
    required: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("artifact name must be a non-empty string")
        if self.kind not in {"json", "markdown", "text", "raw"}:
            raise ValueError(f"unsupported artifact kind {self.kind!r}")

    def path_template(self, step_name: str) -> str:
        if self.path is not None:
            return str(self.path)
        suffix = {
            "json": ".json",
            "markdown": ".md",
            "text": ".txt",
            "raw": "",
        }[self.kind]
        return f"{{workflow_folder}}/{step_name}/{self.name}{suffix}"

    def materialize(self, step_name: str) -> Artifact:
        template = self.path_template(step_name)
        if self.kind == "json":
            return Artifact.json(template, schema=self.schema, required=self.required, name=self.name)
        if self.kind == "markdown":
            return Artifact.md(template, required=self.required, name=self.name)
        if self.kind == "raw":
            return Artifact.raw(template, required=self.required, name=self.name)
        return Artifact.text(template, required=self.required, name=self.name)


ArtifactInput = Artifact | ArtifactSpec | str


def Json(
    name: str,
    schema: type[BaseModel] | dict[str, object] | None = None,
    *,
    path: str | Path | None = None,
    required: bool = False,
) -> ArtifactSpec:
    return ArtifactSpec(name=name, kind="json", schema=schema, path=path, required=required)


def Md(name: str, *, path: str | Path | None = None, required: bool = False) -> ArtifactSpec:
    return ArtifactSpec(name=name, kind="markdown", path=path, required=required)


def Text(name: str, *, path: str | Path | None = None, required: bool = False) -> ArtifactSpec:
    return ArtifactSpec(name=name, kind="text", path=path, required=required)


def Raw(name: str, *, path: str | Path | None = None, required: bool = False) -> ArtifactSpec:
    return ArtifactSpec(name=name, kind="raw", path=path, required=required)


class _NamedDeclaration:
    __slots__ = ("name", "_explicit_name")
    __autoloop_simple_declaration__ = True
    default_chain_route = "done"

    def __init__(self, *, name: str | None = None) -> None:
        self.name = name
        self._explicit_name = name

    def __set_name__(self, owner: type[object], attr_name: str) -> None:
        if self.name is None:
            self.name = attr_name


class StepDeclaration(_NamedDeclaration):
    """Foundation declaration for future simple-step lowering."""

    kind = "llm"

    def __init__(
        self,
        prompt: PromptInput,
        *,
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        out: Artifact | ArtifactSpec | None = None,
        outputs: Sequence[Artifact | ArtifactSpec] = (),
        routes: RouteMapping | None = None,
        route_summaries: Mapping[str, str] | None = None,
        before: Any | None = None,
        after: Any | None = None,
        control_schema: Any | None = None,
        provider: str | None = None,
        model: str | None = None,
        effort: str | None = None,
        retry: Any | None = None,
        session: Any | None = None,
    ) -> None:
        super().__init__(name=name)
        self.prompt = _normalize_simple_prompt(prompt)
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.outputs = _normalize_outputs(out, outputs)
        self.routes = dict(routes or {})
        self.route_summaries = dict(route_summaries or {})
        self.before = before
        self.after = after
        self.control_schema = control_schema
        self.provider = provider
        self.model = model
        self.effort = effort
        self.retry = retry
        self.session = session


class ReviewStepDeclaration(_NamedDeclaration):
    """Foundation declaration for future review-step lowering."""

    kind = "review"
    default_chain_route = "accepted"

    def __init__(
        self,
        producer: PromptInput,
        verifier: PromptInput,
        *,
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        out: Artifact | ArtifactSpec | None = None,
        outputs: Sequence[Artifact | ArtifactSpec] = (),
        accepted: str = "accepted",
        rework: str = "needs_rework",
        before: Any | None = None,
        after: Any | None = None,
        route_summaries: Mapping[str, str] | None = None,
        provider: str | None = None,
        model: str | None = None,
        effort: str | None = None,
        retry: Any | None = None,
        session: Any | None = None,
    ) -> None:
        super().__init__(name=name)
        self.producer = _normalize_simple_prompt(producer)
        self.verifier = _normalize_simple_prompt(verifier)
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.outputs = _normalize_outputs(out, outputs)
        self.accepted = accepted
        self.rework = rework
        self.before = before
        self.after = after
        self.route_summaries = dict(route_summaries or {})
        self.provider = provider
        self.model = model
        self.effort = effort
        self.retry = retry
        self.session = session


class SystemStepDeclaration(_NamedDeclaration):
    """Foundation declaration for future system-step lowering."""

    kind = "system"

    def __init__(
        self,
        fn: Any,
        *,
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        outputs: Sequence[Artifact | ArtifactSpec] = (),
        routes: RouteMapping | None = None,
        before: Any | None = None,
        after: Any | None = None,
    ) -> None:
        super().__init__(name=name)
        self.fn = fn
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.outputs = tuple(outputs)
        self.routes = dict(routes or {})
        self.before = before
        self.after = after


class WorkflowStep(_NamedDeclaration):
    """Foundation declaration for future child-workflow step lowering."""

    kind = "workflow"

    def __init__(
        self,
        workflow: object,
        *,
        name: str | None = None,
        message: str | None = None,
        message_from: str | None = None,
        params: Mapping[str, object] | None = None,
        input: object | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        out: Artifact | ArtifactSpec | None = None,
        outputs: Sequence[Artifact | ArtifactSpec] = (),
        routes: RouteMapping | None = None,
        before: Any | None = None,
        after: Any | None = None,
    ) -> None:
        super().__init__(name=name)
        self.workflow = workflow
        self.message = message
        self.message_from = message_from
        self.params = dict(params or {})
        self.input = input
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.outputs = _normalize_outputs(out, outputs)
        self.routes = dict(routes or {})
        self.before = before
        self.after = after


@dataclass(frozen=True, slots=True)
class FlowSpec:
    __autoloop_simple_flow_spec__ = True
    items: tuple[ChainNode, ...]


def step(prompt: PromptInput, **kwargs: Any) -> StepDeclaration:
    return StepDeclaration(prompt, **kwargs)


def review_step(producer: PromptInput, verifier: PromptInput, **kwargs: Any) -> ReviewStepDeclaration:
    return ReviewStepDeclaration(producer, verifier, **kwargs)


def system_step(fn: Any, **kwargs: Any) -> SystemStepDeclaration:
    return SystemStepDeclaration(fn, **kwargs)


def workflow_step(workflow: object, **kwargs: Any) -> WorkflowStep:
    return WorkflowStep(workflow, **kwargs)


def chain(*items: ChainNode) -> FlowSpec:
    return FlowSpec(items=tuple(items))


def _normalize_outputs(
    out: Artifact | ArtifactSpec | None,
    outputs: Sequence[Artifact | ArtifactSpec],
) -> tuple[Artifact | ArtifactSpec, ...]:
    declared = list(outputs)
    if out is not None:
        declared.insert(0, out)
    return tuple(declared)


def _normalize_simple_prompt(prompt: PromptInput) -> Prompt:
    if isinstance(prompt, Prompt):
        return prompt
    if isinstance(prompt, Path):
        return Prompt.file(prompt)
    if isinstance(prompt, str):
        return Prompt.inline(prompt)
    raise TypeError(f"unsupported prompt type: {type(prompt)!r}")


__all__ = [
    "Json",
    "Md",
    "Prompt",
    "Raw",
    "Route",
    "RouteInfo",
    "StrictWorkflow",
    "Text",
    "Workflow",
    "WorkflowStep",
    "chain",
    "review_step",
    "step",
    "system_step",
    "workflow_step",
]
