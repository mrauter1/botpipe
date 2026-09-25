import os
import py_compile
import shutil
import sys
from pathlib import Path

import pytest

from botpipe import Botpipe
from botpipe.discovery import resolve_workflow
from botpipe.provenance import (
    capture_workflow_provenance,
    capture_workflow_surface_manifest,
)
from botpipe.providers import FakeProvider
from botpipe.surface_identity import derive_workflow_surface_manifest
from botpipe_optimizer.optimization import load_run_observation


def test_source_capture_reuses_supplied_graph_for_overlapping_partials(
    tmp_path, monkeypatch
):
    from botpipe import provenance
    from botpipe._callables import describe_callable

    source = tmp_path / "shared.py"
    code = (
        "from functools import partial\n"
        "def invoke(callback): return callback()\n"
        "def leaf(): return 1\n"
        "p0 = leaf\n"
        + "".join(f"p{i} = partial(invoke, p{i - 1})\n" for i in range(1, 25))
        + "def entry(): return ("
        + ", ".join(f"p{i}" for i in range(1, 25))
        + ")\n"
    )
    source.write_text(code)
    namespace = {"__name__": "shared"}
    exec(compile(code, str(source), "exec"), namespace)  # noqa: S102
    entry = namespace["entry"]
    graph = describe_callable(entry)
    assert len(graph.nodes) == 27

    def unexpected_traversal(value):
        pytest.fail("Source capture rebuilt a callable already in the graph")

    monkeypatch.setattr(provenance, "describe_callable", unexpected_traversal)
    captured = provenance.capture_orchestration_sources(
        entry, boundary=tmp_path, graph=graph
    )
    assert captured is not None
    assert set(captured["files"]) == {"shared.py"}
    assert len(captured["bindings"]) == 3


def test_source_capture_keeps_code_for_cyclic_decorator(tmp_path):
    from botpipe.provenance import capture_orchestration_sources

    source = tmp_path / "cyclic.py"
    code = "def entry(): return 1\nentry.__wrapped__ = entry\n"
    source.write_text(code)
    namespace = {"__name__": "cyclic"}
    exec(compile(code, str(source), "exec"), namespace)  # noqa: S102
    captured = capture_orchestration_sources(namespace["entry"], boundary=tmp_path)
    assert captured is not None
    assert set(captured["files"]) == {"cyclic.py"}
    assert len(captured["bindings"]) == 1
    assert captured["bindings"]["<workflow>"]["name"] == "entry"


def test_unexpected_observation_failure_is_explicitly_unverified(tmp_path, monkeypatch):
    from botpipe import provenance

    class Definition:
        fingerprint = "known-orchestration"

    def unavailable(*args, **kwargs):
        raise RuntimeError("observation backend unavailable")

    monkeypatch.setattr(provenance, "_verify_loaded_source", unavailable)
    captured = provenance.capture_workflow_provenance(Definition(), tmp_path)

    assert captured == {
        "schema": "botpipe.workflow-provenance.v1",
        "verified": False,
        "workflow_identity": None,
        "surface_id": None,
        "orchestration_id": None,
        "error": "RuntimeError: observation backend unavailable",
    }


def _package(root: Path, name: str = "sample") -> Path:
    package = root / name
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    source = package / "workflow.py"
    source.write_text(
        "from botpipe import workflow\n@workflow\ndef sample():\n    return 7\n"
    )
    (package / "prompt.md").write_text("Original prompt")
    return source


def test_source_surface_is_root_independent_and_tracks_package_resources(tmp_path):
    first = tmp_path / "first"
    source = _package(first)
    flow = {
        "name": "sample",
        "module": "sample.workflow",
        "function": "sample",
        "source": {"path": str(source)},
    }
    before = derive_workflow_surface_manifest(first, flow)
    second = tmp_path / "second"
    shutil.copytree(first, second)
    other = {**flow, "source": {"path": str(second / "sample/workflow.py")}}
    copied = derive_workflow_surface_manifest(second, other)
    assert copied["surface_id"] == before["surface_id"]
    (second / "sample/prompt.md").write_text("Changed prompt")
    assert (
        derive_workflow_surface_manifest(second, other)["surface_id"]
        != before["surface_id"]
    )


