from __future__ import annotations

import json

import pytest

from botpipe.artifacts import (
    Artifact,
    ArtifactCaptureRecoveryError,
    ArtifactError,
    ArtifactStore,
)


def test_known_stopped_rollback_restores_all_old_files_and_removes_new_outputs(
    tmp_path,
):
    store = ArtifactStore(tmp_path)
    writes = [
        Artifact.text("old.txt", required=True),
        Artifact.json("new.json", required=True),
        Artifact.text("untouched.txt"),
    ]
    (tmp_path / "old.txt").write_text("old value")
    (tmp_path / "untouched.txt").write_text("old optional")
    paths = store.prepare(writes, "attempt-1")
    paths["old"].write_text("new value")

    with pytest.raises(ArtifactError, match="Required artifact"):
        store.capture(writes, "attempt-1")

    store.rollback("attempt-1")
    assert paths["old"].read_text() == "old value"
    assert not paths["new"].exists()
    assert paths["untouched"].read_text() == "old optional"

    # Recovery may call rollback again after losing the acknowledgement.
    store.rollback("attempt-1")
    assert paths["old"].read_text() == "old value"
    with pytest.raises(ArtifactError, match="rolled-back"):
        store.capture(writes, "attempt-1")
    assert [
        path.read_text() for path in store._operation("attempt-1").glob("quarantine/*")
    ] == ["new value"]


def test_rollback_after_invalid_partial_set_allows_clean_retry(tmp_path):
    store = ArtifactStore(tmp_path)
    writes = [
        Artifact.json("report.json", required=True),
        Artifact.text("notes.txt", required=True),
    ]
    (tmp_path / "report.json").write_text('{"old": true}')
    first = store.prepare(writes, "attempt-1")
    first["report"].write_text("invalid")
    first["notes"].write_text("partial")
    with pytest.raises(ArtifactError, match="Invalid json"):
        store.capture(writes, "attempt-1")
    store.rollback("attempt-1")

    second = store.prepare(writes, "attempt-2")
    second["report"].write_text('{"fresh": true}')
    second["notes"].write_text("complete")
    captured = store.capture(writes, "attempt-2")
    assert captured.report.read_json() == {"fresh": True}
    assert captured.notes.read_text() == "complete"


def test_destinations_resolves_without_resuming_a_rolled_back_attempt(tmp_path):
    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt")]
    destination = store.prepare(writes, "turn")["result"]
    destination.write_text("attempt")
    store.rollback("turn")

    assert store.destinations(writes) == {"result": destination}
    with pytest.raises(ArtifactError, match="rolled back"):
        store.prepare(writes, "turn")


@pytest.mark.parametrize("phase", ["quarantine", "restore"])
def test_rollback_resumes_after_interruption_at_each_rename(
    tmp_path, monkeypatch, phase
):
    import botpipe.artifacts as module

    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt", required=True)]
    destination = tmp_path / "result.txt"
    destination.write_text("before")
    store.prepare(writes, "turn")
    destination.write_text("attempt")
    operation = store._operation("turn")
    real_replace = module.os.replace
    interrupted = False

    def interrupt_after_rename(source, target):
        nonlocal interrupted
        source, target = module.Path(source), module.Path(target)
        should_interrupt = (
            phase == "quarantine" and target == operation / "quarantine" / "0"
        ) or (phase == "restore" and target == destination)
        real_replace(source, target)
        if should_interrupt and not interrupted:
            interrupted = True
            raise KeyboardInterrupt()

    monkeypatch.setattr(module.os, "replace", interrupt_after_rename)
    with pytest.raises(KeyboardInterrupt):
        store.rollback("turn")
    monkeypatch.setattr(module.os, "replace", real_replace)

    ArtifactStore(tmp_path).rollback("turn")
    assert destination.read_text() == "before"
    assert (operation / "quarantine" / "0").read_text() == "attempt"
    assert json.loads((operation / "rollback.json").read_text())["completed"]


def test_rollback_fence_survives_interruption_before_first_move(tmp_path, monkeypatch):
    import botpipe.artifacts as module

    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt", required=True)]
    destination = store.prepare(writes, "turn")["result"]
    destination.write_text("attempt")
    real_atomic = module._atomic

    def interrupt_after_fence(path, data):
        real_atomic(path, data)
        if path.name == "rollback.json":
            raise KeyboardInterrupt()

    monkeypatch.setattr(module, "_atomic", interrupt_after_fence)
    with pytest.raises(KeyboardInterrupt):
        store.rollback("turn")
    monkeypatch.setattr(module, "_atomic", real_atomic)

    with pytest.raises(ArtifactError, match="rolled-back"):
        store.capture(writes, "turn")
    store.rollback("turn")
    assert not destination.exists()


def test_directory_and_symlink_attempts_are_quarantined_without_recursive_deletion(
    tmp_path,
):
    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("old.txt"), Artifact.text("created.txt")]
    (tmp_path / "old.txt").write_text("before")
    paths = store.prepare(writes, "turn")
    paths["old"].symlink_to(tmp_path / "missing-target")
    paths["created"].mkdir()
    (paths["created"] / "nested.txt").write_text("keep quarantined")

    store.rollback("turn")

    assert paths["old"].read_text() == "before"
    assert not paths["created"].exists()
    quarantine = store._operation("turn") / "quarantine"
    assert (quarantine / "0").is_symlink()
    assert (quarantine / "1" / "nested.txt").read_text() == "keep quarantined"


