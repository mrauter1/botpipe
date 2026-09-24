from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest

from botpipe import (
    Artifact,
    Botpipe,
    BotpipeError,
    Provider,
    workflow,
)
from botpipe.providers import (
    FakeProvider,
    ProviderError,
    ProviderInterruptedError,
    ProviderRequest,
    ProviderResponse,
)
from botpipe.recovery import Completed, Running, Stopped, Unknown


def _provider_operation(client: Botpipe, run_id: str) -> dict:
    return next(
        row for row in client.journal.operations(run_id) if row["kind"] == "provider"
    )


def test_recovered_completion_overrides_conflicting_operator_response(tmp_path):
    class ReceiptedProvider(FakeProvider):
        def recover(self, request: ProviderRequest):
            return Completed(ProviderResponse("receipt result", "receipt-session"))

    @workflow
    def conversation():
        session = Provider()
        return session.run("first").value, session.run("second").value

    provider = ReceiptedProvider(
        [SystemExit("response publication was interrupted"), "next result"]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit):
            client.run(conversation, run_id="receipt-wins")
        operation = _provider_operation(client, "receipt-wins")

        client.resolve(
            "receipt-wins",
            operation["id"],
            response=ProviderResponse("operator result", "operator-session"),
        )

        reconciled = client.journal.get(operation["id"])["response"]
        assert reconciled["text"] == "receipt result"
        assert reconciled["session_id"] == "receipt-session"
        result = client.resume("receipt-wins", workflow=conversation)
        assert result.ok, result.error
        assert result.value == ("receipt result", "next result")
        assert provider.calls[-1].session_id == "receipt-session"


class _LegacyRecoveryProvider(FakeProvider):
    def __init__(self, recovery: object):
        super().__init__([SystemExit("provider intent interrupted")])
        self.recovery = recovery
        self.recovery_requests: list[ProviderRequest] = []

    def recover(self, request: ProviderRequest):
        self.recovery_requests.append(request)
        if isinstance(self.recovery, BaseException):
            raise self.recovery
        return self.recovery


@pytest.mark.parametrize(
    "recovery",
    [
        None,
        ProviderError("generic recovery failure"),
        ProviderInterruptedError("liveness unknown", process_alive=None),
    ],
    ids=["none", "provider-error", "interrupted-unknown"],
)
@pytest.mark.parametrize("resolution", ["retry", "response"])
def test_operator_can_explicitly_resolve_unknown_recovery(
    tmp_path, recovery: object, resolution: str
):
    @workflow
    def work():
        return Provider().run("effectful work").value

    provider = _LegacyRecoveryProvider(recovery)
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="unknown-recovery")
        operation = _provider_operation(client, "unknown-recovery")
        if resolution == "retry":
            client.resolve("unknown-recovery", operation["id"], retry=True)
        else:
            client.resolve(
                "unknown-recovery",
                operation["id"],
                response=ProviderResponse("operator claim"),
            )
        after = client.journal.get(operation["id"])["response"]
        if resolution == "retry":
            assert after["retry_authorized"] is True
            assert after["generation"] == 1
        else:
            assert after["text"] == "operator claim"


def test_manual_recovery_uses_timeout_recorded_for_run(tmp_path):
    @workflow
    def work():
        return Provider().run("effectful work").value

    provider = _LegacyRecoveryProvider(None)
    with Botpipe(tmp_path, provider=provider, timeout=7.5) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="recorded-timeout")
        operation = _provider_operation(client, "recorded-timeout")
        client.timeout = 90

        client.resolve("recorded-timeout", operation["id"], retry=True)

        assert provider.recovery_requests[-1].timeout == 7.5


def test_known_stopped_unsafe_attempt_only_reexecutes_after_retry_authorization(
    tmp_path,
):
    @workflow
    def work():
        return Provider().run("effectful work", retry_safe=False).value

    provider = FakeProvider([ProviderError("known synchronous failure"), "done"])
    with Botpipe(tmp_path, provider=provider) as client:
        interrupted = client.run(work, run_id="known-stopped")
        assert interrupted.status == "interrupted"
        assert len(provider.calls) == 1

        still_interrupted = client.resume("known-stopped", workflow=work)
        assert still_interrupted.status == "interrupted"
        assert len(provider.calls) == 1

        operation = _provider_operation(client, "known-stopped")
        client.resolve("known-stopped", operation["id"], retry=True)
        authorized = client.journal.get(operation["id"])["response"]
        assert authorized["retry_authorized"] is True
        assert authorized["retry_origin"] == "operator"
        assert authorized["generation"] == 1
        assert len(provider.calls) == 1

        completed = client.resume("known-stopped", workflow=work)
        assert completed.ok, completed.error
        assert completed.value == "done"
        assert len(provider.calls) == 2
        assert provider.calls[-1].attempt == 2


