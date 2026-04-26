"""Provider retry policy and retry feedback helpers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderRetryPolicy:
    max_attempts: int = 3
    retry_provider_execution_error: bool = True
    retry_illegal_route: bool = True
    retry_invalid_payload: bool = True
    retry_missing_required_output_artifact: bool = True
    retry_invalid_output_artifact: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int):
            raise TypeError("ProviderRetryPolicy.max_attempts must be an integer.")
        if self.max_attempts < 1:
            raise ValueError("ProviderRetryPolicy.max_attempts must be >= 1.")


def build_retry_feedback(
    exc: Exception,
    *,
    step_name: str,
    attempt: int,
    max_attempts: int,
) -> str:
    """Build a deterministic markdown retry note for the next provider attempt."""

    problem = _problem_summary(exc, step_name=step_name)
    return "\n".join(
        (
            "## Retry Feedback",
            "",
            "The previous attempt could not be accepted.",
            "",
            "Attempt:",
            f"- {attempt} of {max_attempts}",
            "",
            "Problem:",
            f"- {problem}",
            "",
            "Action required:",
            "- Repair the issue using the current Runtime Step Contract.",
            "- Use only an allowed route.",
            "- Write all artifacts required by the selected route.",
        )
    )


def _problem_summary(exc: Exception, *, step_name: str) -> str:
    kind = getattr(exc, "_provider_retry_kind", None)
    if kind == "illegal_route":
        return f"The selected route was not allowed for step {step_name!r}."
    if kind == "invalid_payload":
        return "The structured output payload did not satisfy the declared output contract."
    if kind == "missing_required_output_artifact":
        artifact_name = _failure_context_field(exc, "artifact_name")
        if artifact_name:
            return f"The selected route is missing required output artifact {artifact_name!r}."
        return "The selected route is missing a required output artifact."
    if kind == "invalid_output_artifact":
        artifact_name = _failure_context_field(exc, "artifact_name")
        if artifact_name:
            return f"Output artifact {artifact_name!r} did not pass runtime validation."
        return "One or more output artifacts did not pass runtime validation."
    if kind == "provider_transport_failure":
        return "The provider transport failed before a usable response was accepted."
    if kind == "malformed_provider_output":
        return "The provider response could not be parsed into a valid workflow outcome."
    message = str(exc).strip()
    return message or f"The provider attempt for step {step_name!r} failed."


def _failure_context_field(exc: Exception, key: str) -> str | None:
    failure_context = getattr(exc, "_failure_context", None)
    if not isinstance(failure_context, dict):
        return None
    value = failure_context.get(key)
    if isinstance(value, str) and value:
        return value
    return None
