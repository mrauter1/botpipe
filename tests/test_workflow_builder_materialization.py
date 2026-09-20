import json
from pathlib import Path

import pytest

from labs.workflows.workflow_idea_to_workflow_package.materialization import (
    _materialize_generated_workflow_manifest_activity,
    _revalidate_generated_workflow_materialization,
    _validate_generated_workflow_candidate_activity,
    freeze_generated_workflow_candidate,
    prepare_generated_workflow_candidate,
)


class _ManifestHandle:
    def __init__(self, path: Path):
        self.path = path

    def read_bytes(self):
        return self.path.read_bytes()

    def to_record(self):
        return {
            "name": "workflow_package_manifest",
            "path": str(self.path),
            "digest": "fixture",
            "kind": "json",
            "source_path": str(self.path),
        }


def _file(path: str, content: str, role: str = "source"):
    return {
        "path": path,
        "role": role,
        "purpose": "fixture",
        "required": True,
        "implements": "fixture design",
        "content": content,
    }


def _materialize(tmp_path, repo, manifest):
    package_name = manifest["package_name"]
    shape = manifest["authoring_shape"]
    workspace = prepare_generated_workflow_candidate.__wrapped__(
        str(repo), str(tmp_path / "candidate"), package_name, shape
    )
    frozen = freeze_generated_workflow_candidate.__wrapped__(
        workspace, str(tmp_path / "frozen")
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    handle = _ManifestHandle(path)
    generated = _materialize_generated_workflow_manifest_activity.__wrapped__(
        workspace, handle, package_name, shape
    )
    _revalidate_generated_workflow_materialization(
        generated, candidate_workspace=workspace, manifest_handle=handle
    )
    return workspace, frozen, generated


def test_invalid_generated_python_is_a_recorded_validation_result(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# fixture\n")
    workspace, frozen, generated = _materialize(
        tmp_path,
        repo,
        {
            "package_name": "broken",
            "authoring_shape": "flow_specs",
            "workflow_reference": ".botpipe/workflows/broken/flow.py:Broken",
            "files": [_file(".botpipe/workflows/broken/flow.py", "def Broken(:\n")],
        },
    )

    outcome = _validate_generated_workflow_candidate_activity.__wrapped__(
        workspace,
        frozen,
        generated["workflow_reference"],
        str(tmp_path / "validation"),
        None,
    )

    assert outcome["validation"]["success"] is False
    assert outcome["validation"]["checks"][0]["kind"] == "compile_probe"
    assert "invalid syntax" in outcome["validation"]["errors"][0]


def test_complete_manifest_replaces_only_the_managed_existing_boundary(tmp_path):
    repo = tmp_path / "repo"
    package = repo / "labs/workflows/existing"
    package.mkdir(parents=True)
    (repo / "README.md").write_text("keep me\n")
    (repo / "unrelated.txt").write_text("also keep me\n")
    (package / "flow.py").write_text("OLD = True\n")
    (package / "specs.py").write_text("OLD = True\n")
    (package / "workflow.toml").write_text('name = "old"\n')
    (package / "undeclared.py").write_text("HIDDEN = True\n")
    unchanged = 'VALUE = "preserved"\n'
    (package / "helper.py").write_text(unchanged)

    workspace, _, generated = _materialize(
        tmp_path,
        repo,
        {
            "package_name": "existing",
            "authoring_shape": "package",
            "workflow_reference": "labs/workflows/existing/flow.py:Existing",
            "files": [
                _file("labs/workflows/existing/helper.py", unchanged),
                _file(
                    "labs/workflows/existing/flow.py",
                    "from botpipe import workflow\n"
                    '@workflow(name="existing")\n'
                    "def Existing(): return 1\n",
                ),
                _file("labs/workflows/existing/specs.py", "VALUE = 1\n"),
                _file(
                    "labs/workflows/existing/workflow.toml",
                    'name = "existing"\nfunction = "Existing"\n',
                ),
            ],
        },
    )

    root = Path(generated["root"])
    assert not (root / "labs/workflows/existing/undeclared.py").exists()
    assert (root / "labs/workflows/existing/helper.py").read_text() == unchanged
    assert (repo / "unrelated.txt").read_text() == "also keep me\n"

    from botpipe_optimizer.candidates import candidate_manifest

    delta = candidate_manifest(workspace)
    assert "labs/workflows/existing/helper.py" in delta.unchanged_paths
    assert "labs/workflows/existing/helper.py" not in delta.changed_paths
    assert "labs/workflows/existing/undeclared.py" in delta.removed_paths
    (package / "flow.py").write_text("EDITED = True\n")
    with pytest.raises(ValueError, match="authoritative source changed"):
        _revalidate_generated_workflow_materialization(
            generated,
            candidate_workspace=workspace,
            manifest_handle=_ManifestHandle(tmp_path / "manifest.json"),
        )


def test_package_catalog_metadata_is_part_of_candidate_validation(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# fixture\n")
    workspace, frozen, generated = _materialize(
        tmp_path,
        repo,
        {
            "package_name": "catalog",
            "authoring_shape": "package",
            "workflow_reference": "labs/workflows/catalog/flow.py:Catalog",
            "files": [
                _file(
                    "labs/workflows/catalog/flow.py",
                    "from botpipe import workflow\n"
                    '@workflow(name="catalog")\n'
                    "def Catalog(): return 1\n",
                ),
                _file("labs/workflows/catalog/specs.py", "VALUE = 1\n"),
                _file("labs/workflows/catalog/workflow.toml", "name = [ broken\n"),
            ],
        },
    )

    outcome = _validate_generated_workflow_candidate_activity.__wrapped__(
        workspace,
        frozen,
        generated["workflow_reference"],
        str(tmp_path / "validation"),
        None,
    )

    assert outcome["validation"]["success"] is False
    assert any(
        error.startswith("catalog:") for error in outcome["validation"]["errors"]
    )


def test_existing_workspace_workflow_package_is_rejected_as_runtime_state(tmp_path):
    repo = tmp_path / "repo"
    package = repo / ".botpipe/workflows/existing"
    package.mkdir(parents=True)
    (repo / "README.md").write_text("# fixture\n")
    (package / "flow.py").write_text("OLD = True\n")
    (package / "stale.py").write_text("STALE = True\n")

    with pytest.raises(ValueError, match="target already exists"):
        prepare_generated_workflow_candidate.__wrapped__(
            str(repo), str(tmp_path / "candidate"), "existing", "flow_specs"
        )
