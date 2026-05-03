"""Simple workflow authoring declarations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import BaseModel

from autoloop.core import Artifact
from autoloop.core.context import context_runtime
from autoloop.core.effects import Effects, WorklistEffect
from autoloop.core.operations import OperationStepSpec, classify_call, execute_step_operation, llm_call
from autoloop.core.primitives import AWAIT_INPUT, Event, FAIL, FINISH, Goto, Outcome, RequestInput, SELF, Fail
from autoloop.core.prompts import Prompt
from autoloop.core.routes import Route
from autoloop.core.sessions import Continuity
from autoloop.core.step_state import StateVar
from autoloop.core.steps import ControlRoutes, Session, normalize_control_routes
from autoloop.core.validation_helpers import ValidationResult, render_validation_feedback
from autoloop.core.worklists import Worklist


PromptInput = str | Path | Prompt
RouteMapping = Mapping[str, Route | object]


class EmptyState(BaseModel):
    """Default state model for workflows that do not declare ``State``."""


class EmptyParams(BaseModel):
    """Default params model for workflows that do not declare ``Params``."""


class Workflow:
    """Simple public authoring surface."""

    extensions: tuple[object, ...] = ()
    Params = EmptyParams
    State = EmptyState


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    """Simple authoring artifact declaration with optional inferred step-local paths."""

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
    default_chain_route = "done"

    def __init__(self, *, name: str | None = None) -> None:
        self.name = name
        self._explicit_name = name

    def __set_name__(self, owner: type[object], attr_name: str) -> None:
        if self.name is None:
            self.name = attr_name

    def __getattr__(self, item: str) -> Artifact | ArtifactSpec:
        for collection_name in ("writes", "verifier_writes"):
            try:
                artifacts = object.__getattribute__(self, collection_name)
            except AttributeError:
                artifacts = ()
            for artifact in artifacts:
                if getattr(artifact, "name", None) == item:
                    return artifact
        raise AttributeError(item)


class StepDeclaration(_NamedDeclaration):
    """Simple step declaration lowered during workflow definition discovery."""

    kind = "step"

    def __init__(
        self,
        prompt: PromptInput,
        *,
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        writes: Sequence[Artifact | ArtifactSpec] = (),
        scope: Worklist | str | None = None,
        item_state: type[BaseModel] | Mapping[str, StateVar] | None = None,
        routes: RouteMapping | None = None,
        before: Any | None = None,
        after: Any | None = None,
        control_schema: Any | None = None,
        retry: Any | None = None,
        session: Any | None = None,
        control_routes: ControlRoutes | bool = True,
    ) -> None:
        super().__init__(name=name)
        self.prompt = _normalize_simple_prompt(prompt)
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.writes = _normalize_writes(writes)
        self.scope = scope
        self.item_state = item_state
        self.routes = dict(routes or {})
        self.before = before
        self.after = after
        self.control_schema = control_schema
        self.retry = retry
        self.session = session
        self.control_routes = normalize_control_routes(
            control_routes,
            default=ControlRoutes(question="auto"),
        )


class ProduceVerifyStepDeclaration(_NamedDeclaration):
    """Simple producer/verifier declaration lowered during workflow definition discovery."""

    kind = "produce_verify"
    default_chain_route = "accepted"

    def __init__(
        self,
        producer_prompt: PromptInput,
        verifier_prompt: PromptInput,
        *,
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        verifier_reads: Sequence[ArtifactInput] = (),
        verifier_requires: Sequence[ArtifactInput] = (),
        producer_writes: Sequence[Artifact | ArtifactSpec] = (),
        verifier_writes: Sequence[Artifact | ArtifactSpec] = (),
        scope: Worklist | str | None = None,
        routes: RouteMapping | None = None,
        state: type[BaseModel] | Mapping[str, StateVar] | None = None,
        item_state: type[BaseModel] | Mapping[str, StateVar] | None = None,
        before_producer: Any | None = None,
        after_producer: Any | None = None,
        before_verifier: Any | None = None,
        after_verifier: Any | None = None,
        control_schema: Any | None = None,
        retry: Any | None = None,
        session: Any | None = None,
        verifier_session: Any | None = None,
        control_routes: ControlRoutes | bool = True,
    ) -> None:
        super().__init__(name=name)
        self.producer_prompt = _normalize_simple_prompt(producer_prompt)
        self.verifier_prompt = _normalize_simple_prompt(verifier_prompt)
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.verifier_reads = tuple(verifier_reads)
        self.verifier_requires = tuple(verifier_requires)
        self.writes = _normalize_writes(producer_writes)
        self.verifier_writes = _normalize_writes(verifier_writes)
        self.scope = scope
        self.routes = dict(routes or {})
        self.state = state
        self.item_state = item_state
        self.before_producer = before_producer
        self.after_producer = after_producer
        self.before_verifier = before_verifier
        self.after_verifier = after_verifier
        self.control_schema = control_schema
        self.retry = retry
        self.session = session
        self.verifier_session = verifier_session
        self.control_routes = normalize_control_routes(
            control_routes,
            default=ControlRoutes(question="auto"),
        )


class PythonStepDeclaration(_NamedDeclaration):
    """Simple python-step declaration lowered during workflow definition discovery."""

    kind = "python"

    def __init__(
        self,
        fn: Any,
        *,
        name: str | None = None,
        reads: Sequence[ArtifactInput] = (),
        requires: Sequence[ArtifactInput] = (),
        writes: Sequence[Artifact | ArtifactSpec] = (),
        routes: RouteMapping | None = None,
        before: Any | None = None,
        after: Any | None = None,
        control_routes: ControlRoutes | bool = True,
    ) -> None:
        super().__init__(name=name)
        self.fn = fn
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.writes = _normalize_writes(writes)
        self.routes = dict(routes or {})
        self.before = before
        self.after = after
        self.control_routes = normalize_control_routes(
            control_routes,
            default=ControlRoutes(question="never"),
        )


class _WorkflowStepDeclaration(_NamedDeclaration):
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
        routes: RouteMapping | None = None,
        before: Any | None = None,
        after: Any | None = None,
        control_routes: ControlRoutes | bool = True,
    ) -> None:
        super().__init__(name=name)
        self.workflow = workflow
        self.message = message
        self.message_from = message_from
        self.params = dict(params or {})
        self.input = input
        self.reads = tuple(reads)
        self.requires = tuple(requires)
        self.writes = _normalize_writes(writes)
        self.routes = dict(routes or {})
        self.before = before
        self.after = after
        self.control_routes = normalize_control_routes(
            control_routes,
            default=ControlRoutes(question="never"),
        )


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
        self.control_routes = ControlRoutes(question="never")

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


def step(
    prompt: PromptInput,
    *,
    name: str | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    writes: Sequence[Artifact | ArtifactSpec] = (),
    scope: Worklist | str | None = None,
    item_state: type[BaseModel] | Mapping[str, StateVar] | None = None,
    routes: RouteMapping | None = None,
    before: Any | None = None,
    after: Any | None = None,
    control_schema: Any | None = None,
    retry: Any | None = None,
    session: Any | None = None,
    control_routes: ControlRoutes | bool = True,
) -> StepDeclaration:
    return StepDeclaration(
        prompt,
        name=name,
        reads=reads,
        requires=requires,
        writes=writes,
        scope=scope,
        item_state=item_state,
        routes=routes,
        before=before,
        after=after,
        control_schema=control_schema,
        retry=retry,
        session=session,
        control_routes=control_routes,
    )


def produce_verify_step(
    *,
    producer_prompt: PromptInput,
    verifier_prompt: PromptInput,
    name: str | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    verifier_reads: Sequence[ArtifactInput] = (),
    verifier_requires: Sequence[ArtifactInput] = (),
    producer_writes: Sequence[Artifact | ArtifactSpec] = (),
    verifier_writes: Sequence[Artifact | ArtifactSpec] = (),
    scope: Worklist | str | None = None,
    routes: RouteMapping | None = None,
    state: type[BaseModel] | Mapping[str, StateVar] | None = None,
    item_state: type[BaseModel] | Mapping[str, StateVar] | None = None,
    before_producer: Any | None = None,
    after_producer: Any | None = None,
    before_verifier: Any | None = None,
    after_verifier: Any | None = None,
    control_schema: Any | None = None,
    retry: Any | None = None,
    session: Any | None = None,
    verifier_session: Any | None = None,
    control_routes: ControlRoutes | bool = True,
) -> ProduceVerifyStepDeclaration:
    return ProduceVerifyStepDeclaration(
        producer_prompt,
        verifier_prompt,
        name=name,
        reads=reads,
        requires=requires,
        verifier_reads=verifier_reads,
        verifier_requires=verifier_requires,
        producer_writes=producer_writes,
        verifier_writes=verifier_writes,
        scope=scope,
        routes=routes,
        state=state,
        item_state=item_state,
        before_producer=before_producer,
        after_producer=after_producer,
        before_verifier=before_verifier,
        after_verifier=after_verifier,
        control_schema=control_schema,
        retry=retry,
        session=session,
        verifier_session=verifier_session,
        control_routes=control_routes,
    )


def python_step(
    fn: Any | None = None,
    *,
    name: str | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    writes: Sequence[Artifact | ArtifactSpec] = (),
    routes: RouteMapping | None = None,
    before: Any | None = None,
    after: Any | None = None,
    control_routes: ControlRoutes | bool = True,
) -> PythonStepDeclaration | Any:
    if fn is None:
        def decorator(inner: Any) -> PythonStepDeclaration:
            return PythonStepDeclaration(
                inner,
                name=name,
                reads=reads,
                requires=requires,
                writes=writes,
                routes=routes,
                before=before,
                after=after,
                control_routes=control_routes,
            )

        return decorator
    return PythonStepDeclaration(
        fn,
        name=name,
        reads=reads,
        requires=requires,
        writes=writes,
        routes=routes,
        before=before,
        after=after,
        control_routes=control_routes,
    )


def validation_step(
    fn: Any | None = None,
    *,
    name: str | None = None,
    feedback: Artifact | ArtifactSpec,
    success: str = "done",
    repair: str = "repair",
    failed: object | None = None,
    reads: Sequence[ArtifactInput] = (),
    requires: Sequence[ArtifactInput] = (),
    writes: Sequence[Artifact | ArtifactSpec] = (),
    routes: RouteMapping | None = None,
    before: Any | None = None,
    after: Any | None = None,
    control_routes: ControlRoutes | bool = True,
) -> PythonStepDeclaration | Any:
    combined_writes = tuple(dict.fromkeys((*writes, feedback)))
    implicit_routes = {"failed": failed} if failed is not None else {}

    def decorator(inner: Any) -> PythonStepDeclaration:
        step_name = name or getattr(inner, "__name__", "validation")

        def handler(ctx):
            try:
                result = inner(ctx)
            except Exception as exc:
                if failed is None:
                    raise
                return Event("failed", reason=f"{type(exc).__name__}: {exc}")
            if not isinstance(result, ValidationResult):
                raise TypeError(f"validation_step {step_name!r} must return ValidationResult")
            runtime = context_runtime(ctx)
            if result.ok:
                runtime.emit_runtime_event(
                    "validation_step_passed",
                    feedback_artifact=None,
                    message=None,
                    details=[],
                )
                return Event(success)
            if ctx.artifacts is None:
                raise RuntimeError("validation_step requires runtime artifact handles")
            feedback_name = _artifact_reference_name(feedback)
            feedback_handle = getattr(ctx.artifacts, feedback_name)
            feedback_handle.write_text(render_validation_feedback(result))
            runtime.emit_runtime_event(
                "validation_step_failed_repairable",
                feedback_artifact=str(feedback_handle.path),
                message=result.message,
                details=list(result.details),
            )
            return Event(
                repair,
                reason=result.message,
                handoff=f"Review feedback artifact: {feedback_handle.path}",
            )

        declaration = PythonStepDeclaration(
            handler,
            name=name,
            reads=reads,
            requires=requires,
            writes=combined_writes,
            routes=routes,
            before=before,
            after=after,
            control_routes=control_routes,
        )
        setattr(declaration, "implicit_routes", dict(implicit_routes))
        return declaration

    if fn is None:
        return decorator
    return decorator(fn)


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
    routes: RouteMapping | None = None,
    before: Any | None = None,
    after: Any | None = None,
    control_routes: ControlRoutes | bool = True,
) -> _WorkflowStepDeclaration:
    return _WorkflowStepDeclaration(
        workflow,
        name=name,
        message=message,
        message_from=message_from,
        params=params,
        input=input,
        reads=reads,
        requires=requires,
        writes=writes,
        routes=routes,
        before=before,
        after=after,
        control_routes=control_routes,
    )


def _normalize_writes(
    writes: Sequence[Artifact | ArtifactSpec],
) -> tuple[Artifact | ArtifactSpec, ...]:
    return tuple(writes)


def _artifact_reference_name(reference: Artifact | ArtifactSpec) -> str:
    name = getattr(reference, "name", None)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("validation_step feedback artifacts must have a stable name")
    return name.strip()


def _normalize_simple_prompt(prompt: PromptInput) -> Prompt:
    if isinstance(prompt, Prompt):
        return prompt
    if isinstance(prompt, Path):
        return Prompt.file(prompt)
    if isinstance(prompt, str):
        return Prompt.inline(prompt)
    raise TypeError(f"unsupported prompt type: {type(prompt)!r}")


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


class LLMOperation:
    """Public LLM operation surface for inline calls and operation steps."""

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

    def __repr__(self) -> str:
        return "LLMOperation()"


class ClassifyOperation:
    """Public classification operation surface for inline calls and operation steps."""

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

    def __repr__(self) -> str:
        return "ClassifyOperation()"


llm = LLMOperation()
classify = ClassifyOperation()


__all__ = [
    "AWAIT_INPUT",
    "Continuity",
    "Effects",
    "Event",
    "FAIL",
    "Fail",
    "FINISH",
    "Goto",
    "Json",
    "LLMOperation",
    "Md",
    "Outcome",
    "Prompt",
    "Raw",
    "RequestInput",
    "Route",
    "SELF",
    "Session",
    "StateVar",
    "Text",
    "ValidationResult",
    "Workflow",
    "WorklistEffect",
    "Worklist",
    "ClassifyOperation",
    "classify",
    "llm",
    "produce_verify_step",
    "python_step",
    "step",
    "validation_step",
    "workflow_step",
]
