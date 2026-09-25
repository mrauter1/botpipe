from __future__ import annotations

import importlib
import os
import subprocess
import sys

import pytest

from botpipe import Botpipe, Provider, Session, codec, workflow
from botpipe.capabilities import CapabilityStatus, CodexCapabilities
from botpipe.errors import SessionError
from botpipe.journal import Journal
from botpipe.providers import CodexProvider, FakeProvider, ProviderResponse
from botpipe.recovery import Completed, Stopped, Unknown
from botpipe.session_bindings import SessionBinding


def _create_run(journal: Journal, run_id: str, task_id: str = "task") -> None:
    folder = journal.path / "tasks" / task_id / "runs" / run_id
    journal.create_run(
        {
            "run_id": run_id,
            "task_id": task_id,
            "folder": str(folder),
            "status": "running",
            "args": codec.encode(()),
            "kwargs": codec.encode({}),
        }
    )


def _begin_provider(
    journal: Journal,
    run_id: str,
    operation_id: str,
    operation_key: str,
    *,
    ordinal: int = 0,
    attempt: int = 1,
) -> None:
    journal.begin(
        operation_id=operation_id,
        run_id=run_id,
        scope="root",
        ordinal=ordinal,
        kind="provider",
        name="turn",
        fingerprint=f"fingerprint-{operation_id}",
        inputs=codec.encode({"operation_key": operation_key}),
        limit=10,
    )
    journal.prepare_attempt(
        operation_id,
        attempt,
        {
            "prompt": f"prompt for {operation_id}",
            "operation_key": operation_key,
        },
    )


def _reserve(
    journal: Journal, run_id: str, operation_id: str, attempt: int = 1
) -> None:
    journal.reserve_budgets(
        run_id,
        operation_id,
        [],
        1.0,
        {},
        30.0,
        {
            "dispatch_id": f"dispatch-{operation_id}",
            "attempt": attempt,
            "provider": "fake",
        },
    )


def test_foreign_run_clears_exact_owner_that_failed_before_dispatch(tmp_path):
    journal = Journal(tmp_path)
    _create_run(journal, "first")
    _begin_provider(journal, "first", "first-op", "first-key")
    binding = SessionBinding(journal, "shared")
    binding.claim("first", "first-key", "first-op", 1)

    checked = binding.check("second-key")

    assert checked["pending"] is None
    assert binding.read()["pending"] is None
    assert not any(
        event["event"] == "provider_dispatch_reserved"
        for event in journal.events("first")
    )


def test_foreign_run_cannot_clear_dispatched_exact_owner(tmp_path):
    journal = Journal(tmp_path)
    _create_run(journal, "first")
    _begin_provider(journal, "first", "first-op", "first-key")
    binding = SessionBinding(journal, "shared")
    binding.claim("first", "first-key", "first-op", 1)
    _reserve(journal, "first", "first-op")
    before = binding.path.read_bytes()

    with pytest.raises(
        SessionError, match="unfinished run first operation first-op attempt 1"
    ):
        binding.check("second-key")

    assert binding.path.read_bytes() == before


@pytest.mark.parametrize("status", ["pending", "incomplete", "completed"])
def test_server_startup_before_dispatch_requires_binding_settlement(tmp_path, status):
    journal = Journal(tmp_path)
    _create_run(journal, "first")
    _begin_provider(journal, "first", "first-op", "first-key")
    binding = SessionBinding(journal, "shared")
    binding.claim("first", "first-key", "first-op", 1)
    journal.attempt_checkpoint("first-op", 1, {"disposal": {"status": status}})
    before = binding.path.read_bytes()

    with pytest.raises(SessionError, match="unfinished run"):
        binding.check("second-key")
    assert binding.path.read_bytes() == before

    journal.attempt_checkpoint("first-op", 1, {"disposal": {"status": "completed"}})
    binding.finish("first", "first-key", operation_id="first-op", attempt=1)
    assert binding.check("second-key")["pending"] is None


