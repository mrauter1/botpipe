"""Recovery must distinguish provider snapshots from explicitly adopted files."""

import hashlib
import json

import pytest

from botpipe import Artifact, Botpipe, BotpipeError, Provider, workflow
from botpipe.artifacts import ArtifactStore
from botpipe.providers import FakeProvider, ProviderResponse
from botpipe.recovery import Running, Unknown


def _provider_row(client, run_id):
    return next(
        row for row in client.journal.operations(run_id) if row["kind"] == "provider"
    )


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("interface", ["sdk", "cli"])
def test_interrupted_initial_capture_requires_explicit_file_identity(
    tmp_path, monkeypatch, interface
):
    import botpipe.artifacts as artifacts

    destination = tmp_path / "result.txt"
    optional = tmp_path / "optional.txt"

    def write(request):
        request.artifacts["result"].write_text("provider output")
        return ProviderResponse("actual response", session_id="actual-session")

    @workflow
    def job():
        return Provider().run(
            "write",
            writes=[Artifact.text(destination, required=True), Artifact.text(optional)],
        )

    original = artifacts._validate

    def crash(data, kind, schema):
        original(data, kind, schema)
        raise KeyboardInterrupt("before capture inventory")

    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:
        monkeypatch.setattr(artifacts, "_validate", crash)
        first = client.run(job)
        assert first.status == "interrupted"
        assert not list(tmp_path.rglob("capture.pending.json"))
        monkeypatch.setattr(artifacts, "_validate", original)
        destination.write_text("operator selected replacement")
        resumed = client.resume(first.run_id, workflow=job)
        assert resumed.status == "interrupted"
        assert "no durable artifact inventory" in resumed.error
        row = _provider_row(client, first.run_id)
        before = row["response"]
        with pytest.raises(ValueError, match="every declared output"):
            client.resolve(
                first.run_id,
                row["id"],
                artifact_digests={"result": _digest(destination)},
            )
        assert client.journal.get(row["id"])["response"] == before
        digests = {"result": _digest(destination), "optional": None}
        if interface == "cli":
            import botpipe.cli as cli

            monkeypatch.setattr(cli, "_client", lambda args: client)
            assert (
                cli.main(
                    [
                        "resolve",
                        first.run_id,
                        row["id"],
                        "--artifact-digests",
                        json.dumps(digests),
                        "--no-resume",
                    ]
                )
                == 0
            )
        else:
            client.resolve(first.run_id, row["id"], artifact_digests=digests)
        # The provider receipt remains authoritative; only the files are adopted.
        saved = client.journal.get(row["id"])["response"]
        assert saved["text"] == "actual response"
        assert saved["session_id"] == "actual-session"
        assert saved["artifact_resolution"]["source"] == "operator"
        complete = client.resume(first.run_id, workflow=job)
        assert complete.ok, complete.error
        assert (
            complete.value.artifacts.result.read_text()
            == "operator selected replacement"
        )
        assert "optional" not in complete.value.artifacts
        assert len(provider.calls) == 1
        intent = json.loads(next(tmp_path.rglob("capture.pending.json")).read_text())
        assert intent["source"] == "operator"


def test_reconciled_invalid_artifact_is_validated_during_capture_and_repaired(
    tmp_path, monkeypatch
):
    destination = tmp_path / "result.json"

    def invalid(request):
        request.artifacts["result"].write_text("not json")
        return "invalid response"

    def repair(request):
        assert not request.artifacts["result"].exists()
        request.artifacts["result"].write_text('{"fixed": true}')
        return "repair response"

    @workflow
    def job():
        return Provider().run(
            "write",
            writes=[Artifact.json(destination, required=True)],
            output_retries=1,
        )

    capture = ArtifactStore.capture
    provider = FakeProvider([invalid, repair])
    with Botpipe(tmp_path, provider=provider) as client:
        monkeypatch.setattr(
            ArtifactStore,
            "capture",
            lambda *args, **kwargs: (_ for _ in ()).throw(
                KeyboardInterrupt("before capture intent")
            ),
        )
        first = client.run(job, run_id="invalid-before-capture")
        assert first.status == "interrupted"
        assert not list(tmp_path.rglob("capture.json"))
        assert not list(tmp_path.rglob("capture.pending.json"))

        monkeypatch.setattr(ArtifactStore, "capture", capture)
        operation = _provider_row(client, first.run_id)
        client.resolve(
            first.run_id,
            operation["id"],
            artifact_digests={"result": _digest(destination)},
        )
        assert destination.read_text() == "not json"
        assert client.journal.get(operation["id"])["status"] == "response"
        assert not list(tmp_path.rglob("capture.json"))

        resumed = client.resume(first.run_id, workflow=job)

    assert resumed.ok, resumed.error
    assert resumed.value.value == "repair response"
    assert resumed.value.artifacts.result.read_text() == '{"fixed": true}'
    assert destination.read_text() == '{"fixed": true}'
    assert len(provider.calls) == 2


