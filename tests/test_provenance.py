import os
import py_compile
import shutil
import sys
from pathlib import Path

import pytest

from botpipe import Botpipe
from botpipe.discovery import resolve_workflow
from botpipe.provenance import capture_workflow_provenance
from botpipe.providers import FakeProvider
from botpipe.surface_identity import derive_workflow_surface_manifest
from botpipe_optimizer.optimization import load_run_observation


def _package(root: Path) -> Path:
    package = root / "sample"
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


def test_resume_retains_recorded_start_provenance_and_exposes_source_drift(tmp_path):
    source = _package(tmp_path)
    flow = resolve_workflow(f"{source}:sample", tmp_path)
    with Botpipe(tmp_path, provider=FakeProvider([])) as client:
        result = client.run(flow)
        assert result.ok
        original = client.inspect(result.run_id)["run"]
        assert original["provenance_start"]["verified"]
        assert (
            original["provenance_start"]["surface_id"]
            == original["provenance_end"]["surface_id"]
        )
        (source.parent / "prompt.md").write_text("Updated external resource")
        assert client.resume(result.run_id, workflow=flow).ok
        current = client.inspect(result.run_id)["run"]
        assert current["provenance_start"] == original["provenance_start"]
        assert (
            current["provenance_end"]["surface_id"]
            != current["provenance_start"]["surface_id"]
        )


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
        assert not record["run"]["provenance_start"]["verified"]
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