def test_rollback_refuses_replaced_parent_and_preserves_external_tree(tmp_path):
    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("nested/result.txt")]
    destination = store.prepare(writes, "turn")["result"]
    destination.parent.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "result.txt").write_text("external")
    destination.parent.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ArtifactError, match="contains a symlink"):
        store.rollback("turn")
    assert (outside / "result.txt").read_text() == "external"


def test_rollback_detects_destination_change_after_durable_inventory(
    tmp_path, monkeypatch
):
    import botpipe.artifacts as module

    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt")]
    destination = store.prepare(writes, "turn")["result"]
    destination.write_text("provider output")
    real_atomic = module._atomic

    def replace_after_inventory(path, data):
        real_atomic(path, data)
        if path.name == "rollback.json":
            destination.write_text("editor output")

    monkeypatch.setattr(module, "_atomic", replace_after_inventory)
    with pytest.raises(ArtifactError, match="changed during rollback"):
        store.rollback("turn")
    assert destination.read_text() == "editor output"


def test_published_capture_is_recoverable_and_cannot_be_rolled_back(tmp_path):
    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt", required=True)]
    destination = store.prepare(writes, "turn")["result"]
    destination.write_text("published")
    captured = store.capture(writes, "turn")
    destination.unlink()
    destination.mkdir()

    recovered = ArtifactStore(tmp_path).captured("turn")
    assert recovered is not None
    assert recovered.result == captured.result
    assert recovered.result.read_text() == "published"
    with pytest.raises(ArtifactError, match="prepared capture"):
        store.rollback("turn")


def test_capture_recovery_repeats_publication_directory_sync(tmp_path, monkeypatch):
    import botpipe.artifacts as module

    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("result.txt", required=True)]
    destination = store.prepare(writes, "turn")["result"]
    destination.write_text("published")
    captured = store.capture(writes, "turn")
    synced = []
    monkeypatch.setattr(module, "_sync_dir", synced.append)

    assert store.captured("turn").result == captured.result
    assert captured.result.path.parent in synced
    assert (store._operation("turn")) in synced


def test_prepare_does_not_fallback_to_copy_when_atomic_rename_fails(
    tmp_path, monkeypatch
):
    import errno

    import botpipe.artifacts as module

    destination = tmp_path / "result.txt"
    destination.write_text("before")
    real_replace = module.os.replace

    def cross_device(source, target):
        if module.Path(source) == destination:
            raise OSError(errno.EXDEV, "cross-device link")
        return real_replace(source, target)

    monkeypatch.setattr(module.os, "replace", cross_device)
    with pytest.raises(OSError) as failure:
        ArtifactStore(tmp_path).prepare([Artifact.text("result.txt")], "turn")
    assert failure.value.errno == errno.EXDEV
    assert destination.read_text() == "before"


def test_restore_resumes_after_interruption_after_atomic_publication(
    tmp_path, monkeypatch
):
    import botpipe.artifacts as module

    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("first.txt"), Artifact.text("second.txt")]
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first before")
    second.write_text("second before")
    store.prepare(writes, "turn")
    real_link = module.os.link
    interrupted = False

    def interrupt_after_link(source, target, **kwargs):
        nonlocal interrupted
        real_link(source, target, **kwargs)
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt()

    monkeypatch.setattr(module.os, "link", interrupt_after_link)
    with pytest.raises(KeyboardInterrupt):
        store.restore("turn")
    monkeypatch.setattr(module.os, "link", real_link)

    ArtifactStore(tmp_path).restore("turn")
    assert first.read_text() == "first before"
    assert second.read_text() == "second before"
    manifest = json.loads((store._operation("turn") / "prepare.json").read_text())
    assert manifest["restored"]
    assert manifest["restore_completed"]


def test_restore_never_overwrites_destination_that_appears_during_restore(
    tmp_path, monkeypatch
):
    import botpipe.artifacts as module

    store = ArtifactStore(tmp_path)
    destination = tmp_path / "result.txt"
    destination.write_text("before")
    store.prepare([Artifact.text("result.txt")], "turn")
    real_link = module.os.link

    def editor_wins_race(source, target, **kwargs):
        destination.write_text("editor value")
        return real_link(source, target, **kwargs)

    monkeypatch.setattr(module.os, "link", editor_wins_race)
    with pytest.raises(ArtifactError, match="conflicts with restoration"):
        store.restore("turn")
    assert destination.read_text() == "editor value"


def test_restore_repairs_a_partially_completed_preparation(tmp_path, monkeypatch):
    import botpipe.artifacts as module

    store = ArtifactStore(tmp_path)
    writes = [Artifact.text("first.txt"), Artifact.text("second.txt")]
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("first before")
    second.write_text("second before")
    real_replace = module.os.replace

    def fail_after_first_backup(source, target):
        real_replace(source, target)
        if module.Path(source) == first:
            raise OSError("lost backup acknowledgement")

    monkeypatch.setattr(module.os, "replace", fail_after_first_backup)
    with pytest.raises(OSError, match="lost backup acknowledgement"):
        store.prepare(writes, "turn")
    monkeypatch.setattr(module.os, "replace", real_replace)

    store.restore("turn")
    assert first.read_text() == "first before"
    assert second.read_text() == "second before"


def test_capture_recovery_revalidates_prepared_blob(tmp_path, monkeypatch):
    import hashlib

    store = ArtifactStore(tmp_path)
    writes = [Artifact.json("result.json", required=True)]
    destination = store.prepare(writes, "turn")["result"]
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
    destination = store.prepare(writes, "turn")["result"]
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
