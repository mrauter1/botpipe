from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from botpipe import Botpipe, Provider, Session, StreamEvent
from botpipe.policy import NetworkMode, SandboxMode
from botpipe.providers import FakeProvider, ProviderResponse


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


def test_typed_repairs_continue_same_thread_and_charge_all_usage(tmp_path: Path):
    fake = FakeProvider(
        [
            ProviderResponse("not-json", "thread-1", {"tokens": 3}),
            ProviderResponse('{"count": 2}', "thread-1", {"tokens": 5}),
        ]
    )
    provider = Provider(runtime=runtime(tmp_path, fake), session=Session.task("typed"))

    result = provider.run("count", returns=Answer, output_retries=1)

    assert result.value == Answer(count=2)
    assert result.usage == {"tokens": 8}
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
            return None

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


def test_query_unknown_recovery_retries_same_thread(tmp_path: Path):
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

    assert resumed.value == "recovered"
    assert [call.attempt for call in adapter.calls] == [1, 2]
    assert adapter.calls[1].session_id == "thread-1"


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


def test_failed_preflight_restores_artifacts_and_clears_writer_fence(tmp_path: Path):
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
            return None

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


def test_read_only_run_still_obeys_workspace_fence(tmp_path: Path):
    from botpipe import WorkspaceUnresolved

    fake = FakeProvider(["must not dispatch"])
    managed_runtime = runtime(tmp_path, fake)
    with managed_runtime.workspace_turn(
        run_id="orphan", operation_id="uncertain-edit"
    ) as turn:
        turn.mark_unresolved("uncertain-edit")

    try:
        Provider(runtime=managed_runtime).run("inspect", sandbox="read-only")
    except WorkspaceUnresolved as exc:
        assert "orphan" in str(exc)
    else:
        raise AssertionError("read-only run bypassed the unresolved workspace fence")
    assert fake.calls == []
