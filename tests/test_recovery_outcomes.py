from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from botpipe.policy import Policy
from botpipe.providers import (
    CodexProvider,
    FakeProvider,
    ProviderError,
    ProviderInterruptedError,
    ProviderRequest,
    ProviderResponse,
    receipt_path,
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


class RecoveryAdapter:
    name = "test"

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
def test_recovery_failures_are_normalized_conservatively(
    tmp_path: Path, result: object, outcome_type: type
) -> None:
    assert isinstance(
        recover_outcome(RecoveryAdapter(result), request(tmp_path)), outcome_type
    )


def test_untyped_completed_response_is_rejected(tmp_path: Path) -> None:
    response = ProviderResponse("done", "session-1")

    outcome = recover_outcome(RecoveryAdapter(response), request(tmp_path))

    assert isinstance(outcome, Unknown)
    assert "unsupported recovery result ProviderResponse" in (outcome.detail or "")


@pytest.mark.parametrize(
    "result",
    [Completed("not a response"), RecoveryOutcome()],  # type: ignore[arg-type]
)
def test_malformed_explicit_recovery_outcome_is_unknown(
    tmp_path: Path, result: object
) -> None:
    assert isinstance(
        recover_outcome(RecoveryAdapter(result), request(tmp_path)), Unknown
    )


def _write_receipt(req: ProviderRequest, value: dict[str, object]) -> None:
    path = receipt_path(req)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_native_failed_receipt_proves_attempt_stopped(tmp_path: Path) -> None:
    req = request(tmp_path)
    _write_receipt(
        req,
        {
            "operation_id": req.operation_id,
            "attempt": req.attempt,
            "status": "failed",
            "error": "provider rejected request",
        },
    )

    outcome = CodexProvider(("codex", "exec")).recover(req)

    assert outcome == Stopped("provider rejected request")


def test_native_starting_receipt_without_pid_remains_unknown(tmp_path: Path) -> None:
    req = request(tmp_path)
    _write_receipt(
        req,
        {
            "operation_id": req.operation_id,
            "attempt": req.attempt,
            "status": "starting",
        },
    )

    outcome = CodexProvider(("codex", "exec")).recover(req)

    assert isinstance(outcome, Unknown)
    assert "no verifiable process id" in (outcome.detail or "")


def test_native_completed_prior_attempt_wins_over_later_terminal_state(
    tmp_path: Path,
) -> None:
    first = request(tmp_path)
    _write_receipt(
        first,
        {
            "operation_id": first.operation_id,
            "attempt": 1,
            "status": "completed",
            "response": {
                "text": "authoritative",
                "session_id": "s1",
                "usage": {},
                "metadata": {},
            },
        },
    )
    second = request(tmp_path, attempt=2)
    _write_receipt(
        second,
        {
            "operation_id": second.operation_id,
            "attempt": 2,
            "status": "failed",
            "error": "later failure",
        },
    )

    outcome = CodexProvider(("codex", "exec")).recover(second)

    assert outcome == Completed(ProviderResponse("authoritative", "s1"))


@pytest.mark.parametrize(
    ("status", "expected_type"),
    [("running", Running), ("starting", Unknown)],
)
def test_native_prior_completion_waits_for_newer_attempt_to_be_quiescent(
    tmp_path: Path, status: str, expected_type: type
) -> None:
    first = request(tmp_path)
    _write_receipt(
        first,
        {
            "operation_id": first.operation_id,
            "attempt": 1,
            "status": "completed",
            "response": {"text": "authoritative"},
        },
    )
    second = request(tmp_path, attempt=2)
    current: dict[str, object] = {
        "operation_id": second.operation_id,
        "attempt": 2,
        "status": status,
    }
    if status == "running":
        current["pid"] = os.getpid()
    _write_receipt(second, current)

    outcome = CodexProvider(("codex", "exec")).recover(second)

    assert isinstance(outcome, expected_type)


@pytest.mark.parametrize(
    ("operation_id", "attempt"),
    [("different-operation", 1), ("run:scope:1", 2), ("run:scope:1", True)],
)
def test_native_receipt_requires_exact_operation_and_attempt_identity(
    tmp_path: Path, operation_id: str, attempt: object
) -> None:
    req = request(tmp_path)
    _write_receipt(
        req,
        {
            "operation_id": operation_id,
            "attempt": attempt,
            "status": "completed",
            "response": {"text": "wrong response"},
        },
    )

    outcome = CodexProvider(("codex", "exec")).recover(req)

    assert isinstance(outcome, Unknown)
    assert "identity does not match" in (outcome.detail or "")


def test_fake_provider_only_reports_knowledge_for_matching_attempt(
    tmp_path: Path,
) -> None:
    req = request(tmp_path)
    provider = FakeProvider([ProviderError("known synchronous failure")])
    with pytest.raises(ProviderError):
        provider.run(req)

    assert isinstance(provider.recover(req), Stopped)
    assert isinstance(provider.recover(request(tmp_path, attempt=2)), Unknown)


def test_fake_provider_does_not_claim_control_interruption_stopped(
    tmp_path: Path,
) -> None:
    req = request(tmp_path)
    provider = FakeProvider([KeyboardInterrupt()])
    with pytest.raises(KeyboardInterrupt):
        provider.run(req)

    assert isinstance(provider.recover(req), Unknown)


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
