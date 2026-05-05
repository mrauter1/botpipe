"""Workflow step and session declarations."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Mapping, Sequence

from .primitives import Event
from .prompts import PromptSpec
from .providers.retries import ProviderRetryPolicy
from .routes import Route
from .sessions import Continuity

if TYPE_CHECKING:
    from .artifacts import Artifact
    from .worklists import Worklist


_STEP_COUNTER = count()
_SESSION_COUNTER = count()


@dataclass(frozen=True, slots=True)
class ControlRoutes:
    """Declarative runtime control-route policy for a step."""

    question: Literal["auto", "always", "never"] = "auto"


_DEFAULT_PROVIDER_CONTROL_ROUTES = ControlRoutes(question="auto")
_DEFAULT_NON_PROVIDER_CONTROL_ROUTES = ControlRoutes(question="never")


def normalize_control_routes(
    control_routes: ControlRoutes | bool | None,
    *,
    default: ControlRoutes,
) -> ControlRoutes:
    """Normalize step control-route declarations across authoring surfaces."""

    if control_routes is None:
        return default
    if isinstance(control_routes, ControlRoutes):
        return control_routes
    if isinstance(control_routes, bool):
        return default if control_routes else ControlRoutes(question="never")
    raise TypeError("control_routes must be a ControlRoutes instance, boolean, or None")


def _normalize_route_metadata(
    route_metadata: Mapping[str, Route | str] | None,
) -> dict[str, Route]:
    normalized: dict[str, Route] = {}
    for route_name, info in dict(route_metadata or {}).items():
        if not isinstance(route_name, str) or not route_name.strip():
            raise ValueError("route metadata keys must be non-empty strings")
        if isinstance(info, str):
            normalized[route_name.strip()] = Route(summary=info)
            continue
        if isinstance(info, Route):
            normalized[route_name.strip()] = info
            continue
        raise TypeError("route metadata values must be Route instances or summary strings")
    return normalized


class Session:
    """Session slot marker."""

    __slots__ = ("name", "continuity", "open", "_order")

    def __init__(self, *, continuity: Continuity | None = None, open: bool = False) -> None:
        self.name: str | None = None
        self.continuity = continuity or Continuity.run()
        self.open = bool(open)
        self._order = next(_SESSION_COUNTER)

    def bind_name(self, name: str) -> None:
        if self.name is None:
            self.name = name
        elif self.name != name:
            raise ValueError(f"session already named {self.name!r}; cannot rename to {name!r}")

    @staticmethod
    def run(*, open: bool = False) -> "Session":
        return Session(continuity=Continuity.run(), open=open)

    @staticmethod
    def task(*, open: bool = False) -> "Session":
        return Session(continuity=Continuity.task(), open=open)

    @staticmethod
    def work_item(worklist: object | str, *, open: bool = False) -> "Session":
        return Session(continuity=Continuity.work_item(worklist), open=open)

    @staticmethod
    def fresh(*, open: bool = False) -> "Session":
        return Session(continuity=Continuity.fresh(), open=open)

    def __repr__(self) -> str:
        return f"Session(name={self.name!r}, continuity={self.continuity!r}, open={self.open!r})"


class Step:
    """Base step declaration."""

    kind = "step"
    default_control_routes = _DEFAULT_NON_PROVIDER_CONTROL_ROUTES

    def __init__(
        self,
        *,
        name: str,
        session: Session | None = None,
        scope: "Worklist | str | None" = None,
        reads: Sequence["Artifact | str | Path"] | None = None,
        requires: Sequence["Artifact | str"] | None = None,
        writes: Mapping[str, Artifact] | None = None,
        log_artifacts: Sequence[Artifact] | None = None,
        expected_output_schema: Any | None = None,
        route_metadata: Mapping[str, Route | str] | None = None,
        retry_policy: ProviderRetryPolicy | None = None,
        before: Any | None = None,
        after: Any | None = None,
        state_fields: Mapping[str, object] | None = None,
        item_state: object | None = None,
        control_routes: ControlRoutes | bool | None = None,
    ) -> None:
        self.name = name
        self.session = session
        self.scope = scope
        self.reads = tuple(reads or ())
        self.requires = tuple(requires or ())
        self.writes = dict(writes or {})
        self.log_artifacts = tuple(log_artifacts or ())
        self.expected_output_schema = expected_output_schema
        self.route_metadata = deepcopy(_normalize_route_metadata(route_metadata))
        self.retry_policy = retry_policy
        self.before = before
        self.after = after
        self.state_fields = dict(state_fields or {})
        self.item_state = item_state
        self.control_routes = normalize_control_routes(control_routes, default=self.default_control_routes)
        self._order = next(_STEP_COUNTER)
        for artifact_name, artifact in self.writes.items():
            artifact.bind_name(artifact_name)

    def __getattr__(self, item: str) -> Artifact:
        try:
            return self.writes[item]
        except KeyError as exc:
            raise AttributeError(item) from exc

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"


class ProduceVerifyStep(Step):
    """Producer/verifier step."""

    kind = "pair"
    default_control_routes = _DEFAULT_PROVIDER_CONTROL_ROUTES

    def __init__(
        self,
        *,
        name: str,
        producer: PromptSpec,
        verifier: PromptSpec,
        session: Session | None = None,
        verifier_session: Session | None = None,
        scope: "Worklist | str | None" = None,
        reads: Sequence[Artifact] | None = None,
        requires: Sequence[Artifact] | None = None,
        verifier_requires: Sequence[Artifact | str] | None = None,
        producer_writes: Mapping[str, Artifact] | None = None,
        verifier_writes: Mapping[str, Artifact] | None = None,
        log_artifacts: Sequence[Artifact] | None = None,
        expected_output_schema: Any | None = None,
        route_metadata: Mapping[str, Route | str] | None = None,
        retry_policy: ProviderRetryPolicy | None = None,
        before: Any | None = None,
        after: Any | None = None,
        before_producer: Any | None = None,
        after_producer: Any | None = None,
        before_verifier: Any | None = None,
        after_verifier: Any | None = None,
        state_fields: Mapping[str, object] | None = None,
        item_state: object | None = None,
        control_routes: ControlRoutes | bool | None = None,
    ) -> None:
        super().__init__(
            name=name,
            session=session,
            scope=scope,
            reads=reads,
            requires=requires,
            writes=_merge_pair_artifacts(producer_writes, verifier_writes),
            log_artifacts=log_artifacts,
            expected_output_schema=expected_output_schema,
            route_metadata=route_metadata,
            retry_policy=retry_policy,
            before=before,
            after=after,
            state_fields=state_fields,
            item_state=item_state,
            control_routes=control_routes,
        )
        self.producer = producer
        self.verifier = verifier
        self.verifier_session = verifier_session
        self.verifier_requires = tuple(verifier_requires or ())
        self.producer_writes = tuple(dict(producer_writes or {}).keys())
        self.verifier_writes = tuple(dict(verifier_writes or {}).keys())
        self.retry_policy = retry_policy or ProviderRetryPolicy()
        self.before_producer = before_producer if before_producer is not None else before
        self.after_producer = after_producer
        self.before_verifier = before_verifier
        self.after_verifier = after_verifier if after_verifier is not None else after


def _merge_pair_artifacts(
    producer_writes: Mapping[str, "Artifact"] | None,
    verifier_writes: Mapping[str, "Artifact"] | None,
) -> dict[str, "Artifact"]:
    merged = dict(producer_writes or {})
    for name, artifact in dict(verifier_writes or {}).items():
        if name in merged and merged[name] is not artifact:
            raise ValueError(
                f"duplicate pair-step artifact name {name!r} across producer_writes and verifier_writes"
            )
        merged[name] = artifact
    return merged


class PromptStep(Step):
    """Single provider turn."""

    kind = "llm"
    default_control_routes = _DEFAULT_PROVIDER_CONTROL_ROUTES

    def __init__(
        self,
        *,
        name: str,
        producer: PromptSpec,
        session: Session | None = None,
        scope: "Worklist | str | None" = None,
        reads: Sequence[Artifact] | None = None,
        requires: Sequence[Artifact] | None = None,
        writes: Mapping[str, Artifact] | None = None,
        log_artifacts: Sequence[Artifact] | None = None,
        expected_output_schema: Any | None = None,
        route_metadata: Mapping[str, Route | str] | None = None,
        retry_policy: ProviderRetryPolicy | None = None,
        before: Any | None = None,
        after: Any | None = None,
        state_fields: Mapping[str, object] | None = None,
        item_state: object | None = None,
        control_routes: ControlRoutes | bool | None = None,
    ) -> None:
        super().__init__(
            name=name,
            session=session,
            scope=scope,
            reads=reads,
            requires=requires,
            writes=writes,
            log_artifacts=log_artifacts,
            expected_output_schema=expected_output_schema,
            route_metadata=route_metadata,
            retry_policy=retry_policy,
            before=before,
            after=after,
            state_fields=state_fields,
            item_state=item_state,
            control_routes=control_routes,
        )
        self.producer = producer
        self.retry_policy = retry_policy or ProviderRetryPolicy()


class PythonStep(Step):
    """Pure python-step handler."""

    kind = "system"

    def __init__(
        self,
        *,
        name: str,
        session: Session | None = None,
        reads: Sequence["Artifact | str | Path"] | None = None,
        requires: Sequence["Artifact | str"] | None = None,
        writes: Mapping[str, Artifact] | None = None,
        log_artifacts: Sequence[Artifact] | None = None,
        expected_output_schema: Any | None = None,
        route_metadata: Mapping[str, Route | str] | None = None,
        handler: Any | None = None,
        retry_policy: ProviderRetryPolicy | None = None,
        before: Any | None = None,
        after: Any | None = None,
        state_fields: Mapping[str, object] | None = None,
        item_state: object | None = None,
        control_routes: ControlRoutes | bool | None = None,
    ) -> None:
        super().__init__(
            name=name,
            session=session,
            scope=None,
            reads=reads,
            requires=requires,
            writes=writes,
            log_artifacts=log_artifacts,
            expected_output_schema=expected_output_schema,
            route_metadata=route_metadata,
            retry_policy=retry_policy,
            before=before,
            after=after,
            state_fields=state_fields,
            item_state=item_state,
            control_routes=control_routes,
        )
        self.handler = handler


class ChildWorkflowStep(Step):
    """Child-workflow invocation step."""

    kind = "workflow"

    def __init__(
        self,
        *,
        name: str,
        workflow: str | type[Any],
        message: str | None = None,
        message_from: "Artifact | str | Path | None" = None,
        params: Mapping[str, object] | None = None,
        input: object | None = None,
        session: Session | None = None,
        scope: "Worklist | str | None" = None,
        reads: Sequence["Artifact | str | Path"] | None = None,
        requires: Sequence["Artifact | str"] | None = None,
        writes: Mapping[str, Artifact] | None = None,
        log_artifacts: Sequence[Artifact] | None = None,
        route_metadata: Mapping[str, Route | str] | None = None,
        retry_policy: ProviderRetryPolicy | None = None,
        before: Any | None = None,
        after: Any | None = None,
        state_fields: Mapping[str, object] | None = None,
        control_routes: ControlRoutes | bool | None = None,
    ) -> None:
        super().__init__(
            name=name,
            session=session,
            scope=scope,
            reads=reads,
            requires=requires,
            writes=writes,
            log_artifacts=log_artifacts,
            expected_output_schema=None,
            route_metadata=route_metadata,
            retry_policy=retry_policy,
            before=before,
            after=after,
            state_fields=state_fields,
            control_routes=control_routes,
        )
        self.workflow = workflow
        self.message = message
        self.message_from = message_from
        self.params = dict(params or {})
        self.input = input


class BranchGroupStep(Step):
    """Composite step that owns internal branch-group metadata."""

    kind = "branch_group"

    def __init__(
        self,
        *,
        name: str,
        branch_group: Any,
        route_metadata: Mapping[str, Route | str] | None = None,
    ) -> None:
        super().__init__(
            name=name,
            session=None,
            scope=None,
            reads=(),
            requires=(),
            writes={},
            log_artifacts=(),
            expected_output_schema=None,
            route_metadata=route_metadata,
            retry_policy=None,
            before=None,
            after=None,
            control_routes=ControlRoutes(question="never"),
        )
        self.branch_group = branch_group
