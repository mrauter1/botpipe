"""Typed durable checkpoints for one provider operation.

This module is the only place that interprets the journal response mapping;
callers operate on variants and serialize a complete legal state.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping

from .errors import ReplayMismatch
from .providers import ProviderResponse
from .recovery import Completed, RecoveryOutcome, Running, Stopped


class ProviderCheckpointError(ReplayMismatch):
    """A provider checkpoint cannot be interpreted safely."""


class RecoveryAction(Enum):
    USE_RESPONSE = "use_response"
    START_RETRY = "start_retry"
    ALLOW_RESOLUTION = "allow_resolution"
    BLOCK = "block"


_MISSING = object()


def _generation(record: Mapping[str, Any]) -> int:
    value = record.get("generation", 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderCheckpointError("Provider checkpoint generation is invalid")
    return value


def _request(record: Mapping[str, Any]) -> dict[str, Any]:
    value = record.get("request", _MISSING)
    if value is _MISSING:
        raise ProviderCheckpointError("Provider checkpoint request is missing")
    if type(value) is not dict:
        raise ProviderCheckpointError("Provider checkpoint request is invalid")
    allowed = {"session_id", "receipt_dir", "prompt", "artifacts", "reads",
               "operation", "provider", "instructions", "settings", "allow_commands",
               "policy"}
    unknown = set(value) - allowed
    if unknown:
        raise ProviderCheckpointError(
            "Provider checkpoint request contains unknown fields: "
            + ", ".join(sorted(unknown))
        )
    session_id = value.get("session_id")
    if "session_id" in value and session_id is not None and type(session_id) is not str:
        raise ProviderCheckpointError(
            "Provider checkpoint request session_id is invalid"
        )
    for name in ("receipt_dir", "prompt"):
        if name in value and type(value[name]) is not str:
            raise ProviderCheckpointError(
                f"Provider checkpoint request {name} is invalid"
            )
    if "artifacts" in value:
        artifacts = value["artifacts"]
        if type(artifacts) is not dict or not all(
            type(name) is str and type(path) is str for name, path in artifacts.items()
        ):
            raise ProviderCheckpointError(
                "Provider checkpoint request artifacts are invalid"
            )
    if "reads" in value and (
        type(value["reads"]) is not list
        or not all(type(path) is str for path in value["reads"])
    ):
        raise ProviderCheckpointError("Provider checkpoint request reads are invalid")
    if "operation" in value and value["operation"] not in {"generate", "query", "run"}:
        raise ProviderCheckpointError("Provider checkpoint operation is invalid")
    if "provider" in value and (type(value["provider"]) is not str or not value["provider"]):
        raise ProviderCheckpointError("Provider checkpoint backend is invalid")
    if value.get("instructions") is not None and type(value["instructions"]) is not str:
        raise ProviderCheckpointError("Provider checkpoint instructions are invalid")
    if "settings" in value and type(value["settings"]) is not dict:
        raise ProviderCheckpointError("Provider checkpoint settings are invalid")
    if "policy" in value:
        if type(value["policy"]) is not dict:
            raise ProviderCheckpointError("Provider checkpoint policy is invalid")
        from .policy import Policy

        try:
            Policy.from_dict(value["policy"])
        except (TypeError, ValueError) as exc:
            raise ProviderCheckpointError(
                "Provider checkpoint policy is invalid"
            ) from exc
    if "allow_commands" in value:
        grants = value["allow_commands"]
        if type(grants) is not list or any(
            type(argv) is not list or not argv or any(type(arg) is not str or not arg or "\x00" in arg for arg in argv)
            for argv in grants
        ):
            raise ProviderCheckpointError("Provider checkpoint command grants are invalid")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ProviderCheckpointError("Provider checkpoint request is not finite JSON") from exc
    return dict(value)


def _only(record: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = set(record) - allowed
    if unknown:
        raise ProviderCheckpointError(
            "Provider checkpoint contains unknown fields: " + ", ".join(sorted(unknown))
        )


def _response(record: Mapping[str, Any]) -> ProviderResponse:
    try:
        response = ProviderResponse(
            **{
                key: record[key]
                for key in ("text", "session_id", "usage", "metadata")
                if key in record
            }
        )
        response.to_record()
    except (TypeError, ValueError, RecursionError) as exc:
        raise ProviderCheckpointError(
            f"Provider checkpoint response is invalid: {exc}"
        ) from exc
    return response


def _artifact_resolution(record: Mapping[str, Any]) -> dict[str, Any] | None:
    value = record.get("artifact_resolution")
    if value is None:
        return None
    if type(value) is not dict or value.get("source") != "operator":
        raise ProviderCheckpointError(
            "Provider checkpoint artifact resolution is invalid"
        )
    digests = value.get("digests")
    if type(digests) is not dict or not all(
        type(name) is str and (type(digest) is str or digest is None)
        for name, digest in digests.items()
    ):
        raise ProviderCheckpointError(
            "Provider checkpoint artifact resolution digests are invalid"
        )
    if set(value) != {"source", "digests"}:
        raise ProviderCheckpointError(
            "Provider checkpoint artifact resolution contains unknown fields"
        )
    return {"source": "operator", "digests": dict(digests)}


def _repair_history(record: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    value = record.get("repairs", ())
    if type(value) not in (list, tuple):
        raise ProviderCheckpointError("Provider repair history is invalid")
    result = []
    for attempt in value:
        if type(attempt) is not dict or "repairs" in attempt:
            raise ProviderCheckpointError("Provider repair attempt is invalid")
        parsed = ProviderCheckpoint.from_record(attempt)
        if not isinstance(parsed, ValidationFailedCheckpoint):
            raise ProviderCheckpointError(
                "Provider repair history must contain rejected completed attempts"
            )
        result.append(dict(attempt))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ProviderCheckpoint:
    generation: int
    repairs: tuple[dict[str, Any], ...] = field(default_factory=tuple, kw_only=True)

    @classmethod
    def from_record(cls, record: Mapping[str, object] | None) -> ProviderCheckpoint:
        if record is None:
            record = {}
        if not isinstance(record, Mapping):
            raise ProviderCheckpointError("Provider checkpoint must be a mapping")
        raw = dict(record)
        generation = _generation(raw)
        if not raw:
            return EmptyCheckpoint(0)
        repairs = _repair_history(raw)
        history_field = {"repairs"} if "repairs" in raw else set()
        if "preparing" in raw:
            _only(raw, {"generation", "preparing", "feedback"} | history_field)
            if raw["preparing"] is not True:
                raise ProviderCheckpointError(
                    "Provider preparing checkpoint marker is invalid"
                )
            feedback = raw.get("feedback")
            if feedback is not None and type(feedback) is not str:
                raise ProviderCheckpointError(
                    "Provider repair feedback is invalid"
                )
            return PreparingCheckpoint(generation, feedback, repairs=repairs)
        if raw.get("retry_authorized") is True:
            _only(
                raw,
                {"generation", "retry_authorized", "request"} | history_field,
            )
            if generation < 1:
                raise ProviderCheckpointError(
                    "Authorized retry must name a later generation"
                )
            return RetryAuthorizedCheckpoint(
                generation, _request(raw), repairs=repairs
            )
        if "retry_authorized" in raw:
            raise ProviderCheckpointError(
                "Provider retry authorization marker is invalid"
            )
        if raw.get("not_dispatched") is True:
            _only(
                raw,
                {
                    "generation",
                    "request",
                    "not_dispatched",
                    "restoration_pending",
                    "budget_error",
                    "policy_error",
                    "cancellation_error",
                }
                | history_field,
            )
            pending = raw.get("restoration_pending")
            if type(pending) is not bool:
                raise ProviderCheckpointError("Provider restoration marker is invalid")
            errors = [
                (name, raw[name])
                for name in (
                    "budget_error",
                    "policy_error",
                    "cancellation_error",
                )
                if name in raw
            ]
            if len(errors) != 1 or type(errors[0][1]) is not str:
                raise ProviderCheckpointError(
                    "Non-dispatched checkpoint needs exactly one provider error"
                )
            return NotDispatchedCheckpoint(
                generation,
                _request(raw),
                pending,
                errors[0][0],
                errors[0][1],
                repairs=repairs,
            )
        if "not_dispatched" in raw or "restoration_pending" in raw:
            raise ProviderCheckpointError(
                "Provider non-dispatch markers are contradictory"
            )
        if "text" not in raw:
            _only(raw, {"generation", "request"} | history_field)
            return IntentCheckpoint(generation, _request(raw), repairs=repairs)

        response = _response(raw)
        request = _request(raw)
        resolution = _artifact_resolution(raw)
        common = {
            "generation",
            "request",
            "text",
            "session_id",
            "usage",
            "metadata",
            "artifact_resolution",
        } | history_field
        if "output_error" in raw:
            _only(raw, common | {"validated_value", "output_error"})
            error = raw["output_error"]
            if (
                type(error) is not dict
                or set(error) != {"message", "retryable"}
                or type(error.get("message")) is not str
                or type(error.get("retryable")) is not bool
            ):
                raise ProviderCheckpointError(
                    "Provider output failure checkpoint is invalid"
                )
            return ValidationFailedCheckpoint(
                generation=generation,
                request=request,
                response=response,
                artifact_resolution=resolution,
                output_error=dict(error),
                validated_value=raw.get("validated_value", _MISSING),
                repairs=repairs,
            )
        if "validated_value" in raw:
            _only(raw, common | {"validated_value"})
            return ValidatedCheckpoint(
                generation=generation,
                request=request,
                response=response,
                artifact_resolution=resolution,
                validated_value=raw["validated_value"],
                repairs=repairs,
            )
        _only(raw, common)
        return RespondedCheckpoint(
            generation, request, response, resolution, repairs=repairs
        )

    @property
    def attempt_generation(self) -> int:
        return self.generation

    @property
    def request_data(self) -> dict[str, Any] | None:
        return None

    def to_record(self) -> dict[str, Any]:
        raise NotImplementedError

    def _repair_record(self) -> dict[str, Any]:
        return {"repairs": [dict(attempt) for attempt in self.repairs]} if self.repairs else {}

    def has_unresolved_effects(self, *, has_writes: bool) -> bool:
        # An unfinished provider intent is conservatively effectful even if it
        # declares no files: the provider itself may have external effects.
        return True


@dataclass(frozen=True, slots=True)
class EmptyCheckpoint(ProviderCheckpoint):
    def to_record(self) -> dict[str, Any]:
        return self._repair_record()


@dataclass(frozen=True, slots=True)
class PreparingCheckpoint(ProviderCheckpoint):
    feedback: str | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "preparing": True,
            **({"feedback": self.feedback} if self.feedback is not None else {}),
            **self._repair_record(),
        }


@dataclass(frozen=True, slots=True)
class IntentCheckpoint(ProviderCheckpoint):
    request: dict[str, Any]

    @property
    def request_data(self) -> dict[str, Any]:
        return dict(self.request)

    def to_record(self) -> dict[str, Any]:
        return {
            "request": dict(self.request),
            "generation": self.generation,
            **self._repair_record(),
        }


@dataclass(frozen=True, slots=True)
class RetryAuthorizedCheckpoint(IntentCheckpoint):
    @property
    def attempt_generation(self) -> int:
        return self.generation - 1

    def to_record(self) -> dict[str, Any]:
        return {
            "retry_authorized": True,
            "generation": self.generation,
            "request": dict(self.request),
            **self._repair_record(),
        }


@dataclass(frozen=True, slots=True)
class NotDispatchedCheckpoint(IntentCheckpoint):
    restoration_pending: bool
    error_kind: str
    error: str

    def to_record(self) -> dict[str, Any]:
        return {
            "request": dict(self.request),
            "generation": self.generation,
            "not_dispatched": True,
            "restoration_pending": self.restoration_pending,
            self.error_kind: self.error,
            **self._repair_record(),
        }

    def has_unresolved_effects(self, *, has_writes: bool) -> bool:
        return self.restoration_pending


@dataclass(frozen=True, slots=True)
class RespondedCheckpoint(IntentCheckpoint):
    response: ProviderResponse
    artifact_resolution: dict[str, Any] | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            **self.response.to_record(),
            "request": dict(self.request),
            "generation": self.generation,
            **(
                {"artifact_resolution": dict(self.artifact_resolution)}
                if self.artifact_resolution is not None
                else {}
            ),
            **self._repair_record(),
        }

    def has_unresolved_effects(self, *, has_writes: bool) -> bool:
        # The durable response resolves provider dispatch. Only publication of
        # declared outputs can still affect the workspace.
        return has_writes


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidatedCheckpoint(RespondedCheckpoint):
    validated_value: Any

    def to_record(self) -> dict[str, Any]:
        return {
            **RespondedCheckpoint.to_record(self),
            "validated_value": self.validated_value,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class ValidationFailedCheckpoint(RespondedCheckpoint):
    output_error: dict[str, Any]
    validated_value: Any = _MISSING

    def to_record(self) -> dict[str, Any]:
        return {
            **RespondedCheckpoint.to_record(self),
            **(
                {"validated_value": self.validated_value}
                if self.validated_value is not _MISSING
                else {}
            ),
            "output_error": dict(self.output_error),
        }


class ProviderLifecycle:
    """Single owner for recovery and explicit-retry decisions."""

    @staticmethod
    def recovery_action(
        checkpoint: ProviderCheckpoint, outcome: RecoveryOutcome
    ) -> RecoveryAction:
        if isinstance(outcome, Completed):
            return RecoveryAction.USE_RESPONSE
        if isinstance(checkpoint, RetryAuthorizedCheckpoint) and isinstance(
            outcome, Stopped
        ):
            return RecoveryAction.START_RETRY
        return RecoveryAction.BLOCK

    @staticmethod
    def completed(
        checkpoint: ProviderCheckpoint, response: ProviderResponse
    ) -> RespondedCheckpoint:
        if isinstance(checkpoint, RespondedCheckpoint):
            return checkpoint
        request = checkpoint.request_data
        if request is None:
            raise ProviderCheckpointError(
                "Cannot complete a provider checkpoint without a request"
            )
        return RespondedCheckpoint(
            checkpoint.attempt_generation,
            request,
            response,
            repairs=checkpoint.repairs,
        )

    @staticmethod
    def reconciliation_action(outcome: RecoveryOutcome) -> RecoveryAction:
        if isinstance(outcome, Completed):
            return RecoveryAction.USE_RESPONSE
        if isinstance(outcome, Stopped):
            return RecoveryAction.ALLOW_RESOLUTION
        return RecoveryAction.BLOCK

    @staticmethod
    def authorize_retry(checkpoint: ProviderCheckpoint) -> RetryAuthorizedCheckpoint:
        request = checkpoint.request_data
        if request is None or isinstance(checkpoint, NotDispatchedCheckpoint):
            raise ProviderCheckpointError(
                "This provider checkpoint cannot authorize a retry"
            )
        if isinstance(checkpoint, RetryAuthorizedCheckpoint):
            return checkpoint
        return RetryAuthorizedCheckpoint(
            checkpoint.generation + 1,
            request,
            repairs=checkpoint.repairs,
        )

    @staticmethod
    def validation_failed(
        checkpoint: RespondedCheckpoint, *, message: str, retryable: bool
    ) -> ValidationFailedCheckpoint:
        return ValidationFailedCheckpoint(
            generation=checkpoint.generation,
            request=checkpoint.request,
            response=checkpoint.response,
            artifact_resolution=checkpoint.artifact_resolution,
            output_error={"message": message, "retryable": retryable},
            validated_value=(
                checkpoint.validated_value
                if isinstance(checkpoint, ValidatedCheckpoint)
                else _MISSING
            ),
            repairs=checkpoint.repairs,
        )

    @staticmethod
    def with_artifact_resolution(
        checkpoint: RespondedCheckpoint, digests: dict[str, str | None]
    ) -> RespondedCheckpoint:
        return replace(
            checkpoint,
            artifact_resolution={"source": "operator", "digests": dict(digests)},
        )

    @staticmethod
    def blocked_message(outcome: RecoveryOutcome) -> str:
        state = (
            "still running" if isinstance(outcome, Running) else "not confirmed stopped"
        )
        return (
            f"The provider is {state}; reconciliation is blocked. "
            f"{getattr(outcome, 'detail', None) or ''}"
        ).strip()


__all__ = [
    "EmptyCheckpoint",
    "IntentCheckpoint",
    "NotDispatchedCheckpoint",
    "PreparingCheckpoint",
    "ProviderCheckpoint",
    "ProviderCheckpointError",
    "ProviderLifecycle",
    "RecoveryAction",
    "RespondedCheckpoint",
    "RetryAuthorizedCheckpoint",
    "ValidatedCheckpoint",
    "ValidationFailedCheckpoint",
]
