from __future__ import annotations

from functools import partial
import json

import pytest

from botpipe import Botpipe, ReplayMismatch, activity, ask, codec, parallel, workflow
from botpipe.providers import FakeProvider


def test_activity_body_can_change_while_completed_outcome_replays(tmp_path):
    effects = []

    @activity(name="calculate")
    def original(value):
        effects.append("original")
        return value + 1

    @workflow(name="mutable-job")
    def first():
        return original(3), ask("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(first, run_id="mutable-activity")
        assert paused.status == "awaiting_input"

        @activity(name="calculate")
        def revised(value):
            effects.append("revised")
            return value + 100

        @workflow(name="mutable-job")
        def second():
            return revised(3), ask("Continue?")

        resumed = client.resume(paused.run_id, workflow=second, answer="yes")

    assert resumed.ok, resumed.error
    assert resumed.value == (4, "yes")
    assert effects == ["original"]


def test_activity_argument_change_is_a_replay_mismatch(tmp_path):
    @activity(name="calculate")
    def calculate(value):
        return value

    @workflow(name="mutable-job")
    def first():
        calculate(1)
        return ask("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(first, run_id="changed-argument")

        @workflow(name="mutable-job")
        def second():
            calculate(2)
            return ask("Continue?")

        resumed = client.resume(paused.run_id, workflow=second, answer="yes")

    assert resumed.status == "failed"
    assert "ReplayMismatch" in resumed.error


def test_completed_root_returns_saved_result_without_a_revision_or_execution(tmp_path):
    executions = []

    @workflow(name="completed-job")
    def first():
        executions.append("first")
        return "saved"

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        completed = client.run(first, run_id="completed-root")
        before_run = client.journal.run(completed.run_id)
        before_events = client.journal.events(completed.run_id)

        @workflow(name="completed-job")
        def revised():
            executions.append("revised")
            return "new"

        replayed = client.resume(
            completed.run_id,
            workflow=revised,
            answer="ignored",
            max_operations=client.max_operations + 10,
        )

        assert client.journal.run(completed.run_id) == before_run
        assert client.journal.events(completed.run_id) == before_events

    assert replayed.ok
    assert replayed.value == "saved"
    assert executions == ["first"]


@pytest.mark.parametrize(
    ("recorded_safe", "current_safe"),
    [(True, False), (False, True)],
)
def test_automatic_activity_retry_requires_recorded_and_current_safety(
    tmp_path, recorded_safe, current_safe
):
    effects = []

    @activity(name="uncertain", retry_safe=recorded_safe)
    def interrupted():
        effects.append("interrupted")
        raise KeyboardInterrupt

    @workflow(name="retry-job")
    def first():
        return interrupted()

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        initial = client.run(first, run_id=f"retry-{recorded_safe}-{current_safe}")
        assert initial.status == "interrupted"

        @activity(name="uncertain", retry_safe=current_safe)
        def revised():
            effects.append("retried")
            return "done"

        @workflow(name="retry-job")
        def second():
            return revised()

        replayed = client.resume(initial.run_id, workflow=second)

    assert replayed.status == "interrupted"
    assert effects == ["interrupted"]


def test_explicit_recovery_retry_overrides_safety_change(tmp_path):
    effects = []

    @activity(name="uncertain", retry_safe=True)
    def interrupted():
        effects.append("interrupted")
        raise KeyboardInterrupt

    @workflow(name="retry-job")
    def first():
        return interrupted()

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        initial = client.run(first, run_id="explicit-retry")
        operation = client.journal.operations(initial.run_id)[0]
        client.resolve(initial.run_id, operation["id"], retry=True)

        @activity(name="uncertain", retry_safe=False)
        def revised():
            effects.append("retried")
            return "done"

        @workflow(name="retry-job")
        def second():
            return revised()

        replayed = client.resume(initial.run_id, workflow=second)

    assert replayed.ok, replayed.error
    assert replayed.value == "done"
    assert effects == ["interrupted", "retried"]


def test_parallel_partial_code_changes_replay_but_binding_changes_do_not(tmp_path):
    def branch(value):
        return value + 1

    selected = partial(branch, 3)

    @workflow(name="parallel-job")
    def job():
        result = parallel(selected)
        ask("Continue?")
        return result

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job, run_id="parallel-partial")
        assert paused.status == "awaiting_input"

        def branch(value):
            return value + 100

        selected = partial(branch, 3)
        completed = client.resume(paused.run_id, workflow=job, answer="yes")
        assert completed.ok, completed.error
        assert completed.value == [4]

    selected = partial(branch, 4)
    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        # The completed root is authoritative and does not re-enter orchestration.
        assert client.resume("parallel-partial", workflow=job).value == [4]


def test_pending_parallel_partial_binding_change_is_rejected(tmp_path):
    def branch(value):
        return value

    selected = partial(branch, 1)

    @workflow(name="parallel-job")
    def job():
        parallel(selected)
        return ask("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job, run_id="parallel-binding")
        selected = partial(branch, 2)
        replayed = client.resume(paused.run_id, workflow=job, answer="yes")

    assert replayed.status == "failed"
    assert "ReplayMismatch" in replayed.error


def test_recorded_inputs_must_match_their_replay_fingerprint(tmp_path):
    @activity(name="calculate")
    def calculate(value):
        return value

    @workflow(name="integrity-job")
    def job():
        calculate(1)
        return ask("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job, run_id="input-integrity")
        operation = client.journal.operations(paused.run_id)[0]
        inputs = client.journal.get(operation["id"])["inputs"]
        decoded = codec.decode(inputs)
        decoded["args"] = (2,)
        encoded = codec.encode(decoded)
        with client.journal.transaction() as database:
            database.execute(
                "UPDATE operations SET inputs=? WHERE id=?",
                (json.dumps(encoded), operation["id"]),
            )

        with pytest.raises(ReplayMismatch, match="replay fingerprint"):
            client.resume(paused.run_id, workflow=job, answer="yes")


def test_reducing_activity_retries_cannot_abandon_later_history(tmp_path):
    attempts = []

    @activity(name="flaky", retry_safe=True, retries=1)
    def initially_flaky():
        attempts.append("initial")
        if len(attempts) == 1:
            raise ValueError("retry")
        return "saved"

    @workflow(name="retry-count-job")
    def first():
        initially_flaky()
        return ask("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(first, run_id="reduced-retries")
        assert paused.status == "awaiting_input"

        @activity(name="flaky", retry_safe=True, retries=0)
        def revised():
            attempts.append("revised")
            return "new"

        @workflow(name="retry-count-job")
        def second():
            revised()
            return ask("Continue?")

        replayed = client.resume(paused.run_id, workflow=second, answer="yes")

    assert replayed.status == "failed"
    assert "ReplayMismatch" in replayed.error
    assert attempts == ["initial", "initial"]


def test_exception_slot_layout_is_verified_before_resume(tmp_path):
    class SlottedFailure(Exception):
        __slots__ = ("code",)

        def __init__(self, code):
            self.code = code
            super().__init__(code)

    @activity(name="fails")
    def fails():
        raise SlottedFailure(9)

    @workflow(name="slot-job")
    def job():
        try:
            fails()
        except SlottedFailure:
            return ask("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job, run_id="slot-layout")
        operation = client.journal.operations(paused.run_id)[0]
        error = operation["error"]
        error["slots"] = []
        with client.journal.transaction() as database:
            database.execute(
                "UPDATE operations SET error=? WHERE id=?",
                (json.dumps(error), operation["id"]),
            )

        with pytest.raises(ReplayMismatch, match="slots no longer match"):
            client.resume(paused.run_id, workflow=job, answer="yes")