@pytest.mark.parametrize(
    "corruption", ["missing_operation", "wrong_key", "wrong_kind", "missing_attempt"]
)
def test_foreign_run_rejects_corrupt_owner_without_mutating_binding(
    tmp_path, corruption
):
    journal = Journal(tmp_path)
    _create_run(journal, "first")
    binding = SessionBinding(journal, "shared")
    operation_id = "missing-op"
    operation_key = "first-key"
    attempt = 1
    if corruption != "missing_operation":
        operation_id = "first-op"
        if corruption == "wrong_kind":
            journal.begin(
                operation_id=operation_id,
                run_id="first",
                scope="root",
                ordinal=0,
                kind="activity",
                name="effect",
                fingerprint="fingerprint",
                inputs=codec.encode({"operation_key": operation_key}),
                limit=10,
            )
        else:
            recorded_key = (
                "different-key" if corruption == "wrong_key" else operation_key
            )
            _begin_provider(journal, "first", operation_id, recorded_key)
        if corruption == "missing_attempt":
            attempt = 2
    binding.claim("first", operation_key, operation_id, attempt)
    before = binding.path.read_bytes()

    with pytest.raises(SessionError, match="invalid owner (operation|attempt)"):
        binding.check("second-key")

    assert binding.path.read_bytes() == before


def test_operator_retry_without_prepared_next_attempt_retains_ownership(tmp_path):
    journal = Journal(tmp_path)
    _create_run(journal, "first")
    _begin_provider(journal, "first", "first-op", "first-key")
    journal.response(
        "first-op",
        {
            "retry_authorized": True,
            "retry_origin": "operator",
            "generation": 1,
            "request": {"operation_key": "first-key", "session_id": "thread-1"},
        },
    )
    binding = SessionBinding(journal, "shared")
    binding.claim("first", "first-key", "first-op", 2)
    before = binding.path.read_bytes()

    with pytest.raises(
        SessionError, match="unfinished run first operation first-op attempt 2"
    ):
        binding.check("second-key")

    assert journal.attempt("first-op", 2) is None
    assert binding.path.read_bytes() == before


def test_old_completed_replay_settles_without_touching_foreign_binding(tmp_path):
    journal = Journal(tmp_path)
    _create_run(journal, "old")
    _begin_provider(journal, "old", "old-op", "old-key")
    _create_run(journal, "new")
    _begin_provider(journal, "new", "new-op", "new-key")
    binding = SessionBinding(journal, "shared")
    binding.claim("new", "new-key", "new-op", 1)
    binding.advance("new-key", "thread-new")
    before = binding.path.read_bytes()

    binding.finish(
        "old",
        "old-key",
        operation_id="old-op",
        attempt=1,
        session_id="thread-old",
    )

    assert binding.path.read_bytes() == before
    settlement = journal.events("old")[-1]
    assert settlement["event"] == "provider_call_finished"
    assert settlement["operation_id"] == "old-op"
    assert settlement["data"] == {
        "operation_key": "old-key",
        "attempt": 1,
        "session_id": "thread-old",
        "outcome": "completed",
    }


def test_finish_repairs_thread_from_durable_response_before_clearing_owner(tmp_path):
    journal = Journal(tmp_path)
    _create_run(journal, "run")
    _begin_provider(journal, "run", "op", "key")
    binding = SessionBinding(journal, "shared")
    binding.claim("run", "key", "op", 1)
    binding.advance("key", "thread-old")
    journal.response(
        "op",
        {
            "generation": 0,
            "request": {"operation_key": "key", "session_id": "thread-old"},
            "text": "done",
            "session_id": "thread-new",
            "usage": {},
            "metadata": {},
            "validated_value": codec.encode("done"),
        },
    )

    binding.finish(
        "run",
        "key",
        operation_id="op",
        attempt=1,
        session_id="thread-new",
    )

    assert binding.read() == {
        "format": 1,
        "key": "shared",
        "session_id": "thread-new",
        "pending": None,
    }
    assert journal.events("run")[-1]["data"]["session_id"] == "thread-new"


def test_finish_repairs_binding_after_settlement_event_was_already_durable(tmp_path):
    journal = Journal(tmp_path)
    _create_run(journal, "run")
    _begin_provider(journal, "run", "op", "key")
    binding = SessionBinding(journal, "shared")
    binding.claim("run", "key", "op", 1)
    journal.event(
        "run",
        "provider_call_finished",
        {
            "operation_key": "key",
            "attempt": 1,
            "session_id": "thread-new",
            "outcome": "completed",
        },
        "op",
    )

    binding.finish(
        "run",
        "key",
        operation_id="op",
        attempt=1,
        session_id="thread-new",
    )

    assert binding.read()["session_id"] == "thread-new"
    assert binding.read()["pending"] is None
    assert (
        sum(
            event["event"] == "provider_call_finished"
            for event in journal.events("run")
        )
        == 1
    )