def test_completed_resume_returns_record_without_reobserving_source_drift(tmp_path):
    source = _package(tmp_path)
    flow = resolve_workflow(f"{source}:sample", tmp_path)
    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        result = client.run(flow)
        assert result.ok
        original = client.inspect(result.run_id)["run"]
        assert original["provenance_state"] == "known"
        assert original["surface_id"]
        (source.parent / "prompt.md").write_text("Updated external resource")
        assert client.resume(result.run_id, workflow=flow).ok
        current = client.inspect(result.run_id)["run"]
        assert current == original


def test_ordinary_provenance_is_compact_and_full_manifest_is_explicit(tmp_path):
    source = _package(tmp_path, "compact_sample")
    flow = resolve_workflow(f"{source}:sample", tmp_path)

    compact = capture_workflow_provenance(flow, tmp_path)
    manifest = capture_workflow_surface_manifest(flow, tmp_path)

    assert compact == {
        "schema": "botpipe.workflow-provenance.v1",
        "verified": True,
        "workflow_identity": compact["workflow_identity"],
        "surface_id": manifest["surface_id"],
        "orchestration_id": flow.fingerprint,
    }
    assert "files" in manifest
    assert "surface_manifest" not in compact


def test_workflow_surface_rejects_linked_package_content(tmp_path):
    source = _package(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("not an owned source file")
    try:
        (source.parent / "linked.md").symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation unavailable")
    flow = {
        "name": "sample",
        "module": "sample.workflow",
        "function": "sample",
        "source": {"path": str(source)},
    }
    with pytest.raises(ValueError, match="symlink"):
        derive_workflow_surface_manifest(tmp_path, flow)


@pytest.mark.parametrize("edit_global", [False, True])
def test_loaded_definition_cannot_claim_new_source_bytes(tmp_path, edit_global):
    source = tmp_path / "stale.py"
    code = "from botpipe import workflow\nVALUE = 'OLD'\n@workflow\ndef stale():\n" + (
        "    return VALUE\n" if edit_global else "    return 'OLD'\n"
    )
    source.write_text(code)
    flow = resolve_workflow(f"{source}:stale", tmp_path)
    assert capture_workflow_provenance(flow, tmp_path)["verified"]
    source.write_text(code.replace("OLD", "NEW"))
    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        result = client.run(flow)
        assert result.value == "OLD"
        record = client.inspect(result.run_id)
        assert record["run"]["provenance_state"] == "unknown"
        revisions = [
            event["data"]["provenance"]
            for event in record["events"]
            if event["event"] == "execution_revision"
        ]
        assert revisions
        assert all(not revision["verified"] for revision in revisions)
        assert load_run_observation(record).provenance_state != "known"


@pytest.mark.parametrize("edit_global", [False, True])
def test_stale_valid_pyc_cannot_claim_current_source_bytes(tmp_path, edit_global):
    source = tmp_path / "cached.py"
    code = "from botpipe import workflow\nVALUE = 'OLD'\n@workflow\ndef cached():\n" + (
        "    return VALUE\n" if edit_global else "    return 'OLD'\n"
    )
    source.write_text(code)
    saved = source.stat()
    py_compile.compile(str(source), doraise=True)
    source.write_text(code.replace("OLD", "NEW"))
    os.utime(source, ns=(saved.st_atime_ns, saved.st_mtime_ns))
    flow = resolve_workflow(f"{source}:cached", tmp_path)
    assert flow.fn() == "OLD"
    evidence = capture_workflow_provenance(flow, tmp_path)
    assert not evidence["verified"]
    assert "loaded workflow code" in evidence["error"]


@pytest.mark.parametrize("filename", ["flow.py", "workflow.py", "task.py"])
def test_namespace_surface_boundary_is_independent_of_selection_alias(
    tmp_path, filename
):
    package = tmp_path / ("alias_namespace_" + Path(filename).stem)
    package.mkdir()
    source = package / filename
    source.write_text(
        "from botpipe import workflow\n@workflow\ndef demo():\n    return 7\n"
    )
    (package / "prompt.md").write_text("resource")
    reference = f"{package.name}.{source.stem}"
    try:
        by_module = resolve_workflow(f"{reference}:demo", tmp_path)
        by_file = resolve_workflow(f"{source}:demo", tmp_path)
        first = derive_workflow_surface_manifest(tmp_path, by_module)
        second = derive_workflow_surface_manifest(tmp_path, by_file)
        assert first["surface_id"] == second["surface_id"]
        assert len(first["relative_paths"]) == (1 if filename == "task.py" else 2)
    finally:
        sys.modules.pop(reference, None)
        sys.modules.pop(package.name, None)
