from __future__ import annotations

import pytest
from pydantic import BaseModel, field_validator

from botpipe import Artifact, Botpipe, Session, workflow
from botpipe.artifacts import ArtifactStore
from botpipe.providers import FakeProvider, ProviderPolicyError, ProviderResponse
from botpipe.recovery import Stopped


def _provider_operation(client, run_id):
    return next(
        row for row in client.inspect(run_id)["operations"] if row["kind"] == "provider"
    )


def test_exhausted_repairs_restore_every_original_and_require_fresh_outputs(
    tmp_path,
):
    first_path = tmp_path / "exact" / "first.txt"
    second_path = tmp_path / "exact" / "second.json"
    first_path.parent.mkdir()
    first_path.write_text("original first")
    second_path.write_text('{"original": 2}')
    declarations = [
        Artifact.text(first_path, required=True),
        Artifact.json(second_path, required=True),
    ]

    def invalid(request):
        assert request.artifacts == {"first": first_path, "second": second_path}
        request.artifacts["first"].write_text("valid first attempt")
        request.artifacts["second"].write_text("invalid json")
        return "first response"

    def missing(request):
        # The prior attempted files were quarantined and both originals were
        # backed up again for this generation. No stale output can satisfy it.
        assert not request.artifacts["first"].exists()
        assert not request.artifacts["second"].exists()
        request.artifacts["first"].write_text("valid second attempt")
        return "second response"

    @workflow
    def writer():
        return Session().run("write", writes=declarations, retries=1)

    provider = FakeProvider([invalid, missing])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(writer)

    assert result.status == "failed"
    assert "Required artifact was not written" in result.error
    assert first_path.read_text() == "original first"
    assert second_path.read_text() == '{"original": 2}'
    assert len(provider.calls) == 2


def test_codec_preflight_failure_rolls_back_without_repeating_provider(
    tmp_path, monkeypatch
):
    import botpipe.sessions as sessions

    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("old first")
    second.write_text("old second")

    def write(request):
        request.artifacts["first"].write_text("new first")
        request.artifacts["second"].write_text("new second")
        return "unsupported checkpoint"

    @workflow
    def writer():
        return Session().run(
            "write",
            writes=[
                Artifact.text("first.txt", required=True),
                Artifact.text("second.txt", required=True),
            ],
        )

    real_encode = sessions.codec.encode

    def reject_value(value):
        if value == "unsupported checkpoint":
            raise TypeError("value cannot be stored")
        return real_encode(value)

    monkeypatch.setattr(sessions.codec, "encode", reject_value)
    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(writer)

    assert result.status == "failed"
    assert "value cannot be stored" in result.error
    assert first.read_text() == "old first"
    assert second.read_text() == "old second"
    assert len(provider.calls) == 1


def test_new_client_recovers_typed_value_and_capture_after_finish_crash(
    tmp_path, monkeypatch
):
    validations = []

    class Answer(BaseModel):
        count: int

        @field_validator("count")
        @classmethod
        def record_validation(cls, value):
            validations.append(value)
            return value

    def write(request):
        request.artifacts["first"].write_text("published first")
        request.artifacts["second"].write_text("published second")
        return ProviderResponse('{"count": 3}', usage={"total_tokens": 4})

    @workflow
    def writer():
        return Session().run(
            "write",
            returns=Answer,
            writes=[
                Artifact.text("first.txt", required=True),
                Artifact.text("second.txt", required=True),
            ],
        )

    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:
        finish = client.journal.finish
        interrupted = False

        def crash_provider_finish(operation_id, result):
            nonlocal interrupted
            if (
                client.journal.get(operation_id)["kind"] == "provider"
                and not interrupted
            ):
                interrupted = True
                raise KeyboardInterrupt()
            return finish(operation_id, result)

        monkeypatch.setattr(client.journal, "finish", crash_provider_finish)
        paused = client.run(writer, task_id="task", run_id="run")
        first_path = provider.calls[0].artifacts["first"]
        second_path = provider.calls[0].artifacts["second"]
    assert paused.status == "interrupted"
    assert validations == [3]

    first_path.unlink()
    second_path.write_text("mutable edit")
    replacement = FakeProvider([])
    with Botpipe(tmp_path, provider=replacement) as client:
        resumed = client.resume(paused.run_id, workflow=writer)

    assert resumed.ok, resumed.error
    assert resumed.value.value.count == 3
    assert resumed.value.artifacts.first.read_text() == "published first"
    assert resumed.value.artifacts.second.read_text() == "published second"
    assert resumed.value.usage == {"total_tokens": 4}
    assert validations == [3]
    assert replacement.calls == []