def test_sibling_settlement_cannot_clear_exact_pending_repair(tmp_path):
    journal = Journal(tmp_path)
    _create_run(journal, "run")
    _begin_provider(journal, "run", "first-op", "logical-key", ordinal=0)
    _begin_provider(journal, "run", "repair-op", "logical-key", ordinal=1)
    binding = SessionBinding(journal, "shared")
    binding.claim("run", "logical-key", "repair-op", 1)
    _reserve(journal, "run", "repair-op")
    journal.event(
        "run",
        "provider_call_finished",
        {
            "operation_key": "logical-key",
            "attempt": 1,
            "session_id": "thread-first",
            "outcome": "completed",
        },
        "first-op",
    )
    before = binding.path.read_bytes()

    with pytest.raises(
        SessionError, match="unfinished run run operation repair-op attempt 1"
    ):
        binding.check("foreign-key")

    assert binding.path.read_bytes() == before


def test_foreign_run_cannot_clear_pre_dispatch_repair_after_logical_call_dispatched(
    tmp_path,
):
    journal = Journal(tmp_path)
    _create_run(journal, "run")
    _begin_provider(journal, "run", "first-op", "logical-key", ordinal=0)
    _reserve(journal, "run", "first-op")
    _begin_provider(journal, "run", "repair-op", "logical-key", ordinal=1)
    binding = SessionBinding(journal, "shared")
    binding.claim("run", "logical-key", "first-op", 1)
    binding.claim("run", "logical-key", "repair-op", 1)
    before = binding.path.read_bytes()

    with pytest.raises(
        SessionError, match="unfinished run run operation repair-op attempt 1"
    ):
        binding.check("foreign-key")

    assert not any(
        event["event"] == "provider_dispatch_reserved"
        and event.get("operation_id") == "repair-op"
        for event in journal.events("run")
    )
    assert binding.path.read_bytes() == before


def test_task_session_reads_latest_thread_across_process_and_reused_runtime(
    tmp_path, monkeypatch
):
    module_name = f"shared_session_{tmp_path.name.replace('-', '_')}"
    (tmp_path / f"{module_name}.py").write_text(
        "from botpipe import Provider, Session, workflow\n"
        "@workflow\n"
        "def talk():\n"
        "    return Provider(session=Session.task('shared')).run('talk').value\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    definition = importlib.import_module(module_name).talk
    state = tmp_path / "state"

    def first_turn(request):
        assert request.session_id is None
        return ProviderResponse("first", "thread-first")

    def third_turn(request):
        assert request.session_id == "thread-second"
        return ProviderResponse("third", "thread-third")

    provider = FakeProvider([first_turn, third_turn])
    with Botpipe(tmp_path, state_dir=state, provider=provider) as client:
        first = client.run(definition, run_id="parent-first", task_id="shared-task")
        assert first.ok, first.error

        script = (
            "import importlib, sys\n"
            "from botpipe import Botpipe\n"
            "from botpipe.providers import FakeProvider, ProviderResponse\n"
            "definition = importlib.import_module(sys.argv[1]).talk\n"
            "def respond(request):\n"
            "    if request.session_id != 'thread-first':\n"
            "        raise AssertionError(f'unexpected thread: {request.session_id!r}')\n"
            "    return ProviderResponse('second', 'thread-second')\n"
            "with Botpipe(sys.argv[2], state_dir=sys.argv[3], provider=FakeProvider([respond])) as client:\n"
            "    result = client.run(definition, run_id='child', task_id='shared-task')\n"
            "    if not result.ok:\n"
            "        raise AssertionError(result.error)\n"
        )
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            filter(None, (str(tmp_path), environment.get("PYTHONPATH")))
        )
        child = subprocess.run(
            [sys.executable, "-c", script, module_name, str(tmp_path), str(state)],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        assert child.returncode == 0, child.stderr

        third = client.run(definition, run_id="parent-third", task_id="shared-task")
        assert third.ok, third.error

    assert [request.session_id for request in provider.calls] == [
        None,
        "thread-second",
    ]
    binding = next((state / "sessions").glob("*.json"))
    assert '"session_id": "thread-third"' in binding.read_text()
    assert '"pending": null' in binding.read_text()


@pytest.mark.parametrize("choice", ["accept", "fail"])
def test_resume_finishes_selected_resolution_after_binding_settlement_crash(
    tmp_path, monkeypatch, choice
):
    def interrupted(_request):
        raise SystemExit("turn interrupted")

    @workflow
    def work():
        return Provider(session=Session.task("shared")).run("work").value

    provider = FakeProvider([interrupted, "next run"])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit, match="turn interrupted"):
            client.run(work, run_id="original", task_id="task")
        operation = next(
            row
            for row in client.journal.operations("original")
            if row["kind"] == "provider"
        )

        def crash_before_settlement(self, *args, **kwargs):
            raise SystemExit("binding settlement interrupted")

        with monkeypatch.context() as patch:
            patch.setattr(SessionBinding, "finish", crash_before_settlement)
            with pytest.raises(SystemExit, match="binding settlement interrupted"):
                client.resolve("original", operation["id"], **{choice: True})

        interrupted_events = client.journal.events("original")
        assert (
            sum(event["event"] == "resolution_selected" for event in interrupted_events)
            == 1
        )
        assert not any(
            event["event"] == "operation_reconciled" for event in interrupted_events
        )
        assert (
            SessionBinding(
                client.journal, codec.decode(operation["inputs"])["session"]
            ).read()["pending"]
            is not None
        )

        resumed = client.resume("original", workflow=work)
        assert resumed.status == ("failed" if choice == "fail" else "completed")
        events = client.journal.events("original")
        assert sum(event["event"] == "operation_reconciled" for event in events) == 1
        assert sum(event["event"] == "provider_call_finished" for event in events) == 1
        assert (
            SessionBinding(
                client.journal, codec.decode(operation["inputs"])["session"]
            ).read()["pending"]
            is None
        )
        assert client.run(work, task_id="task").ok


