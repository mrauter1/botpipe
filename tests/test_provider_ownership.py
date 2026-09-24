from __future__ import annotations

import sys
import threading
from dataclasses import replace

import pytest

from botpipe import (
    Artifact,
    Botpipe,
    Provider,
    Session,
    codec,
    provider_budget,
    workflow,
)
from botpipe.capabilities import CapabilityStatus, CodexCapabilities
from botpipe.policy import Policy
from botpipe.providers import (
    CodexProvider,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)
from botpipe.recovery import Completed, Stopped
from botpipe.session_bindings import SessionBinding


def request(
    tmp_path, *, operation_id="operation", session_key=None, operation_key=None
):
    checkpoints: list[dict] = []
    call = ProviderRequest(
        operation_id=operation_id,
        prompt="work",
        workspace=tmp_path,
        session_id=None,
        output_schema=None,
        policy=Policy(),
        artifacts={},
        timeout=2,
        session_key=session_key,
        operation_key=operation_key,
        on_checkpoint=checkpoints.append,
    )
    return call, checkpoints


class Adapter:
    def __init__(self, name: str, *, close_error: str | None = None):
        self.name = name
        self.close_error = close_error
        self.calls: list[ProviderRequest] = []
        self.recoveries: list[tuple[str, str]] = []
        self.closed = 0
        self.disposed = 0

    def start_turn(self, call, on_event=None):
        self.calls.append(call)
        call.on_checkpoint(
            {
                "status": "turn_intent",
                "session_id": self.name,
            }
        )
        call.on_checkpoint(
            {
                "status": "turn_acknowledged",
                "session_id": self.name,
                "turn_id": "turn",
            }
        )
        return ProviderResponse("done", self.name)

    def recover_turn(self, call, *, thread_id, turn_id):
        self.recoveries.append((thread_id, turn_id))
        return "completed", ProviderResponse("recovered", thread_id)

    def probe(self, *, deadline=None):
        return CodexCapabilities(
            executable=sys.executable,
            version="fixture",
            identity="fixture",
            methods=frozenset(),
            presets={name: CapabilityStatus(True) for name in ("run", "query", "generate")},
        )

    def dispose(self):
        self.disposed += 1
        if self.close_error:
            raise RuntimeError(self.close_error)

    def close(self):
        self.closed += 1
        if self.close_error:
            raise RuntimeError(self.close_error)


def test_concurrent_first_use_constructs_one_adapter_for_one_operation(tmp_path):
    constructing = threading.Event()
    release = threading.Event()
    created: list[Adapter] = []

    def factory():
        owner = Adapter(f"adapter-{len(created)}")
        created.append(owner)
        constructing.set()
        assert release.wait(30)
        return owner

    provider = CodexProvider(adapter_factory=factory)
    first, _ = request(tmp_path, operation_id="first", session_key="task:shared", operation_key="logical")
    second, _ = request(tmp_path, operation_id="second", session_key="task:shared", operation_key="logical")
    results: list[ProviderResponse] = []
    workers = [
        threading.Thread(target=lambda call=call: results.append(provider.run(call)))
        for call in (first, second)
    ]
    workers[0].start()
    assert constructing.wait(30)
    workers[1].start()
    release.set()
    for worker in workers:
        worker.join(timeout=30)

    assert all(not worker.is_alive() for worker in workers)
    assert len(created) == 1
    assert len(created[0].calls) == 2
    assert len(results) == 2


def test_capability_probe_cache_is_shared_without_starting_an_idle_server(
    tmp_path, monkeypatch
):
    import botpipe.codex_appserver as appserver

    probes = []
    capabilities = CodexCapabilities(
        executable=sys.executable,
        version="fixture",
        identity="fixture",
        methods=frozenset(),
    )

    def probe(*args, **kwargs):
        probes.append((args, kwargs))
        return capabilities

    monkeypatch.setattr(appserver, "probe_codex", probe)
    provider = CodexProvider(sys.executable)

    assert provider.probe() is capabilities
    assert provider.probe() is capabilities
    call, _ = request(tmp_path, session_key="task:probe")
    owner = provider._adapter_for(call)
    assert owner.probe() is capabilities

    assert len(probes) == 1
    assert provider._probe_adapter._process is None
    assert owner._process is None


