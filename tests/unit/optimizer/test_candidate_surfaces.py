from __future__ import annotations

from tests.unit._stdlib_and_extensions_shared import _build_lifecycle_context
from tests.unit._stdlib_and_extensions_shared import *

def test_candidate_surface_helpers_normalize_repo_boundary_and_stay_reexported_from_stdlib(tmp_path: Path) -> None:
    package_dir = tmp_path / "workflows" / "demo_workflow"
    tests_dir = tmp_path / "tests" / "runtime"
    (package_dir / "prompts").mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    workflow_path = package_dir / "workflow.py"
    prompt_path = package_dir / "prompts" / "assess.md"
    doc_path = package_dir / "README.md"
    runtime_test_path = tests_dir / "test_demo_workflow.py"
    workflow_path.write_text("# workflow\n", encoding="utf-8")
    prompt_path.write_text("Prompt.\n", encoding="utf-8")
    doc_path.write_text("# Demo Workflow\n", encoding="utf-8")
    runtime_test_path.write_text("def test_demo():\n    assert True\n", encoding="utf-8")

    boundary = normalize_candidate_surface_boundary(
        tmp_path,
        {
            "package_dir": str(package_dir),
            "editable_paths": [
                str(workflow_path),
                str(prompt_path),
                str(workflow_path),
            ],
            "doc_path": str(doc_path),
            "runtime_test_path": str(runtime_test_path),
        },
        error_prefix="selected_workflow_authoring_surface.json",
    )

    assert boundary == {
        "package_root_relative_path": "workflows/demo_workflow",
        "doc_relative_path": "workflows/demo_workflow/README.md",
        "runtime_test_relative_path": "tests/runtime/test_demo_workflow.py",
        "baseline_relative_paths": [
            "workflows/demo_workflow/prompts/assess.md",
            "workflows/demo_workflow/workflow.py",
        ],
        "baseline_source_entries": [
            {
                "relative_path": "workflows/demo_workflow/prompts/assess.md",
                "source_path": str(prompt_path),
            },
            {
                "relative_path": "workflows/demo_workflow/workflow.py",
                "source_path": str(workflow_path),
            },
        ],
    }
    assert candidate_surface_helpers.normalize_candidate_surface_boundary is normalize_candidate_surface_boundary
    assert candidate_surface_helpers.materialize_baseline_surface is materialize_baseline_surface
    assert candidate_surface_helpers.derive_candidate_surface_manifest is derive_candidate_surface_manifest
    assert (
        candidate_surface_helpers.normalize_candidate_surface_overlay_result
        is normalize_candidate_surface_overlay_result
    )
    assert candidate_surface_helpers.validate_baseline_surface_manifest is validate_baseline_surface_manifest
    assert (
        candidate_surface_helpers.validate_authoritative_surface_sources_unchanged
        is validate_authoritative_surface_sources_unchanged
    )
    assert candidate_surface_helpers.validate_candidate_surface_manifest is validate_candidate_surface_manifest
    assert candidate_surface_helpers.validate_candidate_surface_overlay is validate_candidate_surface_overlay