def test_manual_response_cancels_unprepared_retry_after_binding_finish_crash(
    tmp_path, monkeypatch
):
    class StoppedProvider(FakeProvider):
        def recover(self, request):
            return Stopped("attempt is stopped")

    def interrupted(_request):
        raise SystemExit("turn interrupted")

    @workflow
    def work():
        return Provider(session=Session.task("shared")).run("work").value

    provider = StoppedProvider([interrupted])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit, match="turn interrupted"):
            client.run(work, run_id="original", task_id="task")
        operation = next(
            row
            for row in client.journal.operations("original")
            if row["kind"] == "provider"
        )
        client.resolve("original", operation["id"], retry=True)
        session_key = codec.decode(operation["inputs"])["session"]
        binding = SessionBinding(client.journal, session_key)
        assert binding.read()["pending"]["attempt"] == 2
        assert client.journal.attempt(operation["id"], 2) is None

        def crash_before_settlement(self, *args, **kwargs):
            raise SystemExit("binding settlement interrupted")

        with monkeypatch.context() as patch:
            patch.setattr(SessionBinding, "finish", crash_before_settlement)
            with pytest.raises(SystemExit, match="binding settlement interrupted"):
                client.resolve(
                    "original",
                    operation["id"],
                    response=ProviderResponse(
                        "recovered manually", session_id="thread-manual"
                    ),
                )

        latest = client.journal.get(operation["id"])["response"]
        assert latest["generation"] == 0
        assert "retry_authorized" not in latest
        assert binding.read()["pending"]["attempt"] == 2
        assert client.journal.attempt(operation["id"], 2) is None

        resumed = client.resume("original", workflow=work)

        assert resumed.ok, resumed.error
        assert resumed.value == "recovered manually"
        assert binding.read()["pending"] is None
        assert binding.read()["session_id"] == "thread-manual"
        assert len(provider.calls) == 1


