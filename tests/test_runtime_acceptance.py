"""Adversarial checks across the journal, runtime and provider boundary."""

from __future__ import annotations

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import BaseModel

from botpipe import (
    Artifact,
    Botpipe,
    RunBusy,
    Provider,
    Session,
    UncertainOperation,
    activity,
    aparallel,
    ask_human,
    parallel,
    workflow,
)
from botpipe.providers import FakeProvider, ProviderResponse
from botpipe.recovery import Stopped


class Decision(BaseModel):
    accepted: bool


class DomainRejection(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(code, message)


def test_runtime_rejects_secret_bearing_policy_before_journal_creation(tmp_path):
    from botpipe import ConfigurationError, Policy

    with pytest.raises(ConfigurationError, match="credential"):
        Botpipe(
            tmp_path,
            provider=None,
            policy=Policy(base_url="https://user:password@example.org"),
        )
    assert not (tmp_path / ".botpipe-v2" / "state.sqlite3").exists()


def _acceptance_transform(value):
    return value + 1


def _acceptance_changed_transform(value):
    return value + 100


@workflow
def _comprehension_workflow():
    return tuple(_acceptance_transform(index) for index in range(2))


def test_saved_provider_response_survives_process_restart_before_completion(
    tmp_path, monkeypatch
):
    """Crash after durable receipt, before typed value/artifact commit."""

    def produce(request):
        request.artifacts["report"].write_text("original report")
        return ProviderResponse(
            '{"accepted":true}', "conversation-7", {"input_tokens": 9}
        )

    @workflow
    def report():
        return Provider().run(
            "prepare report",
            returns=Decision,
            writes=[Artifact.text("report.txt", required=True)],
        )

    first = Botpipe(tmp_path, provider=FakeProvider([produce]))
    original_finish = first.journal.finish

    def crash_at_provider_commit(operation_id, value):
        if first.journal.get(operation_id)["kind"] == "provider":
            raise SystemExit("simulated process loss")
        return original_finish(operation_id, value)

    monkeypatch.setattr(first.journal, "finish", crash_at_provider_commit)
    with pytest.raises(SystemExit):
        first.run(report, run_id="receipt-crash")
    assert len(first.provider.calls) == 1
    assert first.journal.operations("receipt-crash")[-1]["status"] == "response"
    first.close()

    provider = FakeProvider([])
    with Botpipe(tmp_path, provider=provider) as restarted:
        recovered = restarted.resume("receipt-crash", workflow=report)
        assert recovered.ok, recovered.error
        assert recovered.value.value == Decision(accepted=True)
        assert recovered.value.artifacts["report"].read_text() == "original report"
        assert recovered.usage == {"input_tokens": 9}
        assert provider.calls == []
        replayed = restarted.resume("receipt-crash", workflow=report)
        assert replayed.ok
        assert replayed.usage == {"input_tokens": 9}
        assert provider.calls == []


def test_interrupted_unsafe_activity_requires_reconciliation_and_accepts_observed_result(
    tmp_path,
):
    effects = []

    @activity(retry_safe=False)
    def charge():
        effects.append("charged")
        raise SystemExit("lost after external effect")

    @workflow
    def checkout():
        return {"receipt": charge()}

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        with pytest.raises(SystemExit):
            client.run(checkout, run_id="charge-crash")
        interrupted = client.resume("charge-crash", workflow=checkout)
        assert interrupted.status == "interrupted"
        assert effects == ["charged"]
        operation = client.journal.operations("charge-crash")[0]
        client.resolve("charge-crash", operation["id"], response="receipt-verified")
        recovered = client.resume("charge-crash", workflow=checkout)
        assert recovered.ok, recovered.error
        assert recovered.value == {"receipt": "receipt-verified"}
        assert effects == ["charged"]


def test_explicit_retry_of_interrupted_unsafe_activity_is_recorded_and_replayed_once(
    tmp_path,
):
    effects = []

    @activity(retry_safe=False)
    def submit():
        effects.append("attempt")
        if len(effects) == 1:
            raise SystemExit("simulated crash")
        return "accepted"

    @workflow
    def submission():
        return submit()

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        with pytest.raises(SystemExit):
            client.run(submission, run_id="retry-crash")
        operation = client.journal.operations("retry-crash")[0]
        client.resolve("retry-crash", operation["id"], retry=True)
        resumed = client.resume("retry-crash", workflow=submission)
        assert resumed.ok, resumed.error
        assert resumed.value == "accepted"
        assert client.resume("retry-crash", workflow=submission).ok
        assert effects == ["attempt", "attempt"]
        assert any(
            event["event"] == "operation_reconciled"
            for event in client.inspect("retry-crash")["events"]
        )


def test_provider_reconciliation_preserves_session_for_following_turn(tmp_path):
    @workflow
    def conversation():
        session = Session()
        first = Provider(session=session).run("first").value
        second = Provider(session=session).run("second").value
        return first, second

    provider = FakeProvider([SystemExit("response lost"), "second result"])
    provider.recover = lambda request: Stopped("test observed callback is quiescent")
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit):
            client.run(conversation, run_id="session-crash")
        operation = next(
            row
            for row in client.journal.operations("session-crash")
            if row["kind"] == "provider"
        )
        client.resolve(
            "session-crash",
            operation["id"],
            response=ProviderResponse("first result", "reconciled-session"),
        )
        recovered = client.resume("session-crash", workflow=conversation)
        assert recovered.ok, recovered.error
        assert recovered.value == ("first result", "second result")
        assert len(provider.calls) == 2
        assert provider.calls[-1].session_id == "reconciled-session"


