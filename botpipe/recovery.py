"""Explicit native recovery outcomes.

Adapters cross this boundary with one of the variants below.  Historical
``ProviderResponse | None`` recovery values are intentionally not converted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Protocol

if TYPE_CHECKING:
    from .providers import ProviderRequest


class RecoveryOutcome:
    """Knowledge established while reconciling one provider attempt."""

    __slots__ = ()


class DurableResponse(Protocol):
    """A typed terminal value that can cross the durable recovery boundary."""

    def to_record(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Completed(RecoveryOutcome):
    """The provider has an authoritative response for the attempt."""

    response: DurableResponse
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class Stopped(RecoveryOutcome):
    """The attempt cannot continue and has no completed response."""

    detail: str | None = None


@dataclass(frozen=True, slots=True)
class Running(RecoveryOutcome):
    """The attempt is known to still be capable of effects."""

    detail: str | None = None


@dataclass(frozen=True, slots=True)
class Unknown(RecoveryOutcome):
    """Recovery could not prove whether the attempt completed or stopped."""

    detail: str | None = None


def recover_outcome(provider: Any, request: ProviderRequest) -> RecoveryOutcome:
    """Call a native recovery hook and validate its typed outcome.

    Exceptions and malformed outcomes never prove that effects stopped.  They
    become :class:`Unknown`; no legacy response/``None`` conversion exists.
    """

    # Imported lazily so providers can import the outcome classes without a
    # module cycle.
    from .providers import (
        ProviderError,
        ProviderInterruptedError,
    )

    recover = getattr(provider, "recover", None)
    if not callable(recover):
        return Unknown("provider does not implement recovery")
    try:
        value = recover(request)
    except ProviderInterruptedError as exc:
        detail = str(exc)
        if exc.process_alive is True:
            return Running(detail)
        if exc.process_alive is False:
            return Stopped(detail)
        return Unknown(detail)
    except ProviderError as exc:
        return Unknown(str(exc))
    except Exception as exc:
        return Unknown(f"recovery failed: {exc}")

    if isinstance(value, Completed):
        to_record = getattr(value.response, "to_record", None)
        if not callable(to_record):
            return Unknown(
                "provider returned Completed with a response that has no typed record"
            )
        try:
            record = to_record()
            if type(record) is not dict:
                raise TypeError("to_record() did not return a plain object")
        except (TypeError, ValueError, RecursionError) as exc:
            return Unknown(f"provider returned an invalid completed response: {exc}")
        return value
    if isinstance(value, (Stopped, Running, Unknown)):
        return value
    if isinstance(value, RecoveryOutcome):
        return Unknown(
            f"provider returned unsupported recovery outcome {type(value).__name__}"
        )
    if value is None:
        return Unknown("provider returned no typed recovery outcome")
    return Unknown(
        f"provider returned unsupported recovery result {type(value).__name__}"
    )


def cancellation_evidence(
    events: Iterable[Mapping[str, Any]],
    *,
    operation_id: str,
    identity: Mapping[str, Any] | None,
) -> RecoveryOutcome | None:
    """Return authoritative cancellation evidence for one exact attempt."""

    if identity is None:
        return None
    facts: list[tuple[str, dict[str, Any] | None]] = []
    for event in events:
        if (
            event.get("event") != "cancellation_outcome"
            or event.get("operation_id") != operation_id
        ):
            continue
        data = event.get("data")
        if not isinstance(data, Mapping):
            continue
        if data.get("attempt") != dict(identity):
            continue
        outcome = data.get("outcome")
        if outcome in {"running", "unknown"}:
            continue
        if outcome not in {"completed", "stopped"}:
            return Unknown("matching cancellation evidence is malformed")
        allowed = {"outcome", "detail", "attempt"}
        if outcome == "completed":
            allowed.add("response")
        if set(data) - allowed:
            return Unknown("matching cancellation evidence is malformed")
        detail = data.get("detail")
        if detail is not None and type(detail) is not str:
            return Unknown("matching cancellation evidence is malformed")
        response = data.get("response")
        if outcome == "completed":
            if type(response) is not dict:
                return Unknown("matching cancellation evidence is malformed")
            facts.append((outcome, response))
        else:
            if "response" in data:
                return Unknown("matching cancellation evidence is malformed")
            facts.append((outcome, None))
    if not facts:
        return None
    first = facts[0]
    if any(fact != first for fact in facts[1:]):
        return Unknown("conflicting terminal cancellation evidence")
    if first[0] == "stopped":
        return Stopped("stopped attempt recorded during cancellation")
    record = first[1]
    assert record is not None
    try:
        from .provider_checkpoints import canonical_provider_response

        response = canonical_provider_response(
            record,
            allow_mapping=True,
        )
        if response.to_record() != record:
            raise ValueError("response has unknown fields")
    except Exception as exc:
        return Unknown(f"matching cancellation evidence is invalid: {exc}")
    return Completed(response, "completed response recorded during cancellation")


__all__ = [
    "Completed",
    "DurableResponse",
    "RecoveryOutcome",
    "Running",
    "Stopped",
    "Unknown",
    "cancellation_evidence",
    "recover_outcome",
]