def test_completed_resolution_disposes_owner_before_clearing_session_binding(
    tmp_path,
):
    @workflow
    def work():
        return Provider(session=Session.task("shared")).run("work").value

    provider = FakeProvider([SystemExit("turn interrupted")])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit, match="turn interrupted"):
            client.run(work, run_id="original", task_id="task")
        operation = next(
            row
            for row in client.journal.operations("original")
            if row["kind"] == "provider"
        )
        inputs = codec.decode(operation["inputs"])
        binding = SessionBinding(client.journal, inputs["session"])
        calls = []

        provider.recover = lambda request: Completed(
            ProviderResponse("recovered", session_id="thread-recovered")
        )

        def release(operation_key, *, require_owner=False, abort=False):
            if not require_owner:
                return
            durable = client.journal.attempt(operation["id"], 1)
            assert durable["disposal"] == {"status": "pending"}
            assert binding.read()["pending"] is not None
            calls.append((operation_key, require_owner, abort))

        provider.release_operation = release
        client.resolve("original", operation["id"], retry=True)

        assert calls == [(inputs["operation_key"], True, False)]
        attempt = client.journal.attempt(operation["id"], 1)
        assert attempt["disposal"] == {"status": "completed"}
        assert "cleanup" not in attempt
        assert binding.read()["pending"] is None
        resumed = client.resume("original", workflow=work)
        assert resumed.ok, resumed.error
        assert resumed.value == "recovered"
        assert len(provider.calls) == 1


def test_failed_completed_disposal_is_acknowledged_without_redispatch(
    tmp_path,
):
    @workflow
    def work():
        return Provider(session=Session.task("shared")).run("work").value

    provider = FakeProvider([SystemExit("turn interrupted")])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit, match="turn interrupted"):
            client.run(work, run_id="original", task_id="task")
        operation = next(
            row
            for row in client.journal.operations("original")
            if row["kind"] == "provider"
        )
        provider.recover = lambda request: Completed(
            ProviderResponse("durable", session_id="thread-durable")
        )

        def release(_operation_key, *, require_owner=False, abort=False):
            assert require_owner is True
            assert abort is False
            raise RuntimeError("normal disposal was not verified")

        provider.release_operation = release
        client.resolve("original", operation["id"], retry=True)

        attempt = client.journal.attempt(operation["id"], 1)
        assert attempt["disposal"] == {
            "status": "incomplete",
            "error": "normal disposal was not verified",
            "resolved_by": "operator",
            "resolution": "accept",
        }
        assert client.journal.get(operation["id"])["response"]["text"] == "durable"
        resumed = client.resume("original", workflow=work)
        assert resumed.ok and resumed.value == "durable"
        assert len(provider.calls) == 1


def test_saved_completed_resolution_reuses_disposal_after_settlement_crash(
    tmp_path, monkeypatch
):
    @workflow
    def work():
        return Provider(session=Session.task("shared")).run("work").value

    provider = FakeProvider([SystemExit("turn interrupted")])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit, match="turn interrupted"):
            client.run(work, run_id="original", task_id="task")
        operation = next(
            row
            for row in client.journal.operations("original")
            if row["kind"] == "provider"
        )
        provider.recover = lambda request: Completed(
            ProviderResponse("recovered", session_id="thread-recovered")
        )
        required_releases = []

        def release(operation_key, *, require_owner=False, abort=False):
            if require_owner:
                required_releases.append((operation_key, abort))

        provider.release_operation = release

        def crash_before_settlement(self, *args, **kwargs):
            raise SystemExit("binding settlement interrupted")

        with monkeypatch.context() as patch:
            patch.setattr(SessionBinding, "finish", crash_before_settlement)
            with pytest.raises(SystemExit, match="binding settlement interrupted"):
                client.resolve("original", operation["id"], retry=True)

        assert client.journal.attempt(operation["id"], 1)["disposal"] == {
            "status": "completed"
        }
        resumed = client.resume("original", workflow=work)
        assert resumed.ok and resumed.value == "recovered"
        assert len(required_releases) == 1
        assert len(provider.calls) == 1


def test_unknown_operator_accept_aborts_owner_and_retains_uncertainty(tmp_path):
    @workflow
    def work():
        return Provider(session=Session.task("shared")).run("work").value

    provider = FakeProvider([SystemExit("turn interrupted")])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit, match="turn interrupted"):
            client.run(work, run_id="original", task_id="task")
        operation = next(
            row
            for row in client.journal.operations("original")
            if row["kind"] == "provider"
        )
        inputs = codec.decode(operation["inputs"])
        binding = SessionBinding(client.journal, inputs["session"])
        calls = []
        provider.recover = lambda request: Unknown("native outcome is uncertain")

        def release(operation_key, *, require_owner=False, abort=False):
            calls.append((operation_key, require_owner, abort))
            raise RuntimeError("abort cleanup was not verified")

        provider.release_operation = release
        client.resolve(
            "original",
            operation["id"],
            accept=True,
            response=ProviderResponse("accepted", session_id="thread-accepted"),
        )

        assert calls == [(inputs["operation_key"], True, True)]
        assert client.journal.attempt(operation["id"], 1)["cleanup"] == {
            "status": "incomplete",
            "error": "abort cleanup was not verified",
            "resolved_by": "operator",
            "resolution": "accept",
        }
        selected = next(
            event
            for event in client.journal.events("original")
            if event["event"] == "resolution_selected"
        )
        assert selected["data"]["prior_outcome"] == "Unknown"
        assert selected["data"]["detail"] == "native outcome is uncertain"
        assert binding.read()["pending"] is None


