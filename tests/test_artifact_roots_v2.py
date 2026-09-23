import pytest

from botpipe.artifacts import Artifact, ArtifactError, ArtifactStore


def test_task_artifacts_outside_workspace_are_allowed_explicitly(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    task = tmp_path / "state" / "tasks" / "task"
    store = ArtifactStore(
        task / "runs" / "run", workspace=workspace, allowed_roots=(task,)
    )
    declaration = Artifact.md(str(task / "plan" / "review.md"), required=True)
    assert store.destinations((declaration,))["review"] == task / "plan" / "review.md"
    with pytest.raises(ArtifactError, match="escapes"):
        store.destinations((Artifact.md(str(tmp_path / "unrelated.md")),))


def test_allowed_task_root_does_not_authorize_runtime_metadata(tmp_path):
    task = tmp_path / "task"
    store = ArtifactStore(task / "runs" / "run", allowed_roots=(task,))
    with pytest.raises(ArtifactError, match="metadata"):
        store.destinations((Artifact.json(str(task / "receipts" / "turn.json")),))
