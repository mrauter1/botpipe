from __future__ import annotations

import json
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import pytest

from botpipe import (
    Botpipe,
    ReplayMismatch,
    Workflow,
    activity,
    ask_human,
    codec,
    parallel,
    workflow,
)
from botpipe.providers import FakeProvider


def _rewrite_ledger_record(
    run_folder: Path,
    *,
    operation_id: str,
    event: str,
    update,
) -> None:
    ledger = run_folder / "ledger.jsonl"
    records = [json.loads(line) for line in ledger.read_text().splitlines()]
    matching = [
        record
        for record in records
        if record.get("event") == event
        and record.get("operation_id") == operation_id
    ]
    assert len(matching) == 1
    update(matching[0])
    ledger.write_text(
        "".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records)
    )


@dataclass
class _BoundCallback:
    amount: int

    def __call__(self):
        return self.amount


@dataclass
class _OpaqueDataclassCallback:
    nondurable_state: object

    def __call__(self):
        return "opaque"


def test_activity_body_can_change_while_completed_outcome_replays(tmp_path):
    effects = []

    @activity(name="calculate")
    def original(value):
        effects.append("original")
        return value + 1

    @workflow(name="mutable-job")
    def first():
        return original(3), ask_human("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(first, run_id="mutable-activity")
        assert paused.status == "awaiting_input"

        @activity(name="calculate")
        def revised(value):
            effects.append("revised")
            return value + 100

        @workflow(name="mutable-job")
        def second():
            return revised(3), ask_human("Continue?")

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
        return ask_human("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(first, run_id="changed-argument")

        @workflow(name="mutable-job")
        def second():
            calculate(2)
            return ask_human("Continue?")

        resumed = client.resume(paused.run_id, workflow=second, answer="yes")

    assert resumed.status == "failed"
    assert "ReplayMismatch" in resumed.error


def test_activity_keyword_order_change_rejects_before_answer(tmp_path):
    effects = []

    @activity(name="calculate")
    def calculate(**values):
        effects.append(tuple(values))
        return "saved"

    @workflow(name="activity-keyword-order-job")
    def first():
        calculate(left=1, right=2)
        return ask_human("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(first, run_id="activity-keyword-order")
        assert paused.status == "awaiting_input"
        waiting = paused.pending_input["operation_id"]

        @workflow(name="activity-keyword-order-job")
        def second():
            calculate(right=2, left=1)
            return ask_human("Continue?")

        replayed = client.resume(paused.run_id, workflow=second, answer="yes")

        assert replayed.status == "failed"
        assert "ReplayMismatch" in replayed.error
        assert client.journal.get(waiting)["status"] == "waiting"

    assert effects == [("left", "right")]


def test_activity_keyword_order_unchanged_resumes_successfully(tmp_path):
    effects = []

    @activity(name="calculate")
    def calculate(**values):
        effects.append(tuple(values))
        return "saved"

    @workflow(name="same-activity-keyword-order-job")
    def first():
        calculate(left=1, right=2)
        return ask_human("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(first, run_id="same-activity-keyword-order")

        @workflow(name="same-activity-keyword-order-job")
        def second():
            calculate(left=1, right=2)
            return ask_human("Continue?")

        replayed = client.resume(paused.run_id, workflow=second, answer="yes")

    assert replayed.ok, replayed.error
    assert replayed.value == "yes"
    assert effects == [("left", "right")]


def test_child_keyword_order_change_rejects_before_answer_and_effects(tmp_path):
    effects = []

    @workflow(name="keyword-child")
    def child(**values):
        answer = ask_human("Continue?")
        effects.append((tuple(values), answer))
        return answer

    @workflow(name="child-keyword-order-job")
    def first():
        return child(left=1, right=2)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(first, run_id="child-keyword-order")
        assert paused.status == "awaiting_input"
        waiting = paused.pending_input["operation_id"]

        @workflow(name="child-keyword-order-job")
        def second():
            return child(right=2, left=1)

        replayed = client.resume(paused.run_id, workflow=second, answer="yes")

        assert replayed.status == "failed"
        assert "ReplayMismatch" in replayed.error
        assert client.journal.get(waiting)["status"] == "waiting"

    assert effects == []


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
        ask_human("Continue?")
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
        return ask_human("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job, run_id="parallel-binding")
        selected = partial(branch, 2)
        replayed = client.resume(paused.run_id, workflow=job, answer="yes")

    assert replayed.status == "failed"
    assert "ReplayMismatch" in replayed.error


def test_pending_partial_preserves_explicit_callable_data_state(tmp_path, monkeypatch):
    calls = []

    def branch(callback):
        ask_human("Continue?")
        return callback()

    selected = partial(branch, _BoundCallback(1))

    @workflow(name="callable-data-job")
    def job():
        return parallel(selected)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        first = client.run(job, run_id="same-callable-data")
        assert first.status == "awaiting_input"

        def revised(callback):
            calls.append(callback.amount)
            return callback.amount + 100

        monkeypatch.setattr(_BoundCallback, "__call__", revised)
        selected = partial(branch, _BoundCallback(1))
        same_state = client.resume(first.run_id, workflow=job, answer="yes")
        assert same_state.ok, same_state.error
        assert same_state.value == [101]
        assert calls == [1]

        second = client.run(job, run_id="changed-callable-data")
        assert second.status == "awaiting_input"
        waiting = second.pending_input["operation_id"]
        selected = partial(branch, _BoundCallback(2))
        changed_state = client.resume(second.run_id, workflow=job, answer="yes")

        assert changed_state.status == "failed"
        assert "ReplayMismatch" in changed_state.error
        assert client.journal.get(waiting)["status"] == "waiting"
        assert calls == [1]


def test_pending_partial_keyword_order_change_is_rejected(tmp_path):
    def branch(**values):
        ask_human("Continue?")
        return list(values)

    selected = partial(branch, left=1, right=2)

    @workflow(name="keyword-order-job")
    def job():
        return parallel(selected)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job, run_id="keyword-order")
        assert paused.status == "awaiting_input"
        waiting = paused.pending_input["operation_id"]

        selected = partial(branch, right=2, left=1)
        replayed = client.resume(paused.run_id, workflow=job, answer="yes")

        assert replayed.status == "failed"
        assert "ReplayMismatch" in replayed.error
        assert client.journal.get(waiting)["status"] == "waiting"


def test_named_partial_child_retains_bound_inputs(tmp_path):
    def branch(value):
        ask_human("Continue?")
        return value

    selected = Workflow(partial(branch, 1), name="bound")

    @workflow(name="named-partial-job")
    def job():
        return selected()

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job, run_id="named-partial")
        assert paused.status == "awaiting_input"
        waiting = paused.pending_input["operation_id"]

        selected = Workflow(partial(branch, 2), name="bound")
        replayed = client.resume(paused.run_id, workflow=job, answer="yes")

        assert replayed.status == "failed"
        assert "ReplayMismatch" in replayed.error
        assert client.journal.get(waiting)["status"] == "waiting"


def test_partial_opaque_and_workflow_callbacks_remain_logical_references(tmp_path):
    def branch(callback):
        ask_human("Continue?")
        return callback()

    @workflow(name="bound-child")
    def child():
        return "workflow"

    selected = partial(branch, _OpaqueDataclassCallback(object()))

    @workflow(name="reference-binding-job")
    def job():
        return parallel(selected)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        opaque = client.run(job, run_id="opaque-binding")
        assert opaque.status == "awaiting_input"
        opaque = client.resume(opaque.run_id, workflow=job, answer="yes")
        assert opaque.ok, opaque.error
        assert opaque.value == ["opaque"]

        selected = partial(branch, child)
        workflow_callback = client.run(job, run_id="workflow-binding")
        assert workflow_callback.status == "awaiting_input"
        workflow_callback = client.resume(
            workflow_callback.run_id, workflow=job, answer="yes"
        )
        assert workflow_callback.ok, workflow_callback.error
        assert workflow_callback.value == ["workflow"]


def test_recorded_inputs_must_match_their_replay_fingerprint(tmp_path):
    @activity(name="calculate")
    def calculate(value):
        return value

    @workflow(name="integrity-job")
    def job():
        calculate(1)
        return ask_human("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job, run_id="input-integrity")
        operation = client.journal.operations(paused.run_id)[0]
        run_folder = Path(client.journal.run(paused.run_id)["folder"])
        operation_id = operation["id"]

    def change_inputs(record):
        inputs = record["data"]["operation"]["inputs"]
        decoded = codec.decode(inputs)
        decoded["args"] = (2,)
        record["data"]["operation"]["inputs"] = codec.encode(decoded)

    _rewrite_ledger_record(
        run_folder,
        operation_id=operation_id,
        event="operation_started",
        update=change_inputs,
    )
    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
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
        return ask_human("Continue?")

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
            return ask_human("Continue?")

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
            return ask_human("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job, run_id="slot-layout")
        operation = client.journal.operations(paused.run_id)[0]
        run_folder = Path(client.journal.run(paused.run_id)["folder"])
        operation_id = operation["id"]

    def change_error_layout(record):
        record["data"]["error"]["slots"] = []

    _rewrite_ledger_record(
        run_folder,
        operation_id=operation_id,
        event="operation_failed",
        update=change_error_layout,
    )
    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        with pytest.raises(ReplayMismatch, match="slots no longer match"):
            client.resume(paused.run_id, workflow=job, answer="yes")
