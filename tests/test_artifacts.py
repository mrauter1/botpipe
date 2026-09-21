from __future__ import annotations

import json

import pytest
from pydantic import BaseModel

from botpipe.artifacts import (
    Artifact,
    ArtifactError,
    ArtifactHandle,
    ArtifactMap,
    ArtifactStore,
)


class Report(BaseModel):
    count: int


def test_multiple_artifacts_are_immutable_and_serializable(tmp_path):
    store = ArtifactStore(tmp_path)
    writes = [
        Artifact.json("report.json", schema=Report, required=True),
        Artifact.md("notes.md", required=True),
    ]
    paths = store.prepare(writes, "turn-1")
    paths["report"].write_text('{"count": 2}')
    paths["notes"].write_text("First report")
    result = store.capture(writes, "turn-1")
    restored = ArtifactMap.from_record(json.loads(json.dumps(result.to_record())))
    assert restored.report.read_model() == Report(count=2)
    assert restored.notes.read_text() == "First report"
    paths["report"].write_text('{"count": 99}')
    assert result.report.read_json() == {"count": 2}
    assert store.capture(writes, "turn-1").report.digest == result.report.digest


def test_preparation_cannot_accept_stale_output_and_is_idempotent(tmp_path):
    store = ArtifactStore(tmp_path)
    writes = [Artifact.json("report.json", required=True)]
    (tmp_path / "report.json").write_text('{"stale": true}')
    paths = store.prepare(writes, "turn-1")
    assert not paths["report"].exists()
    with pytest.raises(ArtifactError, match="Required artifact"):
        store.capture(writes, "turn-1")
    paths["report"].write_text('{"fresh": true}')
    store.prepare(writes, "turn-1")
    assert store.capture(writes, "turn-1").report.read_json() == {"fresh": True}


def test_optional_stale_output_is_not_returned(tmp_path):
    (tmp_path / "optional.txt").write_text("stale")
    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("optional.txt")]
    store.prepare(writes, "turn")
    assert not store.capture(writes, "turn")


def test_schemas_and_required_outputs_are_validated_as_one_set(tmp_path):
    store = ArtifactStore(tmp_path)
    writes = [
        Artifact.text("good.txt", required=True),
        Artifact.json("bad.json", schema=Report, required=True),
    ]
    paths = store.prepare(writes, "turn")
    paths["good"].write_text("valid")
    paths["bad"].write_text('{"count": "oops"}')
    with pytest.raises(ArtifactError, match="Invalid json artifact"):
        store.capture(writes, "turn")
    assert not list((tmp_path / ".artifacts").rglob("capture.json"))
    paths["bad"].write_text('{"count": 3}')
    assert len(store.capture(writes, "turn")) == 2


def test_json_schema_validation_and_local_model_round_trip(tmp_path):
    class LocalModel(BaseModel):
        value: int

    store = ArtifactStore(tmp_path)
    handle = store.publish(
        Artifact.json("local.json", schema=LocalModel), {"value": 1}, "local"
    )
    restored = ArtifactHandle.from_record(handle.to_record())
    assert restored.read_model(LocalModel).value == 1
    with pytest.raises(ArtifactError, match="Pass a model type"):
        restored.read_model()
    with pytest.raises(ArtifactError, match="Invalid json artifact"):
        store.publish(
            Artifact.json("bad.json", schema={"type": "integer"}), "bad", "bad"
        )


@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        ".artifacts/pwn.txt",
        "receipts/response.json",
        "state.sqlite",
        "journal.db-wal",
    ],
)
def test_runtime_state_and_escape_paths_are_rejected(tmp_path, path):
    with pytest.raises(ArtifactError):
        ArtifactStore(tmp_path).prepare([Artifact.text(path)], "turn")


def test_symlinks_and_protected_paths_are_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "link").symlink_to(outside, target_is_directory=True)
    store = ArtifactStore(folder, workspace=tmp_path, forbidden_paths=[outside])
    for path in ("link/file.txt", outside / "file.txt"):
        with pytest.raises(ArtifactError):
            store.prepare([Artifact.text(path)], "turn")


def test_new_versions_and_materialized_aliases_do_not_mutate_snapshots(tmp_path):
    store = ArtifactStore(tmp_path)
    artifact = Artifact.json("plan.json")
    first = store.publish(artifact, {"version": 1}, "v1")
    second = store.publish(artifact, {"version": 2}, "v2")
    assert first.path != second.path
    assert store.materialize(second) == tmp_path / "plan.json"
    assert first.read_json() == {"version": 1}
    assert second.read_json() == {"version": 2}
    with pytest.raises(ArtifactError, match="changed"):
        store.publish(artifact, {"version": 3}, "v2")


