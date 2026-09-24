from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import BaseModel

from botpipe.artifacts import (
    Artifact,
    ArtifactCaptureRecoveryError,
    ArtifactError,
    ArtifactHandle,
    ArtifactMap,
    ArtifactStore,
)


class Report(BaseModel):
    count: int


def test_current_preexisting_artifacts_are_captured_and_immutable(tmp_path):
    store = ArtifactStore(tmp_path)
    writes = [
        Artifact.json("report.json", schema=Report, required=True),
        Artifact.md("notes.md", required=True),
    ]
    paths = store.destinations(writes)
    paths["report"].write_text('{"count": 2}')
    paths["notes"].write_text("Existing report")

    result = store.capture(writes, "turn-1")
    restored = ArtifactMap.from_record(json.loads(json.dumps(result.to_record())))
    assert restored.report.read_model() == Report(count=2)
    assert restored.notes.read_text() == "Existing report"

    paths["report"].write_text('{"count": 99}')
    assert result.report.read_json() == {"count": 2}
    assert store.capture(writes, "turn-1").report.digest == result.report.digest


def test_missing_required_fails_and_missing_optional_is_omitted(tmp_path):
    store = ArtifactStore(tmp_path)
    optional = Artifact.text("optional.txt")
    assert not store.capture([optional], "optional")

    required = Artifact.text("required.txt", required=True)
    with pytest.raises(ArtifactError, match="Required artifact is missing"):
        store.capture([required], "required")
    assert not (store._operation("required") / "capture.json").exists()


def test_preexisting_optional_artifact_is_current_output(tmp_path):
    destination = tmp_path / "optional.txt"
    destination.write_text("already here")
    captured = ArtifactStore(tmp_path).capture(
        [Artifact.text("optional.txt")], "turn"
    )
    assert captured.optional.read_text() == "already here"
    assert destination.read_text() == "already here"


def test_validation_failure_leaves_all_current_files_untouched(tmp_path):
    good = tmp_path / "good.txt"
    bad = tmp_path / "bad.json"
    good.write_text("valid")
    bad.write_text('{"count": "oops"}')
    store = ArtifactStore(tmp_path)
    writes = [
        Artifact.text("good.txt", required=True),
        Artifact.json("bad.json", schema=Report, required=True),
    ]

    with pytest.raises(ArtifactError, match="Invalid json artifact"):
        store.capture(writes, "turn")

    assert good.read_text() == "valid"
    assert bad.read_text() == '{"count": "oops"}'
    assert not list((tmp_path / ".artifacts").rglob("capture.json"))
    assert not list((tmp_path / ".artifacts").rglob("capture.pending.json"))


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
    ],
)
def test_artifact_store_metadata_and_escape_paths_are_rejected(tmp_path, path):
    with pytest.raises(ArtifactError):
        ArtifactStore(tmp_path).destinations([Artifact.text(path)])


@pytest.mark.parametrize("path", ["receipts/response.json", "state.sqlite"])
def test_ordinary_directories_and_database_names_are_valid_artifacts(tmp_path, path):
    assert ArtifactStore(tmp_path).destinations([Artifact.text(path)])


def test_symlinks_and_protected_paths_are_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    folder = tmp_path / "run"
    folder.mkdir()
    (folder / "link").symlink_to(outside, target_is_directory=True)
    store = ArtifactStore(folder, workspace=tmp_path, forbidden_paths=[outside])
    for path in ("link/file.txt", outside / "file.txt"):
        with pytest.raises(ArtifactError):
            store.destinations([Artifact.text(path)])


def test_destinations_are_read_only_unless_parent_creation_is_requested(tmp_path):
    existing = tmp_path / "existing.txt"
    existing.write_text("keep")
    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("nested/result.txt"), Artifact.text(existing)]

    paths = store.destinations(writes)
    assert not paths["result"].parent.exists()
    assert existing.read_text() == "keep"

    created = store.destinations(writes, create_parents=True)
    assert created == paths
    assert paths["result"].parent.is_dir()
    assert existing.read_text() == "keep"


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


def test_interruption_after_blob_publish_replays_without_mutable_source(
    tmp_path, monkeypatch
):
    import botpipe.artifacts as module

    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt", required=True)]
    destination = tmp_path / "result.txt"
    destination.write_text("captured bytes")
    atomic = module._atomic

    def fail_capture_manifest(path, data):
        if path.name == "capture.json":
            raise KeyboardInterrupt()
        return atomic(path, data)

    monkeypatch.setattr(module, "_atomic", fail_capture_manifest)
    with pytest.raises(KeyboardInterrupt):
        store.capture(writes, "turn")
    monkeypatch.setattr(module, "_atomic", atomic)
    destination.write_text("later edit")

    recreated = ArtifactStore(tmp_path)
    assert recreated.capture(writes, "turn").result.read_text() == "captured bytes"


