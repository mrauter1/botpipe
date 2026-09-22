from __future__ import annotations

import hashlib
import sqlite3

import pytest
from pydantic import BaseModel

from botpipe import Artifact, Botpipe, BotpipeError, Provider, Session, activity, workflow
from botpipe.providers import (
    FakeProvider,
    ProviderContinuation,
    ProviderInterruptedError,
    ProviderResponse,
)
from botpipe.recovery import Completed


def test_old_journal_is_rejected_before_schema_mutation(tmp_path):
    from botpipe.journal import Journal

    path = tmp_path / "state.sqlite3"
    db = sqlite3.connect(path)
    db.executescript("CREATE TABLE legacy(value TEXT); PRAGMA user_version=1;")
    db.close()

    with pytest.raises(ValueError, match="fresh state directory"):
        Journal(path)

    check = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert tables == {"legacy"}
        assert check.execute("PRAGMA user_version").fetchone()[0] == 1
    finally:
        check.close()


def test_version_two_journal_is_rejected_without_implicit_migration(tmp_path):
    from botpipe.journal import JOURNAL_APPLICATION_ID, Journal

    path = tmp_path / "state.sqlite3"
    db = sqlite3.connect(path)
    db.executescript(
        "CREATE TABLE sessions(native_session_id TEXT);"
        f"PRAGMA application_id={JOURNAL_APPLICATION_ID};"
        "PRAGMA user_version=2;"
    )
    db.close()

    with pytest.raises(ValueError, match="fresh state directory"):
        Journal(path)

    check = sqlite3.connect(path)
    try:
        columns = [
            row[1] for row in check.execute("PRAGMA table_info(sessions)")
        ]
        assert columns == ["native_session_id"]
        assert check.execute("PRAGMA user_version").fetchone()[0] == 2
    finally:
        check.close()


def test_session_codec_preserves_an_unbound_resource_reference():
    from botpipe import codec

    original = Session()
    restored = codec.decode(codec.encode(original))
    assert isinstance(restored, Session)
    assert restored.id is None
    assert restored.to_record()["token"] == original.to_record()["token"]


def test_session_revision_rejects_a_stale_loaded_handle(tmp_path):
    provider = FakeProvider(
        [
            ProviderResponse("one", "native"),
            ProviderResponse("bound", "native"),
            ProviderResponse("advanced", "native"),
        ]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        first = Provider(runtime=client)
        first.generate("one")
        stale = Session.load(first.session.id, state_dir=client.state_dir)
        # A suspended run binds through the real provider path, capturing the
        # full selected profile/adapter affinity at revision two.
        @workflow
        def suspended_turn(session):
            Provider(session=session).generate("bind")
            ask_human("continue?")
            return Provider(session=session).generate("stale")

        from botpipe import ask_human

        paused = client.run(suspended_turn, stale)
        assert paused.status == "awaiting_input"
        external = Session.load(first.session.id, state_dir=client.state_dir)
        Provider(runtime=client, session=external).generate("advance")
        result = client.answer(
            paused.run_id,
            paused.pending_input["operation_id"],
            "yes",
            workflow=suspended_turn,
        )
        assert result.status == "failed"
        assert "SessionHistoryConflict" in result.error


def test_completed_continuation_survives_a_new_standalone_run(tmp_path):
    continuation = ProviderContinuation(
        "native-thread", "fake", {"adapter_version": "test-v1"}
    )
    native = FakeProvider(
        [
            ProviderResponse("first", "native-thread", continuation=continuation),
            ProviderResponse("second", "native-thread", continuation=continuation),
        ]
    )
    with Botpipe(tmp_path, provider=native) as client:
        provider = Provider(runtime=client)
        assert provider.generate("first").value == "first"
        assert provider.generate("second").value == "second"

    assert native.calls[0].continuation is None
    assert native.calls[1].continuation == continuation
    assert native.calls[1].session_id == "native-thread"
    assert native.calls[0].receipt_dir != native.calls[1].receipt_dir


def test_raw_same_session_response_preserves_typed_continuation(tmp_path):
    continuation = ProviderContinuation(
        "native-thread", "fake", {"authority": {"tools": ["read"]}}
    )
    native = FakeProvider(
        [
            ProviderResponse("first", continuation=continuation),
            "legacy response",
            "next",
        ]
    )

    with Botpipe(tmp_path, provider=native) as client:
        provider = Provider(runtime=client)
        provider.generate("first")
        provider.generate("second")
        provider.generate("third")

    assert native.calls[1].continuation == continuation
    assert native.calls[2].continuation == continuation


def test_replay_detects_changed_session_alias_sharing(tmp_path):
    from botpipe import ask_human

    split = False

    @workflow
    def conversation():
        shared = Session()
        Provider(session=shared).generate("one")
        selected = Session() if split else shared
        Provider(session=selected).generate("two")
        return ask_human("continue?")

    provider = FakeProvider(
        [ProviderResponse("one", "native"), ProviderResponse("two", "native")]
    )
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(conversation)
        assert paused.status == "awaiting_input"
        split = True
        completed = client.answer(
            paused.run_id,
            paused.pending_input["operation_id"],
            "yes",
            workflow=conversation,
        )
        assert completed.status == "failed"
        assert "ReplayMismatch" in completed.error
        assert len(provider.calls) == 2


def test_constructor_sessions_are_independent_and_task_sessions_persist(tmp_path):
    @workflow
    def talk():
        first, second = Session(), Session()
        Provider(session=first).run("first")
        Provider(session=second).run("second")
        Provider(session=first).run("continue first")
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


def test_explicit_retry_recovers_completed_receipt_before_preparing_new_artifacts(
    tmp_path,
):
    class ReceiptedProvider(FakeProvider):
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

    provider = ReceiptedProvider([])
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
        assert len(details["operations"]) == 3


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
