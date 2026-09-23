from __future__ import annotations

from pathlib import Path

import pytest

from botpipe.policy import Policy
from botpipe.providers import (
    FakeProvider,
    ProviderError,
    ProviderInterruptedError,
    ProviderRequest,
    ProviderResponse,
)
from botpipe.recovery import (
    Completed,
    RecoveryOutcome,
    Running,
    Stopped,
    Unknown,
    recover_outcome,
)


def request(tmp_path: Path, *, attempt: int = 1) -> ProviderRequest:
    return ProviderRequest(
        operation_id="run:scope:1",
        prompt="work",
        workspace=tmp_path,
        session_id=None,
        output_schema=None,
        policy=Policy(),
        artifacts={},
        receipt_dir=tmp_path / "receipts",
        timeout=2,
        attempt=attempt,
    )


class LegacyProvider:
    name = "legacy"

    def __init__(self, result: object) -> None:
        self.result = result

    def recover(self, request: ProviderRequest) -> object:
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


@pytest.mark.parametrize(
    ("result", "outcome_type"),
    [
        (None, Unknown),
        (ProviderError("transport failed"), Unknown),
        (RuntimeError("adapter failed"), Unknown),
        (ProviderInterruptedError("live", process_alive=True), Running),
        (ProviderInterruptedError("gone", process_alive=False), Stopped),
        (ProviderInterruptedError("unverifiable", process_alive=None), Unknown),
    ],
)
def test_legacy_recovery_is_normalized_conservatively(
    tmp_path: Path, result: object, outcome_type: type
) -> None:
    assert isinstance(
        recover_outcome(LegacyProvider(result), request(tmp_path)), outcome_type
    )


def test_legacy_completed_response_is_preserved(tmp_path: Path) -> None:
    response = ProviderResponse("done", "session-1")

    outcome = recover_outcome(LegacyProvider(response), request(tmp_path))

    assert outcome == Completed(response, "legacy provider returned a response")


@pytest.mark.parametrize(
    "result",
    [Completed("not a response"), RecoveryOutcome()],  # type: ignore[arg-type]
)
def test_malformed_explicit_recovery_outcome_is_unknown(
    tmp_path: Path, result: object
) -> None:
    assert isinstance(
        recover_outcome(LegacyProvider(result), request(tmp_path)), Unknown
    )


def test_fake_provider_only_reports_knowledge_for_matching_attempt(
    tmp_path: Path,
) -> None:
    req = request(tmp_path)
    provider = FakeProvider([ProviderError("known synchronous failure")])
    with pytest.raises(ProviderError):
        provider.run(req)

    assert isinstance(provider.recover(req), Stopped)
    assert isinstance(provider.recover(request(tmp_path, attempt=2)), Unknown)


def test_fake_provider_knows_scripted_control_interruption_is_stopped(
    tmp_path: Path,
) -> None:
    req = request(tmp_path)
    provider = FakeProvider([KeyboardInterrupt()])
    with pytest.raises(KeyboardInterrupt):
        provider.run(req)

    assert isinstance(provider.recover(req), Stopped)


def test_fake_provider_does_not_claim_failed_callback_effects_stopped(
    tmp_path: Path,
) -> None:
    req = request(tmp_path)

    def callback(_request: ProviderRequest) -> None:
        raise ProviderError("callback may have started an external effect")

    provider = FakeProvider([callback])
    with pytest.raises(ProviderError):
        provider.run(req)

    assert isinstance(provider.recover(req), Unknown)