def test_pending_capture_without_blob_requires_unchanged_source(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt", required=True)]
    destination = tmp_path / "result.txt"
    destination.write_text("inventoried")

    def interrupt_before_snapshot(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(store, "_snapshot", interrupt_before_snapshot)
    with pytest.raises(KeyboardInterrupt):
        store.capture(writes, "turn")
    destination.write_text("changed")

    with pytest.raises(ArtifactCaptureRecoveryError, match="capture intent"):
        ArtifactStore(tmp_path).capture(writes, "turn")
    assert destination.read_text() == "changed"


def test_published_capture_replay_does_not_observe_mutable_destination(tmp_path):
    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt", required=True)]
    destination = tmp_path / "result.txt"
    destination.write_text("published")
    original = store.capture(writes, "turn")
    destination.unlink()
    destination.mkdir()
    (store._operation("turn") / "capture.pending.json").write_text("damaged")

    replay = store.capture(writes, "turn")
    recovered = ArtifactStore(tmp_path).captured("turn")
    assert recovered is not None
    assert replay.result == original.result == recovered.result
    assert replay.result.read_text() == "published"


def test_snapshot_tampering_is_detected_on_replay(tmp_path):
    store = ArtifactStore(tmp_path)
    destination = tmp_path / "x.txt"
    destination.write_text("original")
    handle = store.capture([Artifact.text("x.txt")], "turn").x
    handle.path.chmod(0o644)
    handle.path.write_text("changed")

    with pytest.raises(ArtifactError, match="modified"):
        store.captured("turn")


def test_capture_recovery_repeats_publication_directory_sync(tmp_path, monkeypatch):
    import botpipe.artifacts as module

    store = ArtifactStore(tmp_path)
    destination = tmp_path / "result.txt"
    destination.write_text("published")
    captured = store.capture([Artifact.text("result.txt", required=True)], "turn")
    synced = []
    monkeypatch.setattr(module, "_sync_dir", synced.append)

    assert store.captured("turn").result == captured.result
    assert captured.result.path.parent in synced
    assert store._operation("turn") in synced


def test_hardlink_alias_to_explicitly_protected_state_is_rejected(tmp_path):
    import os

    protected = tmp_path / "ledger"
    protected.write_bytes(b"runtime state")
    alias = tmp_path / "report.txt"
    os.link(protected, alias)
    store = ArtifactStore(tmp_path, forbidden_paths=[protected])
    with pytest.raises(ArtifactError, match="protected state"):
        store.destinations([Artifact.text(alias)])


def test_capture_recovery_revalidates_pending_blob(tmp_path, monkeypatch):
    store = ArtifactStore(tmp_path)
    writes = [Artifact.json("result.json", required=True)]
    destination = tmp_path / "result.json"
    destination.write_text('{"valid": true}')

    def interrupt_before_snapshot(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(store, "_snapshot", interrupt_before_snapshot)
    with pytest.raises(KeyboardInterrupt):
        store.capture(writes, "turn")

    invalid = b"not json"
    digest = hashlib.sha256(invalid).hexdigest()
    intent_path = store._operation("turn") / "capture.pending.json"
    intent = json.loads(intent_path.read_text())
    intent["contents"][0].update(digest=digest, length=len(invalid))
    intent_path.write_text(json.dumps(intent))
    blob = store.root / "blobs" / digest[:2] / digest / destination.name
    blob.parent.mkdir(parents=True)
    blob.write_bytes(invalid)

    with pytest.raises(ArtifactCaptureRecoveryError):
        ArtifactStore(tmp_path).capture(writes, "turn")


@pytest.mark.parametrize("corruption", ["missing-required", "nonhex-digest"])
def test_capture_recovery_rejects_malformed_pending_content(
    tmp_path, monkeypatch, corruption
):
    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt", required=True)]
    destination = tmp_path / "result.txt"
    destination.write_text("provider output")

    def interrupt_before_snapshot(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(store, "_snapshot", interrupt_before_snapshot)
    with pytest.raises(KeyboardInterrupt):
        store.capture(writes, "turn")
    intent_path = store._operation("turn") / "capture.pending.json"
    intent = json.loads(intent_path.read_text())
    if corruption == "missing-required":
        intent["contents"] = []
    else:
        intent["contents"][0]["digest"] = "z" * 64
    intent_path.write_text(json.dumps(intent))

    with pytest.raises(ArtifactCaptureRecoveryError):
        ArtifactStore(tmp_path).capture(writes, "turn")


def test_generic_schema_round_trip_requires_explicit_model_type(tmp_path):
    handle = ArtifactStore(tmp_path).publish(
        Artifact.json("reports.json", schema=list[Report]), [{"count": 2}], "generic"
    )
    restored = ArtifactHandle.from_record(handle.to_record())
    assert restored.read_model(list[Report]) == [Report(count=2)]
    with pytest.raises(ArtifactError, match="Pass a model type"):
        restored.read_model()
