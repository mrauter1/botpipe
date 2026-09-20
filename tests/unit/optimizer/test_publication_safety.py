from pathlib import Path
from types import SimpleNamespace

import pytest

from botpipe.stdlib.lifecycle import write_workflow_json


def test_json_publication_does_not_follow_an_escaping_parent_link(tmp_path: Path) -> None:
    root = tmp_path / "workflow"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        (root / "linked").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    sentinel = outside / "receipt.json"
    sentinel.write_text("previous")
    with pytest.raises(ValueError, match="ctx.workflow_folder"):
        write_workflow_json(SimpleNamespace(workflow_folder=root), "linked/receipt.json", {"published": True})
    assert sentinel.read_text() == "previous"


def test_invalid_json_preserves_a_previous_receipt(tmp_path: Path) -> None:
    target = tmp_path / "receipt.json"
    target.write_text('{"previous": true}')
    with pytest.raises(ValueError):
        write_workflow_json(SimpleNamespace(workflow_folder=tmp_path), "receipt.json", {"metric": float("nan")})
    assert target.read_text() == '{"previous": true}'


def test_failed_atomic_replace_preserves_a_previous_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import botpipe.stdlib.lifecycle as lifecycle
    target = tmp_path / "receipt.json"
    target.write_text('{"previous": true}')
    def fail_replace(source, destination):
        raise OSError("simulated interrupted publication")
    monkeypatch.setattr(lifecycle.os, "replace", fail_replace)
    with pytest.raises(OSError, match="interrupted"):
        write_workflow_json(SimpleNamespace(workflow_folder=tmp_path), "receipt.json", {"published": True})
    assert target.read_text() == '{"previous": true}'
    assert list(tmp_path.iterdir()) == [target]
