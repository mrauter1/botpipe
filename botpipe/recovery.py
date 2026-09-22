"""Explicit native recovery outcomes.

Adapters cross this boundary with one of the variants below.  Historical
``ProviderResponse | None`` recovery values are intentionally not converted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

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


__all__ = [
    "Completed",
    "DurableResponse",
    "RecoveryOutcome",
    "Running",
    "Stopped",
    "Unknown",
    "recover_outcome",
]