def test_resume_finishes_rollback_interrupted_after_quarantine(tmp_path, monkeypatch):
    import botpipe.artifacts as artifacts

    destination = tmp_path / "result.json"
    destination.write_text('{"old": true}')

    def invalid(request):
        request.artifacts["result"].write_text("invalid")
        return "response"

    @workflow
    def writer():
        return Session().run(
            "write",
            writes=[Artifact.json(destination, required=True)],
            retries=0,
        )

    provider = FakeProvider([invalid])
    real_replace = artifacts.os.replace
    interrupted = False

    def crash_after_quarantine(source, target):
        nonlocal interrupted
        real_replace(source, target)
        if "quarantine" in artifacts.Path(target).parts and not interrupted:
            interrupted = True
            raise KeyboardInterrupt()

    monkeypatch.setattr(artifacts.os, "replace", crash_after_quarantine)
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(writer, task_id="task", run_id="run")
    assert paused.status == "interrupted"
    monkeypatch.setattr(artifacts.os, "replace", real_replace)

    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        resumed = client.resume(paused.run_id, workflow=writer)
    assert resumed.status == "failed", resumed.error
    assert "Invalid json artifact" in resumed.error
    assert destination.read_text() == '{"old": true}'
    assert len(provider.calls) == 1


def test_authorized_retry_resumes_between_old_rollback_and_new_prepare(
    tmp_path, monkeypatch
):
    destination = tmp_path / "result.txt"
    destination.write_text("original")

    class StoppedProvider(FakeProvider):
        def recover(self, request):
            return Stopped("attempt is stopped")

    def interrupted(request):
        request.artifacts["result"].write_text("old attempt")
        raise KeyboardInterrupt()

    def retry(request):
        assert not request.artifacts["result"].exists()
        request.artifacts["result"].write_text("fresh attempt")
        return "done"

    @workflow
    def writer():
        return Session().run(
            "write", writes=[Artifact.text(destination, required=True)]
        )

    provider = StoppedProvider([interrupted, retry])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(writer, task_id="task", run_id="run")
        operation = _provider_operation(client, paused.run_id)
        client.resolve(paused.run_id, operation["id"], retry=True)

        real_prepare = ArtifactStore.prepare
        interrupted_prepare = False

        def crash_before_new_prepare(store, writes, operation_id):
            nonlocal interrupted_prepare
            if operation_id.endswith(":generation:1") and not interrupted_prepare:
                interrupted_prepare = True
                raise KeyboardInterrupt()
            return real_prepare(store, writes, operation_id)

        monkeypatch.setattr(ArtifactStore, "prepare", crash_before_new_prepare)
        crashed = client.resume(paused.run_id, workflow=writer)
    assert crashed.status == "interrupted"
    assert destination.read_text() == "original"

    monkeypatch.setattr(ArtifactStore, "prepare", real_prepare)
    with Botpipe(tmp_path, provider=provider) as client:
        resumed = client.resume(paused.run_id, workflow=writer)
    assert resumed.ok, resumed.error
    assert resumed.value.artifacts.result.read_text() == "fresh attempt"
    assert len(provider.calls) == 2


def test_capture_oserror_stays_interrupted_and_recovers_without_provider(
    tmp_path, monkeypatch
):
    destination = tmp_path / "result.txt"
    destination.write_text("original")

    def write(request):
        request.artifacts["result"].write_text("provider output")
        return "done"

    @workflow
    def writer():
        return Session().run(
            "write", writes=[Artifact.text(destination, required=True)]
        )

    real_capture = ArtifactStore.capture
    failed = False

    def fail_once(store, writes, operation_id):
        nonlocal failed
        if not failed:
            failed = True
            real_capture(store, writes, operation_id)
            raise OSError("simulated publication failure")
        return real_capture(store, writes, operation_id)

    monkeypatch.setattr(ArtifactStore, "capture", fail_once)
    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(writer, task_id="task", run_id="run")
    assert paused.status == "interrupted"
    assert destination.read_text() == "provider output", paused.error
    destination.write_text("mutable edit after publication")

    replacement = FakeProvider([])
    with Botpipe(tmp_path, provider=replacement) as client:
        resumed = client.resume(paused.run_id, workflow=writer)
    assert resumed.ok, resumed.error
    assert resumed.value.artifacts.result.read_text() == "provider output"
    assert len(provider.calls) == 1
    assert replacement.calls == []