def test_distinct_sessions_have_distinct_process_owners(tmp_path):
    created: list[Adapter] = []

    def factory():
        owner = Adapter(f"adapter-{len(created)}")
        created.append(owner)
        return owner

    provider = CodexProvider(adapter_factory=factory)
    for key in ("task:a", "task:b"):
        call, _ = request(tmp_path, operation_id=key, session_key=key)
        provider.run(call)

    assert len(created) == 2
    assert [owner.calls[0].session_key for owner in created] == ["task:a", "task:b"]
    provider.close()
    assert [owner.closed for owner in created] == [1, 1]


def test_independent_repairs_share_operation_owner_until_explicit_release(tmp_path):
    created: list[Adapter] = []

    def factory():
        owner = Adapter(f"adapter-{len(created)}")
        created.append(owner)
        return owner

    provider = CodexProvider(adapter_factory=factory)
    first, _ = request(tmp_path, operation_id="attempt-1", operation_key="logical")
    repair, _ = request(tmp_path, operation_id="attempt-2", operation_key="logical")
    later, _ = request(tmp_path, operation_id="later", operation_key="logical")

    provider.run(first)
    provider.run(repair)
    assert len(created) == 1
    provider.release_operation("logical")
    assert created[0].disposed == 1
    provider.run(later)
    assert len(created) == 2


def test_completed_response_checkpoint_is_durable_before_return(tmp_path):
    adapter = Adapter("thread")
    provider = CodexProvider(adapter=adapter)
    call, checkpoints = request(tmp_path, session_key="task:one")

    response = provider.run(call)

    assert response.text == "done"
    assert checkpoints[-1] == {
        "status": "completed",
        "response": response.to_record(),
    }


def test_recovery_uses_only_supplied_checkpoint(tmp_path):
    adapter = Adapter("thread")
    provider = CodexProvider(adapter=adapter)
    call, checkpoints = request(tmp_path, session_key="task:one")

    assert isinstance(provider.recover(call), Stopped)
    completed = provider.recover(
        replace(
            call,
            checkpoint={
                "status": "completed",
                "response": ProviderResponse("from ledger", "thread").to_record(),
            },
        )
    )
    assert isinstance(completed, Completed)
    assert completed.response.text == "from ledger"
    assert adapter.recoveries == []

    recovered = provider.recover(
        replace(
            call,
            checkpoint={
                "status": "turn_acknowledged",
                "session_id": "thread",
                "turn_id": "turn",
            },
        )
    )
    assert isinstance(recovered, Completed)
    assert recovered.response.text == "recovered"
    assert adapter.recoveries == [("thread", "turn")]
    assert checkpoints[-1]["status"] == "completed"


def test_close_retries_only_operation_owners_whose_cleanup_failed(tmp_path):
    available = [Adapter("a", close_error="first failed"), Adapter("b")]
    provider = CodexProvider(adapter_factory=lambda: available.pop(0))
    owners = []
    for key in ("a", "b"):
        call, _ = request(tmp_path, operation_id=key, session_key=key)
        provider.run(call)
        owners.append(provider._owners[key])

    with pytest.raises(ProviderError, match="first failed"):
        provider.close()
    assert [owner.closed for owner in owners] == [1, 1]
    assert list(provider._owners.values()) == [owners[0]]

    owners[0].close_error = None
    provider.close()

    assert [owner.closed for owner in owners] == [2, 1]
    assert provider._owners == {}


def test_failed_operation_cleanup_retains_its_owner(tmp_path):
    owner = Adapter("operation", close_error="cleanup unverified")
    provider = CodexProvider(adapter=owner)
    call, _ = request(tmp_path, operation_key="logical")
    provider.run(call)

    with pytest.raises(RuntimeError, match="cleanup unverified"):
        provider.release_operation("logical")

    assert provider._owners["logical"] is owner