def test_nested_input_rebuilds_locals_without_repeating_completed_effects(tmp_path):
    effects = []

    @activity
    def remember(label):
        effects.append(label)
        return label.upper()

    @workflow
    def child():
        before = remember("child-before")
        approved = ask_human("Approve?", returns=bool)
        return before, approved, remember("child-after")

    @workflow
    def parent():
        before = remember("parent-before")
        return before, child(), remember("parent-after")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(parent)
        assert paused.status == "awaiting_input", paused.error
        assert effects == ["parent-before", "child-before"]
        still_paused = client.resume(paused.run_id, workflow=parent)
        assert still_paused.status == "awaiting_input"
        assert effects == ["parent-before", "child-before"]
        completed = client.answer(paused.run_id, paused.pending_input["operation_id"], True, workflow=parent)
        assert completed.ok, completed.error
        assert completed.value == (
            "PARENT-BEFORE",
            ("CHILD-BEFORE", True, "CHILD-AFTER"),
            "PARENT-AFTER",
        )
        assert effects == [
            "parent-before",
            "child-before",
            "child-after",
            "parent-after",
        ]
        assert client.resume(paused.run_id, workflow=parent).value == completed.value
        assert len(effects) == 4


def test_parallel_completed_branch_is_not_repeated_when_other_branch_pauses(tmp_path):
    effects = []

    @activity
    def effect(label):
        effects.append(label)
        return label

    def review():
        before = effect("review-started")
        return before, ask_human("Review note?")

    @workflow
    def job():
        return parallel(lambda: effect("built"), review)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(job)
        assert paused.status == "awaiting_input", paused.error
        assert sorted(effects) == ["built", "review-started"]
        resumed = client.answer(
            paused.run_id,
            paused.pending_input["operation_id"],
            "approved",
            workflow=job,
        )
        assert resumed.ok, resumed.error
        assert resumed.value == ["built", ("review-started", "approved")]
        assert sorted(effects) == ["built", "review-started"]


def test_parallel_human_requests_are_individually_targeted(tmp_path):
    @workflow
    def approvals():
        return parallel(
            lambda: ask_human("First?"),
            lambda: ask_human("Second?"),
        )

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(approvals)
        pending = client.pending(paused.run_id)
        assert {item["question"] for item in pending} == {"First?", "Second?"}

        first = client.answer(
            paused.run_id, pending[0]["operation_id"], "one", workflow=approvals
        )
        assert first.status == "awaiting_input"
        remaining = client.pending(paused.run_id)
        assert len(remaining) == 1
        completed = client.answer(
            paused.run_id,
            remaining[0]["operation_id"],
            "two",
            workflow=approvals,
        )
        assert completed.ok
        assert set(completed.value) == {"one", "two"}


