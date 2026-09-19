from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Callable

import pytest

from botpipe.core.branch_groups.manifest import BranchManifest, render_branch_group_context
from botpipe.core.branch_groups.outcomes import select_branch_group_outcome
from botpipe.core.branch_groups.results import BranchResult, BranchStatus
from botpipe.core.errors import WorkflowExecutionError
from botpipe.core.primitives import Event


def _branch(
    name: str,
    index: int,
    status: BranchStatus,
    *,
    route: str | None = None,
    runtime_control: str | None = None,
    reason: str | None = None,
    question: str | None = None,
    error: dict[str, Any] | None = None,
) -> BranchResult:
    return BranchResult(
        name=name,
        index=index,
        input={"area": name},
        step_name=f"{name}_review",
        status=status,
        route=route,
        destination="publish" if status == "completed" else None,
        runtime_control=runtime_control,
        reason=reason,
        question=question,
        artifacts=(),
        raw_output_path=None,
        raw_output_paths={},
        provider_session=None,
        provider_sessions={},
        error=error,
        started_at="2026-05-09T08:00:00+00:00",
        finished_at="2026-05-09T08:00:01+00:00",
        duration_ms=1000,
        usage={},
        cancellation_requested=status == "cancelled",
        cancellation_completed=status == "cancelled",
        cancellation_supported=True,
    )


def _manifest(*branches: BranchResult) -> BranchManifest:
    return BranchManifest(
        schema="botpipe.branch_results/v1",
        kind="parallel",
        name="reviews",
        started_at="2026-05-09T08:00:00+00:00",
        finished_at="2026-05-09T08:00:01+00:00",
        duration_ms=1000,
        concurrency=5,
        settle="wait_all",
        success_routes=("done",),
        branches=branches,
    )


def _spec(outcome: str | Callable[..., object]) -> SimpleNamespace:
    return SimpleNamespace(name="reviews", success_routes=("done",), outcome=outcome)


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        (
            "all_done",
            Event(
                "question",
                reason="One or more branches need input.",
                question="cost: Approve cost review?",
            ),
        ),
        (
            "all_settled",
            Event(
                "question",
                reason="One or more branches need input.",
                question="cost: Approve cost review?",
            ),
        ),
        ("any_done", Event("done")),
    ],
)
def test_each_builtin_policy_is_equivalent_for_typed_and_mapping_manifests(
    policy: str,
    expected: Event,
) -> None:
    manifest = _manifest(
        _branch("security", 0, "completed", route="done"),
        _branch(
            "cost",
            1,
            "needs_input",
            runtime_control="request_input",
            reason="Awaiting reviewer input.",
            question="Approve cost review?",
        ),
    )

    typed_event = select_branch_group_outcome(_spec(policy), manifest, context=None)
    mapping_event = select_branch_group_outcome(_spec(policy), manifest.to_dict(), context=None)

    assert typed_event == mapping_event == expected


def test_mixed_outcomes_preserve_policy_priority_and_ordered_partial_diagnostics() -> None:
    mixed = _manifest(
        _branch("completed", 0, "completed", route="done"),
        _branch("failed", 1, "failed", reason="Provider failed."),
        _branch(
            "needs",
            2,
            "needs_input",
            runtime_control="request_input",
            question="Choose a budget.",
        ),
        _branch(
            "cancelled",
            3,
            "cancelled",
            runtime_control="cancelled_by_peer",
            reason="Cancelled after fail-fast.",
        ),
        _branch("skipped", 4, "skipped", reason="Not scheduled."),
    )

    assert select_branch_group_outcome(_spec("any_done"), mixed, context=None) == Event("done")
    for policy in ("all_done", "all_settled"):
        assert select_branch_group_outcome(_spec(policy), mixed, context=None) == Event(
            "question",
            reason="One or more branches need input.",
            question="needs: Choose a budget.",
        )

    non_success = _manifest(
        _branch("completed", 0, "completed", route="review"),
        _branch("failed", 1, "failed", reason="Provider failed."),
        _branch(
            "cancelled",
            2,
            "cancelled",
            runtime_control="cancelled_by_peer",
            reason="Cancelled after fail-fast.",
        ),
        _branch("skipped", 3, "skipped", reason="Not scheduled."),
    )
    expected_reason = (
        "Branch group settled without full success: "
        "completed=completed/review, failed=failed/none, "
        "cancelled=cancelled/cancelled_by_peer, skipped=skipped/none"
    )

    assert select_branch_group_outcome(_spec("all_done"), non_success.to_dict(), context=None) == Event(
        "partial",
        reason=expected_reason,
    )
    assert select_branch_group_outcome(_spec("all_settled"), non_success, context=None) == Event(
        "partial",
        reason=expected_reason,
    )
    assert select_branch_group_outcome(_spec("any_done"), non_success, context=None) == Event(
        "partial",
        reason=expected_reason,
    )


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        ("all_done", Event("done")),
        ("all_settled", Event("done")),
        ("any_done", Event("partial", reason="Branch group settled without full success: ")),
    ],
)
def test_empty_branch_collection_preserves_existing_all_and_any_behavior(policy: str, expected: Event) -> None:
    empty = _manifest()

    assert select_branch_group_outcome(_spec(policy), empty, context=None) == expected
    assert select_branch_group_outcome(_spec(policy), empty.to_dict(), context=None) == expected


