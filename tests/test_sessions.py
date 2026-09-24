from __future__ import annotations

import hashlib
import subprocess
import sys
import threading
import time

import pytest
from pydantic import BaseModel

from botpipe import (
    Artifact,
    Botpipe,
    BotpipeError,
    Provider,
    Session,
    activity,
    parallel,
    workflow,
)
from botpipe.locks import session_lock
from botpipe.providers import (
    FakeProvider,
    ProviderInterruptedError,
    ProviderResponse,
    ProviderTimeoutError,
)


def test_distinct_handles_for_same_task_session_serialize_turns(tmp_path):
    guard = threading.Lock()
    active = maximum = 0

    def respond(request):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.05)
        with guard:
            active -= 1
        return ProviderResponse("ok", request.session_id or "native-session")

    @workflow
    def talk():
        return parallel(
            lambda: Provider(session=Session.task("shared")).query("first"),
            lambda: Provider(session=Session.task("shared")).query("second"),
        )

    provider = FakeProvider([respond, respond])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(talk)

    assert result.ok, result.error
    assert maximum == 1
    assert [call.session_id for call in provider.calls] == [None, "native-session"]


def test_session_lock_serializes_across_processes(monkeypatch, tmp_path):
    monkeypatch.setenv("BOTPIPE_COORDINATION_DIR", str(tmp_path / "coordination"))
    journal, ready = tmp_path / "state", tmp_path / "ready"
    script = (
        "import sys\n"
        "from pathlib import Path\n"
        "from botpipe.locks import session_lock\n"
        "with session_lock(sys.argv[1], 'shared', timeout=1):\n"
        " Path(sys.argv[2]).write_text('ready')\n"
        " sys.stdin.read(1)\n"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(journal), str(ready)],
        stdin=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        with pytest.raises(ProviderTimeoutError, match="session"), session_lock(
            journal, "shared", timeout=0.05
        ):
            pass
    finally:
        assert process.stdin is not None
        process.stdin.write(b"x")
        process.stdin.flush()
        process.wait(timeout=5)


def test_provider_resolution_obeys_cross_process_session_lock(
    monkeypatch, tmp_path
):
    import botpipe.runtime as runtime

    from botpipe import codec
    from botpipe.recovery import Stopped

    monkeypatch.setenv("BOTPIPE_COORDINATION_DIR", str(tmp_path / "coordination"))
    recoveries = []

    class InterruptedProvider(FakeProvider):
        def recover(self, request):
            recoveries.append(request.operation_id)
            return Stopped("stopped")

    @workflow
    def work():
        return Provider(session=Session.task("shared")).run("work")

    def fail_fast_session_lock(journal, session_key, **options):
        return session_lock(journal, session_key, **{**options, "timeout": 0})

    provider = InterruptedProvider([SystemExit("interrupted")])
    with Botpipe(tmp_path, provider=provider) as client:
        with pytest.raises(SystemExit):
            client.run(work, run_id="session-resolution")
        operation = next(
            row
            for row in client.journal.operations("session-resolution")
            if row["kind"] == "provider"
        )
        session_key = codec.decode(operation["inputs"])["session"]
        ready = tmp_path / "resolve-ready"
        script = (
            "import sys\n"
            "from pathlib import Path\n"
            "from botpipe.locks import session_lock\n"
            "with session_lock(sys.argv[1], sys.argv[2], timeout=1):\n"
            " Path(sys.argv[3]).write_text('ready')\n"
            " sys.stdin.read(1)\n"
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(client.journal.path),
                session_key,
                str(ready),
            ],
            stdin=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists()
            # Limit only the contention check, once the other process owns the
            # real lock. Durable fixture creation has no tiny dispatch deadline.
            with monkeypatch.context() as patch:
                patch.setattr(runtime, "acquire_session_lock", fail_fast_session_lock)
                with pytest.raises(ProviderTimeoutError, match="session"):
                    client.resolve("session-resolution", operation["id"], retry=True)
            assert recoveries == []
        finally:
            assert process.stdin is not None
            process.stdin.write(b"x")
            process.stdin.flush()
            process.wait(timeout=5)

        client.resolve("session-resolution", operation["id"], retry=True)
        assert recoveries == [operation["id"]]


