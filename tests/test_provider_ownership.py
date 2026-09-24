from __future__ import annotations

import sys
import threading
from dataclasses import replace

import pytest

from botpipe import Botpipe, Provider, workflow
from botpipe.capabilities import CapabilityStatus, CodexCapabilities
from botpipe.policy import Policy
from botpipe.providers import (
    CodexProvider,
    ProviderError,
    ProviderRequest,
    ProviderResponse,
)
from botpipe.recovery import Completed, Stopped


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

    def close(self):
        self.closed += 1
        if self.close_error:
            raise RuntimeError(self.close_error)


def test_concurrent_first_use_constructs_one_adapter_for_one_session(tmp_path):
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
    first, _ = request(tmp_path, operation_id="first", session_key="task:shared")
    second, _ = request(tmp_path, operation_id="second", session_key="task:shared")
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
    assert created[0].closed == 1
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


def test_close_retries_only_session_owners_whose_cleanup_failed(tmp_path):
    available = [Adapter("a", close_error="first failed"), Adapter("b")]
    provider = CodexProvider(adapter_factory=lambda: available.pop(0))
    owners = []
    for key in ("a", "b"):
        call, _ = request(tmp_path, operation_id=key, session_key=key)
        provider.run(call)
        owners.append(provider._owners[("session", key)])

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

    assert provider._owners[("operation", "logical")] is owner


def test_operation_cleanup_reserves_owner_key_until_failure_is_known(tmp_path):
    closing = threading.Event()
    finish_close = threading.Event()

    class BlockingOwner(Adapter):
        def close(self):
            self.closed += 1
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


def test_cleanup_failure_resumes_durable_response_without_another_turn(tmp_path):
    class FlakyCleanupOwner(Adapter):
        def probe(self, *, deadline=None):
            return CodexCapabilities(
                executable=sys.executable,
                version="fixture",
                identity="fixture",
                methods=frozenset(),
                presets={
                    name: CapabilityStatus(True)
                    for name in ("run", "query", "generate")
                },
            )

        def close(self):
            self.closed += 1
            if self.closed == 1:
                raise RuntimeError("cleanup failed once")

    @workflow
    def work():
        return Provider(session=None).run("work").value

    owner = FlakyCleanupOwner("thread")
    backend = CodexProvider(adapter=owner)
    with Botpipe(
        tmp_path,
        provider=backend,
        state_dir=tmp_path / "state",
    ) as client:
        first = client.run(work)
        assert first.status == "interrupted"
        assert len(owner.calls) == 1
        operation = client.journal.get(f"{first.run_id}:root:0")
        attempt = client.journal.attempt(operation["id"], 1)
        assert attempt["cleanup"]["status"] == "incomplete"

        resumed = client.resume(first.run_id, workflow=work)

        assert resumed.ok, resumed.error
        assert resumed.value == "done"
        assert len(owner.calls) == 1
        assert owner.closed == 2
        assert client.journal.attempt(operation["id"], 1)["cleanup"] == {
            "status": "completed"
        }


def test_operator_accepts_cleanup_unknown_after_fresh_runtime(tmp_path):
    class UnverifiedCleanupOwner(Adapter):
        def probe(self, *, deadline=None):
            return CodexCapabilities(
                executable=sys.executable,
                version="fixture",
                identity="fixture",
                methods=frozenset(),
                presets={
                    name: CapabilityStatus(True)
                    for name in ("run", "query", "generate")
                },
            )

        def close(self):
            self.closed += 1
            if self.closed == 1:
                raise RuntimeError("cleanup owner was lost")

    @workflow
    def work():
        return Provider(session=None).run("work").value

    state = tmp_path / "state"
    old_owner = UnverifiedCleanupOwner("old-thread")
    old_backend = CodexProvider(adapter=old_owner)
    original = Botpipe(tmp_path, provider=old_backend, state_dir=state)
    first = original.run(work)
    assert first.status == "interrupted"
    assert len(old_owner.calls) == 1

    fresh_owner = UnverifiedCleanupOwner("unused")
    fresh_backend = CodexProvider(adapter=fresh_owner)
    with Botpipe(tmp_path, provider=fresh_backend, state_dir=state) as restarted:
        operation = restarted.journal.get(f"{first.run_id}:root:0")
        restarted.resolve(first.run_id, operation["id"], accept=True)
        cleanup = restarted.journal.attempt(operation["id"], 1)["cleanup"]
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