def test_adopted_files_must_still_match_when_resume_runs(tmp_path, monkeypatch):
    destination = tmp_path / "result.txt"

    def write(request):
        destination.write_text("selected")
        return "done"

    @workflow
    def job():
        return Provider().run(
            "write", writes=[Artifact.text(destination, required=True)]
        )

    capture = ArtifactStore.capture
    with Botpipe(tmp_path, provider=FakeProvider([write])) as client:
        monkeypatch.setattr(
            ArtifactStore,
            "capture",
            lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()),
        )
        first = client.run(job)
        monkeypatch.setattr(ArtifactStore, "capture", capture)
        row = _provider_row(client, first.run_id)
        client.resolve(
            first.run_id, row["id"], artifact_digests={"result": _digest(destination)}
        )
        destination.write_text("later change")
        resumed = client.resume(first.run_id, workflow=job)
        assert resumed.status == "interrupted"
        assert "changed after operator approval" in resumed.error
        assert not list(tmp_path.rglob("capture.pending.json"))


@pytest.mark.parametrize("outcome", [Unknown("unknown writer"), Running("live writer")])
def test_artifact_reconciliation_cannot_bypass_writer_safety(tmp_path, outcome):
    class RecoveringProvider(FakeProvider):
        def recover(self, request):
            return outcome

    @workflow
    def job():
        return Provider().run(
            "write", writes=[Artifact.text("result.txt", required=True)]
        )

    with Botpipe(
        tmp_path, provider=RecoveringProvider([SystemExit("interrupted dispatch")])
    ) as client:
        with pytest.raises(SystemExit):
            client.run(job, run_id="uncertain")
        row = _provider_row(client, "uncertain")
        before = row["response"]
        with pytest.raises(BotpipeError, match="reconciliation is blocked"):
            client.resolve(
                "uncertain",
                row["id"],
                response=ProviderResponse("claimed"),
                artifact_digests={"result": "0" * 64},
            )
        assert client.journal.get(row["id"])["response"] == before


def test_optional_absence_is_durable_after_inventory(tmp_path, monkeypatch):
    destination = tmp_path / "optional.txt"

    @workflow
    def job():
        return Provider().run("optional", writes=[Artifact.text(destination)])

    capture = ArtifactStore.capture

    def crash_after_capture(*args, **kwargs):
        capture(*args, **kwargs)
        raise KeyboardInterrupt()

    with Botpipe(tmp_path, provider=FakeProvider(["no file"])) as client:
        monkeypatch.setattr(ArtifactStore, "capture", crash_after_capture)
        first = client.run(job)
        monkeypatch.setattr(ArtifactStore, "capture", capture)
        destination.write_text("later addition")
        resumed = client.resume(first.run_id, workflow=job)
        assert resumed.ok, resumed.error
        assert not resumed.value.artifacts


def test_no_write_response_can_recover_without_capture_inventory(tmp_path, monkeypatch):
    @workflow
    def job():
        return Provider().run("text only")

    capture = ArtifactStore.capture
    with Botpipe(tmp_path, provider=FakeProvider(["done"])) as client:
        monkeypatch.setattr(
            ArtifactStore,
            "capture",
            lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()),
        )
        first = client.run(job)
        monkeypatch.setattr(ArtifactStore, "capture", capture)
        resumed = client.resume(first.run_id, workflow=job)
        assert resumed.ok, resumed.error
        assert resumed.value.value == "done"


@pytest.mark.parametrize("mutation", ["invalid_json", "directory"])
def test_approved_artifact_drift_cannot_trigger_output_repair(
    tmp_path, monkeypatch, mutation
):
    destination = tmp_path / "result.json"
    destination.write_text('{"previous": true}')

    def write(request):
        destination.write_text('{"approved": true}')
        return "done"

    @workflow
    def job():
        return Provider().run(
            "write", writes=[Artifact.json(destination, required=True)]
        )

    capture = ArtifactStore.capture
    provider = FakeProvider([write])
    with Botpipe(tmp_path, provider=provider) as client:

        def stop_before_capture(*args, **kwargs):
            raise KeyboardInterrupt()

        monkeypatch.setattr(ArtifactStore, "capture", stop_before_capture)
        first = client.run(job)
        monkeypatch.setattr(ArtifactStore, "capture", capture)
        row = _provider_row(client, first.run_id)
        client.resolve(
            first.run_id, row["id"], artifact_digests={"result": _digest(destination)}
        )
        if mutation == "invalid_json":
            destination.write_text("no longer JSON")
        else:
            destination.unlink()
            destination.mkdir()
        resumed = client.resume(first.run_id, workflow=job)
        assert resumed.status == "interrupted", resumed.error
        assert client.journal.get(row["id"])["status"] == "response"
        assert len(provider.calls) == 1
        assert not list(tmp_path.rglob("rollback.json"))
        if mutation == "invalid_json":
            assert destination.read_text() == "no longer JSON"
        else:
            assert destination.is_dir()