def test_constructor_sessions_are_independent_and_task_sessions_persist(tmp_path):
    @workflow
    def talk():
        first, second = Provider(), Provider()
        first.run("first")
        second.run("second")
        first.run("continue first")
        Provider(session=Session.task("persistent")).run("task conversation")

    provider = FakeProvider(
        [
            ProviderResponse("ok", "one"),
            ProviderResponse("ok", "two"),
            ProviderResponse("ok", "one"),
            ProviderResponse("ok", "task"),
            "next-one",
            "next-two",
            "next-one-again",
            "next-task",
        ]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        assert client.run(talk, task_id="same").ok
        assert client.run(talk, task_id="same").ok
    assert [r.session_id for r in provider.calls[:4]] == [None, None, "one", None]
    assert provider.calls[-1].session_id == "task"


def test_explicit_retry_adopts_completed_response_without_repeating_effects(
    tmp_path,
):
    from botpipe.recovery import Completed

    class RecoveringProvider(FakeProvider):
        def run(self, request):
            self.calls.append(request)
            request.artifacts["report"].write_text("completed before process loss")
            self.receipt = ProviderResponse("done", "session")
            raise KeyboardInterrupt()

        def recover(self, request):
            return Completed(self.receipt)

    @workflow
    def report():
        return Provider().run(
            "report", writes=Artifact.text("report.txt", required=True)
        )

    provider = RecoveringProvider([])
    with Botpipe(tmp_path, provider=provider) as client:
        interrupted = client.run(report)
        op = next(
            r
            for r in client.inspect(interrupted.run_id)["operations"]
            if r["kind"] == "provider"
        )
        client.resolve(interrupted.run_id, op["id"], retry=True)
        recovered = client.resume(interrupted.run_id, workflow=report)
        assert recovered.status == "interrupted", recovered.error
        client.resolve(
            interrupted.run_id,
            op["id"],
            artifact_digests={
                "report": hashlib.sha256(
                    provider.calls[0].artifacts["report"].read_bytes()
                ).hexdigest()
            },
        )
        recovered = client.resume(interrupted.run_id, workflow=report)
        assert recovered.ok, recovered.error
        assert (
            recovered.value.artifacts.report.read_text()
            == "completed before process loss"
        )
        assert len(provider.calls) == 1


def test_explicit_retry_does_not_remove_files_from_live_provider(tmp_path):
    class LiveProvider(FakeProvider):
        def run(self, request):
            self.calls.append(request)
            request.artifacts["report"].write_text("still being produced")
            raise KeyboardInterrupt()

        def recover(self, request):
            raise ProviderInterruptedError("still running", process_alive=True)

    @workflow
    def report():
        return Provider().run(
            "report", writes=Artifact.text("report.txt", required=True)
        )

    provider = LiveProvider([])
    with Botpipe(tmp_path, provider=provider) as client:
        interrupted = client.run(report)
        op = next(
            r
            for r in client.inspect(interrupted.run_id)["operations"]
            if r["kind"] == "provider"
        )
        before = client.journal.get(op["id"])["response"]
        with pytest.raises(BotpipeError, match="still running"):
            client.resolve(interrupted.run_id, op["id"], retry=True)
        assert (
            provider.calls[0].artifacts["report"].read_text() == "still being produced"
        )
        assert len(provider.calls) == 1
        assert client.journal.get(op["id"])["response"] == before


def test_repair_usage_is_charged_once_in_results_and_run_totals(tmp_path):
    class Answer(BaseModel):
        accepted: bool

    @workflow
    def review():
        return Provider().run("review", returns=Answer)

    provider = FakeProvider(
        [
            ProviderResponse("invalid", usage={"input_tokens": 3}),
            ProviderResponse('{"accepted":true}', usage={"input_tokens": 5}),
        ]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(review)
        assert result.ok, result.error
        assert result.value.usage["input_tokens"] == 8
        assert result.usage["input_tokens"] == 8
        replay = client.resume(result.run_id, workflow=review)
        assert replay.value.usage["input_tokens"] == 8
        assert replay.usage["input_tokens"] == 8
        assert len(provider.calls) == 2


def test_operation_budget_can_be_extended_without_repeating_effects(tmp_path):
    effects = []

    @activity
    def effect(value):
        effects.append(value)
        return value

    @workflow
    def limited():
        return effect(1) + effect(2)

    with Botpipe(tmp_path, provider=FakeProvider([]), max_operations=1) as client:
        limited_result = client.run(limited)
        assert limited_result.status == "budget_exceeded"
        resumed = client.resume(
            limited_result.run_id, workflow=limited, max_operations=2
        )
        assert resumed.ok, resumed.error
        assert resumed.value == 3
        assert effects == [1, 2]


def test_inspection_does_not_require_original_result_model_type(tmp_path):
    from botpipe import codec

    class LocalAnswer(BaseModel):
        accepted: bool

    @workflow
    def answer():
        return Provider().run("answer", returns=LocalAnswer)

    with Botpipe(tmp_path, provider=FakeProvider(['{"accepted":true}'])) as client:
        result = client.run(answer)
        assert result.ok
        codec._TYPES.pop(f"{LocalAnswer.__module__}:{LocalAnswer.__qualname__}")
        details = client.inspect(result.run_id)
        assert details["run"]["status"] == "completed"
        assert len(details["operations"]) == 2


def test_repeated_retry_authorization_cannot_advance_past_live_attempt(tmp_path):
    class LiveProvider(FakeProvider):
        def run(self, request):
            self.calls.append(request)
            request.artifacts["report"].write_text("live output")
            raise KeyboardInterrupt()

        def recover(self, request):
            raise ProviderInterruptedError("still running", process_alive=True)

    @workflow
    def report():
        return Provider().run(
            "report", writes=Artifact.text("report.txt", required=True)
        )

    with Botpipe(tmp_path, provider=LiveProvider([])) as client:
        paused = client.run(report)
        operation = next(
            row
            for row in client.inspect(paused.run_id)["operations"]
            if row["kind"] == "provider"
        )
        before = client.journal.get(operation["id"])["response"]
        with pytest.raises(BotpipeError, match="still running"):
            client.resolve(paused.run_id, operation["id"], retry=True)
        with pytest.raises(BotpipeError, match="still running"):
            client.resolve(paused.run_id, operation["id"], retry=True)
        assert client.journal.get(operation["id"])["response"] == before
        assert "retry_authorized" not in before
        assert client.resume(paused.run_id, workflow=report).status == "interrupted"
        assert client.provider.calls[0].artifacts["report"].read_text() == "live output"


def test_observed_response_cannot_release_a_known_live_provider(tmp_path):
    class LiveProvider(FakeProvider):
        def recover(self, request):
            raise ProviderInterruptedError("still running", process_alive=True)

    @workflow
    def report():
        return Provider().run("report")

    with Botpipe(tmp_path, provider=LiveProvider([KeyboardInterrupt()])) as client:
        paused = client.run(report)
        operation = next(
            row
            for row in client.inspect(paused.run_id)["operations"]
            if row["kind"] == "provider"
        )
        with pytest.raises(BotpipeError, match="still running"):
            client.resolve(
                paused.run_id, operation["id"], response=ProviderResponse("done")
            )
        assert client.journal.get(operation["id"])["status"] != "completed"


def test_pure_library_helper_defaults_are_not_workflow_arguments(tmp_path):
    from pydantic import Field

    @workflow
    def schema_metadata():
        return Field(default=3, gt=0).default

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        result = client.run(schema_metadata)
        assert result.ok and result.value == 3
        replay = client.resume(result.run_id, workflow=schema_metadata)
        assert replay.ok and replay.value == 3