def test_operation_cleanup_reserves_owner_key_until_failure_is_known(tmp_path):
    closing = threading.Event()
    finish_close = threading.Event()

    class BlockingOwner(Adapter):
        def dispose(self):
            self.disposed += 1
            closing.set()
            assert finish_close.wait(30)
            raise RuntimeError("cleanup unverified")

    created = []

    def factory():
        owner = BlockingOwner("operation") if not created else Adapter("new")
        created.append(owner)
        return owner

    provider = CodexProvider(adapter_factory=factory)
    call, _ = request(tmp_path, operation_key="logical")
    provider.run(call)

    cleanup_errors = []
    cleanup = threading.Thread(
        target=lambda: _capture_error(
            cleanup_errors, provider.release_operation, "logical"
        )
    )
    replacement = []
    replacement_ready = threading.Event()

    def acquire_owner():
        replacement.append(provider._adapter_for(call))
        replacement_ready.set()

    cleanup.start()
    assert closing.wait(30)
    contender = threading.Thread(target=acquire_owner)
    contender.start()
    assert not replacement_ready.wait(0.1)
    finish_close.set()
    cleanup.join(timeout=30)
    contender.join(timeout=30)

    assert cleanup_errors and "cleanup unverified" in str(cleanup_errors[0])
    assert replacement == [created[0]]
    assert len(created) == 1


@pytest.mark.parametrize("named", [False, True])
def test_disposal_failure_resumes_durable_response_without_another_turn(tmp_path, named):
    class FlakyDisposalOwner(Adapter):
        def dispose(self):
            self.disposed += 1
            if self.disposed == 1:
                raise RuntimeError("cleanup failed once")

    @workflow
    def work():
        return Provider(session=Session.task("shared") if named else None).run("work").value

    owner = FlakyDisposalOwner("thread")
    backend = CodexProvider(adapter=owner)
    with Botpipe(
        tmp_path,
        provider=backend,
        state_dir=tmp_path / "state",
    ) as client:
        first = client.run(work, task_id="task")
        assert first.status == "interrupted"
        assert len(owner.calls) == 1
        operation = next(row for row in client.journal.operations(first.run_id) if row["kind"] == "provider")
        attempt = client.journal.attempt(operation["id"], 1)
        assert attempt["disposal"]["status"] == "incomplete"
        if named:
            other_owner = Adapter("must-not-dispatch")
            other_provider = CodexProvider(adapter=other_owner)
            with Botpipe(tmp_path, provider=other_provider, state_dir=tmp_path / "state") as other:
                blocked = other.run(work, task_id="task")
            assert blocked.status == "failed"
            assert "unfinished run" in blocked.error
            assert other_owner.calls == []

        resumed = client.resume(first.run_id, workflow=work)

        assert resumed.ok, resumed.error
        assert resumed.value == "done"
        assert len(owner.calls) == 1
        assert owner.disposed == 2
        assert client.journal.attempt(operation["id"], 1)["disposal"] == {
            "status": "completed"
        }


@pytest.mark.parametrize("named", [False, True])
def test_operator_accepts_disposal_unknown_after_fresh_runtime(tmp_path, named):
    class UnverifiedDisposalOwner(Adapter):
        def dispose(self):
            self.disposed += 1
            if self.disposed == 1:
                raise RuntimeError("cleanup owner was lost")

    @workflow
    def work():
        return Provider(session=Session.task("shared") if named else None).run("work").value

    state = tmp_path / "state"
    old_owner = UnverifiedDisposalOwner("old-thread")
    old_backend = CodexProvider(adapter=old_owner)
    original = Botpipe(tmp_path, provider=old_backend, state_dir=state)
    first = original.run(work)
    assert first.status == "interrupted"
    assert len(old_owner.calls) == 1

    fresh_owner = UnverifiedDisposalOwner("unused")
    fresh_backend = CodexProvider(adapter=fresh_owner)
    with Botpipe(tmp_path, provider=fresh_backend, state_dir=state) as restarted:
        operation = next(row for row in restarted.journal.operations(first.run_id) if row["kind"] == "provider")
        restarted.resolve(first.run_id, operation["id"], accept=True)
        cleanup = restarted.journal.attempt(operation["id"], 1)["disposal"]
        assert cleanup["status"] == "incomplete"
        assert cleanup["resolved_by"] == "operator"
        assert cleanup["resolution"] == "accept"

        resumed = restarted.resume(first.run_id, workflow=work)

        assert resumed.ok, resumed.error
        assert resumed.value == "done"
        assert fresh_owner.calls == []

    old_backend.close()