def test_stopped_operator_retry_aborts_before_claiming_next_attempt(tmp_path):
    @workflow
    def work():
        return Provider(session=Session.task("shared")).run("work").value

    provider = FakeProvider([SystemExit("turn interrupted")])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit, match="turn interrupted"):
            client.run(work, run_id="original", task_id="task")
        operation = next(
            row
            for row in client.journal.operations("original")
            if row["kind"] == "provider"
        )
        inputs = codec.decode(operation["inputs"])
        binding = SessionBinding(client.journal, inputs["session"])
        calls = []

        def release(operation_key, *, require_owner=False, abort=False):
            assert binding.read()["pending"]["attempt"] == 1
            assert client.journal.attempt(operation["id"], 1)["cleanup"] == {
                "status": "pending"
            }
            calls.append((operation_key, require_owner, abort))

        provider.release_operation = release
        client.resolve("original", operation["id"], retry=True)

        assert calls == [(inputs["operation_key"], True, True)]
        assert client.journal.attempt(operation["id"], 1)["cleanup"] == {
            "status": "completed"
        }
        assert binding.read()["pending"]["attempt"] == 2


def test_unknown_retry_abandons_cleanup_failed_owner_before_redispatch(
    tmp_path, monkeypatch
):
    created = []

    class Owner:
        def __init__(self, *, interrupted):
            self.interrupted = interrupted
            self.calls = []
            self.closed = 0
            self.disposed = 0

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

        def start_turn(self, request, on_event=None):
            self.calls.append(request)
            request.on_checkpoint(
                {"status": "turn_intent", "session_id": "thread"}
            )
            request.on_checkpoint(
                {
                    "status": "turn_acknowledged",
                    "session_id": "thread",
                    "turn_id": "turn",
                }
            )
            if self.interrupted:
                raise SystemExit("turn interrupted")
            return ProviderResponse("retried", session_id="thread-retried")

        def dispose(self):
            self.disposed += 1

        def close(self):
            self.closed += 1
            raise RuntimeError("abort cleanup was not verified")

    def factory():
        owner = Owner(interrupted=not created)
        created.append(owner)
        return owner

    @workflow
    def work():
        return Provider(session=Session.task("shared")).run("work").value

    backend = CodexProvider(adapter_factory=factory)
    with Botpipe(tmp_path, provider=backend) as client:
        with pytest.raises(SystemExit, match="turn interrupted"):
            client.run(work, run_id="original", task_id="task")
        operation = next(
            row
            for row in client.journal.operations("original")
            if row["kind"] == "provider"
        )
        backend.recover = lambda request: Unknown("native outcome is uncertain")

        checkpoint = client.journal.attempt_checkpoint

        def crash_after_abandonment(operation_id, attempt, update):
            checkpoint(operation_id, attempt, update)
            cleanup = update.get("cleanup") or {}
            if cleanup.get("resolution") == "retry":
                raise SystemExit("crashed after owner abandonment")

        with monkeypatch.context() as patch:
            patch.setattr(
                client.journal,
                "attempt_checkpoint",
                crash_after_abandonment,
            )
            with pytest.raises(SystemExit, match="after owner abandonment"):
                client.resolve("original", operation["id"], retry=True)

        cleanup = client.journal.attempt(operation["id"], 1)["cleanup"]
        assert cleanup["status"] == "incomplete"
        assert cleanup["resolved_by"] == "operator"
        assert cleanup["resolution"] == "retry"
        assert created[0].closed == 1
        assert backend._owners == {}
        assert "retry_authorized" not in client.journal.get(operation["id"])[
            "response"
        ]

        resumed = client.resume("original", workflow=work)
        assert resumed.ok and resumed.value == "retried"
        assert len(created) == 2
        assert len(created[0].calls) == 1
        assert len(created[1].calls) == 1
