"""Lowering helpers for branch-group composite metadata."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from botlane.core.steps import ProduceVerifyStep, Step

from .models import BranchGroupDeclarationSpec, BranchStepDeclarationSpec


def declared_internal_route_tags(declaration: object, *, step: Step) -> tuple[str, ...]:
    merged_routes: dict[str, object] = {}
    raw_routes = getattr(declaration, "routes", None)
    implicit_routes = getattr(declaration, "implicit_routes", None)
    if isinstance(raw_routes, Mapping):
        merged_routes.update(raw_routes)
    if isinstance(implicit_routes, Mapping):
        merged_routes.update(implicit_routes)
    if merged_routes:
        return tuple(merged_routes.keys())
    if isinstance(step, ProduceVerifyStep):
        return ("accepted", "needs_rework")
    return ("done",)


def build_branch_group_declaration_spec(
    *,
    name: str,
    kind: str,
    branches: tuple[BranchStepDeclarationSpec, ...],
    concurrency: int | None,
    settle: str,
    success_routes: tuple[str, ...],
    outcome: object,
    fan_in_step: Step | None,
    composite_route_tags: tuple[str, ...],
    default_chain_route: str,
    rework_chain_route: str | None = None,
) -> BranchGroupDeclarationSpec:
    return BranchGroupDeclarationSpec(
        name=name,
        kind=kind,
        branches=branches,
        concurrency=concurrency,
        settle=settle,
        success_routes=success_routes,
        outcome=outcome if callable(outcome) or isinstance(outcome, str) else None,
        fan_in_step=fan_in_step,
        composite_route_tags=composite_route_tags,
        default_chain_route=default_chain_route,
        rework_chain_route=rework_chain_route,
    )