def _capture_error(errors, function, *args):
    try:
        function(*args)
    except Exception as exc:  # noqa: BLE001 - test captures thread failures
        errors.append(exc)


def test_codex_run_requires_durable_checkpoint_callback(tmp_path):
    call, _ = request(tmp_path, session_key="task:one")
    with pytest.raises(ProviderError, match="on_checkpoint"):
        CodexProvider(adapter=Adapter("thread")).run(replace(call, on_checkpoint=None))


@pytest.mark.parametrize("named", [False, True])
def test_each_logical_call_disposes_its_server_and_retains_repair_history(tmp_path, named):
    from pydantic import BaseModel

    class Answer(BaseModel):
        value: int

    created = []

    class RepairAdapter(Adapter):
        def start_turn(self, call, on_event=None):
            if len(created) > 1:
                assert created[-2].disposed == 1
            response = super().start_turn(call, on_event)
            return replace(
                response,
                text="invalid" if len(self.calls) == 1 and self is created[0] else '{"value": 7}',
            )

    def factory():
        owner = RepairAdapter(f"thread-{len(created)}")
        created.append(owner)
        return owner

    @workflow
    def work():
        provider = Provider(session=Session.task("shared") if named else None)
        first = provider.run("first", returns=Answer)
        second = provider.run("second", returns=Answer)
        return first.value.value + second.value.value

    backend = CodexProvider(adapter_factory=factory)
    with Botpipe(tmp_path, provider=backend) as client:
        result = client.run(work, task_id="task")
        assert result.ok, result.error
        assert result.value == 14
        assert len(created) == 2
        assert [len(owner.calls) for owner in created] == [2, 1]
        assert created[0].calls[1].session_id == "thread-0"
        assert created[1].calls[0].session_id == ("thread-0" if named else None)
        assert [owner.disposed for owner in created] == [1, 1]
        assert [owner.closed for owner in created] == [0, 0]
        assert backend._owners == {}
        resumed = client.resume(result.run_id, workflow=work)
        assert resumed.ok, resumed.error
        assert len(created) == 2


@pytest.mark.parametrize("retry_safe", [False, True])
@pytest.mark.parametrize("disposal_fails", [False, True])
def test_terminal_validation_failure_disposes_owner(tmp_path, retry_safe, disposal_fails):
    class InvalidAdapter(Adapter):
        def start_turn(self, call, on_event=None):
            return replace(super().start_turn(call, on_event), text="invalid")

        def dispose(self):
            self.disposed += 1
            if disposal_fails and self.disposed == 1:
                raise RuntimeError("disposal interrupted")

    @workflow
    def work():
        return Provider(session=Session.task("shared")).run(
            "work", returns=int, output_retries=1, retry_safe=retry_safe,
        ).value

    owner = InvalidAdapter("thread")
    with Botpipe(tmp_path, provider=CodexProvider(adapter=owner)) as client:
        result = client.run(work, task_id="task")
        if disposal_fails:
            assert result.status == "interrupted", result.error
            operation = [row for row in client.journal.operations(result.run_id) if row["kind"] == "provider"][-1]
            assert operation["status"] == "response"
            result = client.resume(result.run_id, workflow=work)
        assert result.status == "failed", result.error
        assert len(owner.calls) == (2 if retry_safe else 1)
        assert owner.disposed == (2 if disposal_fails else 1)
        assert owner.closed == 0
        assert client.provider._owners == {}


