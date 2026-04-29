"""Simple workflow authoring declarations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import BaseModel

try:  # pragma: no branch - prefer installed-package imports when available
    from autoloop_v3.core import Artifact, Workflow as _StrictWorkflow
    from autoloop_v3.core.artifacts import ResolvedArtifacts
    from autoloop_v3.core.context import ChildWorkflowResult
    from autoloop_v3.core.descriptors import Param, StateVar
    from autoloop_v3.core.operations import OperationStepSpec, classify_call, execute_step_operation, llm_call
    from autoloop_v3.core.primitives import Checkpoint, Event, FAIL, FINISH, Outcome, PAUSE, SELF, SUCCESS
    from autoloop_v3.core.prompts import Prompt
    from autoloop_v3.core.routes import Route, RouteInfo
    from autoloop_v3.core.sessions import Continuity
    from autoloop_v3.core.steps import AfterHookResult
    from autoloop_v3.core.steps import Session
except ModuleNotFoundError:  # pragma: no cover - direct repo-root import fallback
    from core import Artifact, Workflow as _StrictWorkflow
    from core.artifacts import ResolvedArtifacts
    from core.context import ChildWorkflowResult
    from core.descriptors import Param, StateVar
    from core.operations import OperationStepSpec, classify_call, execute_step_operation, llm_call
    from core.primitives import Checkpoint, Event, FAIL, FINISH, Outcome, PAUSE, SELF, SUCCESS
    from core.prompts import Prompt
    from core.routes import Route, RouteInfo
    from core.sessions import Continuity
    from core.steps import AfterHookResult
    from core.steps import Session


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
        writes: Sequence[Artifact | ArtifactSpec] = (),
        out: Artifact | ArtifactSpec | None = None,
        outputs: Sequence[Artifact | ArtifactSpec] = (),
        routes: RouteMapping | None = None,
        route_infos: Mapping[str, RouteInfo | str] | None = None,
        route_summaries: Mapping[str, str] | None = None,
        before: Any | None = None,
        after: Any | None = None,
        on_route: Any | None = None,
        control_schema: Any | None = None,
        retry: Any | None = None,
        session: Any | None = None,
        control_routes: bool = True,
    ) -> None:
        super().__init__(name=name)
        self.prompt = _normalize_simple_prompt(prompt)
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.outputs = _normalize_outputs(out=out, outputs=outputs, writes=writes)
        self.writes = self.outputs
        self.routes = dict(routes or {})
        self.route_infos = _normalize_simple_route_infos(route_infos, route_summaries=route_summaries)
        self.before = before
        self.after = after
        self.on_route = on_route
        self.control_schema = control_schema
        self.retry = retry
        self.session = session
        self.control_routes = control_routes


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
        review_requires: Sequence[ArtifactInput] = (),
        writes: Sequence[Artifact | ArtifactSpec] = (),
        review_writes: Sequence[Artifact | ArtifactSpec] = (),
        out: Artifact | ArtifactSpec | None = None,
        outputs: Sequence[Artifact | ArtifactSpec] = (),
        accepted: str = "accepted",
        rework: str = "needs_rework",
        routes: RouteMapping | None = None,
        route_infos: Mapping[str, RouteInfo | str] | None = None,
        before: Any | None = None,
        after: Any | None = None,
        route_summaries: Mapping[str, str] | None = None,
        control_schema: Any | None = None,
        retry: Any | None = None,
        session: Any | None = None,
        review_session: Any | None = None,
        state: Mapping[str, Any] | None = None,
        before_do: Any | None = None,
        after_do: Any | None = None,
        before_review: Any | None = None,
        after_review: Any | None = None,
        on_route: Any | None = None,
        control_routes: bool = True,
    ) -> None:
        super().__init__(name=name)
        self.producer = _normalize_simple_prompt(producer)
        self.verifier = _normalize_simple_prompt(verifier)
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.review_requires = tuple(review_requires)
        self.outputs = _normalize_outputs(out=out, outputs=outputs, writes=writes)
        self.writes = self.outputs
        self.review_outputs = tuple(review_writes)
        self.review_writes = self.review_outputs
        self.accepted = accepted
        self.rework = rework
        self.routes = dict(routes or {})
        self.before = before
        self.after = after
        self.state = dict(state or {})
        self.before_do = before_do
        self.after_do = after_do
        self.before_review = before_review
        self.after_review = after_review
        self.on_route = on_route
        self.route_infos = _normalize_simple_route_infos(route_infos, route_summaries=route_summaries)
        self.control_schema = control_schema
        self.retry = retry
        self.session = session
        self.review_session = review_session
        self.control_routes = control_routes


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
        writes: Sequence[Artifact | ArtifactSpec] = (),
        out: Artifact | ArtifactSpec | None = None,
        outputs: Sequence[Artifact | ArtifactSpec] = (),
        routes: RouteMapping | None = None,
        route_infos: Mapping[str, RouteInfo | str] | None = None,
        route_summaries: Mapping[str, str] | None = None,
        before: Any | None = None,
        after: Any | None = None,
        on_route: Any | None = None,
        control_routes: bool = True,
    ) -> None:
        super().__init__(name=name)
        self.fn = fn
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.outputs = _normalize_outputs(out=out, outputs=outputs, writes=writes)
        self.writes = self.outputs
        self.routes = dict(routes or {})
        self.route_infos = _normalize_simple_route_infos(route_infos, route_summaries=route_summaries)
        self.before = before
        self.after = after
        self.on_route = on_route
        self.control_routes = control_routes


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
        writes: Sequence[Artifact | ArtifactSpec] = (),
        out: Artifact | ArtifactSpec | None = None,
        outputs: Sequence[Artifact | ArtifactSpec] = (),
        routes: RouteMapping | None = None,
        route_infos: Mapping[str, RouteInfo | str] | None = None,
        route_summaries: Mapping[str, str] | None = None,
        before: Any | None = None,
        after: Any | None = None,
        on_route: Any | None = None,
        control_routes: bool = True,
    ) -> None:
        super().__init__(name=name)
        self.workflow = workflow
        self.message = message
        self.message_from = message_from
        self.params = dict(params or {})
        self.input = input
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.outputs = _normalize_outputs(out=out, outputs=outputs, writes=writes)
        self.writes = self.outputs
        self.routes = dict(routes or {})
        self.route_infos = _normalize_simple_route_infos(route_infos, route_summaries=route_summaries)
        self.before = before
        self.after = after
        self.on_route = on_route
        self.control_routes = control_routes


class OperationStepDeclaration(_NamedDeclaration):
    """Simple feedforward value-producing declaration."""

    kind = "operation"

    def __init__(
        self,
        operation_kind: str,
        prompt: PromptInput,
        *,
        returns: Any = str,
        choices: Sequence[str] = (),
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        retry: int = 3,
    ) -> None:
        super().__init__(name=name)
        self.operation_kind = operation_kind
        self.prompt = _normalize_simple_prompt(prompt)
        self.returns = returns
        self.choices = _normalize_simple_choices(choices) if operation_kind == "classify" else ()
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.retry = retry
        self.control_routes = False

    def build_handler(self) -> Any:
        step_name = self.name or "<operation>"
        spec = OperationStepSpec(
            operation_kind=self.operation_kind,
            prompt=self.prompt,
            returns=self.returns,
            choices=tuple(self.choices),
            retry=self.retry,
        )

        def handler(ctx: Any) -> str:
            execute_step_operation(ctx, step_name=step_name, spec=spec)
            return "done"

        handler.__name__ = f"_operation_step_{step_name}"
        return handler


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
    writes: Sequence[Artifact | ArtifactSpec] = (),
    out: Artifact | ArtifactSpec | None = None,
    outputs: Sequence[Artifact | ArtifactSpec] = (),
    routes: RouteMapping | None = None,
    route_infos: Mapping[str, RouteInfo | str] | None = None,
    route_summaries: Mapping[str, str] | None = None,
    before: Any | None = None,
    after: Any | None = None,
    on_route: Any | None = None,
    control_schema: Any | None = None,
    retry: Any | None = None,
    session: Any | None = None,
    control_routes: bool = True,
) -> StepDeclaration:
    return StepDeclaration(
        prompt,
        name=name,
        reads=reads,
        requires=requires,
        writes=writes,
        out=out,
        outputs=outputs,
        routes=routes,
        route_infos=route_infos,
        route_summaries=route_summaries,
        before=before,
        after=after,
        on_route=on_route,
        control_schema=control_schema,
        retry=retry,
        session=session,
        control_routes=control_routes,
    )


def review_step(
    producer: PromptInput,
    verifier: PromptInput,
    *,
    name: str | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    review_requires: Sequence[ArtifactInput] = (),
    writes: Sequence[Artifact | ArtifactSpec] = (),
    review_writes: Sequence[Artifact | ArtifactSpec] = (),
    out: Artifact | ArtifactSpec | None = None,
    outputs: Sequence[Artifact | ArtifactSpec] = (),
    accepted: str = "accepted",
    rework: str = "needs_rework",
    routes: RouteMapping | None = None,
    route_infos: Mapping[str, RouteInfo | str] | None = None,
    route_summaries: Mapping[str, str] | None = None,
    before: Any | None = None,
    after: Any | None = None,
    state: Mapping[str, Any] | None = None,
    before_do: Any | None = None,
    after_do: Any | None = None,
    before_review: Any | None = None,
    after_review: Any | None = None,
    on_route: Any | None = None,
    control_schema: Any | None = None,
    retry: Any | None = None,
    session: Any | None = None,
    review_session: Any | None = None,
    control_routes: bool = True,
) -> ReviewStepDeclaration:
    return ReviewStepDeclaration(
        producer,
        verifier,
        name=name,
        reads=reads,
        requires=requires,
        review_requires=review_requires,
        writes=writes,
        review_writes=review_writes,
        out=out,
        outputs=outputs,
        accepted=accepted,
        rework=rework,
        routes=routes,
        route_infos=route_infos,
        before=before,
        after=after,
        state=state,
        before_do=before_do,
        after_do=after_do,
        before_review=before_review,
        after_review=after_review,
        on_route=on_route,
        route_summaries=route_summaries,
        control_schema=control_schema,
        retry=retry,
        session=session,
        review_session=review_session,
        control_routes=control_routes,
    )


def do_review_step(
    do: PromptInput | None = None,
    *,
    review: PromptInput | None = None,
    producer: PromptInput | None = None,
    verifier: PromptInput | None = None,
    name: str | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    review_requires: Sequence[ArtifactInput] = (),
    writes: Sequence[Artifact | ArtifactSpec] = (),
    review_writes: Sequence[Artifact | ArtifactSpec] = (),
    out: Artifact | ArtifactSpec | None = None,
    outputs: Sequence[Artifact | ArtifactSpec] = (),
    accepted: str = "accepted",
    rework: str = "needs_rework",
    routes: RouteMapping | None = None,
    route_infos: Mapping[str, RouteInfo | str] | None = None,
    route_summaries: Mapping[str, str] | None = None,
    before: Any | None = None,
    after: Any | None = None,
    state: Mapping[str, Any] | None = None,
    before_do: Any | None = None,
    after_do: Any | None = None,
    before_review: Any | None = None,
    after_review: Any | None = None,
    on_route: Any | None = None,
    control_schema: Any | None = None,
    retry: Any | None = None,
    session: Any | None = None,
    review_session: Any | None = None,
    control_routes: bool = True,
) -> ReviewStepDeclaration:
    normalized_do = do if do is not None else producer
    normalized_review = review if review is not None else verifier
    if normalized_do is None or normalized_review is None:
        raise TypeError("do_review_step() requires both do= and review= prompts")
    return ReviewStepDeclaration(
        normalized_do,
        normalized_review,
        name=name,
        reads=reads,
        requires=requires,
        review_requires=review_requires,
        writes=writes,
        review_writes=review_writes,
        out=out,
        outputs=outputs,
        accepted=accepted,
        rework=rework,
        routes=routes,
        route_infos=route_infos,
        before=before,
        after=after,
        state=state,
        before_do=before_do,
        after_do=after_do,
        before_review=before_review,
        after_review=after_review,
        on_route=on_route,
        route_summaries=route_summaries,
        control_schema=control_schema,
        retry=retry,
        session=session,
        review_session=review_session,
        control_routes=control_routes,
    )


def python_step(
    fn: Any | None = None,
    *,
    name: str | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    writes: Sequence[Artifact | ArtifactSpec] = (),
    out: Artifact | ArtifactSpec | None = None,
    outputs: Sequence[Artifact | ArtifactSpec] = (),
    routes: RouteMapping | None = None,
    route_infos: Mapping[str, RouteInfo | str] | None = None,
    route_summaries: Mapping[str, str] | None = None,
    before: Any | None = None,
    after: Any | None = None,
    on_route: Any | None = None,
    control_routes: bool = True,
) -> SystemStepDeclaration | Any:
    if fn is None:
        def decorator(inner: Any) -> SystemStepDeclaration:
            return SystemStepDeclaration(
                inner,
                name=name,
                reads=reads,
                requires=requires,
                writes=writes,
                out=out,
                outputs=outputs,
                routes=routes,
                route_infos=route_infos,
                route_summaries=route_summaries,
                before=before,
                after=after,
                on_route=on_route,
                control_routes=control_routes,
            )

        return decorator
    return SystemStepDeclaration(
        fn,
        name=name,
        reads=reads,
        requires=requires,
        writes=writes,
        out=out,
        outputs=outputs,
        routes=routes,
        route_infos=route_infos,
        route_summaries=route_summaries,
        before=before,
        after=after,
        on_route=on_route,
        control_routes=control_routes,
    )


def system_step(
    fn: Any | None = None,
    *,
    name: str | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    writes: Sequence[Artifact | ArtifactSpec] = (),
    out: Artifact | ArtifactSpec | None = None,
    outputs: Sequence[Artifact | ArtifactSpec] = (),
    routes: RouteMapping | None = None,
    route_infos: Mapping[str, RouteInfo | str] | None = None,
    route_summaries: Mapping[str, str] | None = None,
    before: Any | None = None,
    after: Any | None = None,
    on_route: Any | None = None,
    control_routes: bool = True,
) -> SystemStepDeclaration | Any:
    return python_step(
        fn,
        name=name,
        reads=reads,
        requires=requires,
        writes=writes,
        out=out,
        outputs=outputs,
        routes=routes,
        route_infos=route_infos,
        route_summaries=route_summaries,
        before=before,
        after=after,
        on_route=on_route,
        control_routes=control_routes,
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
    writes: Sequence[Artifact | ArtifactSpec] = (),
    out: Artifact | ArtifactSpec | None = None,
    outputs: Sequence[Artifact | ArtifactSpec] = (),
    routes: RouteMapping | None = None,
    route_infos: Mapping[str, RouteInfo | str] | None = None,
    route_summaries: Mapping[str, str] | None = None,
    before: Any | None = None,
    after: Any | None = None,
    on_route: Any | None = None,
    control_routes: bool = True,
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
        writes=writes,
        out=out,
        outputs=outputs,
        routes=routes,
        route_infos=route_infos,
        route_summaries=route_summaries,
        before=before,
        after=after,
        on_route=on_route,
        control_routes=control_routes,
    )


def chain(*items: ChainNode) -> FlowSpec:
    return FlowSpec(items=tuple(items))


def _normalize_outputs(
    *,
    out: Artifact | ArtifactSpec | None,
    outputs: Sequence[Artifact | ArtifactSpec],
    writes: Sequence[Artifact | ArtifactSpec],
) -> tuple[Artifact | ArtifactSpec, ...]:
    if writes and outputs:
        raise TypeError("use either writes= or outputs=, not both")
    declared = list(writes or outputs)
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


def _normalize_simple_choices(choices: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for choice in choices:
        if not isinstance(choice, str) or not choice.strip():
            raise TypeError("classification choices must be non-empty strings")
        normalized.append(choice.strip())
    if not normalized:
        raise TypeError("classification choices must not be empty")
    unique = tuple(dict.fromkeys(normalized))
    if len(unique) != len(normalized):
        raise TypeError("classification choices must not repeat")
    return unique


class _LLMOperationSurface:
    def __call__(
        self,
        prompt: PromptInput,
        *,
        returns: Any = str,
        retry: int = 3,
        provider: Any | None = None,
        prompt_registry: Any | None = None,
        context: Any | None = None,
        run_folder: Path | None = None,
    ) -> Any:
        normalized_prompt = _normalize_simple_prompt(prompt)
        return llm_call(
            normalized_prompt,
            returns=returns,
            retry=retry,
            provider=provider,
            prompt_registry=prompt_registry,
            context=context,
            run_folder=run_folder,
        )

    def step(
        self,
        *,
        prompt: PromptInput,
        returns: Any = str,
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        retry: int = 3,
    ) -> OperationStepDeclaration:
        return OperationStepDeclaration(
            "llm",
            prompt,
            returns=returns,
            name=name,
            reads=reads,
            requires=requires,
            retry=retry,
        )


class _ClassifyOperationSurface:
    def __call__(
        self,
        prompt: PromptInput,
        *,
        choices: Sequence[str],
        retry: int = 3,
        provider: Any | None = None,
        prompt_registry: Any | None = None,
        context: Any | None = None,
        run_folder: Path | None = None,
    ) -> str:
        normalized_prompt = _normalize_simple_prompt(prompt)
        return classify_call(
            normalized_prompt,
            choices=choices,
            retry=retry,
            provider=provider,
            prompt_registry=prompt_registry,
            context=context,
            run_folder=run_folder,
        )

    def step(
        self,
        *,
        prompt: PromptInput,
        choices: Sequence[str],
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        retry: int = 3,
    ) -> OperationStepDeclaration:
        return OperationStepDeclaration(
            "classify",
            prompt,
            choices=choices,
            name=name,
            reads=reads,
            requires=requires,
            retry=retry,
        )


llm = _LLMOperationSurface()
classify = _ClassifyOperationSurface()


__all__ = [
    "AfterHookResult",
    "Checkpoint",
    "ChildWorkflowResult",
    "Continuity",
    "Event",
    "FAIL",
    "FINISH",
    "Json",
    "Md",
    "Outcome",
    "PAUSE",
    "Param",
    "Prompt",
    "Raw",
    "ResolvedArtifacts",
    "Route",
    "RouteInfo",
    "SELF",
    "StateVar",
    "SUCCESS",
    "Session",
    "StrictWorkflow",
    "Text",
    "Workflow",
    "WorkflowStep",
    "classify",
    "chain",
    "do_review_step",
    "llm",
    "python_step",
    "review_step",
    "step",
    "system_step",
    "workflow_step",
]