def test_repeated_live_reconciliation_remains_blocked(tmp_path):
    class LiveProvider(FakeProvider):
        def recover(self, request: ProviderRequest):
            return Running("the owned attempt is live")

    @workflow
    def work():
        return Provider().run("effectful work").value

    provider = LiveProvider([SystemExit("runtime interrupted")])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="live-attempt")
        operation = _provider_operation(client, "live-attempt")
        before = deepcopy(client.journal.get(operation["id"])["response"])

        for _ in range(2):
            with pytest.raises(BotpipeError, match="still running"):
                client.resolve("live-attempt", operation["id"], retry=True)

        assert client.journal.get(operation["id"])["response"] == before
        assert len(provider.calls) == 1


def test_explicit_unknown_outcome_allows_operator_response(tmp_path):
    class UnknownProvider(FakeProvider):
        def recover(self, request: ProviderRequest):
            return Unknown("supervisor state unavailable")

    @workflow
    def work():
        return Provider().run("effectful work").value

    provider = UnknownProvider([SystemExit("runtime interrupted")])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="explicit-unknown")
        operation = _provider_operation(client, "explicit-unknown")

        client.resolve(
            "explicit-unknown",
            operation["id"],
            response=ProviderResponse("operator claim"),
        )
        assert client.journal.get(operation["id"])["response"]["text"] == "operator claim"


def test_manual_response_cancels_pending_retry_without_preparing_new_outputs(tmp_path):
    class StoppedProvider(FakeProvider):
        def recover(self, request):
            return Stopped("attempt is quiescent")

    destination = tmp_path / "report.txt"
    destination.write_text("previous output")

    def interrupted(request):
        request.artifacts["report"].write_text("resolved output")
        raise KeyboardInterrupt()

    @workflow
    def writer():
        return Provider().run(
            "write", writes=[Artifact.text(destination, required=True)], output_retries=0
        )

    provider = StoppedProvider([interrupted])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(writer)
        operation = _provider_operation(client, paused.run_id)
        client.resolve(paused.run_id, operation["id"], retry=True)
        client.resolve(
            paused.run_id,
            operation["id"],
            response=ProviderResponse("recovered manually"),
            artifact_digests={
                "report": hashlib.sha256(destination.read_bytes()).hexdigest()
            },
        )
        resolved = client.journal.get(operation["id"])["response"]
        assert resolved["generation"] == 0
        assert "retry_authorized" not in resolved
        result = client.resume(paused.run_id, workflow=writer)

    assert result.ok, result.error
    assert result.value.value == "recovered manually"
    assert result.value.artifacts.report.read_text() == "resolved output"
    assert destination.read_text() == "resolved output"
    assert len(provider.calls) == 1


@pytest.mark.parametrize("resolution", ["automatic", "manual"])
def test_invalid_completed_response_stays_uncommitted(tmp_path, resolution):
    class MalformedProvider(FakeProvider):
        state = "stopped"

        def recover(self, request):
            if self.state == "stopped":
                return Stopped("attempt stopped")
            return Completed(ProviderResponse("done", usage=[]))

    @workflow
    def job():
        return Provider().run("work")

    provider = MalformedProvider([KeyboardInterrupt()])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(job)
        operation = _provider_operation(client, paused.run_id)
        if resolution == "manual":
            with pytest.raises(TypeError, match="usage and metadata must be plain JSON objects"):
                client.resolve(
                    paused.run_id,
                    operation["id"],
                    response=ProviderResponse("done", usage=[]),
                )
        provider.state = "malformed"
        for _ in range(2):
            resumed = client.resume(paused.run_id, workflow=job)
            assert resumed.status == "interrupted", resumed.error
            assert "invalid completed response" in resumed.error
            assert client.journal.get(operation["id"])["status"] != "completed"
    assert len(provider.calls) == 1