@pytest.mark.parametrize(
    "fields",
    [
        {"usage": {"unsupported": object()}},
        {"metadata": {"unsupported": object()}},
        {"usage": None},
        {"metadata": {"tuple": (1, 2)}},
    ],
)
def test_invalid_response_envelope_preserves_uncertain_outputs(tmp_path, fields):
    destination = tmp_path / "result.txt"
    destination.write_text("original")

    def write(request):
        request.artifacts["result"].write_text("attempted output")
        return ProviderResponse("done", **fields)

    @workflow
    def writer():
        return Session().run(
            "write", writes=[Artifact.text(destination, required=True)]
        )

    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:
        result = client.run(writer)
        replay = client.resume(result.run_id, workflow=writer)

    assert result.status == replay.status == "interrupted"
    assert "ProviderResponse" in result.error
    assert destination.read_text() == "attempted output"
    assert len(provider.calls) == 1


def test_preparation_io_failure_resumes_before_first_dispatch(tmp_path, monkeypatch):
    import botpipe.artifacts as artifacts

    destination = tmp_path / "result.txt"
    destination.write_text("original")

    def write(request):
        assert not request.artifacts["result"].exists()
        request.artifacts["result"].write_text("fresh output")
        return "done"

    @workflow
    def writer():
        return Session().run(
            "write", writes=[Artifact.text(destination, required=True)]
        )

    original_replace = artifacts.os.replace
    failed = False

    def fail_after_backup(source, target):
        nonlocal failed
        original_replace(source, target)
        if "previous" in artifacts.Path(target).parts and not failed:
            failed = True
            raise OSError("lost backup acknowledgement")

    monkeypatch.setattr(artifacts.os, "replace", fail_after_backup)
    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:
        interrupted = client.run(writer)
        assert interrupted.status == "interrupted", interrupted.error
        assert provider.calls == []
        resumed = client.resume(interrupted.run_id, workflow=writer)

    assert resumed.ok, resumed.error
    assert resumed.value.artifacts.result.read_text() == "fresh output"
    assert len(provider.calls) == 1


def test_rejected_dispatch_resumes_interrupted_restoration(tmp_path, monkeypatch):
    import botpipe.artifacts as artifacts

    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    first.write_text("old first")
    second.write_text("old second")

    @workflow
    def writer():
        return Session().run(
            "write", writes=[Artifact.text(first), Artifact.text(second)]
        )

    original_link = artifacts.os.link
    failed = False

    def fail_after_first_restore(source, target, **kwargs):
        nonlocal failed
        original_link(source, target, **kwargs)
        if artifacts.Path(target) == first and not failed:
            failed = True
            raise OSError("lost restore acknowledgement")

    monkeypatch.setattr(artifacts.os, "link", fail_after_first_restore)

    class BeforeDispatchPolicyProvider(FakeProvider):
        # Native adapters reserve dispatch themselves and reject unsupported
        # policy before launching a process.
        _reserves_dispatch = True

    provider = BeforeDispatchPolicyProvider([ProviderPolicyError("unsupported policy")])
    with Botpipe(tmp_path, provider=provider) as client:
        interrupted = client.run(writer)
        assert interrupted.status == "interrupted", interrupted.error
        resumed = client.resume(interrupted.run_id, workflow=writer)

    assert resumed.status == "failed"
    assert "unsupported policy" in resumed.error
    assert first.read_text() == "old first"
    assert second.read_text() == "old second"
    assert len(provider.calls) == 1


