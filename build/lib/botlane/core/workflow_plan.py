"""Internal executable workflow plan.

Not part of the public botlane authoring API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from .identifiers import ArtifactId
from .route_contracts import RouteContract
from .step_plans import StepPlan

if TYPE_CHECKING:
    from .reference_graph import ReferenceGraph


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

    artifacts: dict[str, Any]
    artifacts_by_id: dict[ArtifactId, Any]
    artifacts_by_qualified_name: dict[str, Any]

    extensions: tuple[Any, ...]
    provider_policy: Any
    source_hash: str | None
    topology_hash: str
    reference_graph: ReferenceGraph | None = None
