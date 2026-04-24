"""Optional route-contract helper bundles for common flow patterns."""

from __future__ import annotations

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.route_contracts import RouteContract
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from core.route_contracts import RouteContract


def review_gate_contracts(
    *,
    complete: str = "review_complete",
    rework: str = "needs_rework",
    required_artifacts: tuple[str, ...] = (),
) -> dict[str, RouteContract]:
    """Return one explicit review gate bundle without hiding transitions."""

    return {
        complete: RouteContract(
            summary="The review outcome is complete and ready for the next explicit transition.",
            required_artifacts=required_artifacts,
            work_item_effect="Advances the reviewed work item once the declared evidence exists.",
        ),
        rework: RouteContract(
            summary="The same review boundary still holds, but the work needs local repair before it can advance.",
            required_artifacts=required_artifacts,
            work_item_effect="Keeps the current review boundary intact and routes back for local rework.",
        ),
    }


def publication_gate_contracts(
    *,
    published: str = "published",
    required_artifacts: tuple[str, ...] = (),
) -> dict[str, RouteContract]:
    """Return one minimal publication gate bundle."""

    return {
        published: RouteContract(
            summary="Publication completed and the required receipt artifacts exist.",
            required_artifacts=required_artifacts,
            work_item_effect="Marks the current work item as published without introducing hidden automation.",
        )
    }


__all__ = ["publication_gate_contracts", "review_gate_contracts"]
