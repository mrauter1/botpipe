from __future__ import annotations

import sys
from dataclasses import replace

import pytest

from botpipe.discovery import resolve_workflow
from botpipe.surface_identity import derive_workflow_surface_manifest
from botpipe_optimizer.candidates import (
    candidate_surface_manifest,
    evaluate_candidate_workspace,
    freeze_candidate_workspace,
    prepare_candidate_workspace,
    validate_candidate,
)
from botpipe_optimizer.execution_trees import materialize_execution_arm
from botpipe_optimizer.surface_identity import validate_surface_manifest


def source_project(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "workflow.py").write_text(
        "from botpipe import workflow\n@workflow\ndef demo():\n    return 1\n"
    )
    return project


def test_native_workflow_validation_runs_modified_bytes_and_isolated_test(tmp_path):
    project = source_project(tmp_path)
    workspace = prepare_candidate_workspace(
        project, ["workflow.py"], tmp_path / "surface"
    )
    frozen = freeze_candidate_workspace(workspace, tmp_path / "frozen")
    (workspace.candidate_root / "workflow.py").write_text(
        "from botpipe import workflow\n@workflow\ndef demo():\n    return 2\n"
    )
    result = validate_candidate(
        workspace,
        frozen,
        workflow_refs=["workflow.py:demo"],
        staging_parent=tmp_path / "checks",
        target_test_argv=[
            sys.executable,
            "-c",
            "from workflow import demo; assert demo.fn() == 2",
        ],
    )
    assert result.success, result.model_dump()
    assert result.derived_changes == ("workflow.py",)
    assert result.compiled_workflows[0]["workflow_name"] == "demo"
    assert result.environment["interpreter"]
    assert (project / "workflow.py").read_text().endswith("return 1\n")


def test_exact_added_path_preserves_siblings_and_rejects_source_collision(tmp_path):
    project = source_project(tmp_path)
    tests = project / "tests/runtime"
    tests.mkdir(parents=True)
    existing = tests / "test_existing.py"
    existing.write_text("# existing test\n")
    added = "tests/runtime/test_generated.py"
    workspace = replace(
        prepare_candidate_workspace(project, ["workflow.py"], tmp_path / "surface"),
        allowed_added_paths=(added,),
    )
    frozen = freeze_candidate_workspace(workspace, tmp_path / "frozen")
    candidate_test = workspace.candidate_root / added
    candidate_test.parent.mkdir(parents=True)
    candidate_test.write_text("# generated test\n")

    surface = candidate_surface_manifest(workspace, frozen)
    assert surface["boundary"]["added_paths"] == [added]
    assert set(surface["relative_paths"]) == {"workflow.py", added}
    unexpected = candidate_test.with_name("test_other.py")
    unexpected.write_text("# outside the exact addition\n")
    with pytest.raises(ValueError, match="outside the allowlist"):
        candidate_surface_manifest(workspace, frozen)
    unexpected.unlink()

    (project / added).write_text("# created while authoring was in progress\n")
    with pytest.raises(ValueError, match="source appeared at generated target"):
        candidate_surface_manifest(workspace, frozen)
    assert existing.read_text() == "# existing test\n"


def test_invalid_candidate_cannot_hide_behind_imported_original(tmp_path):
    project = source_project(tmp_path)
    resolved = resolve_workflow("workflow.py:demo", workspace=project)
    assert resolved.fn() == 1
    workspace = prepare_candidate_workspace(
        project, ["workflow.py"], tmp_path / "surface"
    )
    frozen = freeze_candidate_workspace(workspace, tmp_path / "frozen")
    (workspace.candidate_root / "workflow.py").write_text("this is invalid syntax !!!")
    result = validate_candidate(
        workspace,
        frozen,
        workflow_refs=["workflow.py:demo"],
        staging_parent=tmp_path / "checks",
        target_test_argv=[sys.executable, "-c", "raise AssertionError('must not run')"],
    )
    assert not result.success
    assert len(result.checks) == 1
    assert result.checks[0].kind == "compile_probe"


