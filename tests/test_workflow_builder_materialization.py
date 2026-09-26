import json
import sys
from pathlib import Path

import pytest

from botpipe import Botpipe
from botpipe.policy import SandboxMode
from botpipe.providers import FakeProvider
from labs.workflows.workflow_idea_to_workflow_package import (
    Params,
    WorkflowIdeaToWorkflowPackage,
)
from labs.workflows.workflow_idea_to_workflow_package.materialization import (
    WorkflowManifestValidationError,
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


def _file(path: str, content: str, *, role: str | None = None):
    item = {"path": path, "content": content}
    if role is not None:
        item["role"] = role
    return item


def _manifest(package_name: str, flow: str, *, extra=(), metadata: str | None = None):
    root = f".botpipe/workflows/{package_name}"
    function = "GeneratedWorkflow"
    return {
        "package_name": package_name,
        "workflow_reference": f"{root}/flow.py:{function}",
        "files": [
            _file(f"{root}/flow.py", flow, role="workflow"),
            _file(
                f"{root}/workflow.toml",
                metadata
                if metadata is not None
                else f'name = "{package_name}"\nfunction = "{function}"\n',
                role="discovery",
            ),
            *extra,
        ],
    }


def _materialize(tmp_path, repo, manifest):
    package_name = manifest["package_name"]
    workspace = prepare_generated_workflow_candidate.__wrapped__(
        str(repo), str(tmp_path / "candidate"), package_name
    )
    frozen = freeze_generated_workflow_candidate.__wrapped__(
        workspace, str(tmp_path / "frozen")
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    handle = _ManifestHandle(path)
    generated = _materialize_generated_workflow_manifest_activity.__wrapped__(
        workspace, handle, package_name
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
        _manifest("broken", "def GeneratedWorkflow(:\n"),
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


def test_complete_manifest_materializes_only_package_and_optional_test(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("keep me\n")
    (repo / "unrelated.txt").write_text("also keep me\n")
    flow = (
        "from botpipe import workflow\n"
        '@workflow(name="generated")\n'
        "def GeneratedWorkflow(): return 1\n"
    )
    test_path = "tests/runtime/test_generated.py"
    workspace, _, generated = _materialize(
        tmp_path,
        repo,
        _manifest(
            "generated",
            flow,
            extra=[_file(test_path, "def test_generated(): assert True\n")],
        ),
    )

    root = Path(generated["root"])
    assert (root / ".botpipe/workflows/generated/flow.py").read_text() == flow
    assert (root / test_path).is_file()
    assert (repo / "unrelated.txt").read_text() == "also keep me\n"
    assert {item["path"] for item in generated["files"]} == {
        ".botpipe/workflows/generated/flow.py",
        ".botpipe/workflows/generated/workflow.toml",
        test_path,
    }

    from botpipe_optimizer.candidates import candidate_manifest

    delta = candidate_manifest(workspace)
    assert set(delta.changed_paths) == {
        ".botpipe/workflows/generated/flow.py",
        ".botpipe/workflows/generated/workflow.toml",
        test_path,
    }
    (repo / "README.md").write_text("edited after preparation\n")
    with pytest.raises(ValueError, match="authoritative source changed"):
        _revalidate_generated_workflow_materialization(
            generated,
            candidate_workspace=workspace,
            manifest_handle=_ManifestHandle(tmp_path / "manifest.json"),
        )


def test_workspace_catalog_metadata_is_part_of_candidate_validation(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# fixture\n")
    workspace, frozen, generated = _materialize(
        tmp_path,
        repo,
        _manifest(
            "catalog",
            "from botpipe import workflow\n"
            '@workflow(name="catalog")\n'
            "def GeneratedWorkflow(): return 1\n",
            metadata="name = [ broken\n",
        ),
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


def test_empty_candidate_reset_requires_and_preserves_ownership(tmp_path):
    repo = tmp_path / "empty"
    repo.mkdir()
    destination = tmp_path / "candidate"
    first = prepare_generated_workflow_candidate.__wrapped__(
        str(repo), str(destination), "fresh"
    )
    (first.candidate_root / "stale.txt").write_text("discard me")

    second = prepare_generated_workflow_candidate.__wrapped__(
        str(repo), str(destination), "fresh"
    )

    assert second.allowed_paths == ()
    assert not (second.candidate_root / "stale.txt").exists()
    unmanaged = tmp_path / "unmanaged"
    unmanaged.mkdir()
    (unmanaged / "keep.txt").write_text("do not replace")
    with pytest.raises(ValueError, match="not managed"):
        prepare_generated_workflow_candidate.__wrapped__(
            str(repo), str(unmanaged), "other"
        )


def test_only_optimizer_baselines_can_opt_into_empty_surface(tmp_path):
    from botpipe.surface_identity import derive_surface_manifest as derive_runtime
    from botpipe_optimizer.surface_identity import derive_surface_manifest

    root = tmp_path / "surface"
    root.mkdir()
    boundary = {"editable_paths": [], "editable_roots": []}

    with pytest.raises(ValueError, match="at least one regular file"):
        derive_runtime(
            root,
            expected_root=root,
            boundary=boundary,
            surface_kind="baseline",
        )
    baseline = derive_surface_manifest(
        root,
        expected_root=root,
        boundary=boundary,
        surface_kind="baseline",
    )
    assert baseline["file_count"] == 0
    for kind in ("candidate", "workflow"):
        with pytest.raises(ValueError, match="at least one regular file"):
            derive_surface_manifest(
                root,
                expected_root=root,
                boundary=boundary,
                surface_kind=kind,
            )


def test_enforced_generated_test_missing_is_recorded_validation_failure(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    workspace, frozen, generated = _materialize(
        tmp_path,
        repo,
        _manifest(
            "untested",
            "from botpipe import workflow\n"
            '@workflow(name="untested")\n'
            "def GeneratedWorkflow(): return 1\n",
        ),
    )

    outcome = _validate_generated_workflow_candidate_activity.__wrapped__(
        workspace,
        frozen,
        generated["workflow_reference"],
        str(tmp_path / "validation"),
        None,
        enforce_generated_test=True,
    )

    assert outcome["validation"]["success"] is False
    assert outcome["validation"]["errors"] == [
        "generated behavioral test is required: tests/runtime/test_untested.py"
    ]
    assert [check["phase"] for check in outcome["validation"]["checks"]] == ["compile"]


def test_target_test_argv_preserves_argument_boundaries_without_a_shell(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    workspace, frozen, generated = _materialize(
        tmp_path,
        repo,
        _manifest(
            "argv_check",
            "from botpipe import workflow\n"
            '@workflow(name="argv_check")\n'
            "def GeneratedWorkflow(): return 1\n",
        ),
    )
    literal = "$HOME; exit 17"

    outcome = _validate_generated_workflow_candidate_activity.__wrapped__(
        workspace,
        frozen,
        generated["workflow_reference"],
        str(tmp_path / "validation"),
        None,
        target_test_argv=(
            sys.executable,
            "-c",
            "import sys; assert sys.argv[1] == '$HOME; exit 17'",
            literal,
        ),
    )

    assert outcome["validation"]["success"] is True
    assert [check["phase"] for check in outcome["validation"]["checks"]] == [
        "compile",
        "test",
    ]


def test_existing_workspace_workflow_package_is_rejected(tmp_path):
    repo = tmp_path / "repo"
    package = repo / ".botpipe/workflows/existing"
    package.mkdir(parents=True)
    (repo / "README.md").write_text("# fixture\n")
    (package / "flow.py").write_text("OLD = True\n")

    with pytest.raises(ValueError, match="target already exists"):
        prepare_generated_workflow_candidate.__wrapped__(
            str(repo), str(tmp_path / "candidate"), "existing"
        )


def test_package_name_cannot_escape_workspace_workflow_root(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# fixture\n")

    with pytest.raises(ValueError, match="Python-style identifier"):
        prepare_generated_workflow_candidate.__wrapped__(
            str(repo), str(tmp_path / "candidate"), "../outside"
        )


def test_manifest_requires_current_workspace_package_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# fixture\n")
    workspace = prepare_generated_workflow_candidate.__wrapped__(
        str(repo), str(tmp_path / "candidate"), "incomplete"
    )
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "package_name": "incomplete",
                "workflow_reference": (
                    ".botpipe/workflows/incomplete/flow.py:GeneratedWorkflow"
                ),
                "files": [
                    _file(
                        ".botpipe/workflows/incomplete/flow.py",
                        "def GeneratedWorkflow(): return 1\n",
                    )
                ],
            }
        )
    )

    with pytest.raises(
        WorkflowManifestValidationError,
        match="workflow package requires:.*workflow.toml",
    ):
        _materialize_generated_workflow_manifest_activity.__wrapped__(
            workspace, _ManifestHandle(path), "incomplete"
        )


@pytest.mark.parametrize("parent_first", [True, False])
def test_conflicting_manifest_paths_are_rejected_before_writes(tmp_path, parent_first):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("original anchor\n")
    workspace = prepare_generated_workflow_candidate.__wrapped__(
        str(repo), str(tmp_path / "candidate"), "conflict"
    )
    root = ".botpipe/workflows/conflict"
    entries = [
        _file(f"{root}/prompts", "not a directory"),
        _file(f"{root}/prompts/run.md", "Run the task."),
    ]
    if not parent_first:
        entries.reverse()
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            _manifest("conflict", "def GeneratedWorkflow(): pass\n", extra=entries)
        )
    )
    with pytest.raises(WorkflowManifestValidationError, match="file paths conflict"):
        _materialize_generated_workflow_manifest_activity.__wrapped__(
            workspace, _ManifestHandle(path), "conflict"
        )
    assert list(workspace.candidate_root.iterdir()) == [
        workspace.candidate_root / "README.md"
    ]
    assert (workspace.candidate_root / "README.md").read_text() == "original anchor\n"


@pytest.mark.parametrize(
    "escaped_path",
    ["../outside.py", "labs/workflows/other/flow.py", ".botpipe/config.toml"],
)
def test_manifest_rejects_paths_outside_generated_boundary(tmp_path, escaped_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# fixture\n")
    workspace = prepare_generated_workflow_candidate.__wrapped__(
        str(repo), str(tmp_path / "candidate"), "safe"
    )
    manifest = _manifest(
        "safe",
        "def GeneratedWorkflow(): return 1\n",
        extra=[_file(escaped_path, "unsafe\n")],
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))

    with pytest.raises(ValueError, match="repo-relative|outside the package boundary"):
        _materialize_generated_workflow_manifest_activity.__wrapped__(
            workspace, _ManifestHandle(path), "safe"
        )


def test_builder_producers_use_run_owned_workspace_and_artifact_destinations(tmp_path):
    from tests.test_labs import _successful_provider

    source = tmp_path / "source"
    state = tmp_path / "state"
    source.mkdir()
    readme = source / "README.md"
    readme.write_text("# authoritative source\n")
    producer_requests = []

    def answer(request):
        if request.preset == "run":
            producer_requests.append(request)
        return _successful_provider(request)

    result = Botpipe(
        source,
        state_dir=state,
        provider=FakeProvider([answer] * 8),
    ).run(
        WorkflowIdeaToWorkflowPackage,
        Params(package_name="isolated_builder"),
        request="Build an echo workflow without editing the source workspace.",
    )

    assert result.ok, result.error
    assert len(producer_requests) == 4
    assert len({request.workspace for request in producer_requests}) == 4
    for request in producer_requests:
        assert request.workspace != source
        assert request.workspace.is_relative_to(state)
        assert request.policy.sandbox_mode is SandboxMode.WORKSPACE_WRITE
        assert request.artifacts
        assert all(
            destination.is_relative_to(request.workspace)
            for destination in request.artifacts.values()
        )
        payload = json.JSONDecoder().raw_decode(
            request.prompt.split("\n\nInput:\n", 1)[1]
        )[0]
        assert Path(payload["source_workspace"]) == source
    assert readme.read_text() == "# authoritative source\n"
    assert not (source / ".botpipe/workflows/isolated_builder").exists()


def test_evaluation_acceptance_repairs_non_accept_package_decision(tmp_path):
    from tests.test_labs import _successful_provider

    (tmp_path / "README.md").write_text("# source\n")
    evaluation_turns = 0

    def answer(request):
        nonlocal evaluation_turns
        payload = json.JSONDecoder().raw_decode(
            request.prompt.split("\n\nInput:\n", 1)[1]
        )[0]
        result = _successful_provider(request)
        if request.artifacts and payload["phase"] == "evaluate_package":
            evaluation_turns += 1
            if evaluation_turns == 1:
                # An accepted payload cannot smuggle a control decision past
                # Python control flow. Local schema repair must correct it.
                result["package_decision"] = "rework"
        return result

    provider = FakeProvider([answer] * 10)
    result = Botpipe(tmp_path, provider=provider).run(
        WorkflowIdeaToWorkflowPackage,
        Params(package_name="decision_repair"),
        request="Build a workflow and accept only an honestly accepted evaluation.",
    )

    assert result.ok, result.error
    assert evaluation_turns == 2
    assert result.value.phases[-1].details["package_decision"] == "accept"


def test_evaluation_source_replan_redesigns_and_rebuilds_with_exact_evidence(
    tmp_path,
):
    from tests.test_labs import _successful_provider

    (tmp_path / "README.md").write_text("# source\n")
    counts = {"design": 0, "build": 0, "evaluate": 0}
    second_design = {}
    second_build = {}
    candidate_roots = []

    def answer(request):
        payload = json.JSONDecoder().raw_decode(
            request.prompt.split("\n\nInput:\n", 1)[1]
        )[0]
        phase = payload["phase"]
        if request.artifacts and phase == "design_workflow":
            counts["design"] += 1
            if counts["design"] == 2:
                second_design.update(payload=payload, reads=set(request.reads))
        if request.artifacts and phase == "build_package":
            counts["build"] += 1
            if counts["build"] == 2:
                second_build.update(payload=payload)
        if request.artifacts and phase == "evaluate_package":
            counts["evaluate"] += 1
            candidate_roots.append(payload["generated_candidate"]["root"])
        result = _successful_provider(request)
        if (
            request.artifacts
            and phase == "evaluate_package"
            and counts["evaluate"] == 1
        ):
            result.update(
                outcome="needs_replan",
                summary="Generated prompt omits a required evidence handoff.",
                replan_reason="Rebuild source and prompts from the exact finding.",
            )
        return result

    result = Botpipe(tmp_path, provider=FakeProvider([answer] * 16)).run(
        WorkflowIdeaToWorkflowPackage,
        Params(package_name="evaluation_rebuild"),
        request="Build, evaluate, and rebuild a rejected generated prompt.",
    )

    assert result.ok, result.error
    assert counts == {"design": 2, "build": 2, "evaluate": 2}
    assert candidate_roots[0] != candidate_roots[1]
    design_payload = second_design["payload"]
    assert design_payload["replan_feedback"]["details"]["outcome"] == "needs_replan"
    assert (
        design_payload["rejected_candidate_evidence"]["generated_candidate"]["root"]
        == candidate_roots[0]
    )
    assert set(map(Path, design_payload["replan_artifacts"])).issubset(
        second_design["reads"]
    )
    assert (
        second_build["payload"]["rejected_candidate_evidence"]
        == design_payload["rejected_candidate_evidence"]
    )


def test_retired_authoring_shape_is_rejected_instead_of_silently_ignored():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="authoring_shape"):
        Params(package_name="example", authoring_shape="single")