def test_aparallel_preserves_order_for_sync_and_async_branches(tmp_path):
    async def later():
        await asyncio.sleep(0)
        return "async"

    @workflow
    async def composed():
        return await aparallel(lambda: "sync", later)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        result = asyncio.run(client.arun(composed))
        assert result.ok, result.error
        assert result.value == ["sync", "async"]
        replay = asyncio.run(client.aresume(result.run_id, workflow=composed))
        assert replay.value == result.value


def test_operation_budget_blocks_new_effects_and_does_not_reset_on_resume(tmp_path):
    effects = []

    @activity
    def effect(value):
        effects.append(value)
        return value

    @workflow
    def bounded():
        return [effect(index) for index in range(3)]

    with Botpipe(tmp_path, provider=FakeProvider([]), max_operations=2) as client:
        result = client.run(bounded)
        assert result.status == "budget_exceeded"
        assert effects == [0, 1]
        client.max_operations = 100
        replay = client.resume(result.run_id, workflow=bounded)
        assert replay.status == "budget_exceeded"
        assert effects == [0, 1]
        assert len(client.journal.operations(result.run_id)) == 2


def test_version_change_does_not_invalidate_recorded_effects(tmp_path):
    effects = []

    @activity
    def effect():
        effects.append("ran")

    @workflow(version="1")
    def versioned():
        effect()
        return ask_human("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        paused = client.run(versioned)
        versioned.version = "2"
        resumed = client.answer(paused.run_id, paused.pending_input["operation_id"], "yes", workflow=versioned)
        assert resumed.ok, resumed.error
        assert effects == ["ran"]
        assert client.journal.run(paused.run_id)["status"] == "completed"


def test_replay_rejects_changed_operation_even_when_mutable_closure_changed(tmp_path):
    settings = {"label": "first"}
    effects = []

    @activity
    def effect(label):
        effects.append(label)

    @workflow
    def job():
        effect(settings["label"])
        return ask_human("Continue?")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        result = client.run(job)
        settings["label"] = "different"
        replay = client.resume(result.run_id, workflow=job)
        assert replay.status == "failed"
        assert "ReplayMismatch" in replay.error
        assert effects == ["first"]


def test_async_children_activities_and_provider_turns_replay_under_arun(tmp_path):
    effects = []

    @activity
    async def record():
        await asyncio.sleep(0)
        effects.append("recorded")
        return 4

    @workflow
    async def child():
        count = await record()
        reply = await Provider().arun("report")
        return count, reply.value

    @workflow
    async def parent():
        return await child()

    provider = FakeProvider(["done"])
    with Botpipe(tmp_path, provider=provider) as client:
        result = asyncio.run(client.arun(parent))
        assert result.ok, result.error
        assert result.value == (4, "done")
        replay = asyncio.run(client.aresume(result.run_id, workflow=parent))
        assert replay.ok, replay.error
        assert replay.value == result.value
        assert effects == ["recorded"]
        assert len(provider.calls) == 1


def test_validation_repair_uses_new_recorded_turn_and_survives_replay(tmp_path):
    @workflow
    def typed():
        return Provider().run("decide", returns=Decision).value

    provider = FakeProvider(
        [ProviderResponse("invalid JSON", "dialogue"), {"accepted": True}]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        completed = client.run(typed)
        assert completed.ok, completed.error
        assert completed.value == Decision(accepted=True)
        assert len(provider.calls) == 2
        assert provider.calls[1].session_id == "dialogue"
        assert "Repair the previous output contract failure" in provider.calls[1].prompt
        replay = client.resume(completed.run_id, workflow=typed)
        assert replay.ok, replay.error
        assert replay.value == completed.value
        assert len(provider.calls) == 2
        rows = [
            row
            for row in client.inspect(completed.run_id)["operations"]
            if row["kind"] == "provider"
        ]
        assert [row["status"] for row in rows] == ["completed"]
        assert len(rows[0]["response"]["repairs"]) == 1
        assert rows[0]["response"]["repairs"][0]["output_error"]["retryable"]


def test_reconciliation_can_supply_none_as_an_activity_result(tmp_path):
    effects = []

    @activity(retry_safe=False)
    def send():
        effects.append("sent")
        raise SystemExit("connection lost after send")

    @workflow
    def job():
        send()
        return "finished"

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        with pytest.raises(SystemExit):
            client.run(job, run_id="void-effect")
        operation = client.journal.operations("void-effect")[0]
        client.resolve("void-effect", operation["id"], response=None)
        assert client.resume("void-effect", workflow=job).value == "finished"
        assert effects == ["sent"]


@pytest.mark.parametrize("different_state_dir", [False, True])
def test_unresolved_provider_fences_entire_workspace_across_runs(
    tmp_path, different_state_dir
):
    @workflow
    def interrupted():
        return Provider().run("edit workspace").value

    @workflow
    def replacement():
        return Provider().run("more edits").value

    with Botpipe(
        tmp_path, provider=FakeProvider([SystemExit("orphan may be editing")])
    ) as first:
        with pytest.raises(SystemExit):
            first.run(interrupted, run_id="orphan-owner")
        state_dir = tmp_path / "different-state" if different_state_dir else None
        provider = FakeProvider(["replacement complete"])
        with Botpipe(tmp_path, provider=provider, state_dir=state_dir) as other:
            with pytest.raises(RunBusy, match="unresolved"):
                other.run(replacement, run_id="replacement-blocked")
            assert provider.calls == []
            operation = next(
                row
                for row in first.journal.operations("orphan-owner")
                if row["kind"] == "provider"
            )
            first.provider.recover = lambda request: Stopped(
                "test observed callback is quiescent"
            )
            first.resolve(
                "orphan-owner",
                operation["id"],
                response=ProviderResponse("verified stopped and completed"),
            )
            completed = other.run(replacement, run_id="replacement-allowed")
            assert completed.ok, completed.error
            assert len(provider.calls) == 1


def test_repeated_async_cancellation_waits_until_effectful_worker_finishes(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    completed = threading.Event()

    def provider_turn(request):
        entered.set()
        assert release.wait(timeout=5), "test did not release provider"
        completed.set()
        return "done"

    @workflow
    def job():
        return Provider().run("work").value

    async def scenario(client):
        task = asyncio.create_task(client.arun(job, run_id="cancelled-client"))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done()
            task.cancel()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not task.done(), (
                "cancellation escaped while provider still owned workspace"
            )
        finally:
            release.set()
            try:
                await task
            except asyncio.CancelledError:
                pass
        assert completed.is_set()
        assert client.journal.run("cancelled-client")["status"] == "interrupted"

    with Botpipe(tmp_path, provider=FakeProvider([provider_turn])) as client:
        asyncio.run(scenario(client))


def test_async_cancellation_remains_pending_until_delayed_run_binding(tmp_path):
    entered_definition = threading.Event()
    release_definition = threading.Event()

    @workflow
    def job():
        return "late"

    async def scenario(client):
        original = client._definition

        def delayed(value):
            entered_definition.set()
            assert release_definition.wait(5)
            return original(value)

        client._definition = delayed
        task = asyncio.create_task(client.arun(job, run_id="delayed-bind"))
        assert await asyncio.to_thread(entered_definition.wait, 2)
        task.cancel()
        await asyncio.sleep(0.35)
        assert not task.done()
        release_definition.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        asyncio.run(scenario(client))
        assert client.journal.run("delayed-bind")["status"] == "interrupted"


def test_async_cancellation_retries_unknown_without_escaping_worker(tmp_path):
    entered = threading.Event()
    release = threading.Event()
    exited = threading.Event()

    class InitiallyUnknown(FakeProvider):
        def __init__(self):
            super().__init__([self.turn])
            self.cancel_calls = 0

        def turn(self, request):
            entered.set()
            assert release.wait(5)
            exited.set()
            return "late"

        def cancel(self, operation_id):
            from botpipe.recovery import Unknown

            self.cancel_calls += 1
            if self.cancel_calls == 1:
                return Unknown("native ownership is still starting")
            release.set()
            return Stopped("stopped after ownership appeared")

    @workflow
    def job():
        return Provider(session=None).run("work").value

    async def scenario(client):
        task = asyncio.create_task(client.arun(job, run_id="unknown-cancel"))
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    native = InitiallyUnknown()
    with Botpipe(tmp_path, provider=native) as client:
        asyncio.run(scenario(client))
        assert native.cancel_calls == 2
        assert exited.is_set()


def test_async_cancellation_joins_driver_when_worker_cancels_itself():
    import asyncio
    import threading

    from botpipe.runtime import _async_call, _bind_async_cancellation

    bound = threading.Event()
    cancelling = threading.Event()
    release_worker = threading.Event()
    release_cancel = threading.Event()
    cancel_finished = threading.Event()

    class Runtime:
        def cancel(self, run_id):
            cancelling.set()
            assert release_cancel.wait(5)
            cancel_finished.set()

    def worker():
        _bind_async_cancellation(Runtime(), "self-cancelling")
        bound.set()
        assert release_worker.wait(5)
        raise asyncio.CancelledError()

    async def exercise():
        task = asyncio.create_task(_async_call(worker))
        try:
            assert await asyncio.to_thread(bound.wait, 5)
            task.cancel()
            assert await asyncio.to_thread(cancelling.wait, 5)
            release_worker.set()
            done, _ = await asyncio.wait((task,), timeout=0.1)
            assert not done, "caller returned before its cancellation driver finished"
            assert not cancel_finished.is_set()
        finally:
            release_worker.set()
            release_cancel.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert await asyncio.to_thread(cancel_finished.wait, 5)

    asyncio.run(exercise())


def test_durable_cancel_request_prevents_late_success_commit(tmp_path):
    entered = threading.Event()
    released = threading.Event()

    class Cancellable(FakeProvider):
        def cancel(self, operation_id):
            from botpipe.recovery import Stopped

            released.set()
            return Stopped("test callback released")

    def provider_turn(request):
        entered.set()
        assert released.wait(timeout=5)
        return "finished while cancellation settled"

    @workflow
    def job():
        return Provider(session=None).run("work").value

    with Botpipe(tmp_path, provider=Cancellable([provider_turn])) as client:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(client.run, job, run_id="cancel-fence")
            assert entered.wait(timeout=2)
            cancelled = client.cancel("cancel-fence")
            result = future.result(timeout=5)
        assert cancelled["run"]["status"] == "interrupted"
        assert result.status == "interrupted"
        assert client.journal.run("cancel-fence")["status"] == "interrupted"


def test_direct_async_provider_cancellation_stops_owned_attempt(tmp_path):
    entered = threading.Event()
    released = threading.Event()
    exited = threading.Event()

    class NativeStop(FakeProvider):
        def cancel(self, operation_id):
            released.set()
            return Stopped("owned attempt stopped")

    def provider_turn(request):
        entered.set()
        assert released.wait(timeout=5)
        exited.set()
        return "late value"

    async def scenario(provider):
        task = asyncio.create_task(provider.agenerate("work"))
        assert await asyncio.to_thread(entered.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with Botpipe(tmp_path, provider=NativeStop([provider_turn])) as client:
        asyncio.run(scenario(Provider(runtime=client, session=None)))
        assert exited.is_set()
        [run] = client.runs()
        assert run["status"] == "interrupted"


def test_completed_run_ignores_global_helper_edits_inside_comprehensions(
    tmp_path, monkeypatch
):
    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        completed = client.run(_comprehension_workflow)
        assert completed.value == (1, 2)
        monkeypatch.setitem(
            _comprehension_workflow.fn.__globals__,
            "_acceptance_transform",
            _acceptance_changed_transform,
        )
        replayed = client.resume(completed.run_id, workflow=_comprehension_workflow)
        assert replayed.value == (1, 2)


def test_replayed_activity_exception_preserves_custom_type_and_constructor_args(
    tmp_path,
):
    effects = []

    @activity
    def rejected():
        effects.append("called")
        raise DomainRejection(409, "already exists")

    @workflow
    def job():
        try:
            rejected()
        except DomainRejection as error:
            return {"recovered": error.code}

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        completed = client.run(job)
        assert completed.ok, completed.error
        assert completed.value == {"recovered": 409}
        replay = client.resume(completed.run_id, workflow=job)
        assert replay.ok, replay.error
        assert replay.value == completed.value
        assert effects == ["called"]


@pytest.mark.parametrize("parallel_branch", [False, True])
def test_alternate_provider_workspace_excludes_independent_clients(
    tmp_path, parallel_branch
):
    origin, target = tmp_path / "origin", tmp_path / "target"
    origin.mkdir()
    target.mkdir()
    entered, release = threading.Event(), threading.Event()

    def hold_target(request):
        entered.set()
        assert release.wait(5), "test did not release provider"
        (request.workspace / "effect.txt").write_text("first owner's effect")
        return "edited"

    @workflow
    def owner():
        def edit():
            return Provider().run("edit alternate target", workspace=target).value

        return parallel(edit) if parallel_branch else edit()

    @workflow
    def contender():
        return Provider().run("edit direct target").value

    other_provider = FakeProvider(["must not dispatch"])
    with (
        Botpipe(origin, provider=FakeProvider([hold_target])) as first,
        Botpipe(target, provider=other_provider) as other,
    ):
        with ThreadPoolExecutor(max_workers=1) as executor:
            running = executor.submit(first.run, owner)
            try:
                assert entered.wait(2), "owner did not dispatch"
                with pytest.raises(RunBusy):
                    other.run(contender)
                assert other_provider.calls == []
            finally:
                release.set()
                result = running.result(timeout=5)
            assert result.ok, result.error


def test_interrupted_alternate_workspace_remains_fenced_after_owner_exits(tmp_path):
    origin, target = tmp_path / "origin", tmp_path / "target"
    origin.mkdir()
    target.mkdir()

    @workflow
    def owner():
        return Provider().run("edit alternate target", workspace=target).value

    @workflow
    def contender():
        return Provider().run("edit direct target").value

    with Botpipe(
        origin, provider=FakeProvider([SystemExit("provider may still own target")])
    ) as first:
        with pytest.raises(SystemExit):
            first.run(owner, run_id="alternate-owner")
        other_provider = FakeProvider(["after reconciliation"])
        with Botpipe(target, provider=other_provider) as other:
            with pytest.raises(RunBusy, match="unresolved"):
                other.run(contender)
            assert other_provider.calls == []
            operation = next(
                row
                for row in first.journal.operations("alternate-owner")
                if row["kind"] == "provider"
            )
            first.provider.recover = lambda request: Stopped(
                "test observed callback is quiescent"
            )
            first.resolve(
                "alternate-owner",
                operation["id"],
                response=ProviderResponse("verified stopped and completed"),
            )
            assert first.resume("alternate-owner", workflow=owner).ok
            assert other.run(contender).ok


def test_raw_reader_cannot_observe_alternate_workspace_with_unresolved_writer(
    tmp_path,
):
    origin, reader_origin, target = (
        tmp_path / "origin",
        tmp_path / "reader",
        tmp_path / "target",
    )
    origin.mkdir()
    reader_origin.mkdir()
    target.mkdir()
    (target / "input.txt").write_text("possibly being changed")

    @workflow
    def owner():
        return Provider().run("edit alternate target", workspace=target).value

    @workflow
    def reader():
        return Provider(session=None).generate(
            "inspect alternate target",
            workspace=target,
            reads=["input.txt"],
        ).value

    with Botpipe(
        origin, provider=FakeProvider([SystemExit("writer may still be active")])
    ) as first:
        with pytest.raises(SystemExit):
            first.run(owner, run_id="unresolved-alternate-writer")
        reader_provider = FakeProvider(["must not observe or dispatch"])
        with Botpipe(reader_origin, provider=reader_provider) as other:
            blocked = other.run(reader, run_id="blocked-alternate-reader")
            assert blocked.status == "failed"
            assert "unresolved" in blocked.error
            assert reader_provider.calls == []


def test_completed_root_does_not_reenter_changed_activity_call(
    tmp_path,
):
    settings = {"label": "original"}
    effects = []

    @activity(retry_safe=True, retries=1)
    def record(label):
        effects.append(label)
        return label

    @workflow
    def job():
        return record(settings["label"])

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        completed = client.run(job)
        assert completed.ok, completed.error
        settings["label"] = "changed"
        replay = client.resume(completed.run_id, workflow=job)
        assert replay.ok
        assert replay.value == "original"
        assert effects == ["original"]


def test_completed_root_does_not_enter_user_exception_handler_after_edit(tmp_path):
    settings = {"label": "original"}
    effects = []

    @activity
    def record(label):
        effects.append(label)
        return label

    @workflow
    def job():
        try:
            return record(settings["label"])
        except Exception:
            return record("fallback side effect")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        completed = client.run(job)
        settings["label"] = "changed"
        replay = client.resume(completed.run_id, workflow=job)
        assert replay.ok
        assert replay.value == "original"
        assert effects == ["original"]


def test_parallel_collect_does_not_commit_an_interrupted_branch_as_error_data(tmp_path):
    effects = []

    @activity(retry_safe=False)
    def interrupted():
        effects.append("effect reached")
        raise SystemExit("lost after side effect")

    @workflow
    def job():
        return parallel(interrupted, settle="collect")

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        with pytest.raises(SystemExit):
            client.run(job, run_id="collect-interrupted")
        operations = client.journal.operations("collect-interrupted")
        group = next(row for row in operations if row["kind"] == "parallel")
        effect = next(row for row in operations if row["kind"] == "activity")
        assert group["status"] == "started"
        client.resolve("collect-interrupted", effect["id"], response="observed receipt")
        recovered = client.resume("collect-interrupted", workflow=job)
        assert recovered.ok, recovered.error
        assert recovered.value == ["observed receipt"]
        assert effects == ["effect reached"]


@pytest.mark.parametrize("settle", ["all", "collect"])
def test_parallel_replay_mismatch_cannot_be_committed_as_branch_error(
    tmp_path, monkeypatch, settle
):
    settings = {"label": "original"}
    effects = []

    @activity(retry_safe=True)
    def branch(label):
        effects.append(label)
        if label == "failure":
            raise ValueError("ordinary branch failure")
        return label

    @workflow
    def job():
        return parallel(
            lambda: branch("failure"),
            lambda: branch(settings["label"]),
            settle=settle,
        )

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        method = "fail" if settle == "all" else "finish"
        original = getattr(client.journal, method)

        def crash_parent(operation_id, record):
            if client.journal.get(operation_id)["kind"] == "parallel":
                raise SystemExit("crash before parent commit")
            return original(operation_id, record)

        monkeypatch.setattr(client.journal, method, crash_parent)
        with pytest.raises(SystemExit):
            client.run(job, run_id="parallel-mismatch")
        monkeypatch.setattr(client.journal, method, original)
        settings["label"] = "changed"

        for _ in range(2):
            replay = client.resume("parallel-mismatch", workflow=job)
            assert replay.status == "failed"
            assert "ReplayMismatch" in replay.error
            group = next(
                row
                for row in client.journal.operations(replay.run_id)
                if row["kind"] == "parallel"
            )
            assert group["status"] == "started"

    assert sorted(effects) == ["failure", "original"]


@pytest.mark.parametrize("through_parallel_child", [False, True])
def test_caught_uncertain_writer_fences_later_same_run_reads(
    tmp_path, through_parallel_child
):
    target = tmp_path / "branch" if through_parallel_child else tmp_path
    target.mkdir(exist_ok=True)
    destination = target / "state.txt"

    def uncertain_write(request):
        request.artifacts["state"].write_text("uncertain mutation")
        raise RuntimeError("provider outcome is unknown")

    def forbidden_observation(request):
        raise AssertionError("same-run read provider must not dispatch")

    provider = FakeProvider([uncertain_write, forbidden_observation])

    def write():
        return Provider(session=None).run(
            "edit state",
            workspace=target,
            writes=(Artifact.text(destination, required=True),),
        )

    @workflow
    def writer():
        return write()

    @workflow
    def job():
        try:
            if through_parallel_child:
                parallel(lambda: writer())
            else:
                write()
        except UncertainOperation:
            pass
        try:
            Provider(session=None).query(
                "observe state", workspace=target, reads=(destination,)
            )
        except UncertainOperation:
            pass
        return "application tried to suppress the fence"

    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(job)
        assert result.status == "interrupted", result.error
        assert "provider outcome is unknown" in result.error
        assert len(provider.calls) == 1
        assert destination.read_text() == "uncertain mutation"
        operations = client.journal.operations(result.run_id)
        assert len([row for row in operations if row["kind"] == "provider"]) == 1
        assert not [row for row in operations if row["kind"] == "read"]
