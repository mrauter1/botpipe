"""Internal executable workflow plan.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel

from .artifact_plan import ArtifactSpec
from .errors import RoutingError, WorkflowCompilationError
from .identifiers import ArtifactId
from .reference_graph import ReferenceGraph
from .route_contracts import RouteContract
from .step_plans import StepPlan


@dataclass(frozen=True, slots=True)
class WorkflowPlan:
    workflow_cls: type[Any]
    workflow_name: str
    state_cls: type[Any]
    input_model: type[Any] | None
    output_model: type[Any] | None
    output_builder: Callable[..., Any] | None
    parameters_cls: type[Any] | None

    entry_step_name: str

    sessions: dict[str, Any]
    default_session_name: str
    default_session_open: bool

    worklists: dict[str, Any]

    steps: dict[str, StepPlan]
    routes: dict[str, dict[str, RouteContract]]
    global_routes: dict[str, RouteContract]

    artifacts: dict[ArtifactId, ArtifactSpec]
    public_artifacts: dict[str, ArtifactId]
    artifacts_by_qualified_name: dict[str, ArtifactId]

    extensions: tuple[Any, ...]
    provider_policy: Any
    source_hash: str | None
    topology_hash: str
    reference_graph: ReferenceGraph = field(default_factory=ReferenceGraph.empty)

    def new_state(self) -> BaseModel:
        try:
            return self.state_cls()
        except Exception as exc:
            raise WorkflowCompilationError(
                f"state model {self.state_cls.__qualname__} requires an explicit initial state"
            ) from exc

    @property
    def artifacts_by_id(self) -> dict[ArtifactId, ArtifactSpec]:
        return self.artifacts

    def artifact_spec(self, artifact_id: ArtifactId) -> ArtifactSpec:
        return self.artifacts[artifact_id]

    def artifact_spec_for_qualified_name(self, qualified_name: str) -> ArtifactSpec:
        return self.artifacts[self.artifacts_by_qualified_name[qualified_name]]

    def artifact_items(self, *, authoritative: bool = False) -> tuple[tuple[str, ArtifactSpec], ...]:
        source = self.artifacts_by_qualified_name if authoritative else self.public_artifacts
        return tuple((name, self.artifacts[artifact_id]) for name, artifact_id in source.items())

    def route(self, step_name: str, tag: str) -> RouteContract:
        step_routes = self.routes.get(step_name, {})
        route = step_routes.get(tag)
        if route is not None:
            if route.disabled:
                raise RoutingError(f"route {tag!r} is disabled for step {step_name!r}")
            return route
        route = self.global_routes.get(tag)
        if route is not None and not route.disabled:
            return route
        raise RoutingError(f"no route for step {step_name!r} and tag {tag!r}")