@pytest.mark.parametrize("named", [False, True])
def test_repair_preflight_failure_aborts_retained_owner(tmp_path, named):
    class RejectRepairAdapter(Adapter):
        def __init__(self, name):
            super().__init__(name)
            self.probes = 0

        def probe(self, *, deadline=None):
            self.probes += 1
            if self.probes > 1:
                from botpipe.providers import ProviderPolicyError

                raise ProviderPolicyError("repair preflight rejected")
            return super().probe(deadline=deadline)

        def start_turn(self, call, on_event=None):
            return replace(super().start_turn(call, on_event), text="invalid")

    @workflow
    def work():
        return Provider(
            session=Session.task("shared") if named else None
        ).run("work", returns=int, output_retries=1).value

    owner = RejectRepairAdapter("thread")
    backend = CodexProvider(adapter=owner)
    with Botpipe(tmp_path, provider=backend) as client:
        result = client.run(work, task_id="task")

        assert result.status == "failed"
        assert "repair preflight rejected" in result.error
        assert len(owner.calls) == 1
        assert owner.closed == 1
        assert owner.disposed == 0
        assert backend._owners == {}
        if named:
            first_operation = next(
                row
                for row in client.journal.operations(result.run_id)
                if row["kind"] == "provider"
            )
            session_key = codec.decode(first_operation["inputs"])["session"]
            assert SessionBinding(client.journal, session_key).read()["pending"] is None
    if named:
        class ValidAdapter(Adapter):
            def start_turn(self, call, on_event=None):
                return replace(super().start_turn(call, on_event), text="7")

        next_owner = ValidAdapter("next-thread")
        with Botpipe(
            tmp_path, provider=CodexProvider(adapter=next_owner)
        ) as restarted:
            reused = restarted.run(work, task_id="task")
        assert reused.ok, reused.error
        assert len(next_owner.calls) == 1
        assert next_owner.calls[0].session_id == "thread"


@pytest.mark.parametrize("named", [False, True])
def test_repair_budget_exhaustion_aborts_retained_owner(tmp_path, named):
    class InvalidAdapter(Adapter):
        def start_turn(self, call, on_event=None):
            return replace(super().start_turn(call, on_event), text="invalid")

    @workflow
    def work():
        with provider_budget(max_turns=1):
            return Provider(
                session=Session.task("shared") if named else None
            ).run("work", returns=int, output_retries=1).value

    owner = InvalidAdapter("thread")
    backend = CodexProvider(adapter=owner)
    with Botpipe(tmp_path, provider=backend) as client:
        result = client.run(work, task_id="task")

        assert result.status == "budget_exceeded"
        assert len(owner.calls) == 1
        assert owner.closed == 1
        assert owner.disposed == 0
        assert backend._owners == {}


@pytest.mark.parametrize("named", [False, True])
def test_repair_preflight_cleanup_failure_resumes_without_redispatch(tmp_path, named):
    class FlakyRejectRepairAdapter(Adapter):
        def __init__(self, name):
            super().__init__(name)
            self.probes = 0

        def probe(self, *, deadline=None):
            self.probes += 1
            if self.probes > 1:
                from botpipe.providers import ProviderPolicyError

                raise ProviderPolicyError("repair preflight rejected")
            return super().probe(deadline=deadline)

        def start_turn(self, call, on_event=None):
            return replace(super().start_turn(call, on_event), text="invalid")

        def close(self):
            self.closed += 1
            if self.closed == 1:
                raise RuntimeError("abort failed once")

    @workflow
    def work():
        return Provider(
            session=Session.task("shared") if named else None
        ).run("work", returns=int, output_retries=1).value

    owner = FlakyRejectRepairAdapter("thread")
    backend = CodexProvider(adapter=owner)
    with Botpipe(tmp_path, provider=backend) as client:
        first = client.run(work, task_id="task")
        assert first.status == "interrupted"
        assert len(owner.calls) == 1
        assert owner.closed == 1

        resumed = client.resume(first.run_id, workflow=work)

        assert resumed.status == "failed"
        assert "repair preflight rejected" in resumed.error
        assert len(owner.calls) == 1
        assert owner.closed == 2
        assert backend._owners == {}