def test_interruption_after_backup_resumes_preparation(tmp_path, monkeypatch):
    import botpipe.artifacts as module

    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("old.txt", required=True)]
    (tmp_path / "old.txt").write_text("before")
    atomic = module._atomic

    def fail_final_manifest(path, data):
        if path.name == "prepare.json" and json.loads(data)["prepared"]:
            raise KeyboardInterrupt()
        return atomic(path, data)

    monkeypatch.setattr(module, "_atomic", fail_final_manifest)
    with pytest.raises(KeyboardInterrupt):
        store.prepare(writes, "turn")
    monkeypatch.setattr(module, "_atomic", atomic)
    store.prepare(writes, "turn")
    assert not (tmp_path / "old.txt").exists()
    store.restore("turn")
    assert (tmp_path / "old.txt").read_text() == "before"
    with pytest.raises(ArtifactError, match="preparation"):
        store.capture(writes, "turn")


def test_interruption_after_blob_publish_resumes_without_stale_output(
    tmp_path, monkeypatch
):
    import botpipe.artifacts as module

    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt", required=True)]
    store.prepare(writes, "turn")
    (tmp_path / "result.txt").write_text("provider result")
    atomic = module._atomic

    def fail_capture_manifest(path, data):
        if path.name == "capture.json":
            raise KeyboardInterrupt()
        return atomic(path, data)

    monkeypatch.setattr(module, "_atomic", fail_capture_manifest)
    with pytest.raises(KeyboardInterrupt):
        store.capture(writes, "turn")
    monkeypatch.setattr(module, "_atomic", atomic)
    recreated = ArtifactStore(tmp_path)
    recreated.prepare(writes, "turn")
    assert recreated.capture(writes, "turn").result.read_text() == "provider result"


def test_restore_never_overwrites_new_provider_output(tmp_path):
    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt")]
    (tmp_path / "result.txt").write_text("old")
    store.prepare(writes, "turn")
    (tmp_path / "result.txt").write_text("new")
    store.restore("turn")
    assert (tmp_path / "result.txt").read_text() == "new"


def test_completed_restore_replay_preserves_later_destination_edits(tmp_path):
    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt")]
    destination = tmp_path / "result.txt"
    destination.write_text("old")
    store.prepare(writes, "turn")

    store.restore("turn")
    assert destination.read_text() == "old"
    destination.write_text("edited after restore")

    store.restore("turn")
    assert destination.read_text() == "edited after restore"


def test_snapshot_tampering_is_detected(tmp_path):
    handle = ArtifactStore(tmp_path).publish(Artifact.text("x.txt"), "original", "x")
    handle.path.chmod(0o644)
    handle.path.write_text("changed")
    with pytest.raises(ArtifactError, match="modified"):
        handle.read_text()


def test_restore_crash_cannot_make_stale_output_capturable(tmp_path, monkeypatch):
    import botpipe.artifacts as module

    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt", required=True)]
    destination = tmp_path / "result.txt"
    destination.write_text("old")
    store.prepare(writes, "turn")
    link = module.os.link

    def interrupt_after_restore(source, path, **kwargs):
        link(source, path, **kwargs)
        if module.Path(path) == destination:
            raise KeyboardInterrupt()

    monkeypatch.setattr(module.os, "link", interrupt_after_restore)
    with pytest.raises(KeyboardInterrupt):
        store.restore("turn")
    assert destination.read_text() == "old"
    with pytest.raises(ArtifactError, match="preparation"):
        store.capture(writes, "turn")


def test_published_capture_replay_does_not_observe_mutable_destination(tmp_path):
    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt", required=True)]
    destination = store.prepare(writes, "turn")["result"]
    destination.write_text("published")
    original = store.capture(writes, "turn")
    destination.unlink()
    destination.mkdir()
    assert store.prepare(writes, "turn")["result"] == destination
    assert store.capture(writes, "turn").result == original.result
    assert original.result.read_text() == "published"


def test_hardlink_alias_to_explicitly_protected_state_is_rejected(tmp_path):
    import os

    protected = tmp_path / "ledger"
    protected.write_bytes(b"runtime state")
    alias = tmp_path / "report.txt"
    os.link(protected, alias)
    store = ArtifactStore(tmp_path, forbidden_paths=[protected])
    with pytest.raises(ArtifactError, match="protected state"):
        store.prepare([Artifact.text(alias)], "turn")


def test_generic_schema_round_trip_requires_explicit_model_type(tmp_path):
    handle = ArtifactStore(tmp_path).publish(
        Artifact.json("reports.json", schema=list[Report]), [{"count": 2}], "generic"
    )
    restored = ArtifactHandle.from_record(handle.to_record())
    assert restored.read_model(list[Report]) == [Report(count=2)]
    # A qualified builtins:list reference would silently lose its element type.
    with pytest.raises(ArtifactError, match="Pass a model type"):
        restored.read_model()
