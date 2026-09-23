from __future__ import annotations

import pytest
from pydantic import BaseModel, model_validator

from botpipe import (
    Artifact,
    Botpipe,
    Provider,
    UncertainOperation,
    provider_budget,
    workflow,
)
from botpipe.errors import ReplayMismatch
from botpipe.provider_checkpoints import (
    EmptyCheckpoint,
    IntentCheckpoint,
    NotDispatchedCheckpoint,
    PreparingCheckpoint,
    ProviderCheckpoint,
    ProviderCheckpointError,
    ProviderLifecycle,
    RecoveryAction,
    RespondedCheckpoint,
    RetryAuthorizedCheckpoint,
    ValidatedCheckpoint,
    ValidationFailedCheckpoint,
)
from botpipe.providers import FakeProvider, ProviderError, ProviderResponse
from botpipe.recovery import Completed, Running, Stopped, Unknown

REQUEST = {
    "session_id": None,
    "receipt_dir": "/tmp/receipts",
    "prompt": "work",
    "artifacts": {},
    "reads": [],
}
RESPONSE = {
    "text": "done",
    "session_id": "session",
    "usage": {"input_tokens": 2},
    "metadata": {"receipt": "one"},
}


@pytest.mark.parametrize(
    ("record", "kind"),
    [
        ({}, EmptyCheckpoint),
        ({"generation": 0, "preparing": True}, PreparingCheckpoint),
        ({"generation": 0, "request": REQUEST}, IntentCheckpoint),
        (
            {"generation": 1, "request": REQUEST, "retry_authorized": True},
            RetryAuthorizedCheckpoint,
        ),
        (
            {
                "generation": 0,
                "request": REQUEST,
                "not_dispatched": True,
                "restoration_pending": False,
                "budget_error": "turns exhausted",
            },
            NotDispatchedCheckpoint,
        ),
        ({**RESPONSE, "generation": 0, "request": REQUEST}, RespondedCheckpoint),
        (
            {
                **RESPONSE,
                "generation": 0,
                "request": REQUEST,
                "validated_value": {"value": "done"},
            },
            ValidatedCheckpoint,
        ),
        (
            {
                **RESPONSE,
                "generation": 0,
                "request": REQUEST,
                "output_error": {"message": "bad output", "retryable": True},
            },
            ValidationFailedCheckpoint,
        ),
    ],
)
def test_legacy_checkpoint_states_round_trip(record, kind):
    checkpoint = ProviderCheckpoint.from_record(record)
    assert type(checkpoint) is kind
    assert ProviderCheckpoint.from_record(checkpoint.to_record()) == checkpoint


@pytest.mark.parametrize(
    "record",
    [
        {"generation": True, "request": REQUEST},
        {"generation": 0, "preparing": True, "request": REQUEST},
        {"generation": 0, "request": REQUEST, "retry_authorized": True},
        {
            "generation": 0,
            "request": REQUEST,
            "not_dispatched": True,
            "restoration_pending": True,
            "budget_error": "budget",
            "policy_error": "policy",
        },
        {**RESPONSE, "generation": 0, "request": REQUEST, "mystery": True},
        {
            **RESPONSE,
            "generation": 0,
            "request": REQUEST,
            "output_error": {"message": "bad", "retryable": "yes"},
        },
        {"generation": 0, "request": {**REQUEST, "prompt": 7}},
        {"generation": 0, "request": {**REQUEST, "extra": "unknown"}},
    ],
)
def test_contradictory_or_unknown_checkpoints_fail_closed(record):
    with pytest.raises(ProviderCheckpointError):
        ProviderCheckpoint.from_record(record)
    assert issubclass(ProviderCheckpointError, ReplayMismatch)


def test_checkpoint_effect_predicate_distinguishes_restored_non_dispatch():
    pending = ProviderCheckpoint.from_record(
        {
            "generation": 0,
            "request": REQUEST,
            "not_dispatched": True,
            "restoration_pending": True,
            "policy_error": "denied",
        }
    )
    restored = ProviderCheckpoint.from_record(
        {**pending.to_record(), "restoration_pending": False}
    )
    validated = ProviderCheckpoint.from_record(
        {
            **RESPONSE,
            "generation": 0,
            "request": REQUEST,
            "validated_value": "done",
        }
    )
    responded = ProviderCheckpoint.from_record(
        {**RESPONSE, "generation": 0, "request": REQUEST}
    )

    assert pending.has_unresolved_effects(has_writes=False)
    assert not restored.has_unresolved_effects(has_writes=True)
    assert not validated.has_unresolved_effects(has_writes=False)
    assert validated.has_unresolved_effects(has_writes=True)
    assert not responded.has_unresolved_effects(has_writes=False)
    assert responded.has_unresolved_effects(has_writes=True)