def test_repair_preflight_cleanup_unknown_can_be_failed_explicitly(tmp_path):
    class UncloseableRejectRepairAdapter(Adapter):
        def __init__(self, name):
            super().__init__(name)
            self.probes = 0
            self.allow_final_close = False

        def probe(self, *, deadline=None):
            self.probes += 1
            if self.probes > 1:
                from botpipe.providers import ProviderPolicyError

                raise ProviderPolicyError("repair preflight rejected")
            return super().probe(deadline=deadline)

        def start_turn(self, call, on_event=None):
            return replace(super().start_turn(call, on_event), text="invalid")

        def close(self):
            self.closed += 1
            if self.allow_final_close:
                return
            raise RuntimeError("abort cannot be verified")

    @workflow
    def work():
        return Provider(session=Session.task("shared")).run(
            "work", returns=int, output_retries=1
        ).value

    owner = UncloseableRejectRepairAdapter("thread")
    backend = CodexProvider(adapter=owner)
    with Botpipe(tmp_path, provider=backend) as client:
        result = client.run(work, task_id="task")
        assert result.status == "interrupted"
        response_operation = next(
            row
            for row in client.journal.operations(result.run_id)
            if row["kind"] == "provider" and row["status"] == "failed"
        )

        client.resolve(result.run_id, response_operation["id"], fail=True)

        attempt = client.journal.attempt(response_operation["id"], 1)
        assert attempt["cleanup"]["status"] == "incomplete"
        assert attempt["cleanup"]["resolved_by"] == "operator"
        assert attempt["cleanup"]["resolution"] == "fail"
        owner.allow_final_close = True


def test_repair_timeout_cleanup_resume_does_not_reenter_preflight(tmp_path):
    class TimeoutRepairAdapter(Adapter):
        def __init__(self, name):
            super().__init__(name)
            self.probes = 0

        def probe(self, *, deadline=None):
            self.probes += 1
            if self.probes == 2:
                raise TimeoutError("repair probe timed out")
            return super().probe(deadline=deadline)

        def start_turn(self, call, on_event=None):
            return replace(super().start_turn(call, on_event), text="invalid")

        def close(self):
            self.closed += 1
            if self.closed == 1:
                raise RuntimeError("abort failed once")

    @workflow
    def work():
        return Provider(session=None).run(
            "work", returns=int, output_retries=1
        ).value

    owner = TimeoutRepairAdapter("thread")
    backend = CodexProvider(adapter=owner)
    with Botpipe(tmp_path, provider=backend) as client:
        first = client.run(work)
        assert first.status == "interrupted"
        assert owner.probes == 2
        assert len(owner.calls) == 1

        resumed = client.resume(first.run_id, workflow=work)

        assert resumed.status == "failed"
        assert "capability probe timed out" in resumed.error
        assert owner.probes == 2
        assert len(owner.calls) == 1
        assert owner.closed == 2


def test_repair_destination_failure_cleanup_resume_does_not_redispatch(
    tmp_path, monkeypatch
):
    from botpipe.artifacts import ArtifactStore

    original_destinations = ArtifactStore.destinations
    inventories = 0

    def fail_repair_inventory(self, declarations, *, create_parents=False):
        nonlocal inventories
        if not create_parents:
            inventories += 1
            if inventories == 2:
                raise OSError("repair destination inventory failed")
        return original_destinations(
            self, declarations, create_parents=create_parents
        )

    monkeypatch.setattr(ArtifactStore, "destinations", fail_repair_inventory)

    class InvalidAdapter(Adapter):
        def start_turn(self, call, on_event=None):
            return replace(super().start_turn(call, on_event), text="invalid")

        def close(self):
            self.closed += 1
            if self.closed == 1:
                raise RuntimeError("abort failed once")

    @workflow
    def work():
        return Provider(session=Session.task("shared")).run(
            "work",
            returns=int,
            writes=[Artifact.text("result.txt")],
            output_retries=1,
        ).value

    owner = InvalidAdapter("thread")
    backend = CodexProvider(adapter=owner)
    with Botpipe(tmp_path, provider=backend) as client:
        first = client.run(work, task_id="task")
        assert first.status == "interrupted"
        assert inventories == 2
        assert len(owner.calls) == 1

        resumed = client.resume(first.run_id, workflow=work)

        assert resumed.status == "failed"
        assert "repair destination inventory failed" in resumed.error
        assert inventories == 2
        assert len(owner.calls) == 1
        assert owner.closed == 2
