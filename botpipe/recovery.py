"""Explicit provider recovery outcomes and legacy adapter normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .providers import ProviderRequest, ProviderResponse


class RecoveryOutcome:
    """Knowledge established while reconciling one provider attempt."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class Completed(RecoveryOutcome):
    """The provider has an authoritative response for the attempt."""

    response: ProviderResponse
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
    """Call a provider's recovery hook and normalize its compatibility surface.

    Third-party providers may still implement the historical contract of
    returning ``ProviderResponse | None`` or raising
    ``ProviderInterruptedError``. Absence of a response and generic failures do
    not prove that effects stopped, so both normalize to :class:`Unknown`.
    """

    # Imported lazily so providers can import the outcome classes without a
    # module cycle.
    from .providers import (
        ProviderError,
        ProviderInterruptedError,
        ProviderResponse,
        _response_record,
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

    if isinstance(value, ProviderResponse):
        value = Completed(value, "legacy provider returned a response")
    if isinstance(value, Completed):
        if not isinstance(value.response, ProviderResponse):
            return Unknown(
                "provider returned Completed with an invalid response object"
            )
        try:
            _response_record(value.response)
        except (TypeError, ValueError) as exc:
            return Unknown(f"provider returned an invalid completed response: {exc}")
        return value
    if isinstance(value, (Stopped, Running, Unknown)):
        return value
    if isinstance(value, RecoveryOutcome):
        return Unknown(
            f"provider returned unsupported recovery outcome {type(value).__name__}"
        )
    if value is None:
        return Unknown("legacy provider returned no recovery result")
    return Unknown(
        f"provider returned unsupported recovery result {type(value).__name__}"
    )


__all__ = [
    "Completed",
    "RecoveryOutcome",
    "Running",
    "Stopped",
    "Unknown",
    "recover_outcome",
]