def test_frozen_baseline_id_matches_native_runtime_surface(tmp_path):
    project = source_project(tmp_path)
    definition = resolve_workflow("workflow.py:demo", workspace=project)
    source = derive_workflow_surface_manifest(project, definition)
    workspace = prepare_candidate_workspace(
        project, source["relative_paths"], tmp_path / "surface"
    )
    bundle = freeze_candidate_workspace(
        workspace, tmp_path / "frozen", boundary=source["boundary"]
    )
    assert bundle.baseline_surface_manifest["surface_id"] == source["surface_id"]


def test_candidate_removals_are_explicit_and_materialized(tmp_path):
    project = tmp_path / "project"
    (project / "pkg").mkdir(parents=True)
    (project / "pkg" / "__init__.py").write_text("")
    (project / "pkg" / "old.py").write_text("VALUE=1")
    workspace = prepare_candidate_workspace(project, ["pkg"], tmp_path / "surface")
    bundle = freeze_candidate_workspace(workspace, tmp_path / "frozen")
    (workspace.candidate_root / "pkg" / "old.py").unlink()
    (workspace.candidate_root / "pkg" / "new.py").write_text("VALUE=2")
    candidate = candidate_surface_manifest(workspace, bundle)
    with pytest.raises(ValueError, match="preserve every baseline path"):
        validate_surface_manifest(
            candidate,
            expected_root=workspace.candidate_root,
            expected_boundary=bundle.boundary,
            expected_surface_kind="candidate",
            baseline_manifest=bundle.baseline_surface_manifest,
            allowed_added_path_prefixes=["pkg"],
        )
    arm = materialize_execution_arm(
        bundle.snapshot,
        tmp_path / "arms",
        candidate_manifest=candidate,
        removed_paths=["pkg/old.py"],
    )
    assert not (arm.root / "pkg" / "old.py").exists()
    assert (arm.root / "pkg" / "new.py").read_text() == "VALUE=2"


def test_validation_detects_test_created_code_and_bounds_streams(tmp_path):
    project = source_project(tmp_path)
    workspace = prepare_candidate_workspace(
        project, ["workflow.py"], tmp_path / "surface"
    )
    frozen = freeze_candidate_workspace(workspace, tmp_path / "frozen")
    with pytest.raises(ValueError, match="changed during test"):
        validate_candidate(
            workspace,
            frozen,
            workflow_refs=["workflow.py:demo"],
            staging_parent=tmp_path / "checks",
            target_test_argv=[
                sys.executable,
                "-c",
                "from pathlib import Path; Path('new_code.py').write_text('VALUE=1')",
            ],
        )
    result = evaluate_candidate_workspace(
        workspace, [sys.executable, "-c", "print('x'*4096)"], max_stream_bytes=128
    )
    assert len(result.command.stdout.encode()) <= 128
    assert result.command.stdout_truncated


def test_baseline_byte_limit_rejects_before_resetting_previous_candidate(tmp_path):
    project = source_project(tmp_path)
    workspace = prepare_candidate_workspace(
        project, ["workflow.py"], tmp_path / "surface"
    )
    before = (workspace.candidate_root / "workflow.py").read_bytes()
    with pytest.raises(ValueError, match="max_bytes"):
        prepare_candidate_workspace(
            project, ["workflow.py"], workspace.root, max_bytes=1
        )
    assert (workspace.candidate_root / "workflow.py").read_bytes() == before


def test_bounded_process_rejects_nonfinite_timeout(tmp_path):
    from botpipe_optimizer.processes import run_bounded_process

    for value in (float("nan"), float("inf"), True):
        with pytest.raises(ValueError, match="timeouts"):
            run_bounded_process(
                [sys.executable, "-c", "pass"], cwd=tmp_path, timeout_seconds=value
            )
