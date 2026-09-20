from __future__ import annotations

import errno
import os
import stat
from types import SimpleNamespace

import pytest

from botpipe import Artifact
from botpipe.artifacts import ArtifactStore
from botpipe.providers import _atomic_bytes
from botpipe.storage import sync_directory


@pytest.mark.skipif(os.name == "nt", reason="POSIX fallback without O_DIRECTORY")
def test_missing_directory_flag_preserves_artifact_and_receipt_publication(
    tmp_path, monkeypatch
):
    import botpipe.storage as storage

    flushed = []

    def fsync(descriptor):
        flushed.append(stat.S_ISDIR(os.fstat(descriptor).st_mode))
        os.fsync(descriptor)

    # This POSIX implementation lacks only the optional open flag. The
    # directory must still be opened and flushed, rather than silently skipped.
    monkeypatch.setattr(
        storage,
        "os",
        SimpleNamespace(
            name="posix",
            O_RDONLY=os.O_RDONLY,
            open=os.open,
            fsync=fsync,
            close=os.close,
        ),
    )
    store = ArtifactStore(tmp_path)
    contracts = [Artifact.json("answer.json", required=True)]
    paths = store.prepare(contracts, "turn")
    paths["answer"].write_text('{"answer":42}')
    assert store.capture(contracts, "turn").answer.read_json() == {"answer": 42}
    _atomic_bytes(tmp_path / "receipt.json", b'{"status":"completed"}')
    assert (tmp_path / "receipt.json").read_bytes() == b'{"status":"completed"}'
    assert flushed and all(flushed)


def test_windows_publication_keeps_file_flush_without_directory_open(
    tmp_path, monkeypatch
):
    import botpipe.storage as storage

    monkeypatch.setattr(storage, "os", SimpleNamespace(name="nt"))
    flushed_files = []
    original = os.fsync

    def fsync(descriptor):
        assert stat.S_ISREG(os.fstat(descriptor).st_mode)
        flushed_files.append(descriptor)
        original(descriptor)

    monkeypatch.setattr(os, "fsync", fsync)
    store = ArtifactStore(tmp_path)
    contracts = [Artifact.text("answer.txt", required=True)]
    paths = store.prepare(contracts, "turn")
    paths["answer"].write_text("answer")
    assert store.capture(contracts, "turn").answer.read_text() == "answer"
    _atomic_bytes(tmp_path / "receipt.json", b'{"status":"completed"}')
    assert (tmp_path / "receipt.json").read_bytes() == b'{"status":"completed"}'
    assert flushed_files


def test_directory_flush_error_propagates_and_closes_descriptor(tmp_path, monkeypatch):
    import botpipe.storage as storage

    closed = []

    def fail(_descriptor):
        raise OSError(errno.EIO, "directory flush failed")

    monkeypatch.setattr(
        storage,
        "os",
        SimpleNamespace(
            name="posix",
            O_RDONLY=0,
            open=lambda path, flags: 71,
            fsync=fail,
            close=closed.append,
        ),
    )
    with pytest.raises(OSError, match="directory flush failed"):
        sync_directory(tmp_path)
    assert closed == [71]
    with pytest.raises(OSError, match="directory flush failed"):
        _atomic_bytes(tmp_path / "receipt.json", b"{}")