def test_normal_recovery_and_reconciliation_share_completed_transition():
    intent = IntentCheckpoint(2, REQUEST)
    response = ProviderResponse("done", "session", {"tokens": 3})
    outcome = Completed(response)

    assert (
        ProviderLifecycle.recovery_action(intent, outcome)
        is RecoveryAction.USE_RESPONSE
    )
    assert (
        ProviderLifecycle.reconciliation_action(outcome) is RecoveryAction.USE_RESPONSE
    )
    recovered = ProviderLifecycle.completed(intent, response)
    assert recovered == RespondedCheckpoint(2, REQUEST, response)


def test_retry_generation_is_idempotent_and_completed_receipt_wins():
    intent = IntentCheckpoint(2, REQUEST)
    authorized = ProviderLifecycle.authorize_retry(intent)
    assert authorized.generation == 3
    assert authorized.attempt_generation == 2
    assert ProviderLifecycle.authorize_retry(authorized) is authorized

    receipt = ProviderResponse("receipt")
    assert (
        ProviderLifecycle.recovery_action(authorized, Completed(receipt))
        is RecoveryAction.USE_RESPONSE
    )
    recovered = ProviderLifecycle.completed(authorized, receipt)
    assert recovered.generation == 2
    assert recovered.response is receipt


def test_running_attempt_blocks_both_recovery_paths():
    authorized = RetryAuthorizedCheckpoint(1, REQUEST)
    assert (
        ProviderLifecycle.recovery_action(authorized, Running("live"))
        is RecoveryAction.BLOCK
    )
    assert (
        ProviderLifecycle.reconciliation_action(Running("live"))
        is RecoveryAction.BLOCK
    )


def test_authorized_unknown_attempt_may_start_explicit_retry():
    authorized = RetryAuthorizedCheckpoint(1, REQUEST)
    assert (
        ProviderLifecycle.recovery_action(authorized, Unknown("unknown"))
        is RecoveryAction.START_RETRY
    )


def test_only_stopped_authorized_attempt_may_start_retry():
    stopped = Stopped("quiescent")
    assert (
        ProviderLifecycle.recovery_action(IntentCheckpoint(0, REQUEST), stopped)
        is RecoveryAction.BLOCK
    )
    assert (
        ProviderLifecycle.recovery_action(
            RetryAuthorizedCheckpoint(1, REQUEST), stopped
        )
        is RecoveryAction.START_RETRY
    )
    assert (
        ProviderLifecycle.reconciliation_action(stopped)
        is RecoveryAction.ALLOW_RESOLUTION
    )


def test_malformed_checkpoint_does_not_fail_operation_or_redispatch(tmp_path):
    @workflow
    def work():
        return Provider().run("effectful work")

    provider = FakeProvider([KeyboardInterrupt("crash after dispatch")])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(work, run_id="malformed")
        operation = next(
            row
            for row in client.journal.operations(paused.run_id)
            if row["kind"] == "provider"
        )
        malformed = dict(operation["response"])
        malformed["request"] = {**malformed["request"], "prompt": 7}
        client.journal.response(operation["id"], malformed)

        replay = client.resume(paused.run_id, workflow=work)
        after = client.journal.get(operation["id"])

    assert "ProviderCheckpointError" in replay.error
    assert after["status"] == "response"
    assert after["response"] == malformed
    assert len(provider.calls) == 1


def _fail_response_once(client, monkeypatch, predicate, *, after_commit):
    original = client.journal.response
    observations = []

    def fault(operation_id, record, session_key=None):
        if not observations and predicate(record):
            if after_commit:
                original(operation_id, record, session_key)
            observations.append(client.journal.get(operation_id).get("response"))
            raise OSError("checkpoint acknowledgement lost")
        return original(operation_id, record, session_key)

    monkeypatch.setattr(client.journal, "response", fault)
    return observations, original


@pytest.mark.parametrize("after_commit", [False, True])
@pytest.mark.parametrize("transition", ["preparing", "intent"])
def test_pre_dispatch_checkpoint_ack_loss_never_duplicates_dispatch(
    tmp_path, monkeypatch, after_commit, transition
):
    @workflow
    def work():
        return Provider().run("work").value

    def target(record):
        if transition == "preparing":
            return record.get("preparing") is True
        return (
            "request" in record and "text" not in record and not record.get("preparing")
        )

    provider = FakeProvider(["done"])
    with Botpipe(tmp_path, provider=provider) as client:
        observations, original = _fail_response_once(
            client, monkeypatch, target, after_commit=after_commit
        )
        first = client.run(work, run_id=f"{transition}-{after_commit}")
        monkeypatch.setattr(client.journal, "response", original)
        result = first if first.ok else client.resume(first.run_id, workflow=work)

    assert result.ok, result.error
    assert result.value == "done"
    assert len(provider.calls) == 1
    if after_commit:
        assert target(observations[0])
    elif transition == "preparing":
        assert observations[0] is None
    else:
        assert observations[0]["preparing"] is True


