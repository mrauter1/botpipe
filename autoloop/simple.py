"""Simple workflow authoring declarations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import BaseModel

try:  # pragma: no branch - prefer installed-package imports when available
    from autoloop_v3.core import Artifact, Workflow as _StrictWorkflow
    from autoloop_v3.core.prompts import Prompt
    from autoloop_v3.core.routes import Route, RouteInfo
    from autoloop_v3.core.steps import AfterHookResult
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core import Artifact, Workflow as _StrictWorkflow
    from core.prompts import Prompt
    from core.routes import Route, RouteInfo
    from core.steps import AfterHookResult


PromptInput = str | Path | Prompt
RouteMapping = Mapping[str, Route | object]
ChainNode = object | tuple[object, str]


class EmptyState(BaseModel):
    """Default state model for workflows that do not declare ``State``."""


class Workflow:
    """Simple public authoring surface."""

    __workflow_abstract__ = True
    __strict_workflow__ = False
    extensions: tuple[object, ...] = ()
    State = EmptyState


class StrictWorkflow(_StrictWorkflow):
    """Strict workflow authoring surface for explicit core-style definitions."""

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
    """Simple step declaration lowered during workflow definition discovery."""

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
        route_infos: Mapping[str, RouteInfo | str] | None = None,
        route_summaries: Mapping[str, str] | None = None,
        before: Any | None = None,
        after: Any | None = None,
        control_schema: Any | None = None,
        retry: Any | None = None,
        session: Any | None = None,
    ) -> None:
        super().__init__(name=name)
        self.prompt = _normalize_simple_prompt(prompt)
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.outputs = _normalize_outputs(out, outputs)
        self.routes = dict(routes or {})
        self.route_infos = _normalize_simple_route_infos(route_infos, route_summaries=route_summaries)
        self.before = before
        self.after = after
        self.control_schema = control_schema
        self.retry = retry
        self.session = session


class ReviewStepDeclaration(_NamedDeclaration):
    """Simple review-step declaration lowered during workflow definition discovery."""

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
        route_infos: Mapping[str, RouteInfo | str] | None = None,
        before: Any | None = None,
        after: Any | None = None,
        route_summaries: Mapping[str, str] | None = None,
        control_schema: Any | None = None,
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
        self.route_infos = _normalize_simple_route_infos(route_infos, route_summaries=route_summaries)
        self.control_schema = control_schema
        self.retry = retry
        self.session = session


class SystemStepDeclaration(_NamedDeclaration):
    """Simple system-step declaration lowered during workflow definition discovery."""

    kind = "system"

    def __init__(
        self,
        fn: Any,
        *,
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        out: Artifact | ArtifactSpec | None = None,
        outputs: Sequence[Artifact | ArtifactSpec] = (),
        routes: RouteMapping | None = None,
        route_infos: Mapping[str, RouteInfo | str] | None = None,
        route_summaries: Mapping[str, str] | None = None,
        before: Any | None = None,
        after: Any | None = None,
    ) -> None:
        super().__init__(name=name)
        self.fn = fn
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.outputs = _normalize_outputs(out, outputs)
        self.routes = dict(routes or {})
        self.route_infos = _normalize_simple_route_infos(route_infos, route_summaries=route_summaries)
        self.before = before
        self.after = after


class WorkflowStep(_NamedDeclaration):
    """Child-workflow invocation step declaration."""

    kind = "workflow"

    def __init__(
        self,
        workflow: object,
        *,
        name: str | None = None,
        message: str | None = None,
        message_from: Artifact | str | Path | None = None,
        params: Mapping[str, object] | None = None,
        input: object | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        out: Artifact | ArtifactSpec | None = None,
        outputs: Sequence[Artifact | ArtifactSpec] = (),
        routes: RouteMapping | None = None,
        route_infos: Mapping[str, RouteInfo | str] | None = None,
        route_summaries: Mapping[str, str] | None = None,
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
        self.route_infos = _normalize_simple_route_infos(route_infos, route_summaries=route_summaries)
        self.before = before
        self.after = after


@dataclass(frozen=True, slots=True)
class FlowSpec:
    __autoloop_simple_flow_spec__ = True
    items: tuple[ChainNode, ...]


def step(
    prompt: PromptInput,
    *,
    name: str | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    out: Artifact | ArtifactSpec | None = None,
    outputs: Sequence[Artifact | ArtifactSpec] = (),
    routes: RouteMapping | None = None,
    route_infos: Mapping[str, RouteInfo | str] | None = None,
    route_summaries: Mapping[str, str] | None = None,
    before: Any | None = None,
    after: Any | None = None,
    control_schema: Any | None = None,
    retry: Any | None = None,
    session: Any | None = None,
) -> StepDeclaration:
    return StepDeclaration(
        prompt,
        name=name,
        reads=reads,
        requires=requires,
        out=out,
        outputs=outputs,
        routes=routes,
        route_infos=route_infos,
        route_summaries=route_summaries,
        before=before,
        after=after,
        control_schema=control_schema,
        retry=retry,
        session=session,
    )


def review_step(
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
    route_infos: Mapping[str, RouteInfo | str] | None = None,
    route_summaries: Mapping[str, str] | None = None,
    before: Any | None = None,
    after: Any | None = None,
    control_schema: Any | None = None,
    retry: Any | None = None,
    session: Any | None = None,
) -> ReviewStepDeclaration:
    return ReviewStepDeclaration(
        producer,
        verifier,
        name=name,
        reads=reads,
        requires=requires,
        out=out,
        outputs=outputs,
        accepted=accepted,
        rework=rework,
        route_infos=route_infos,
        before=before,
        after=after,
        route_summaries=route_summaries,
        control_schema=control_schema,
        retry=retry,
        session=session,
    )


def system_step(
    fn: Any,
    *,
    name: str | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    out: Artifact | ArtifactSpec | None = None,
    outputs: Sequence[Artifact | ArtifactSpec] = (),
    routes: RouteMapping | None = None,
    route_infos: Mapping[str, RouteInfo | str] | None = None,
    route_summaries: Mapping[str, str] | None = None,
    before: Any | None = None,
    after: Any | None = None,
) -> SystemStepDeclaration:
    return SystemStepDeclaration(
        fn,
        name=name,
        reads=reads,
        requires=requires,
        out=out,
        outputs=outputs,
        routes=routes,
        route_infos=route_infos,
        route_summaries=route_summaries,
        before=before,
        after=after,
    )


def workflow_step(
    workflow: object,
    *,
    name: str | None = None,
    message: str | None = None,
    message_from: Artifact | str | Path | None = None,
    params: Mapping[str, object] | None = None,
    input: object | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    out: Artifact | ArtifactSpec | None = None,
    outputs: Sequence[Artifact | ArtifactSpec] = (),
    routes: RouteMapping | None = None,
    route_infos: Mapping[str, RouteInfo | str] | None = None,
    route_summaries: Mapping[str, str] | None = None,
    before: Any | None = None,
    after: Any | None = None,
) -> WorkflowStep:
    return WorkflowStep(
        workflow,
        name=name,
        message=message,
        message_from=message_from,
        params=params,
        input=input,
        reads=reads,
        requires=requires,
        out=out,
        outputs=outputs,
        routes=routes,
        route_infos=route_infos,
        route_summaries=route_summaries,
        before=before,
        after=after,
    )


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


def _normalize_simple_route_infos(
    route_infos: Mapping[str, RouteInfo | str] | None,
    *,
    route_summaries: Mapping[str, str] | None = None,
) -> dict[str, RouteInfo]:
    normalized: dict[str, RouteInfo] = {}
    for route_name, summary in dict(route_summaries or {}).items():
        normalized[route_name] = RouteInfo(summary=summary)
    for route_name, info in dict(route_infos or {}).items():
        if isinstance(info, str):
            normalized[route_name] = RouteInfo(summary=info)
            continue
        if isinstance(info, RouteInfo):
            normalized[route_name] = info
            continue
        raise TypeError("route_infos values must be RouteInfo instances or summary strings")
    return normalized


__all__ = [
    "AfterHookResult",
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
