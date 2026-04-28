from __future__ import annotations

import pytest

from autoloop_v3.core.providers.retries import build_retry_feedback


def _retry_error(
    kind: str,
    *,
    message: str = "provider failed",
    artifact_name: str | None = None,
    failure_context: dict[str, str] | None = None,
) -> Exception:
    error = RuntimeError(message)
    error._provider_retry_kind = kind
    context: dict[str, str] = {}
    if artifact_name is not None:
        context["artifact_name"] = artifact_name
    if failure_context is not None:
        context.update(failure_context)
    if context:
        error._failure_context = context
    return error


@pytest.mark.parametrize(
    ("error", "expected_problem"),
    [
        (_retry_error("illegal_route"), "The selected route was not allowed for step 'review'."),
        (
            _retry_error("invalid_payload"),
            "The structured output payload did not satisfy the declared output contract.",
        ),
        (
            _retry_error(
                "invalid_payload",
                failure_context={
                    "route": "question",
                    "error": "question route requires a non-empty question field",
                },
            ),
            "The selected route 'question' has an invalid payload: question route requires a non-empty question field.",
        ),
        (
            _retry_error(
                "invalid_payload",
                failure_context={
                    "route": "failed",
                    "error": "failed route requires a non-empty reason field",
                },
            ),
            "The selected route 'failed' has an invalid payload: failed route requires a non-empty reason field.",
        ),
        (
            _retry_error("missing_required_output_artifact", artifact_name="review.report"),
            "The selected route is missing required output artifact 'review.report'.",
        ),
        (
            _retry_error("invalid_output_artifact", artifact_name="review.report"),
            "Output artifact 'review.report' did not pass runtime validation.",
        ),
        (
            _retry_error("provider_transport_failure"),
            "The provider transport failed before a usable response was accepted.",
        ),
        (
            _retry_error("malformed_provider_output"),
            "The provider response could not be parsed into a valid workflow outcome.",
        ),
    ],
)
def test_build_retry_feedback_formats_specialized_retry_messages(error: Exception, expected_problem: str) -> None:
    feedback = build_retry_feedback(error, step_name="review", attempt=2, max_attempts=3)

    assert feedback.startswith("## Retry Feedback\n")
    assert "Attempt:\n- 2 of 3" in feedback
    assert f"Problem:\n- {expected_problem}" in feedback
    assert "Action required:" in feedback
    assert "- Use only an allowed route." in feedback
    assert "- If selecting `question`, include a non-empty top-level `question`." in feedback
    assert "- If selecting `blocked` or `failed`, include a concise non-empty `reason`." in feedback
    assert "- Write all artifacts required by the selected route." in feedback


def test_build_retry_feedback_falls_back_to_exception_message_or_step_name() -> None:
    explicit = build_retry_feedback(RuntimeError("custom failure"), step_name="review", attempt=1, max_attempts=3)
    blank = build_retry_feedback(RuntimeError("   "), step_name="review", attempt=1, max_attempts=3)

    assert "Problem:\n- custom failure" in explicit
    assert "Problem:\n- The provider attempt for step 'review' failed." in blank


def test_build_retry_feedback_invalid_payload_without_route_still_surfaces_specific_error() -> None:
    feedback = build_retry_feedback(
        _retry_error(
            "invalid_payload",
            failure_context={"error": "top-level payload must be an object"},
        ),
        step_name="review",
        attempt=1,
        max_attempts=3,
    )

    assert "Problem:\n- The structured output payload is invalid: top-level payload must be an object." in feedback