@pytest.mark.parametrize("after_commit", [False, True])
@pytest.mark.parametrize("transition", ["not_dispatched", "restored"])
@pytest.mark.parametrize("rejection", ["preview", "reservation"])
def test_non_dispatch_checkpoint_ack_loss_preserves_restoration_state(
    tmp_path, monkeypatch, after_commit, transition, rejection
):
    if rejection == "reservation":
        import botpipe.budgets as budgets

        monkeypatch.setattr(
            budgets,
            "dispatch_timeout_ceiling",
            lambda _provider, configured_timeout: configured_timeout,
        )
    destination = tmp_path / "result.txt"
    destination.write_text("before")

    @workflow
    def work():
        with provider_budget(max_turns=1):
            Provider().run("consume budget")
            return Provider().run(
                "denied", writes=Artifact.text(destination, required=True)
            )

    def target(record):
        return record.get("not_dispatched") is True and record.get(
            "restoration_pending"
        ) is (transition == "not_dispatched")

    provider = FakeProvider(["first"])
    with Botpipe(tmp_path, provider=provider) as client:
        observations, original = _fail_response_once(
            client, monkeypatch, target, after_commit=after_commit
        )
        first = client.run(
            work, run_id=f"{rejection}-{transition}-{after_commit}"
        )
        operation = [
            row
            for row in client.journal.operations(first.run_id)
            if row["kind"] == "provider"
        ][-1]
        monkeypatch.setattr(client.journal, "response", original)
        if rejection == "preview" or transition == "restored" or after_commit:
            result = client.resume(first.run_id, workflow=work)
            operation = client.journal.get(operation["id"])
            assert result.status == "budget_exceeded"
            assert destination.read_text() == "before"
            assert operation["response"]["restoration_pending"] is False
        else:
            # The non-dispatch fact did not commit, so an intent remains
            # uncertain and cannot be silently redispatched.
            result = client.resume(first.run_id, workflow=work)
            assert result.status == "interrupted"
            assert operation["response"].get("not_dispatched") is not True

    assert observations
    assert len(provider.calls) == 1
    if after_commit:
        assert target(observations[0])
    elif transition == "not_dispatched":
        assert observations[0].get("not_dispatched") is not True
    else:
        assert observations[0]["restoration_pending"] is True


@pytest.mark.parametrize("after_commit", [False, True])
def test_output_error_checkpoint_ack_loss_has_no_duplicate_dispatch(
    tmp_path, monkeypatch, after_commit
):
    validations = []

    class Answer(BaseModel):
        accepted: bool

        @model_validator(mode="before")
        @classmethod
        def reject(cls, value):
            validations.append(value)
            raise ValueError("invalid answer")

    @workflow
    def work():
        return Provider().run("work", returns=Answer, output_retries=0)

    provider = FakeProvider(['{"accepted": true}'])
    with Botpipe(tmp_path, provider=provider) as client:
        observations, original = _fail_response_once(
            client,
            monkeypatch,
            lambda record: "output_error" in record,
            after_commit=after_commit,
        )
        first = client.run(work, run_id=f"validation-{after_commit}")
        monkeypatch.setattr(client.journal, "response", original)
        result = (
            first
            if first.status == "failed"
            else client.resume(first.run_id, workflow=work)
        )

    assert result.status == "failed"
    assert len(provider.calls) == 1
    # Before commit, validation is the pure work needed to reconstruct the
    # missing checkpoint. After commit, acknowledgement loss cannot repeat it.
    assert len(validations) == (1 if after_commit else 2)
    if after_commit:
        assert "output_error" in observations[0]
    else:
        assert "output_error" not in observations[0]


@pytest.mark.parametrize("after_commit", [False, True])
def test_retry_authorization_ack_loss_never_skips_generation(
    tmp_path, monkeypatch, after_commit
):
    @workflow
    def work():
        return Provider().run("work").value

    provider = FakeProvider([ProviderError("stopped"), "done"])
    with Botpipe(tmp_path, provider=provider) as client:
        first = client.run(work, run_id=f"retry-{after_commit}")
        operation = next(
            row
            for row in client.journal.operations(first.run_id)
            if row["kind"] == "provider"
        )
        observations, original = _fail_response_once(
            client,
            monkeypatch,
            lambda record: record.get("retry_authorized") is True,
            after_commit=after_commit,
        )
        if after_commit:
            client.resolve(first.run_id, operation["id"], retry=True)
        else:
            with pytest.raises(UncertainOperation):
                client.resolve(first.run_id, operation["id"], retry=True)
        monkeypatch.setattr(client.journal, "response", original)
        result = client.resume(first.run_id, workflow=work)

    assert observations
    if after_commit:
        assert observations[0]["retry_authorized"] is True
        assert observations[0]["generation"] == 1
        assert result.ok, result.error
        assert result.value == "done"
        assert len(provider.calls) == 2
        assert provider.calls[-1].attempt == 2
    else:
        assert "retry_authorized" not in observations[0]
        assert observations[0]["generation"] == 0
        assert result.status == "interrupted"
        assert len(provider.calls) == 1
