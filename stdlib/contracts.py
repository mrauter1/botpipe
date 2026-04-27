"""Optional route-info helper bundles for common flow patterns."""

from __future__ import annotations

try:  # pragma: no branch - supports both package and direct repo-root imports
    from ..core.routes import RouteInfo
except ImportError:  # pragma: no cover - direct repo-root import fallback
    from core.routes import RouteInfo


def review_gate_contracts(
    *,
    complete: str = "review_complete",
    rework: str = "needs_rework",
    required_artifacts: tuple[str, ...] = (),
) -> dict[str, RouteInfo]:
    """Return one explicit review gate bundle without hiding transitions."""

    return {
        complete: RouteInfo(
            summary="The review outcome is complete and ready for the next explicit transition.",
            required_outputs=required_artifacts,
        ),
        rework: RouteInfo(
            summary="The same review boundary still holds, but the work needs local repair before it can advance.",
            required_outputs=required_artifacts,
        ),
    }


def publication_gate_contracts(
    *,
    published: str = "published",
    required_artifacts: tuple[str, ...] = (),
) -> dict[str, RouteInfo]:
    """Return one minimal publication gate bundle."""

    return {
        published: RouteInfo(
            summary="Publication completed and the required receipt artifacts exist.",
            required_outputs=required_artifacts,
        )
    }


__all__ = ["publication_gate_contracts", "review_gate_contracts"]
