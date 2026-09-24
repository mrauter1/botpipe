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


@pytest.mark.parametrize(
    "metadata_path",
    [
        "ledger.jsonl",
        "input.json",
        "request.md",
        "operations/provider/attempts/1/request.json",
        "payloads/large-value.json",
        ".artifacts/blobs/result.txt",
    ],
)
def test_allowed_task_root_does_not_authorize_sibling_run_metadata(
    tmp_path, metadata_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    task = state / "tasks" / "task"
    current = task / "runs" / "current"
    sibling_metadata = task / "runs" / "sibling" / metadata_path

    store = ArtifactStore(
        current,
        workspace=workspace,
        allowed_roots=(task,),
        state_dir=state,
    )
    with pytest.raises(ArtifactError, match="protected state"):
        store.destinations((Artifact.json(sibling_metadata),))


@pytest.mark.parametrize("run_name", ["current", "sibling"])
def test_task_artifact_cannot_replace_run_payload_sidecars(tmp_path, run_name):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    state = tmp_path / "state"
    task = state / "tasks" / "task"
    current = task / "runs" / "current"
    payload = task / "runs" / run_name / "payloads" / "value.json"
    store = ArtifactStore(
        current,
        workspace=workspace,
        allowed_roots=(task,),
        state_dir=state,
    )

    with pytest.raises(ArtifactError, match="protected state"):
        store.destinations((Artifact.json(payload),))
