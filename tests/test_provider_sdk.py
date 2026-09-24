from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel

from botpipe import Botpipe, Provider, Session, StreamEvent
from botpipe.policy import NetworkMode, SandboxMode
from botpipe.providers import FakeProvider, ProviderResponse
from botpipe.recovery import Unknown


class Answer(BaseModel):
    count: int


def runtime(tmp_path: Path, fake: FakeProvider) -> Botpipe:
    return Botpipe(tmp_path, provider=fake, state_dir=tmp_path / "state")


def test_provider_is_lazy_and_with_config_shares_managed_session(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider = Provider(workspace=workspace)
    variant = provider.with_config(instructions="Be concise")

    assert list(workspace.iterdir()) == []
    assert provider.config == {"workspace": workspace}
    assert variant.config["instructions"] == "Be concise"
    assert provider.session is None
    assert variant.session is None


def test_retry_safety_is_configurable_and_defaults_true(tmp_path: Path):
    provider = Provider(workspace=tmp_path, retry_safe=False)

    assert provider.config["retry_safe"] is False
    assert provider.with_config(retry_safe=True).config["retry_safe"] is True
    with pytest.raises(TypeError, match="retry_safe"):
        Provider(retry_safe=1)


def test_direct_calls_are_durable_and_continue_one_thread(tmp_path: Path):
    fake = FakeProvider(
        [
            ProviderResponse("first", "thread-1", {"tokens": 1}, {"turn_id": "a"}),
            ProviderResponse("second", "thread-1", {"tokens": 2}, {"turn_id": "b"}),
        ]
    )
    provider = Provider(runtime=runtime(tmp_path, fake))

    first = provider.run("first")
    second = provider.with_config(instructions="continue").run("second")

    assert first.value == "first"
    assert first.run_id and first.operation_id.startswith(first.run_id)
    assert first.metadata == {"turn_id": "a"}
    assert second.value == "second"
    assert [call.session_id for call in fake.calls] == [None, "thread-1"]
    assert fake.calls[1].instructions == "continue"


def test_query_and_generate_apply_fixed_safe_presets(tmp_path: Path):
    fake = FakeProvider(["query", "generate"])
    provider = Provider(
        runtime=runtime(tmp_path, fake),
        sandbox="full-access",
        network=True,
    )

    provider.query("inspect", tools=["web_search"], session=None)
    provider.generate("draft", allowed_tools=["web_search"], session=None)

    query, generate = fake.calls
    assert query.preset == "query"
    assert query.policy.sandbox_mode is SandboxMode.READ_ONLY
    assert query.policy.network is NetworkMode.NONE
    assert query.tools == ("web_search",)
    assert generate.preset == "generate"
    assert generate.policy.sandbox_mode is SandboxMode.READ_ONLY
    assert generate.policy.network is NetworkMode.NONE
    assert generate.tools == ("web_search",)


@pytest.mark.parametrize("preset", ["run", "query", "generate"])
@pytest.mark.parametrize("independent", [False, True])
def test_typed_repairs_continue_same_thread_and_charge_all_usage(
    tmp_path: Path, preset: str, independent: bool
):
    fake = FakeProvider(
        [
            ProviderResponse("not-json", "thread-1", {"tokens": 3}),
            ProviderResponse('{"count": 2}', "thread-1", {"tokens": 5}),
            ProviderResponse("next call", "thread-2" if independent else "thread-1"),
        ]
    )
    provider = Provider(
        runtime=runtime(tmp_path, fake),
        session=None if independent else Session.task("typed"),
    )

    call = getattr(provider, preset)
    result = call("count", returns=Answer, output_retries=1)

    assert result.value == Answer(count=2)
    assert result.usage == {"tokens": 8}
    assert [call.session_id for call in fake.calls] == [None, "thread-1"]
    assert call("next").value == "next call"
    assert fake.calls[-1].session_id == (None if independent else "thread-1")


@pytest.mark.parametrize("preset", ["run", "query", "generate"])
def test_independent_repair_restores_thread_on_resume(tmp_path: Path, preset: str):
    from botpipe import workflow

    fake = FakeProvider(
        [
            ProviderResponse("invalid", "thread-1", {"tokens": 3}),
            ProviderResponse('{"count": 2}', "thread-1", {"tokens": 5}),
        ]
    )

    @workflow
    def flow():
        return getattr(Provider(session=None), preset)(
            "count", returns=Answer, output_retries=1
        )

    with Botpipe(
        tmp_path, provider=fake, state_dir=tmp_path / "state", max_operations=1
    ) as client:
        first = client.run(flow)
        assert first.status == "budget_exceeded"
        assert len(fake.calls) == 1

        resumed = client.resume(first.run_id, workflow=flow, max_operations=2)
        assert resumed.ok, resumed.error
        assert resumed.value.value == Answer(count=2)
        assert resumed.value.usage == {"tokens": 8}
        assert [call.session_id for call in fake.calls] == [None, "thread-1"]


def test_session_none_is_independent_and_callback_is_best_effort(tmp_path: Path):
    def first(request):
        request.on_event(StreamEvent("progress", {"step": 1}))
        return ProviderResponse("a", "thread-a")

    def second(request):
        request.on_event(StreamEvent("progress", {"step": 2}))
        return ProviderResponse("b", "thread-b")

    fake = FakeProvider([first, second])
    provider = Provider(runtime=runtime(tmp_path, fake))
    events: list[StreamEvent] = []

    provider.run("a", session=None, on_event=events.append)
    provider.run(
        "b", session=None, on_event=lambda event: (_ for _ in ()).throw(RuntimeError())
    )

    assert [call.session_id for call in fake.calls] == [None, None]
    assert len(events) == 1
    assert events[0].type == "progress"


def test_one_provider_continues_across_nested_workflow_contexts(tmp_path: Path):
    from botpipe import workflow

    fake = FakeProvider(
        [ProviderResponse("parent", "thread-1"), ProviderResponse("child", "thread-1")]
    )
    provider = Provider()

    @workflow
    def child():
        return provider.query("child").value

    @workflow
    def parent():
        return provider.query("parent").value, child()

    outcome = runtime(tmp_path, fake).run(parent)

    assert outcome.value == ("parent", "child")
    assert [call.session_id for call in fake.calls] == [None, "thread-1"]


def test_explicit_session_continues_across_direct_runs(tmp_path: Path):
    fake = FakeProvider(
        [ProviderResponse("one", "thread-1"), ProviderResponse("two", "thread-1")]
    )
    shared = Session()
    provider = Provider(runtime=runtime(tmp_path, fake), session=shared)

    provider.query("one")
    provider.query("two")

    assert [call.session_id for call in fake.calls] == [None, "thread-1"]


def test_capability_failure_is_preserved_before_dispatch(tmp_path: Path):
    from botpipe.capabilities import CapabilityError

    class Capabilities:
        def require(self, preset):
            raise CapabilityError(f"missing {preset}")

    class Adapter:
        name = "fixture"
        calls = 0

        def probe(self):
            return Capabilities()

        def run(self, request):
            self.calls += 1
            raise AssertionError("must not dispatch")

        def recover(self, request):
            return Unknown("preflight rejected before dispatch")

    adapter = Adapter()
    provider = Provider(
        runtime=Botpipe(tmp_path, provider=adapter, state_dir=tmp_path / "state")
    )

    try:
        provider.query("inspect")
    except CapabilityError as exc:
        assert "missing query" in str(exc)
        assert exc.run_id
        assert exc.operation_id
    else:
        raise AssertionError("expected CapabilityError")
    assert adapter.calls == 0


def test_explicit_session_is_shared_by_two_direct_providers(tmp_path: Path):
    fake = FakeProvider(
        [ProviderResponse("one", "thread-1"), ProviderResponse("two", "thread-1")]
    )
    managed_runtime = runtime(tmp_path, fake)
    shared = Session()
    first = Provider(runtime=managed_runtime, session=shared)
    second = Provider(runtime=managed_runtime, session=shared)

    first.query("one")
    second.query("two")

    assert [call.session_id for call in fake.calls] == [None, "thread-1"]


def test_completed_turn_replay_emits_one_replayed_event(tmp_path: Path):
    from botpipe import ask_human, workflow

    fake = FakeProvider([ProviderResponse("done", "thread-1")])
    provider = Provider()
    events: list[StreamEvent] = []

    @workflow
    def flow():
        value = provider.query("inspect", on_event=events.append).value
        return value, ask_human("continue?")

    managed_runtime = runtime(tmp_path, fake)
    paused = managed_runtime.run(flow, run_id="callback-replay")
    assert paused.status == "awaiting_input"
    events.clear()

    resumed = managed_runtime.resume(
        paused.run_id,
        workflow=flow,
        answer="yes",
    )

    assert resumed.ok
    assert [(event.type, event.data["operation_id"]) for event in events] == [
        ("replayed", fake.calls[0].operation_id)
    ]
    assert len(fake.calls) == 1


def test_query_unknown_recovery_remains_unresolved(tmp_path: Path):
    from botpipe import workflow
    from botpipe.providers import ProviderInterruptedError
    from botpipe.recovery import Unknown

    class Adapter:
        name = "fixture"

        def __init__(self):
            self.calls = []

        def run(self, request):
            self.calls.append(request)
            if len(self.calls) == 1:
                request.on_checkpoint({"session_id": "thread-1", "preset": "query"})
                raise ProviderInterruptedError("lost turn acknowledgement")
            return ProviderResponse("recovered", "thread-1")

        def recover(self, request):
            return Unknown("turn id was not durable")

    adapter = Adapter()

    @workflow
    def flow():
        return Provider().query("inspect").value

    managed_runtime = Botpipe(tmp_path, provider=adapter, state_dir=tmp_path / "state")
    first = managed_runtime.run(flow, run_id="safe-retry")
    assert first.status == "interrupted"

    resumed = managed_runtime.resume(first.run_id, workflow=flow)

    assert resumed.status == "interrupted"
    assert [call.attempt for call in adapter.calls] == [1]


@pytest.mark.parametrize("preset", ["run", "query", "generate"])
def test_stopped_provider_attempt_retries_once_on_resume(
    tmp_path: Path, preset: str
):
    from botpipe import workflow
    from botpipe.providers import ProviderError

    fake = FakeProvider([ProviderError("stopped"), "recovered"])

    @workflow
    def flow():
        return getattr(Provider(), preset)("work").value

    managed_runtime = runtime(tmp_path, fake)
    first = managed_runtime.run(flow, run_id=f"stopped-{preset}")
    assert first.status == "interrupted"

    resumed = managed_runtime.resume(first.run_id, workflow=flow)

    assert resumed.value == "recovered"
    assert [call.attempt for call in fake.calls] == [1, 2]
    assert fake.calls[1].deadline is not None


def test_each_resume_dispatches_at_most_one_stopped_replacement(tmp_path: Path):
    from botpipe import workflow
    from botpipe.providers import ProviderError

    fake = FakeProvider(
        [ProviderError("first stopped"), ProviderError("second stopped"), "done"]
    )

    @workflow
    def flow():
        return Provider().run("work").value

    managed_runtime = runtime(tmp_path, fake)
    first = managed_runtime.run(flow, run_id="one-replacement")
    second = managed_runtime.resume(first.run_id, workflow=flow)

    assert second.status == "interrupted"
    assert [call.attempt for call in fake.calls] == [1, 2]

    third = managed_runtime.resume(first.run_id, workflow=flow)
    assert third.value == "done"
    assert [call.attempt for call in fake.calls] == [1, 2, 3]


def test_timeout_does_not_retry_until_a_later_resume(tmp_path: Path):
    from botpipe import workflow
    from botpipe.providers import ProviderTimeoutError
    from botpipe.recovery import Stopped

    class Adapter:
        name = "fixture"

        def __init__(self):
            self.calls = []

        def run(self, request):
            self.calls.append(request)
            if len(self.calls) == 1:
                raise ProviderTimeoutError("attempt timed out")
            return ProviderResponse("done")

        def recover(self, request):
            return Stopped("timed-out attempt is stopped")

    adapter = Adapter()

    @workflow
    def flow():
        return Provider().run("work").value

    managed_runtime = Botpipe(tmp_path, provider=adapter, state_dir=tmp_path / "state")
    first = managed_runtime.run(flow, run_id="timeout-resume")

    assert first.status == "interrupted"
    assert len(adapter.calls) == 1

    resumed = managed_runtime.resume(first.run_id, workflow=flow)
    assert resumed.value == "done"
    assert len(adapter.calls) == 2
    assert adapter.calls[1].deadline is not None


@pytest.mark.parametrize(
    ("recorded_safe", "current_safe"), [(False, True), (True, False)]
)
def test_automatic_provider_retry_requires_recorded_and_current_safety(
    tmp_path: Path, recorded_safe: bool, current_safe: bool
):
    from botpipe import workflow
    from botpipe.providers import ProviderError

    fake = FakeProvider([ProviderError("stopped"), "must not run"])

    @workflow(name="provider-safety-flow")
    def first_flow():
        return Provider().run("work", retry_safe=recorded_safe).value

    managed_runtime = runtime(tmp_path, fake)
    first = managed_runtime.run(
        first_flow, run_id=f"provider-safety-{recorded_safe}-{current_safe}"
    )

    @workflow(name="provider-safety-flow")
    def second_flow():
        return Provider().run("work", retry_safe=current_safe).value

    resumed = managed_runtime.resume(first.run_id, workflow=second_flow)

    assert resumed.status == "interrupted"
    assert len(fake.calls) == 1


def test_operator_retry_overrides_unknown_recovery(tmp_path: Path):
    from botpipe import workflow
    from botpipe.providers import ProviderInterruptedError
    from botpipe.recovery import Unknown

    class Adapter:
        name = "fixture"

        def __init__(self):
            self.calls = []

        def run(self, request):
            self.calls.append(request)
            if len(self.calls) == 1:
                raise ProviderInterruptedError("unknown result")
            return ProviderResponse("operator retry")

        def recover(self, request):
            return Unknown("no durable native turn id")

    adapter = Adapter()

    @workflow
    def flow():
        return Provider().run("work").value

    managed_runtime = Botpipe(tmp_path, provider=adapter, state_dir=tmp_path / "state")
    first = managed_runtime.run(flow, run_id="operator-unknown")
    operation = next(
        row
        for row in managed_runtime.journal.operations(first.run_id)
        if row["kind"] == "provider"
    )
    managed_runtime.resolve(first.run_id, operation["id"], retry=True)

    resumed = managed_runtime.resume(first.run_id, workflow=flow)

    assert resumed.value == "operator retry"
    assert [call.attempt for call in adapter.calls] == [1, 2]


def test_safety_tightening_blocks_saved_automatic_retry_until_operator_override(
    tmp_path: Path,
):
    from botpipe import workflow
    from botpipe.provider_checkpoints import ProviderCheckpoint, ProviderLifecycle
    from botpipe.providers import ProviderError

    fake = FakeProvider([ProviderError("stopped"), "operator retry"])

    @workflow(name="saved-automatic-retry")
    def first_flow():
        return Provider().run("work", retry_safe=True).value

    managed_runtime = runtime(tmp_path, fake)
    first = managed_runtime.run(first_flow, run_id="saved-automatic-retry")
    operation = next(
        row
        for row in managed_runtime.journal.operations(first.run_id)
        if row["kind"] == "provider"
    )
    checkpoint = ProviderCheckpoint.from_record(operation["response"])
    automatic = ProviderLifecycle.authorize_retry(
        checkpoint, origin="automatic"
    )
    managed_runtime.journal.response(operation["id"], automatic.to_record())

    @workflow(name="saved-automatic-retry")
    def tightened_flow():
        return Provider().run("work", retry_safe=False).value

    blocked = managed_runtime.resume(first.run_id, workflow=tightened_flow)
    assert blocked.status == "interrupted"
    assert len(fake.calls) == 1

    managed_runtime.resolve(first.run_id, operation["id"], retry=True)
    resumed = managed_runtime.resume(first.run_id, workflow=tightened_flow)

    assert resumed.value == "operator retry"
    assert len(fake.calls) == 2


def test_retry_unsafe_call_does_not_dispatch_new_output_repair(tmp_path: Path):
    fake = FakeProvider(
        [ProviderResponse("not-json", "thread-1"), ProviderResponse('{"count": 2}')]
    )
    provider = Provider(runtime=runtime(tmp_path, fake))

    with pytest.raises(ValueError):
        provider.run(
            "count", returns=Answer, output_retries=1, retry_safe=False
        )

    assert len(fake.calls) == 1


def test_recorded_unsafe_output_does_not_gain_repair_after_safety_change(
    tmp_path: Path,
):
    from botpipe import workflow

    fake = FakeProvider(
        [ProviderResponse("not-json", "thread-1"), ProviderResponse('{"count": 2}')]
    )

    @workflow(name="unsafe-repair")
    def first_flow():
        return Provider().run(
            "count", returns=Answer, output_retries=1, retry_safe=False
        )

    managed_runtime = runtime(tmp_path, fake)
    first = managed_runtime.run(first_flow, run_id="unsafe-repair")
    assert first.status == "failed"

    @workflow(name="unsafe-repair")
    def revised_flow():
        return Provider().run(
            "count", returns=Answer, output_retries=1, retry_safe=True
        )

    resumed = managed_runtime.resume(first.run_id, workflow=revised_flow)

    assert resumed.status == "failed"
    assert len(fake.calls) == 1


def test_tightened_safety_does_not_dispatch_started_repair(
    tmp_path: Path, monkeypatch
):
    import botpipe.operations as operations
    from botpipe import workflow

    fake = FakeProvider(
        [ProviderResponse("not-json", "thread-1"), ProviderResponse('{"count": 2}')]
    )

    @workflow(name="started-repair")
    def first_flow():
        return Provider().run(
            "count", returns=Answer, output_retries=1, retry_safe=True
        )

    original = operations._preflight_provider
    preflights = 0

    def crash_before_second_dispatch(adapter, request):
        nonlocal preflights
        preflights += 1
        if preflights == 2:
            raise SystemExit("before repair dispatch")
        return original(adapter, request)

    managed_runtime = runtime(tmp_path, fake)
    monkeypatch.setattr(operations, "_preflight_provider", crash_before_second_dispatch)
    with pytest.raises(SystemExit, match="before repair dispatch"):
        managed_runtime.run(first_flow, run_id="started-repair")
    monkeypatch.setattr(operations, "_preflight_provider", original)
    assert len(fake.calls) == 1

    @workflow(name="started-repair")
    def tightened_flow():
        return Provider().run(
            "count", returns=Answer, output_retries=1, retry_safe=False
        )

    resumed = managed_runtime.resume("started-repair", workflow=tightened_flow)

    assert resumed.status == "failed"
    assert len(fake.calls) == 1


def test_retry_safety_tightening_replays_completed_output_repair(tmp_path: Path):
    from botpipe import ask_human, workflow

    fake = FakeProvider(
        [ProviderResponse("not-json", "thread-1"), ProviderResponse('{"count": 2}')]
    )
    safety = [True]

    @workflow
    def flow():
        result = Provider().run(
            "count", returns=Answer, output_retries=1, retry_safe=safety[0]
        )
        ask_human("continue?")
        return result.value.count

    managed_runtime = runtime(tmp_path, fake)
    paused = managed_runtime.run(flow, run_id="repair-replay")
    assert paused.status == "awaiting_input"
    safety[0] = False

    resumed = managed_runtime.resume(paused.run_id, workflow=flow, answer="yes")

    assert resumed.value == 2
    assert len(fake.calls) == 2


def test_codex_retry_uses_supplied_thread_and_current_checkpoint(
    tmp_path: Path,
):
    from dataclasses import replace

    from botpipe.policy import Policy
    from botpipe.providers import CodexProvider, ProviderRequest

    class Adapter:
        def __init__(self):
            self.calls = []

        def start_turn(self, request, on_event=None):
            self.calls.append(request)
            if request.attempt == 1:
                request.on_checkpoint(
                    {"session_id": "thread-1", "profile_hash": "old-profile"}
                )
            return ProviderResponse("done", "thread-1")

        def close(self):
            pass

    adapter = Adapter()
    provider = CodexProvider(adapter=adapter)
    checkpoints = []
    request = ProviderRequest(
        operation_id="retry-thread",
        prompt="work",
        workspace=tmp_path,
        session_id=None,
        output_schema=None,
        policy=Policy(),
        artifacts={},
        timeout=10,
        preset="run",
        on_checkpoint=checkpoints.append,
    )
    provider.run(request)
    current_checkpoint = {"profile_hash": "current-profile"}
    provider.run(
        replace(
            request,
            session_id="thread-1",
            attempt=2,
            checkpoint=current_checkpoint,
        )
    )

    assert adapter.calls[1].session_id == "thread-1"
    assert adapter.calls[1].checkpoint == current_checkpoint
    assert checkpoints[-1]["status"] == "completed"


def test_stopped_policy_failure_preserves_capability_error(tmp_path: Path):
    from botpipe.providers import ProviderPolicyError
    from botpipe.recovery import Stopped

    class Adapter:
        name = "fixture"

        def run(self, request):
            raise ProviderPolicyError("disallowed tool: shell")

        def recover(self, request):
            return Stopped("turn interrupted and stopped")

    provider = Provider(
        runtime=Botpipe(tmp_path, provider=Adapter(), state_dir=tmp_path / "state")
    )

    try:
        provider.query("inspect", tools=["read_file"])
    except ProviderPolicyError as exc:
        assert "disallowed tool" in str(exc)
        assert exc.run_id and exc.operation_id
    else:
        raise AssertionError("expected ProviderPolicyError")


def test_cancelled_direct_call_stops_waiting_for_shared_session(tmp_path: Path):
    import asyncio
    import threading

    entered = threading.Event()
    release = threading.Event()

    def hold(request):
        entered.set()
        assert release.wait(3)
        return ProviderResponse("first", "thread-1")

    fake = FakeProvider([hold, ProviderResponse("second", "thread-1")])
    provider = Provider(runtime=runtime(tmp_path, fake), session=Session())

    async def scenario():
        first = asyncio.create_task(provider.aquery("first"))
        assert await asyncio.to_thread(entered.wait, 1)
        waiting = asyncio.create_task(provider.aquery("second"))
        await asyncio.sleep(0.05)
        waiting.cancel()
        try:
            await asyncio.wait_for(waiting, 0.5)
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("cancelled session waiter did not stop")
        release.set()
        assert (await first).value == "first"

    asyncio.run(scenario())
    assert len(fake.calls) == 1


def test_async_cancellation_keeps_worker_cleanup_failure_as_cause():
    import asyncio
    import threading

    from botpipe.runtime import _async_call

    started = threading.Event()
    release = threading.Event()

    def worker():
        started.set()
        release.wait(2)
        raise RuntimeError("cleanup failed")

    async def scenario():
        task = asyncio.create_task(_async_call(worker))
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        release.set()
        try:
            await task
        except asyncio.CancelledError as exc:
            assert isinstance(exc.__cause__, RuntimeError)
            assert str(exc.__cause__) == "cleanup failed"
        else:
            raise AssertionError("expected cancellation")

    asyncio.run(scenario())


def test_failed_preflight_preserves_artifacts_before_next_run(tmp_path: Path):
    from botpipe import Artifact
    from botpipe.capabilities import CapabilityError

    destination = tmp_path / "existing.txt"
    destination.write_text("original")

    class Capabilities:
        def require(self, preset):
            raise CapabilityError("missing run capability")

    class Adapter:
        name = "fixture"

        def probe(self):
            return Capabilities()

        def run(self, request):
            raise AssertionError("must not dispatch")

        def recover(self, request):
            return Unknown("preflight rejected before dispatch")

    first_runtime = Botpipe(
        tmp_path, provider=Adapter(), state_dir=tmp_path / "first-state"
    )
    try:
        Provider(runtime=first_runtime).run(
            "write", writes=[Artifact.text(destination)]
        )
    except CapabilityError:
        pass
    else:
        raise AssertionError("expected CapabilityError")

    assert destination.read_text() == "original"
    second_fake = FakeProvider(["available"])
    second = Provider(
        runtime=Botpipe(
            tmp_path, provider=second_fake, state_dir=tmp_path / "second-state"
        )
    ).run("write")
    assert second.value == "available"
