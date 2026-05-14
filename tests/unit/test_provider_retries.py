from __future__ import annotations

import pytest

from botpipe.core.errors import FailureContext, ProviderExecutionError, exception_failure_context
from botpipe.core.providers.parsing import parse_outcome_json
from botpipe.core.providers.retries import build_retry_feedback


def _retry_error(
    kind: str,
    *,
    message: str = "provider failed",
    artifact_name: str | None = None,
    failure_context: dict[str, object] | None = None,
) -> Exception:
    context: dict[str, object] = {}
    if artifact_name is not None:
        context["artifact_name"] = artifact_name
    if failure_context is not None:
        context.update(failure_context)
    return ProviderExecutionError(
        message,
        retry_kind=kind,
        failure_context=FailureContext(kind=kind, step_name="review", details=context) if context else None,
    )


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
    assert "- If selecting a question-style route, include non-empty `outcome.route_fields.questions`." in feedback
    assert "- If selecting `blocked` or `failed`, include a concise non-empty `reason`." not in feedback
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


def test_build_retry_feedback_malformed_output_includes_json_diagnostics_and_actual_schema() -> None:
    response_schema = {
        "type": "object",
        "properties": {
            "outcome": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "enum": ["accepted", "needs_rework"]},
                    "payload": {"type": "object"},
                    "route_fields": {"type": "object"},
                },
            }
        },
    }
    feedback = build_retry_feedback(
        _retry_error(
            "malformed_provider_output",
            message="provider returned malformed outcome JSON: Expecting ',' delimiter",
            failure_context={
                "error": "provider returned malformed outcome JSON: Expecting ',' delimiter",
                "json_error_message": "Expecting ',' delimiter",
                "json_error_line": 1,
                "json_error_column": 61,
                "json_error_position": 60,
                "json_error_excerpt": '{"outcome":{"tag":"accepted","payload":{},"route_fields":{}} ```',
            },
        ),
        step_name="review",
        attempt=2,
        max_attempts=3,
        response_schema=response_schema,
    )

    assert (
        "Problem:\n"
        "- The provider response could not be parsed into a valid workflow outcome: "
        "provider returned malformed outcome JSON: Expecting ',' delimiter."
    ) in feedback
    assert "Diagnostics:" in feedback
    assert "- JSON parser error: Expecting ',' delimiter at line 1, column 61, char 60." in feedback
    assert "- Output near parse failure:" in feedback
    assert (
        '````text\n{"outcome":{"tag":"accepted","payload":{},"route_fields":{}} ```\n````'
    ) in feedback
    assert "- Return one complete JSON object only; make sure all braces and brackets are balanced." in feedback
    assert "Expected outcome schema:" in feedback
    assert '"enum": [' in feedback
    assert '"needs_rework"' in feedback
    assert "Canonical outcome envelope:" not in feedback


def test_build_retry_feedback_malformed_output_can_include_canonical_envelope_without_schema() -> None:
    feedback = build_retry_feedback(
        _retry_error(
            "malformed_provider_output",
            message="provider returned malformed outcome JSON: Expecting ',' delimiter",
            failure_context={"error": "provider returned malformed outcome JSON: Expecting ',' delimiter"},
        ),
        step_name="review",
        attempt=2,
        max_attempts=3,
        include_outcome_envelope=True,
    )

    assert "Canonical outcome envelope:" in feedback
    assert "Expected outcome schema:" not in feedback
    assert '"outcome"' in feedback
    assert '"route_fields"' in feedback


def test_build_retry_feedback_malformed_output_omits_outcome_guidance_when_not_requested() -> None:
    feedback = build_retry_feedback(
        _retry_error("malformed_provider_output", message="provider returned unusable JSONL output"),
        step_name="draft",
        attempt=2,
        max_attempts=3,
    )

    assert "Expected outcome schema:" not in feedback
    assert "Canonical outcome envelope:" not in feedback


def test_parse_outcome_json_malformed_error_keeps_decoder_details_for_retry_feedback() -> None:
    raw = '{"outcome":{"tag":"accepted","payload":{},"route_fields":{}}'

    with pytest.raises(ProviderExecutionError, match="malformed outcome JSON") as exc_info:
        parse_outcome_json(raw)

    failure_context = exception_failure_context(exc_info.value)
    assert failure_context is not None
    assert failure_context.details["json_error_message"] == "Expecting ',' delimiter"
    assert failure_context.details["json_error_line"] == 1
    assert failure_context.details["json_error_column"] == 61
    assert failure_context.details["json_error_position"] == 60
    assert failure_context.details["json_error_excerpt"] == raw
    assert failure_context.details["provider_failure_stage"] == "outcome_contract"
