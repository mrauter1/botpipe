from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from botpipe.core.errors import WorkflowExecutionError
from botpipe.core.schema_registry import RUN_METADATA_SCHEMA
from botpipe.runtime import load_run_metadata
from botpipe.runtime import workspace


def _run_workspace(path: Path) -> SimpleNamespace:
    return SimpleNamespace(run_meta_file=path)


def test_merge_run_metadata_preserves_unspecified_fields_and_replaces_explicit_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "run.json"
    original = {
        "schema": RUN_METADATA_SCHEMA,
        "status": "awaiting_input",
        "terminal": "AWAIT_INPUT",
        "pending_input": {"question": "Continue?"},
        "lease": {"host": "runner.example", "pid": 42},
        "error": "existing diagnostic",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:01:00+00:00",
        "parent": {"run_id": "parent-1"},
        "extension": {"accent": "ação"},
        "typed_output": {"old": True, "nested": {"keep": False}},
    }
    path.write_text(json.dumps(original), encoding="utf-8")

    workspace._merge_run_metadata(
        _run_workspace(path),
        {
            "typed_output": {"new": "ação"},
            "finalization": None,
        },
    )

    assert json.loads(path.read_text(encoding="utf-8")) == {
        **original,
        "typed_output": {"new": "ação"},
        "finalization": None,
    }


def test_empty_metadata_merge_does_not_read_or_create_file(tmp_path: Path) -> None:
    path = tmp_path / "missing" / "run.json"

    workspace._merge_run_metadata(_run_workspace(path), {})

    assert not path.exists()
    assert not path.parent.exists()


@pytest.mark.parametrize(
    ("contents", "error_type", "message"),
    [
        (None, FileNotFoundError, None),
        (b"{broken", json.JSONDecodeError, None),
        (b"[]", WorkflowExecutionError, "must contain a JSON object"),
        (
            b'{"schema":"future/v9"}',
            ValueError,
            f"uses unsupported schema 'future/v9'; expected {RUN_METADATA_SCHEMA!r}",
        ),
    ],
    ids=("missing", "malformed-json", "non-object-json", "unsupported-schema"),
)
def test_merge_run_metadata_rejects_missing_or_invalid_source_without_replacement(
    tmp_path: Path,
    contents: bytes | None,
    error_type: type[Exception],
    message: str | None,
) -> None:
    path = tmp_path / "run.json"
    if contents is not None:
        path.write_bytes(contents)

    with pytest.raises(error_type, match=message):
        workspace._merge_run_metadata(
            _run_workspace(path),
            {"typed_output": {"available": True}},
        )

    if contents is None:
        assert not path.exists()
    else:
        assert path.read_bytes() == contents
    assert tuple(tmp_path.iterdir()) == (() if contents is None else (path,))


def test_merge_run_metadata_propagates_unreadable_source_without_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "run.json"
    original = json.dumps({"schema": RUN_METADATA_SCHEMA, "status": "created"}).encode()
    path.write_bytes(original)
    original_read_text = Path.read_text

    def fail_run_metadata_read(candidate: Path, *args: object, **kwargs: object) -> str:
        if candidate == path:
            raise OSError("injected read failure")
        return original_read_text(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail_run_metadata_read)

    with pytest.raises(OSError, match="injected read failure"):
        workspace._merge_run_metadata(_run_workspace(path), {"typed_output": {}})

    assert path.read_bytes() == original
    assert tuple(tmp_path.iterdir()) == (path,)


def test_merge_run_metadata_migrates_legacy_payload_and_preserves_unknown_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "run.json"
    path.write_text('{"custom":{"value":4}}', encoding="utf-8")

    workspace._merge_run_metadata(
        _run_workspace(path),
        {"typed_output": {"available": True}},
    )

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema": RUN_METADATA_SCHEMA,
        "custom": {"value": 4},
        "typed_output": {"available": True},
    }


def test_merge_run_metadata_serialization_failure_preserves_original_and_cleans_temp(
    tmp_path: Path,
) -> None:
    path = tmp_path / "run.json"
    original = json.dumps({"schema": RUN_METADATA_SCHEMA, "status": "created"}).encode()
    path.write_bytes(original)

    with pytest.raises(TypeError):
        workspace._merge_run_metadata(_run_workspace(path), {"typed_output": object()})

    assert path.read_bytes() == original
    assert tuple(tmp_path.iterdir()) == (path,)


def test_merge_run_metadata_replace_failure_preserves_original_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "run.json"
    original = json.dumps({"schema": RUN_METADATA_SCHEMA, "status": "created"}).encode()
    path.write_bytes(original)

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        assert Path(destination) == path
        assert json.loads(Path(source).read_text(encoding="utf-8"))["typed_output"] == {
            "available": True
        }
        raise OSError("injected replace failure")

    monkeypatch.setattr(workspace.os, "replace", fail_replace)

    with pytest.raises(OSError, match="injected replace failure"):
        workspace._merge_run_metadata(
            _run_workspace(path),
            {"typed_output": {"available": True}},
        )

    assert path.read_bytes() == original
    assert tuple(tmp_path.iterdir()) == (path,)


def test_public_run_metadata_reader_accepts_record_string_and_path(tmp_path: Path) -> None:
    run_dir = tmp_path / ".botpipe" / "tasks" / "task-1" / "wf_demo" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    payload = {
        "schema": RUN_METADATA_SCHEMA,
        "task_id": "task-1",
        "workflow_name": "demo",
        "custom": "ação",
    }
    (run_dir / "run.json").write_text(json.dumps(payload), encoding="utf-8")
    record = workspace.list_run_records(tmp_path)[0]

    assert load_run_metadata(record) == payload
    assert load_run_metadata(str(run_dir)) == payload
    assert load_run_metadata(run_dir) == payload


def test_public_run_metadata_reader_migrates_legacy_payload_without_rewriting(
    tmp_path: Path,
) -> None:
    path = tmp_path / "run.json"
    original = b'{"custom":4}'
    path.write_bytes(original)

    assert load_run_metadata(tmp_path) == {"custom": 4, "schema": RUN_METADATA_SCHEMA}
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    ("contents", "error_type", "message"),
    [
        (None, FileNotFoundError, None),
        (b"{broken", json.JSONDecodeError, None),
        (b"[]", WorkflowExecutionError, "must contain a JSON object"),
        (
            b'{"schema":"future/v9"}',
            ValueError,
            f"run.json uses unsupported schema 'future/v9'; expected {RUN_METADATA_SCHEMA!r}",
        ),
    ],
    ids=("missing", "malformed-json", "non-object-json", "unsupported-schema"),
)
def test_public_run_metadata_reader_preserves_errors_and_source(
    tmp_path: Path,
    contents: bytes | None,
    error_type: type[Exception],
    message: str | None,
) -> None:
    path = tmp_path / "run.json"
    if contents is not None:
        path.write_bytes(contents)

    with pytest.raises(error_type, match=message):
        load_run_metadata(tmp_path)

    if contents is None:
        assert not path.exists()
    else:
        assert path.read_bytes() == contents
