"""Branch-group authored and compiled data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Literal

if TYPE_CHECKING:
    from autoloop.core.compiler import CompiledStep
    from autoloop.core.steps import Step


BranchGroupKind = Literal["parallel", "fan_out"]


@dataclass(frozen=True, slots=True)
class FanInHelperReference:
    """Marker for runtime-owned branch-group evidence reads."""

    helper: Literal["results", "context"]

    def __str__(self) -> str:
        return f"FanIn.{self.helper}()"


@dataclass(frozen=True, slots=True)
class BranchStepDeclarationSpec:
    """One authored internal branch execution specification."""

    name: str
    index: int
    input: Any
    step: "Step"


@dataclass(frozen=True, slots=True)
class BranchGroupDeclarationSpec:
    """Authored branch-group metadata carried by one composite step."""

    name: str
    kind: BranchGroupKind
    branches: tuple[BranchStepDeclarationSpec, ...]
    concurrency: int | None
    settle: str
    success_routes: tuple[str, ...]
    outcome: str | Callable[..., Any] | None
    fan_in_step: "Step | None"
    composite_route_tags: tuple[str, ...]
    default_chain_route: str
    rework_chain_route: str | None = None


@dataclass(frozen=True, slots=True)
class CompiledBranchStepSpec:
    """One compiled internal branch execution specification."""

    name: str
    index: int
    input: Any
    step: "CompiledStep"


@dataclass(frozen=True, slots=True)
class CompiledBranchGroupSpec:
    """Compiled branch-group metadata carried by one composite step."""

    name: str
    kind: BranchGroupKind
    branches: tuple[CompiledBranchStepSpec, ...]
    concurrency: int | None
    settle: str
    success_routes: tuple[str, ...]
    outcome: str | Callable[..., Any] | None
    fan_in_step: "CompiledStep | None"
    composite_route_tags: tuple[str, ...]
    default_chain_route: str
    rework_chain_route: str | None = None