def test_candidate_surface_helpers_materialize_baseline_and_derive_candidate_diff(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_and_eval_to_refined_workflow_package")
    package_dir = tmp_path / "workflows" / "demo_workflow"
    tests_dir = tmp_path / "tests" / "runtime"
    (package_dir / "prompts").mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    workflow_path = package_dir / "workflow.py"
    prompt_path = package_dir / "prompts" / "assess.md"
    doc_path = package_dir / "README.md"
    runtime_test_path = tests_dir / "test_demo_workflow.py"
    workflow_path.write_text("BASELINE = True\n", encoding="utf-8")
    prompt_path.write_text("Assess the baseline workflow.\n", encoding="utf-8")
    doc_path.write_text("# Demo Workflow\n", encoding="utf-8")
    runtime_test_path.write_text("def test_demo():\n    assert True\n", encoding="utf-8")

    boundary = normalize_candidate_surface_boundary(
        tmp_path,
        {
            "package_dir": str(package_dir),
            "editable_paths": [str(workflow_path), str(prompt_path)],
            "doc_path": str(doc_path),
            "runtime_test_path": str(runtime_test_path),
        },
        error_prefix="selected_workflow_authoring_surface.json",
    )
    baseline_manifest = {
        "repo_root": str(tmp_path),
        **materialize_baseline_surface(
            workflow_folder=ctx.workflow_folder,
            repo_root=tmp_path,
            baseline_relative_paths=[
                *boundary["baseline_relative_paths"],
                boundary["doc_relative_path"],
                boundary["runtime_test_relative_path"],
            ],
            baseline_dir_name="baseline_workflow_surface",
            candidate_dir_name="candidate_workflow_surface",
        ),
    }

    baseline_root = Path(baseline_manifest["surface_root"])
    candidate_root = ctx.workflow_folder / "candidate_workflow_surface"
    shutil.copytree(baseline_root, candidate_root)
    (candidate_root / "workflows" / "demo_workflow" / "workflow.py").write_text(
        "BASELINE = False\n",
        encoding="utf-8",
    )
    added_path = candidate_root / "workflows" / "demo_workflow" / "prompts" / "extra.md"
    added_path.write_text("Extra prompt.\n", encoding="utf-8")

    candidate_manifest = derive_candidate_surface_manifest(
        workflow_folder=ctx.workflow_folder,
        baseline_manifest=baseline_manifest,
        candidate_dir_name="candidate_workflow_surface",
        baseline_manifest_label="baseline_workflow_manifest.json",
        candidate_manifest_label="candidate_workflow_manifest.json",
    )

    assert baseline_manifest["file_count"] == 4
    assert candidate_manifest["baseline_relative_paths"] == baseline_manifest["relative_paths"]
    assert candidate_manifest["file_count"] == 5
    assert candidate_manifest["changed_relative_paths"] == [
        "workflows/demo_workflow/prompts/extra.md",
        "workflows/demo_workflow/workflow.py",
    ]
    assert candidate_manifest["added_relative_paths"] == ["workflows/demo_workflow/prompts/extra.md"]
    changed_flags = {
        entry["relative_path"]: entry["changed_from_baseline"]
        for entry in candidate_manifest["files"]
    }
    assert changed_flags["workflows/demo_workflow/workflow.py"] is True
    assert changed_flags["workflows/demo_workflow/prompts/extra.md"] is True
    assert changed_flags["workflows/demo_workflow/README.md"] is False
def test_candidate_surface_helpers_validate_baseline_manifest_checks_boundary_and_digest(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_and_eval_to_refined_workflow_package")
    package_dir = tmp_path / "workflows" / "demo_workflow"
    docs_dir = tmp_path / "docs" / "workflows"
    tests_dir = tmp_path / "tests" / "runtime"
    (package_dir / "prompts").mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    workflow_path = package_dir / "workflow.py"
    prompt_path = package_dir / "prompts" / "assess.md"
    doc_path = docs_dir / "demo_workflow.md"
    runtime_test_path = tests_dir / "test_demo_workflow.py"
    workflow_path.write_text("BASELINE = True\n", encoding="utf-8")
    prompt_path.write_text("Assess the baseline workflow.\n", encoding="utf-8")
    doc_path.write_text("# Demo Workflow\n", encoding="utf-8")
    runtime_test_path.write_text("def test_demo():\n    assert True\n", encoding="utf-8")

    boundary = normalize_candidate_surface_boundary(
        tmp_path,
        {
            "package_dir": str(package_dir),
            "editable_paths": [str(workflow_path), str(prompt_path)],
            "doc_path": str(doc_path),
            "runtime_test_path": str(runtime_test_path),
        },
        error_prefix="selected_workflow_authoring_surface.json",
    )
    expected_boundary = {
        "package_name": "demo_workflow",
        **boundary,
    }
    expected_relative_paths = boundary["baseline_relative_paths"]
    baseline_manifest = {
        "surface_kind": "baseline",
        "selected_workflow_name": "demo_workflow",
        "package_name": "demo_workflow",
        "package_root_relative_path": boundary["package_root_relative_path"],
        "doc_relative_path": boundary["doc_relative_path"],
        "runtime_test_relative_path": boundary["runtime_test_relative_path"],
        "repo_root": str(tmp_path),
        **materialize_baseline_surface(
            workflow_folder=ctx.workflow_folder,
            repo_root=tmp_path,
            baseline_relative_paths=expected_relative_paths,
            baseline_dir_name="baseline_workflow_surface",
            candidate_dir_name="candidate_workflow_surface",
        ),
    }

    validated = validate_baseline_surface_manifest(
        baseline_manifest,
        tmp_path,
        manifest_label="baseline_workflow_manifest.json",
        expected_surface_kind="baseline",
        expected_boundary=expected_boundary,
        boundary_field_map={
            "package_name": "package_name",
            "package_root_relative_path": "package_root_relative_path",
            "doc_relative_path": "doc_relative_path",
            "runtime_test_relative_path": "runtime_test_relative_path",
        },
        optional_boundary_fields=("doc_relative_path", "runtime_test_relative_path"),
        expected_relative_paths=expected_relative_paths,
    )

    assert validated["relative_paths"] == expected_relative_paths
    assert sorted(validated["file_entries"]) == expected_relative_paths

    mismatched_boundary = dict(expected_boundary)
    mismatched_boundary["package_name"] = "other_workflow"
    with pytest.raises(
        ValueError,
        match="baseline_workflow_manifest.json package_name must match the expected workflow boundary",
    ):
        validate_baseline_surface_manifest(
            baseline_manifest,
            tmp_path,
            manifest_label="baseline_workflow_manifest.json",
            expected_surface_kind="baseline",
            expected_boundary=mismatched_boundary,
            boundary_field_map={
                "package_name": "package_name",
                "package_root_relative_path": "package_root_relative_path",
                "doc_relative_path": "doc_relative_path",
                "runtime_test_relative_path": "runtime_test_relative_path",
            },
            optional_boundary_fields=("doc_relative_path", "runtime_test_relative_path"),
            expected_relative_paths=expected_relative_paths,
        )

    baseline_root = Path(baseline_manifest["surface_root"])
    (baseline_root / "workflows" / "demo_workflow" / "workflow.py").write_text(
        "BASELINE = False\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match="baseline_workflow_manifest.json surface_sha256 must match the copied baseline surface",
    ):
        validate_baseline_surface_manifest(
            baseline_manifest,
            tmp_path,
            manifest_label="baseline_workflow_manifest.json",
            expected_surface_kind="baseline",
            expected_boundary=expected_boundary,
            boundary_field_map={
                "package_name": "package_name",
                "package_root_relative_path": "package_root_relative_path",
                "doc_relative_path": "doc_relative_path",
                "runtime_test_relative_path": "runtime_test_relative_path",
            },
            optional_boundary_fields=("doc_relative_path", "runtime_test_relative_path"),
            expected_relative_paths=expected_relative_paths,
        )
def test_candidate_surface_helpers_validate_candidate_manifest_checks_boundary_and_digest(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_and_eval_to_refined_workflow_package")
    package_dir = tmp_path / "workflows" / "demo_workflow"
    docs_dir = tmp_path / "docs" / "workflows"
    tests_dir = tmp_path / "tests" / "runtime"
    (package_dir / "prompts").mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)

    workflow_path = package_dir / "workflow.py"
    prompt_path = package_dir / "prompts" / "assess.md"
    doc_path = docs_dir / "demo_workflow.md"
    runtime_test_path = tests_dir / "test_demo_workflow.py"
    workflow_path.write_text("BASELINE = True\n", encoding="utf-8")
    prompt_path.write_text("Assess the baseline workflow.\n", encoding="utf-8")
    doc_path.write_text("# Demo Workflow\n", encoding="utf-8")
    runtime_test_path.write_text("def test_demo():\n    assert True\n", encoding="utf-8")

    boundary = normalize_candidate_surface_boundary(
        tmp_path,
        {
            "package_dir": str(package_dir),
            "editable_paths": [str(workflow_path), str(prompt_path)],
            "doc_path": str(doc_path),
            "runtime_test_path": str(runtime_test_path),
        },
        error_prefix="selected_workflow_authoring_surface.json",
    )
    expected_boundary = {
        "package_name": "demo_workflow",
        **boundary,
    }
    expected_relative_paths = boundary["baseline_relative_paths"]
    baseline_manifest = {
        "surface_kind": "baseline",
        "selected_workflow_name": "demo_workflow",
        "package_name": "demo_workflow",
        "package_root_relative_path": boundary["package_root_relative_path"],
        "doc_relative_path": boundary["doc_relative_path"],
        "runtime_test_relative_path": boundary["runtime_test_relative_path"],
        "repo_root": str(tmp_path),
        **materialize_baseline_surface(
            workflow_folder=ctx.workflow_folder,
            repo_root=tmp_path,
            baseline_relative_paths=expected_relative_paths,
            baseline_dir_name="baseline_workflow_surface",
            candidate_dir_name="candidate_workflow_surface",
        ),
    }

    baseline_root = Path(baseline_manifest["surface_root"])
    candidate_root = ctx.workflow_folder / "candidate_workflow_surface"
    shutil.copytree(baseline_root, candidate_root)
    (candidate_root / "workflows" / "demo_workflow" / "workflow.py").write_text(
        "BASELINE = False\n",
        encoding="utf-8",
    )
    added_path = candidate_root / "workflows" / "demo_workflow" / "prompts" / "extra.md"
    added_path.write_text("Extra prompt.\n", encoding="utf-8")

    base_candidate_manifest = {
        "surface_kind": "candidate",
        "selected_workflow_name": "demo_workflow",
        "package_name": "demo_workflow",
        "package_root_relative_path": boundary["package_root_relative_path"],
        "doc_relative_path": boundary["doc_relative_path"],
        "runtime_test_relative_path": boundary["runtime_test_relative_path"],
        **derive_candidate_surface_manifest(
            workflow_folder=ctx.workflow_folder,
            baseline_manifest=baseline_manifest,
            candidate_dir_name="candidate_workflow_surface",
            baseline_manifest_label="baseline_workflow_manifest.json",
            candidate_manifest_label="candidate_workflow_manifest.json",
        ),
    }

    validated = validate_candidate_surface_manifest(
        base_candidate_manifest,
        repo_root=tmp_path,
        manifest_label="candidate_workflow_manifest.json",
        expected_surface_kind="candidate",
        expected_boundary=expected_boundary,
        boundary_field_map={
            "package_name": "package_name",
            "package_root_relative_path": "package_root_relative_path",
            "doc_relative_path": "doc_relative_path",
            "runtime_test_relative_path": "runtime_test_relative_path",
        },
        optional_boundary_fields=("doc_relative_path", "runtime_test_relative_path"),
        baseline_manifest=baseline_manifest,
        baseline_manifest_label="baseline_workflow_manifest.json",
        allowed_added_path_prefixes=[boundary["package_root_relative_path"]],
        allowed_added_exact_paths=[None, boundary["doc_relative_path"], boundary["runtime_test_relative_path"]],
        require_surface_listing_matches_disk=True,
        require_file_count_matches_relative_paths=True,
    )

    assert validated["baseline_relative_paths"] == expected_relative_paths
    assert "workflows/demo_workflow/prompts/extra.md" in validated["relative_paths"]

    outside_path = candidate_root / "README.md"
    outside_path.write_text("outside boundary\n", encoding="utf-8")
    boundary_breaking_manifest = {
        "surface_kind": "candidate",
        "selected_workflow_name": "demo_workflow",
        "package_name": "demo_workflow",
        "package_root_relative_path": boundary["package_root_relative_path"],
        "doc_relative_path": boundary["doc_relative_path"],
        "runtime_test_relative_path": boundary["runtime_test_relative_path"],
        **derive_candidate_surface_manifest(
            workflow_folder=ctx.workflow_folder,
            baseline_manifest=baseline_manifest,
            candidate_dir_name="candidate_workflow_surface",
            baseline_manifest_label="baseline_workflow_manifest.json",
            candidate_manifest_label="candidate_workflow_manifest.json",
        ),
    }
    with pytest.raises(
        ValueError,
        match="candidate_workflow_manifest.json must stay within the allowed repo-relative boundary",
    ):
        validate_candidate_surface_manifest(
            boundary_breaking_manifest,
            repo_root=tmp_path,
            manifest_label="candidate_workflow_manifest.json",
            expected_surface_kind="candidate",
            expected_boundary=expected_boundary,
            boundary_field_map={
                "package_name": "package_name",
                "package_root_relative_path": "package_root_relative_path",
                "doc_relative_path": "doc_relative_path",
                "runtime_test_relative_path": "runtime_test_relative_path",
            },
            optional_boundary_fields=("doc_relative_path", "runtime_test_relative_path"),
            baseline_manifest=baseline_manifest,
            baseline_manifest_label="baseline_workflow_manifest.json",
            allowed_added_path_prefixes=[boundary["package_root_relative_path"]],
            allowed_added_exact_paths=[None, boundary["doc_relative_path"], boundary["runtime_test_relative_path"]],
            require_surface_listing_matches_disk=True,
            require_file_count_matches_relative_paths=True,
        )

    outside_path.unlink()
    digest_manifest = {
        "surface_kind": "candidate",
        "selected_workflow_name": "demo_workflow",
        "package_name": "demo_workflow",
        "package_root_relative_path": boundary["package_root_relative_path"],
        "doc_relative_path": boundary["doc_relative_path"],
        "runtime_test_relative_path": boundary["runtime_test_relative_path"],
        **derive_candidate_surface_manifest(
            workflow_folder=ctx.workflow_folder,
            baseline_manifest=baseline_manifest,
            candidate_dir_name="candidate_workflow_surface",
            baseline_manifest_label="baseline_workflow_manifest.json",
            candidate_manifest_label="candidate_workflow_manifest.json",
        ),
    }
    (candidate_root / "workflows" / "demo_workflow" / "workflow.py").write_text(
        "BASELINE = \"drifted\"\n",
        encoding="utf-8",
    )
    with pytest.raises(
        ValueError,
        match="candidate_workflow_manifest.json surface_sha256 must match candidate_workflow_surface",
    ):
        validate_candidate_surface_manifest(
            digest_manifest,
            repo_root=tmp_path,
            manifest_label="candidate_workflow_manifest.json",
            expected_surface_kind="candidate",
            expected_boundary=expected_boundary,
            boundary_field_map={
                "package_name": "package_name",
                "package_root_relative_path": "package_root_relative_path",
                "doc_relative_path": "doc_relative_path",
                "runtime_test_relative_path": "runtime_test_relative_path",
            },
            optional_boundary_fields=("doc_relative_path", "runtime_test_relative_path"),
            baseline_manifest=baseline_manifest,
            baseline_manifest_label="baseline_workflow_manifest.json",
            allowed_added_path_prefixes=[boundary["package_root_relative_path"]],
            allowed_added_exact_paths=[None, boundary["doc_relative_path"], boundary["runtime_test_relative_path"]],
            require_surface_listing_matches_disk=True,
            require_file_count_matches_relative_paths=True,
        )
def test_candidate_surface_helpers_reject_authoritative_source_drift(tmp_path: Path) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_and_eval_to_refined_workflow_package")
    workflow_path = tmp_path / "workflows" / "demo_workflow" / "workflow.py"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text("BASELINE = True\n", encoding="utf-8")

    baseline_manifest = {
        "repo_root": str(tmp_path),
        **materialize_baseline_surface(
            workflow_folder=ctx.workflow_folder,
            repo_root=tmp_path,
            baseline_relative_paths=["workflows/demo_workflow/workflow.py"],
            baseline_dir_name="baseline_workflow_surface",
            candidate_dir_name="candidate_workflow_surface",
        ),
    }
    workflow_path.write_text("BASELINE = False\n", encoding="utf-8")

    with pytest.raises(ValueError, match="authoritative workflow drift: workflows/demo_workflow/workflow.py"):
        validate_authoritative_surface_sources_unchanged(
            baseline_manifest,
            tmp_path,
            baseline_manifest_label="baseline_workflow_manifest.json",
            drift_error_prefix="authoritative workflow drift",
        )
def test_candidate_surface_helpers_allow_canonical_relative_paths_with_repo_local_sources(
    tmp_path: Path,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_and_eval_to_refined_workflow_package")
    workflow_path = tmp_path / "workflows" / "release_candidate_to_go_no_go" / "workflow.py"
    workflow_path.parent.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text("BASELINE = True\n", encoding="utf-8")

    canonical_relative_path = "botpipe/workflows/release_candidate_to_go_no_go/workflow.py"
    baseline_manifest = {
        "surface_kind": "baseline",
        "selected_workflow_name": "release_candidate_to_go_no_go",
        "package_name": "release_candidate_to_go_no_go",
        "package_root_relative_path": "botpipe/workflows/release_candidate_to_go_no_go",
        "repo_root": str(tmp_path),
        **materialize_baseline_surface(
            workflow_folder=ctx.workflow_folder,
            repo_root=tmp_path,
            baseline_relative_paths=[
                {
                    "relative_path": canonical_relative_path,
                    "source_path": str(workflow_path),
                }
            ],
            baseline_dir_name="baseline_workflow_surface",
            candidate_dir_name="candidate_workflow_surface",
        ),
    }

    validated = validate_baseline_surface_manifest(
        baseline_manifest,
        tmp_path,
        manifest_label="baseline_workflow_manifest.json",
        expected_surface_kind="baseline",
        expected_boundary={
            "package_name": "release_candidate_to_go_no_go",
            "package_root_relative_path": "botpipe/workflows/release_candidate_to_go_no_go",
        },
        boundary_field_map={
            "package_name": "package_name",
            "package_root_relative_path": "package_root_relative_path",
        },
        expected_relative_paths=[canonical_relative_path],
    )

    assert validated["relative_paths"] == [canonical_relative_path]
    copied_surface_path = Path(baseline_manifest["surface_root"]) / canonical_relative_path
    assert copied_surface_path.read_text(encoding="utf-8") == "BASELINE = True\n"

    validate_authoritative_surface_sources_unchanged(
        baseline_manifest,
        tmp_path,
        baseline_manifest_label="baseline_workflow_manifest.json",
        drift_error_prefix="authoritative workflow drift",
    )

    workflow_path.write_text("BASELINE = False\n", encoding="utf-8")
    with pytest.raises(
        ValueError,
        match="authoritative workflow drift: botpipe/workflows/release_candidate_to_go_no_go/workflow.py",
    ):
        validate_authoritative_surface_sources_unchanged(
            baseline_manifest,
            tmp_path,
            baseline_manifest_label="baseline_workflow_manifest.json",
            drift_error_prefix="authoritative workflow drift",
        )
@pytest.mark.parametrize("raw_relative_path", ["../outside.py", "/tmp/absolute-outside.py"])
def test_candidate_surface_helpers_reject_non_repo_relative_authoritative_drift_paths(
    tmp_path: Path,
    raw_relative_path: str,
) -> None:
    outside_path = tmp_path / "outside.py"
    outside_path.write_text("print('outside')\n", encoding="utf-8")
    relative_path = raw_relative_path
    if raw_relative_path.startswith("/tmp/"):
        relative_path = str(outside_path)

    with pytest.raises(
        ValueError,
        match="baseline_workflow_manifest.json relative_path entries must stay repo-relative",
    ):
        validate_authoritative_surface_sources_unchanged(
            {
                "files": [
                    {
                        "relative_path": relative_path,
                        "authoritative_source_sha256": "deadbeef",
                    }
                ]
            },
            tmp_path,
            baseline_manifest_label="baseline_workflow_manifest.json",
            drift_error_prefix="authoritative workflow drift",
        )
@pytest.mark.parametrize("raw_relative_path", ["../outside.py", "/tmp/absolute-outside.py"])
def test_candidate_surface_helpers_reject_non_repo_relative_baseline_paths(
    tmp_path: Path,
    raw_relative_path: str,
) -> None:
    ctx = _build_lifecycle_context(tmp_path, workflow_name="workflow_and_eval_to_refined_workflow_package")
    outside_path = tmp_path / "outside.py"
    outside_path.write_text("print('outside')\n", encoding="utf-8")
    baseline_relative_path = raw_relative_path
    if raw_relative_path.startswith("/tmp/"):
        baseline_relative_path = str(outside_path)

    with pytest.raises(ValueError, match="baseline_relative_paths entries must stay repo-relative"):
        materialize_baseline_surface(
            workflow_folder=ctx.workflow_folder,
            repo_root=tmp_path,
            baseline_relative_paths=[baseline_relative_path],
            baseline_dir_name="baseline_workflow_surface",
            candidate_dir_name="candidate_workflow_surface",
        )
def test_candidate_surface_helpers_validate_overlay_normalizes_pytest_and_falls_back_to_importable_package_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_folder = tmp_path / ".botpipe" / "tasks" / "task-1" / "wf_demo"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    candidate_root = workflow_folder / "candidate_surface"
    candidate_file = candidate_root / "workflows" / "demo_workflow" / "workflow.py"
    candidate_file.parent.mkdir(parents=True, exist_ok=True)
    candidate_file.write_text("class DemoWorkflow:\n    pass\n", encoding="utf-8")

    repo_root = tmp_path / "phase_only_workspace"
    repo_root.mkdir(parents=True, exist_ok=True)
    installed_root = tmp_path / "installed_botpipe"
    package_root = installed_root / "botpipe"
    (package_root / "core").mkdir(parents=True, exist_ok=True)
    (package_root / "runtime").mkdir(parents=True, exist_ok=True)
    (installed_root / "tests").mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (installed_root / "tests" / "conftest.py").write_text("import pytest\n", encoding="utf-8")

    observed: dict[str, Any] = {}

    def _record_resolve(root: Path, workflow_name: str) -> SimpleNamespace:
        observed.setdefault("resolve_calls", []).append((root, workflow_name))
        return SimpleNamespace(workflow_cls=workflow_name)

    def _record_compile(workflow_cls: object) -> SimpleNamespace:
        return SimpleNamespace(workflow_name=f"compiled::{workflow_cls}")

    def _record_run(command: list[str], **kwargs) -> SimpleNamespace:
        observed["command"] = command
        observed["cwd"] = kwargs["cwd"]
        observed["candidate_exists"] = (kwargs["cwd"] / "workflows" / "demo_workflow" / "workflow.py").is_file()
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setitem(sys.modules, "botpipe", SimpleNamespace(__file__=str(package_root / "__init__.py")))
    monkeypatch.setattr(candidate_surface_helpers, "resolve_workflow_reference", _record_resolve)
    monkeypatch.setattr(candidate_surface_helpers, "compile_workflow", _record_compile)
    monkeypatch.setattr(candidate_surface_helpers.subprocess, "run", _record_run)

    result = validate_candidate_surface_overlay(
        repo_root=repo_root,
        workflow_names=["demo_workflow", "helper_workflow"],
        candidate_manifest={
            "surface_root": str(candidate_root),
            "relative_paths": ["workflows/demo_workflow/workflow.py"],
        },
        target_test_command="pytest -q tests/unit/test_demo.py",
        candidate_manifest_label="candidate_surface_manifest.json",
        overlay_failure_prefix="overlay validation failed",
        overlay_temp_prefix="candidate-surface-overlay-",
    )

    assert result == {
        "compiled_workflow_names": ["compiled::demo_workflow", "compiled::helper_workflow"],
        "test_command": "pytest -q tests/unit/test_demo.py",
        "test_returncode": 0,
    }
    assert observed["command"] == [sys.executable, "-m", "pytest", "-q", "tests/unit/test_demo.py"]
    assert observed["candidate_exists"] is True
    assert observed["cwd"] != repo_root
    assert all(root == observed["cwd"] for root, _workflow_name in observed["resolve_calls"])
    assert [workflow_name for _root, workflow_name in observed["resolve_calls"]] == [
        "demo_workflow",
        "helper_workflow",
    ]


def test_candidate_surface_overlay_does_not_copy_botpipe_runtime_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_folder = tmp_path / ".botpipe" / "tasks" / "task-1" / "wf_demo"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    candidate_root = workflow_folder / "candidate_surface"
    candidate_relative_path = "botpipe/workflows/demo_workflow/workflow.py"
    candidate_file = candidate_root / candidate_relative_path
    candidate_file.parent.mkdir(parents=True, exist_ok=True)
    candidate_file.write_text("class DemoWorkflow:\n    pass\n", encoding="utf-8")

    repo_root = tmp_path / "repo_root"
    package_root = repo_root / "botpipe"
    (package_root / "core").mkdir(parents=True, exist_ok=True)
    (package_root / "runtime").mkdir(parents=True, exist_ok=True)
    (repo_root / "tests").mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (repo_root / "tests" / "conftest.py").write_text("import pytest\n", encoding="utf-8")
    sentinel = repo_root / ".botpipe" / "sentinel.txt"
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("live runtime state\n", encoding="utf-8")

    observed: dict[str, Any] = {}

    def _record_resolve(root: Path, workflow_name: str) -> SimpleNamespace:
        observed.setdefault("resolve_calls", []).append((root, workflow_name))
        return SimpleNamespace(workflow_cls=workflow_name)

    def _record_compile(workflow_cls: object) -> SimpleNamespace:
        return SimpleNamespace(workflow_name=f"compiled::{workflow_cls}")

    def _record_run(command: list[str], **kwargs) -> SimpleNamespace:
        overlay_cwd = kwargs["cwd"]
        observed["command"] = command
        observed["cwd"] = overlay_cwd
        observed["overlay_has_runtime_state"] = (overlay_cwd / ".botpipe").exists()
        observed["candidate_exists"] = (overlay_cwd / candidate_relative_path).is_file()
        observed["candidate_contents"] = (overlay_cwd / candidate_relative_path).read_text(encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(candidate_surface_helpers, "resolve_workflow_reference", _record_resolve)
    monkeypatch.setattr(candidate_surface_helpers, "compile_workflow", _record_compile)
    monkeypatch.setattr(candidate_surface_helpers.subprocess, "run", _record_run)

    result = validate_candidate_surface_overlay(
        repo_root=repo_root,
        workflow_names=["demo_workflow"],
        candidate_manifest={
            "surface_root": str(candidate_root),
            "relative_paths": [candidate_relative_path],
        },
        target_test_command="pytest -q tests/unit/test_demo.py",
        candidate_manifest_label="candidate_surface_manifest.json",
        overlay_failure_prefix="overlay validation failed",
        overlay_temp_prefix="candidate-surface-overlay-",
    )

    assert sentinel.is_file()
    assert result == {
        "compiled_workflow_names": ["compiled::demo_workflow"],
        "test_command": "pytest -q tests/unit/test_demo.py",
        "test_returncode": 0,
    }
    assert observed["command"] == [sys.executable, "-m", "pytest", "-q", "tests/unit/test_demo.py"]
    assert observed["cwd"] != repo_root
    assert observed["overlay_has_runtime_state"] is False
    assert observed["candidate_exists"] is True
    assert observed["candidate_contents"] == "class DemoWorkflow:\n    pass\n"
    assert not (observed["cwd"] / ".botpipe").exists()
    assert all(root == observed["cwd"] for root, _workflow_name in observed["resolve_calls"])


def test_candidate_surface_helpers_normalize_overlay_results_for_single_and_multi_workflow_receipts() -> None:
    single = normalize_candidate_surface_overlay_result(
        {
            "compiled_workflow_names": ["demo_workflow"],
            "test_command": "pytest -q tests/unit/test_demo.py",
            "test_returncode": 0,
        },
        expect_single_compiled_workflow=True,
    )
    multi = normalize_candidate_surface_overlay_result(
        {
            "compiled_workflow_names": ["demo_workflow", "helper_workflow"],
            "test_command": "pytest -q tests/unit/test_demo.py",
            "test_returncode": 0,
        },
        expect_single_compiled_workflow=False,
    )

    assert single == {
        "compiled_workflow_name": "demo_workflow",
        "test_command": "pytest -q tests/unit/test_demo.py",
        "test_returncode": 0,
    }
    assert multi == {
        "compiled_workflow_names": ["demo_workflow", "helper_workflow"],
        "test_command": "pytest -q tests/unit/test_demo.py",
        "test_returncode": 0,
    }

    with pytest.raises(ValueError, match="overlay validation must compile exactly one selected workflow"):
        normalize_candidate_surface_overlay_result(
            {
                "compiled_workflow_names": ["demo_workflow", "helper_workflow"],
                "test_command": "pytest -q tests/unit/test_demo.py",
                "test_returncode": 0,
            },
            expect_single_compiled_workflow=True,
        )
    with pytest.raises(ValueError, match="overlay validation must define non-negative integer test_returncode"):
        normalize_candidate_surface_overlay_result(
            {
                "compiled_workflow_names": ["demo_workflow"],
                "test_command": "pytest -q tests/unit/test_demo.py",
                "test_returncode": -1,
            },
            expect_single_compiled_workflow=True,
        )
@pytest.mark.parametrize("raw_relative_path", ["../outside.py", "/tmp/absolute-outside.py"])
def test_candidate_surface_helpers_reject_non_repo_relative_overlay_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_relative_path: str,
) -> None:
    workflow_folder = tmp_path / ".botpipe" / "tasks" / "task-1" / "wf_demo"
    workflow_folder.mkdir(parents=True, exist_ok=True)
    candidate_root = workflow_folder / "candidate_surface"
    outside_path = workflow_folder / "outside.py"
    outside_path.write_text("print('outside')\n", encoding="utf-8")
    relative_path = raw_relative_path
    if raw_relative_path.startswith("/tmp/"):
        relative_path = str(outside_path)

    repo_root = tmp_path / "phase_only_workspace"
    repo_root.mkdir(parents=True, exist_ok=True)
    installed_root = tmp_path / "installed_botpipe"
    package_root = installed_root / "botpipe"
    (package_root / "core").mkdir(parents=True, exist_ok=True)
    (package_root / "runtime").mkdir(parents=True, exist_ok=True)
    (installed_root / "tests").mkdir(parents=True, exist_ok=True)
    (package_root / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (installed_root / "tests" / "conftest.py").write_text("import pytest\n", encoding="utf-8")

    monkeypatch.setitem(sys.modules, "botpipe", SimpleNamespace(__file__=str(package_root / "__init__.py")))

    with pytest.raises(
        ValueError,
        match="candidate_surface_manifest.json relative_paths entries must stay repo-relative",
    ):
        validate_candidate_surface_overlay(
            repo_root=repo_root,
            workflow_names=["demo_workflow"],
            candidate_manifest={
                "surface_root": str(candidate_root),
                "relative_paths": [relative_path],
            },
            target_test_command="pytest -q tests/unit/test_demo.py",
            candidate_manifest_label="candidate_surface_manifest.json",
            overlay_failure_prefix="overlay validation failed",
            overlay_temp_prefix="candidate-surface-overlay-",
        )