def test_custom_outcome_adapter_supplies_exact_arguments_for_supported_signatures() -> None:
    manifest = _manifest(_branch("security", 0, "completed", route="done"))
    context = object()
    calls: list[tuple[str, tuple[object, ...]]] = []

    def zero() -> Event:
        calls.append(("zero", ()))
        return Event("done")

    def one(payload: object) -> Event:
        calls.append(("one", (payload,)))
        return Event("done")

    def two(payload: object, received_context: object) -> Event:
        calls.append(("two", (payload, received_context)))
        return Event("done")

    def optional_third(payload: object, received_context: object, third: object = "default") -> Event:
        calls.append(("optional_third", (payload, received_context, third)))
        return Event("done")

    def variadic(*args: object) -> Event:
        calls.append(("variadic", args))
        return Event("done")

    for callback in (zero, one, two, optional_third, variadic):
        assert select_branch_group_outcome(_spec(callback), manifest, context=context) == Event("done")

    payload = manifest.to_dict()
    assert calls == [
        ("zero", ()),
        ("one", (payload,)),
        ("two", (payload, context)),
        ("optional_third", (payload, context, "default")),
        ("variadic", (payload, context)),
    ]


def test_custom_outcome_payload_and_context_are_equivalent_for_both_manifest_forms() -> None:
    manifest = _manifest(_branch("security", 0, "completed", route="done"))
    context = object()
    calls: list[tuple[object, object]] = []

    def aggregate(payload: object, received_context: object) -> Event:
        calls.append((payload, received_context))
        return Event("done")

    select_branch_group_outcome(_spec(aggregate), manifest, context=context)
    select_branch_group_outcome(_spec(aggregate), manifest.to_dict(), context=context)

    assert calls[0][0] == calls[1][0] == manifest.to_dict()
    assert isinstance(calls[0][0], dict)
    assert not isinstance(calls[0][0], BranchManifest)
    assert calls[0][1] is calls[1][1] is context


def test_custom_outcome_with_required_third_parameter_keeps_normal_python_type_error() -> None:
    manifest = _manifest(_branch("security", 0, "completed", route="done"))

    def required_third(payload: object, context: object, third: object) -> Event:
        return Event("done")

    with pytest.raises(TypeError, match="third"):
        select_branch_group_outcome(_spec(required_third), manifest, context=object())


def test_custom_non_event_and_unknown_policy_keep_existing_diagnostics() -> None:
    manifest = _manifest(_branch("security", 0, "completed", route="done"))

    with pytest.raises(
        WorkflowExecutionError,
        match="^branch group 'reviews' custom outcome must return botpipe\\.core\\.primitives\\.Event$",
    ):
        select_branch_group_outcome(_spec(lambda: "done"), manifest, context=None)

    with pytest.raises(
        WorkflowExecutionError,
        match="^branch group 'reviews' uses unsupported outcome policy 'unknown'$",
    ):
        select_branch_group_outcome(_spec("unknown"), manifest.to_dict(), context=None)


def test_mapping_manifest_error_rendering_matches_typed_rendering_and_sections() -> None:
    manifest = _manifest(
        _branch(
            "security",
            0,
            "failed",
            reason="Security review failed.",
            error={"type": "ProviderError", "message": "provider unavailable"},
        )
    )

    typed_text = render_branch_group_context(manifest)
    mapping_text = render_branch_group_context(manifest.to_dict())

    assert mapping_text == typed_text
    assert "## Completion Summary" in mapping_text
    assert "## Failure Summary" in mapping_text
    assert "- security: ProviderError: provider unavailable" in mapping_text
    assert "## Branch: security" in mapping_text
    assert "- Error summary:\n  - ProviderError: provider unavailable" in mapping_text