@pytest.mark.parametrize("after_commit", [False, True])
@pytest.mark.parametrize("checkpoint", ["response", "validated_value", "finish"])
def test_checkpoint_io_failure_recovers_without_dispatch(
    tmp_path, monkeypatch, after_commit, checkpoint
):
    def write(request):
        request.artifacts["result"].write_text("committed output")
        return "done"

    @workflow
    def writer():
        return Session().run(
            "write", writes=[Artifact.text("result.txt", required=True)]
        )

    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:
        method = "finish" if checkpoint == "finish" else "response"
        original = getattr(client.journal, method)
        failed = False

        def fail_checkpoint(operation_id, record, **kwargs):
            nonlocal failed
            matches = client.journal.get(operation_id)["kind"] == "provider" and (
                checkpoint == "finish"
                or (
                    "text" in record
                    and ("validated_value" in record)
                    == (checkpoint == "validated_value")
                )
            )
            if matches and not failed:
                failed = True
                if after_commit:
                    original(operation_id, record, **kwargs)
                raise OSError("lost checkpoint acknowledgement")
            return original(operation_id, record, **kwargs)

        monkeypatch.setattr(client.journal, method, fail_checkpoint)
        first = client.run(writer)
        assert first.ok if after_commit else first.status == "interrupted", first.error
        if checkpoint == "finish":
            provider.calls[0].artifacts["result"].write_text("later mutable edit")
        resumed = client.resume(first.run_id, workflow=writer)

    assert resumed.ok, resumed.error
    assert resumed.value.artifacts.result.read_text() == "committed output"
    assert len(provider.calls) == 1


def test_partial_capture_uses_published_blob_after_mutable_source_edit(
    tmp_path, monkeypatch
):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("old first")
    second.write_text("old second")

    def write(request):
        request.artifacts["first"].write_text("provider first")
        request.artifacts["second"].write_text("provider second")
        return "done"

    @workflow
    def writer():
        return Session().run(
            "write",
            writes=[
                Artifact.text(first, required=True),
                Artifact.text(second, required=True),
            ],
        )

    real_snapshot = ArtifactStore._snapshot
    interrupted = False

    def crash_after_first_blob(store, artifact, source, data):
        nonlocal interrupted
        handle = real_snapshot(store, artifact, source, data)
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt()
        return handle

    monkeypatch.setattr(ArtifactStore, "_snapshot", crash_after_first_blob)
    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(writer, task_id="task", run_id="run")
    assert paused.status == "interrupted"
    first.write_text("editor first")
    monkeypatch.setattr(ArtifactStore, "_snapshot", real_snapshot)

    replacement = FakeProvider([])
    with Botpipe(tmp_path, provider=replacement) as client:
        resumed = client.resume(paused.run_id, workflow=writer)

    assert resumed.ok, resumed.error
    assert resumed.value.artifacts.first.read_text() == "provider first"
    assert resumed.value.artifacts.second.read_text() == "provider second"
    assert len(provider.calls) == 1
    assert replacement.calls == []


def test_partial_capture_fences_changed_source_until_intended_bytes_return(
    tmp_path, monkeypatch
):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("old first")
    second.write_text("old second")

    def write(request):
        request.artifacts["first"].write_text("provider first")
        request.artifacts["second"].write_text("provider second")
        return "done"

    @workflow
    def writer():
        return Session().run(
            "write",
            writes=[
                Artifact.text(first, required=True),
                Artifact.text(second, required=True),
            ],
        )

    real_snapshot = ArtifactStore._snapshot
    interrupted = False

    def crash_after_first_blob(store, artifact, source, data):
        nonlocal interrupted
        handle = real_snapshot(store, artifact, source, data)
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt()
        return handle

    monkeypatch.setattr(ArtifactStore, "_snapshot", crash_after_first_blob)
    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:
        paused = client.run(writer, task_id="task", run_id="run")
    assert paused.status == "interrupted"
    second.write_text("editor second")
    monkeypatch.setattr(ArtifactStore, "_snapshot", real_snapshot)

    replacement = FakeProvider([])
    with Botpipe(tmp_path, provider=replacement) as client:
        blocked = client.resume(paused.run_id, workflow=writer)
    assert blocked.status == "interrupted"
    assert "no longer matches its capture intent" in blocked.error
    assert first.read_text() == "provider first"
    assert second.read_text() == "editor second"
    assert replacement.calls == []

    second.write_text("provider second")
    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        resumed = client.resume(paused.run_id, workflow=writer)
    assert resumed.ok, resumed.error
    assert resumed.value.artifacts.first.read_text() == "provider first"
    assert resumed.value.artifacts.second.read_text() == "provider second"
    assert len(provider.calls) == 1
